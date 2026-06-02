# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║   MOTOR SNIPER V60.7 – MÓDULO DE HISTÓRICO E INTELIGÊNCIA DE TRADES ║
║                                                                      ║
║  Responsabilidades:                                                  ║
║  1. Busca o PnL REAL (realizedPnl) na API V5 após o fechamento,      ║
║     evitando o bug do retorno zerado do endpoint de ordens.          ║
║  2. Persiste cada operação encerrada na tabela 'trade_history'.      ║
║  3. Exporta payload JSON estruturado para o "Cérebro" (IA analista). ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import asyncio
import json
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.database.manager import DB_PATH, _connect

# ---------------------------------------------------------------------------
# 1. INICIALIZAÇÃO DA TABELA trade_history
# ---------------------------------------------------------------------------

def init_trade_history_table() -> None:
    """
    Cria (se ainda não existir) a tabela 'trade_history' e garante que
    todas as colunas obrigatórias para a IA analista estejam presentes.
    Chamada automaticamente em init_db() do manager.py.
    """
    conn = _connect()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS trade_history (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            asset          TEXT    NOT NULL,                -- Par de moeda  ex: BNB/USDT
            direction      TEXT    NOT NULL,                -- BUY ou SELL
            entry_price    REAL    NOT NULL DEFAULT 0,      -- Preço real de entrada
            stop_loss      REAL    NOT NULL DEFAULT 0,      -- Preço do Stop Loss configurado
            take_profit    REAL    NOT NULL DEFAULT 0,      -- Preço do Take Profit configurado
            exit_price     REAL    NOT NULL DEFAULT 0,      -- Preço final de saída
            exit_reason    TEXT    NOT NULL DEFAULT 'MANUAL',-- TAKE_PROFIT | STOP_LOSS | MANUAL
            gross_pnl      REAL    NOT NULL DEFAULT 0,      -- Lucro bruto calculado localmente
            net_pnl        REAL    NOT NULL DEFAULT 0,      -- Lucro líquido real capturado da API
            timestamp      TEXT    NOT NULL,                -- Data/hora exata da operação
            market_context TEXT    DEFAULT '{}'             -- JSON com métricas do indicador
        )
    ''')

    # Garante colunas opcionais de rastreabilidade que podem ser úteis à IA
    _safe_add_column(cur, 'trade_history', 'client_id',   'INTEGER DEFAULT 0')
    _safe_add_column(cur, 'trade_history', 'trade_db_id', 'INTEGER DEFAULT 0')  # FK para tabela trades

    # Índices para acelerar as queries da IA
    cur.execute('CREATE INDEX IF NOT EXISTS idx_th_asset     ON trade_history(asset)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_th_direction ON trade_history(direction)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_th_exit_reason ON trade_history(exit_reason)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_th_timestamp ON trade_history(timestamp)')

    conn.commit()
    conn.close()


def _safe_add_column(cur: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    """Adiciona coluna somente se ela ainda não existir (idempotente)."""
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


# ---------------------------------------------------------------------------
# 2. BUSCA DO PnL REAL NA API V5 DA BYBIT (ASYNC)
# ---------------------------------------------------------------------------

async def fetch_realized_pnl_async(
    pybit_session: Any,
    symbol: str,
    direction: str,
    max_retries: int = 3,
    retry_delay_s: float = 0.8,
) -> Optional[float]:
    """
    Busca o PnL LÍQUIDO REAL de uma posição recém-fechada na API V5 da Bybit.

    Estratégia:
      1. Aguarda 500 ms para a exchange liquidar a operação.
      2. Tenta primeiro em 'getClosedPnl' (endpoint mais preciso para histórico).
      3. Faz fallback para 'get_executions' se o primeiro falhar.

    Parâmetros:
        pybit_session : Sessão autenticada pybit.unified_trading.HTTP
        symbol        : Símbolo normalizado ex: "BNBUSDT"
        direction     : 'BUY' ou 'SELL'
        max_retries   : Número de tentativas em caso de resposta vazia
        retry_delay_s : Delay entre tentativas (segundos)

    Retorna:
        float com o net PnL, ou None se não for possível obter.
    """
    if pybit_session is None:
        print("⚠️ [PNL FETCH] pybit_session indisponível – retornando None", flush=True)
        return None

    # Normaliza símbolo: remove '/', ':USDT', espaços
    v5_symbol = str(symbol or '').strip().upper().replace('/', '').replace(':USDT', '')

    # Pausa de segurança para a Bybit liquidar o trade antes de consultarmos
    await asyncio.sleep(0.5)

    for attempt in range(1, max_retries + 1):
        try:
            # ── Estratégia primária: getClosedPnl ────────────────────────────
            print(
                f"   🔍 [PNL FETCH] Tentativa {attempt}/{max_retries} – getClosedPnl "
                f"para {v5_symbol} ({direction})",
                flush=True,
            )
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: pybit_session.get_closed_pnl(
                    category='linear',
                    symbol=v5_symbol,
                    limit=5,
                ),
            )

            ret_code = (response or {}).get('retCode')
            if str(ret_code) == '0':
                rows = (response.get('result') or {}).get('list') or []
                if rows:
                    # O registro mais recente corresponde ao fechamento que acabamos de disparar
                    realized = float(rows[0].get('closedPnl') or 0)
                    print(
                        f"   ✅ [PNL FETCH] realizedPnl (getClosedPnl): ${realized:.4f}",
                        flush=True,
                    )
                    return realized

            # ── Fallback: getExecutionList ────────────────────────────────────
            print(
                f"   🔄 [PNL FETCH] Fallback para getExecutionList ({v5_symbol})",
                flush=True,
            )
            response_exec = await loop.run_in_executor(
                None,
                lambda: pybit_session.get_executions(
                    category='linear',
                    symbol=v5_symbol,
                    limit=10,
                ),
            )

            ret_code_exec = (response_exec or {}).get('retCode')
            if str(ret_code_exec) == '0':
                exec_rows = (response_exec.get('result') or {}).get('list') or []
                # Procura a execução de fechamento (execType='Trade' e closedSize > 0)
                for exec_row in exec_rows:
                    closed_size = float(exec_row.get('closedSize') or 0)
                    exec_pnl = float(exec_row.get('execPnl') or 0)
                    if closed_size > 0 and exec_pnl != 0:
                        print(
                            f"   ✅ [PNL FETCH] execPnl (getExecutionList): ${exec_pnl:.4f}",
                            flush=True,
                        )
                        return exec_pnl

        except Exception as e:
            print(f"   ⚠️ [PNL FETCH] Erro na tentativa {attempt}: {e}", flush=True)

        # Aguarda antes da próxima tentativa, exceto na última
        if attempt < max_retries:
            await asyncio.sleep(retry_delay_s)

    print(
        f"   ⚠️ [PNL FETCH] Não foi possível obter PnL real após {max_retries} tentativas. "
        f"Retornando None.",
        flush=True,
    )
    return None


def fetch_realized_pnl_sync(
    pybit_session: Any,
    symbol: str,
    direction: str,
    max_retries: int = 3,
) -> Optional[float]:
    """
    Wrapper SÍNCRONO para fetch_realized_pnl_async.
    Pode ser chamado a partir de código não-async (ex: endpoints Flask/threading).
    """
    try:
        return asyncio.run(
            fetch_realized_pnl_async(pybit_session, symbol, direction, max_retries)
        )
    except RuntimeError:
        # Loop de evento já em execução (ex: nest_asyncio não disponível)
        # Usa thread auxiliar para executar a corrotina
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                asyncio.run,
                fetch_realized_pnl_async(pybit_session, symbol, direction, max_retries),
            )
            return future.result(timeout=10)


# ---------------------------------------------------------------------------
# 3. REGISTRO DE OPERAÇÃO ENCERRADA EM trade_history
# ---------------------------------------------------------------------------

async def record_closed_trade_async(
    *,
    pybit_session: Any,
    asset: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    exit_price: float,
    exit_reason: str,
    gross_pnl: float,
    market_context: Optional[Dict[str, Any]] = None,
    client_id: int = 0,
    trade_db_id: int = 0,
) -> Dict[str, Any]:
    """
    Orquestra o fechamento completo de uma operação:
      1. Busca o PnL líquido real na API V5 (evita retorno zerado).
      2. Persiste todos os dados na tabela 'trade_history'.

    Retorna um dict com os dados salvos (útil para logs e notificações).
    """
    # Normaliza exit_reason para os valores aceitos
    valid_reasons = {'TAKE_PROFIT', 'STOP_LOSS', 'MANUAL'}
    exit_reason_norm = str(exit_reason or 'MANUAL').upper()
    if exit_reason_norm not in valid_reasons:
        exit_reason_norm = 'MANUAL'

    # Busca o PnL líquido real na Bybit
    net_pnl = await fetch_realized_pnl_async(pybit_session, asset, direction)

    # Se a API não retornou PnL, usa o valor bruto calculado localmente como fallback
    if net_pnl is None:
        print(
            f"   ℹ️ [TRADE HISTORY] Usando gross_pnl como fallback para net_pnl: ${gross_pnl:.4f}",
            flush=True,
        )
        net_pnl = gross_pnl

    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    context_json = json.dumps(market_context or {}, ensure_ascii=False)

    # Garante que a tabela existe antes de inserir
    init_trade_history_table()

    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        '''
        INSERT INTO trade_history
            (asset, direction, entry_price, stop_loss, take_profit,
             exit_price, exit_reason, gross_pnl, net_pnl,
             timestamp, market_context, client_id, trade_db_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            asset, direction, entry_price, stop_loss, take_profit,
            exit_price, exit_reason_norm, gross_pnl, net_pnl,
            timestamp, context_json, client_id, trade_db_id,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    result = {
        'id': new_id,
        'asset': asset,
        'direction': direction,
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'exit_price': exit_price,
        'exit_reason': exit_reason_norm,
        'gross_pnl': gross_pnl,
        'net_pnl': net_pnl,
        'timestamp': timestamp,
        'market_context': market_context or {},
    }

    print(
        f"   💾 [TRADE HISTORY] Operação salva → id={new_id} | {asset} {direction} "
        f"| net_pnl=${net_pnl:.4f} | motivo={exit_reason_norm}",
        flush=True,
    )
    return result


def record_closed_trade_sync(
    *,
    pybit_session: Any,
    asset: str,
    direction: str,
    entry_price: float,
    stop_loss: float = 0.0,
    take_profit: float = 0.0,
    exit_price: float,
    exit_reason: str = 'MANUAL',
    gross_pnl: float = 0.0,
    market_context: Optional[Dict[str, Any]] = None,
    client_id: int = 0,
    trade_db_id: int = 0,
) -> Dict[str, Any]:
    """
    Wrapper SÍNCRONO para record_closed_trade_async.
    Compatível com Flask/threading sem precisar de nest_asyncio.
    """
    coro = record_closed_trade_async(
        pybit_session=pybit_session,
        asset=asset,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        exit_price=exit_price,
        exit_reason=exit_reason,
        gross_pnl=gross_pnl,
        market_context=market_context,
        client_id=client_id,
        trade_db_id=trade_db_id,
    )
    try:
        return asyncio.run(coro)
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result(timeout=15)


# ---------------------------------------------------------------------------
# 4. PIPELINE DE EXPORTAÇÃO PARA A IA – "O CÉREBRO"
# ---------------------------------------------------------------------------

def get_market_intelligence_data(limit: int = 100) -> Dict[str, Any]:
    """
    Exporta as últimas operações do SQLite em um payload JSON estruturado
    pronto para ser enviado ao "Cérebro" (IA analista).

    O payload contém:
      - metadata : informações sobre a janela de dados analisada.
      - summary  : métricas agregadas (win rate, PnL médio, etc.).
      - trades   : lista de operações ordenadas da mais recente para a mais antiga.

    Uso:
        payload = get_market_intelligence_data(limit=50)
        # Enviar para a IA via API ou processar localmente

    Retorna:
        dict com chaves 'metadata', 'summary' e 'trades'.
    """
    # Garante que a tabela existe
    init_trade_history_table()

    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT id, asset, direction, entry_price, stop_loss, take_profit,
               exit_price, exit_reason, gross_pnl, net_pnl, timestamp, market_context
        FROM trade_history
        ORDER BY id DESC
        LIMIT ?
        ''',
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()

    trades = []
    total_net_pnl = 0.0
    wins = 0
    losses = 0
    by_reason: Dict[str, int] = {}
    by_asset: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        row_dict = dict(row)

        # Desserializa market_context de JSON string para dict
        ctx_raw = row_dict.get('market_context') or '{}'
        try:
            row_dict['market_context'] = json.loads(ctx_raw)
        except (json.JSONDecodeError, TypeError):
            row_dict['market_context'] = {}

        net = float(row_dict.get('net_pnl') or 0)
        total_net_pnl += net
        if net > 0:
            wins += 1
        elif net < 0:
            losses += 1

        reason = str(row_dict.get('exit_reason') or 'MANUAL')
        by_reason[reason] = by_reason.get(reason, 0) + 1

        asset = str(row_dict.get('asset') or 'UNKNOWN')
        if asset not in by_asset:
            by_asset[asset] = {'trades': 0, 'net_pnl': 0.0, 'wins': 0, 'losses': 0}
        by_asset[asset]['trades'] += 1
        by_asset[asset]['net_pnl'] = round(by_asset[asset]['net_pnl'] + net, 4)
        if net > 0:
            by_asset[asset]['wins'] += 1
        elif net < 0:
            by_asset[asset]['losses'] += 1

        trades.append(row_dict)

    total_trades = len(trades)
    win_rate = round((wins / total_trades * 100), 2) if total_trades > 0 else 0.0
    avg_net_pnl = round(total_net_pnl / total_trades, 4) if total_trades > 0 else 0.0

    payload = {
        'metadata': {
            'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
            'total_records': total_trades,
            'limit_applied': limit,
            'source': 'trade_history SQLite – Motor Sniper V60.7',
        },
        'summary': {
            'total_net_pnl': round(total_net_pnl, 4),
            'avg_net_pnl_per_trade': avg_net_pnl,
            'win_rate_pct': win_rate,
            'total_wins': wins,
            'total_losses': losses,
            'total_neutral': total_trades - wins - losses,
            'exits_by_reason': by_reason,
            'performance_by_asset': by_asset,
        },
        'trades': trades,
    }

    return payload
