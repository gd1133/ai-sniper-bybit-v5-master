# -*- coding: utf-8 -*-
"""
Feedback Loop Evolutivo — reconciliação Bybit V5 + cooldown + RL de pesos das IAs.

Circuito:
  1) Operação aberta → status ABERTA em ``operacoes``
  2) ``get_closed_pnl`` detecta TP/SL → WIN / LOSS
  3) LOSS → cooldown_moedas 24h (anti-reentrada, ex.: MIRAUSDT)
  4) WIN/LOSS → reajuste de pesos em ``pesos_ia_evolutivo`` (dashboard Render)
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Módulos do Triplo Cérebro (painel Render)
MODULOS_IA = (
    'Groq Tático',
    'Analista de Dados',
    'Aprendizado Neural',
)

TAXA_APRENDIZADO = float(os.getenv('FEEDBACK_LEARNING_RATE', '0.03'))
PESO_MIN = float(os.getenv('FEEDBACK_WEIGHT_MIN', '0.10'))
PESO_MAX = float(os.getenv('FEEDBACK_WEIGHT_MAX', '0.60'))
PESO_INICIAL = float(os.getenv('FEEDBACK_WEIGHT_INIT', '0.33'))
SYNC_MIN_INTERVAL_SECS = float(os.getenv('FEEDBACK_SYNC_INTERVAL_SECS', '30'))


def _normalize_symbol(symbol: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', str(symbol or '').upper().replace(':USDT', ''))


def _db_path() -> str:
    try:
        from src.database.manager import DB_PATH
        return DB_PATH
    except Exception:
        return os.path.abspath(os.path.join(os.getcwd(), 'data', 'database.db'))


class FeedbackLoopEvolutivo:
    """Elo entre fechamento Bybit V5, cooldown SQLite e aprendizado das IAs."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or _db_path()
        self._lock = threading.Lock()
        self._last_sync_ts = 0.0
        self.inicializar_tabelas()

    # ------------------------------------------------------------------ schema
    def inicializar_tabelas(self) -> None:
        """Garante operacoes, pesos_ia_evolutivo, cooldown e dedupe de P&L."""
        try:
            from src.database.manager import _execute_write
        except Exception as err:
            print(f"[FEEDBACK LOOP] manager indisponível: {err}", flush=True)
            return

        def _schema(cur, conn):
            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS operacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER DEFAULT 0,
                    ativo TEXT NOT NULL,
                    side TEXT DEFAULT '',
                    status TEXT DEFAULT 'ABERTA',
                    pnl_realizado REAL DEFAULT 0,
                    entry_price REAL DEFAULT 0,
                    exit_price REAL DEFAULT 0,
                    quantity REAL DEFAULT 0,
                    sinais_json TEXT DEFAULT '',
                    bybit_order_id TEXT DEFAULT '',
                    closed_pnl_order_id TEXT DEFAULT '',
                    closed_at TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )
            cur.execute('CREATE INDEX IF NOT EXISTS idx_operacoes_status ON operacoes(status)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_operacoes_ativo ON operacoes(ativo)')

            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS pesos_ia_evolutivo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    modulo TEXT UNIQUE NOT NULL,
                    peso REAL DEFAULT 0.33,
                    acertos INTEGER DEFAULT 0,
                    erros INTEGER DEFAULT 0,
                    total_amostras INTEGER DEFAULT 0,
                    assertividade REAL DEFAULT 0.0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )

            for modulo in MODULOS_IA:
                cur.execute(
                    '''
                    INSERT OR IGNORE INTO pesos_ia_evolutivo
                        (modulo, peso, acertos, erros, total_amostras, assertividade)
                    VALUES (?, ?, 0, 0, 0, 0.0)
                    ''',
                    (modulo, PESO_INICIAL),
                )

            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS cooldown_moedas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL UNIQUE,
                    motivo TEXT DEFAULT 'STOP_LOSS',
                    bloqueado_ate TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )
            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS feedback_pnl_processados (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT,
                    closed_pnl REAL,
                    status TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )
            return True

        try:
            _execute_write('feedback_loop_init', _schema)
            print("✅ [FEEDBACK LOOP] Tabelas operacoes / pesos_ia_evolutivo prontas", flush=True)
        except Exception as err:
            print(f"⚠️ [FEEDBACK LOOP] Falha ao inicializar tabelas: {err}", flush=True)

    # ----------------------------------------------------------- open logging
    def registrar_operacao_aberta(
        self,
        symbol: str,
        side: str = '',
        *,
        client_id: int = 0,
        entry_price: float = 0.0,
        quantity: float = 0.0,
        bybit_order_id: str = '',
        sinais: dict | None = None,
    ) -> Optional[int]:
        """Grava operação ABERTA (passo 1 do circuito)."""
        from src.database.manager import _execute_write

        ativo = _normalize_symbol(symbol)
        if not ativo:
            return None
        sinais_json = ''
        try:
            if sinais:
                sinais_json = json.dumps(sinais, ensure_ascii=False, default=str)[:4000]
        except Exception:
            sinais_json = ''

        def _op(cur, conn):
            cur.execute(
                '''
                INSERT INTO operacoes
                    (client_id, ativo, side, status, entry_price, quantity, sinais_json, bybit_order_id)
                VALUES (?, ?, ?, 'ABERTA', ?, ?, ?, ?)
                ''',
                (
                    int(client_id or 0),
                    ativo,
                    str(side or '').upper(),
                    float(entry_price or 0),
                    float(quantity or 0),
                    sinais_json,
                    str(bybit_order_id or ''),
                ),
            )
            return cur.lastrowid

        try:
            op_id = _execute_write('registrar_operacao_aberta', _op)
            print(
                f"📝 [FEEDBACK LOOP] Operação #{op_id} ABERTA em {ativo} ({side})",
                flush=True,
            )
            return int(op_id) if op_id else None
        except Exception as err:
            print(f"⚠️ [FEEDBACK LOOP] Erro ao registrar ABERTA {ativo}: {err}", flush=True)
            return None

    # ------------------------------------------------------ Bybit reconciliation
    def sincronizar_trades_fechados(
        self,
        api_key: str = '',
        api_secret: str = '',
        *,
        broker=None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Consulta ``get_closed_pnl(category='linear')`` e reconcilia com ``operacoes`` ABERTA.
        Throttle padrão: 30s entre ciclos (FEEDBACK_SYNC_INTERVAL_SECS).
        """
        now = time.time()
        if not force and (now - self._last_sync_ts) < SYNC_MIN_INTERVAL_SECS:
            return {'skipped': True, 'reason': 'throttle'}

        with self._lock:
            if not force and (time.time() - self._last_sync_ts) < SYNC_MIN_INTERVAL_SECS:
                return {'skipped': True, 'reason': 'throttle'}
            self._last_sync_ts = time.time()

        result = {'processed': 0, 'wins': 0, 'losses': 0, 'errors': []}
        try:
            pnl_list = self._fetch_closed_pnl(api_key, api_secret, broker=broker)
        except Exception as err:
            msg = f'falha get_closed_pnl: {err}'
            print(f"[ERRO FEEDBACK LOOP] {msg}", flush=True)
            result['errors'].append(msg)
            return result

        for trade in pnl_list:
            try:
                handled = self._reconcile_one_closed_trade(trade)
                if not handled:
                    continue
                result['processed'] += 1
                if handled.get('status') == 'WIN':
                    result['wins'] += 1
                elif handled.get('status') == 'LOSS':
                    result['losses'] += 1
            except Exception as err:
                result['errors'].append(str(err))
                print(f"[ERRO FEEDBACK LOOP] item: {err}", flush=True)

        if result['processed']:
            print(
                f"[FEEDBACK LOOP] Reconciliados={result['processed']} "
                f"WIN={result['wins']} LOSS={result['losses']}",
                flush=True,
            )
        return result

    # Alias pedido no enunciado
    sincronizar_trades_fechados_bybit = sincronizar_trades_fechados

    def _fetch_closed_pnl(self, api_key: str, api_secret: str, broker=None) -> List[dict]:
        session = None
        if broker is not None and getattr(broker, 'pybit_session', None) and getattr(broker, 'authenticated', False):
            session = broker.pybit_session
        elif api_key and api_secret:
            from pybit.unified_trading import HTTP
            session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)

        if session is None:
            raise RuntimeError('sessão Bybit indisponível para get_closed_pnl')

        rsp = session.get_closed_pnl(category='linear', limit=50)
        if isinstance(rsp, dict) and rsp.get('retCode') not in (0, '0', None):
            raise RuntimeError(f"retCode={rsp.get('retCode')} {rsp.get('retMsg')}")
        return list((rsp.get('result') or {}).get('list') or [])

    def _already_processed(self, order_id: str) -> bool:
        if not order_id:
            return False
        from src.database.manager import _connect

        conn = None
        try:
            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                'SELECT 1 FROM feedback_pnl_processados WHERE order_id = ? LIMIT 1',
                (order_id,),
            )
            return cur.fetchone() is not None
        except Exception:
            return False
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _mark_processed(self, order_id: str, symbol: str, closed_pnl: float, status: str) -> None:
        if not order_id:
            return
        from src.database.manager import _execute_write

        def _op(cur, conn):
            cur.execute(
                '''
                INSERT OR IGNORE INTO feedback_pnl_processados
                    (order_id, symbol, closed_pnl, status)
                VALUES (?, ?, ?, ?)
                ''',
                (order_id, symbol, closed_pnl, status),
            )
            return True

        try:
            _execute_write('feedback_mark_processed', _op)
        except Exception:
            pass

    def _find_open_operacao(self, symbol_norm: str) -> Optional[dict]:
        from src.database.manager import _connect

        conn = None
        try:
            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                '''
                SELECT id, ativo, status, client_id FROM operacoes
                WHERE status = 'ABERTA'
                ORDER BY id DESC
                LIMIT 200
                '''
            )
            for row in cur.fetchall():
                row_d = dict(row)
                if _normalize_symbol(row_d.get('ativo')) == symbol_norm:
                    return row_d
            # Fallback: trades.open legado
            cur.execute(
                '''
                SELECT id, pair AS ativo, status, client_id FROM trades
                WHERE LOWER(COALESCE(status, '')) = 'open'
                ORDER BY id DESC
                LIMIT 200
                '''
            )
            for row in cur.fetchall():
                row_d = dict(row)
                if _normalize_symbol(row_d.get('ativo')) == symbol_norm:
                    row_d['_from_trades'] = True
                    return row_d
            return None
        except Exception as err:
            print(f"⚠️ [FEEDBACK LOOP] busca ABERTA: {err}", flush=True)
            return None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _reconcile_one_closed_trade(self, trade: dict) -> Optional[dict]:
        symbol = _normalize_symbol(trade.get('symbol'))
        if not symbol:
            return None

        order_id = str(
            trade.get('orderId')
            or trade.get('order_id')
            or f"{symbol}_{trade.get('updatedTime')}_{trade.get('closedPnl')}"
        )
        if self._already_processed(order_id):
            return None

        closed_pnl = float(trade.get('closedPnl') or 0)
        novo_status = 'WIN' if closed_pnl > 0 else 'LOSS'

        try:
            closed_time_ms = int(trade.get('updatedTime') or trade.get('createdTime') or 0)
            closed_at = (
                datetime.fromtimestamp(closed_time_ms / 1000.0, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                if closed_time_ms
                else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            )
        except Exception:
            closed_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

        operacao = self._find_open_operacao(symbol)
        if not operacao:
            # Sem ABERTA local: ainda processa cooldown em LOSS se for fechamento recente
            # mas só marca processado se aplicarmos cooldown para evitar spam.
            age_ok = True
            try:
                if int(trade.get('updatedTime') or 0):
                    age_sec = time.time() - (int(trade['updatedTime']) / 1000.0)
                    # Órfãos: só processa fechamentos muito recentes (evita RL em histórico antigo)
                    age_ok = age_sec <= 2 * 3600
            except Exception:
                age_ok = False
            if novo_status == 'LOSS' and age_ok:
                self._aplicar_cooldown_loss(symbol)
                self.atualizar_inteligencia_ia(novo_status)
                self._mark_processed(order_id, symbol, closed_pnl, novo_status)
                print(
                    f"[FEEDBACK LOOP] {symbol} LOSS sem ABERTA local "
                    f"({closed_pnl:.4f} USDT) — cooldown + RL aplicados",
                    flush=True,
                )
                return {'status': novo_status, 'symbol': symbol, 'orphan': True}
            self._mark_processed(order_id, symbol, closed_pnl, 'SKIP_NO_OPEN')
            return None

        from src.database.manager import _execute_write

        op_id = int(operacao['id'])
        from_trades = bool(operacao.get('_from_trades'))

        def _close_op_clean(cur, conn):
            if from_trades:
                cur.execute(
                    '''
                    UPDATE trades
                    SET status = 'closed',
                        profit = ?,
                        notes = COALESCE(notes, '') || ?,
                        closed_at = ?
                    WHERE id = ?
                    ''',
                    (
                        closed_pnl,
                        f' | FEEDBACK_{novo_status} pnl={closed_pnl:.4f}',
                        closed_at,
                        op_id,
                    ),
                )
                cur.execute(
                    '''
                    INSERT INTO operacoes
                        (client_id, ativo, side, status, pnl_realizado, closed_pnl_order_id, closed_at)
                    VALUES (?, ?, '', ?, ?, ?, ?)
                    ''',
                    (
                        int(operacao.get('client_id') or 0),
                        symbol,
                        novo_status,
                        closed_pnl,
                        order_id,
                        closed_at,
                    ),
                )
            else:
                cur.execute(
                    '''
                    UPDATE operacoes
                    SET status = ?,
                        pnl_realizado = ?,
                        closed_pnl_order_id = ?,
                        closed_at = ?,
                        exit_price = ?
                    WHERE id = ?
                    ''',
                    (
                        novo_status,
                        closed_pnl,
                        order_id,
                        closed_at,
                        float(trade.get('avgExitPrice') or 0),
                        op_id,
                    ),
                )
                cur.execute(
                    "SELECT id, pair FROM trades WHERE LOWER(COALESCE(status,'')) = 'open'"
                )
                for row in cur.fetchall():
                    pair = row['pair'] if hasattr(row, 'keys') else row[1]
                    tid = row['id'] if hasattr(row, 'keys') else row[0]
                    if _normalize_symbol(pair) == symbol:
                        cur.execute(
                            '''
                            UPDATE trades
                            SET status='closed', profit=?, notes=COALESCE(notes,'') || ?, closed_at=?
                            WHERE id=?
                            ''',
                            (
                                closed_pnl,
                                f' | FEEDBACK_{novo_status} pnl={closed_pnl:.4f}',
                                closed_at,
                                tid,
                            ),
                        )
            return True

        _execute_write('feedback_close_operacao', _close_op_clean)

        if novo_status == 'WIN':
            print(
                f"[FEEDBACK LOOP] Trade {symbol} encerrou em WIN (+{closed_pnl:.4f} USDT).",
                flush=True,
            )
        else:
            print(
                f"[FEEDBACK LOOP] Trade {symbol} encerrou em LOSS ({closed_pnl:.4f} USDT). "
                f"Ativando Cooldown 24h.",
                flush=True,
            )
            self._aplicar_cooldown_loss(symbol)

        self.atualizar_inteligencia_ia(novo_status)
        self._mark_processed(order_id, symbol, closed_pnl, novo_status)

        # Espelha no aprendizado legado (Cérebro 3 / adaptive weights)
        try:
            from src.ai_brain.cerebro3_soberano import get_cerebro3_soberano
            get_cerebro3_soberano().aprender_com_resultado(
                resultado='GANHOU' if novo_status == 'WIN' else 'PERDEU',
                condicao_mercado='NEUTRO',
                sinais_usados={
                    'sma200': 1, 'supertrend': 1, 'fibonacci': 1,
                    'volume_climax': 1, 'sup_res': 1,
                },
            )
        except Exception:
            pass

        return {'status': novo_status, 'symbol': symbol, 'pnl': closed_pnl}

    def _aplicar_cooldown_loss(self, symbol: str) -> None:
        try:
            from src.database import manager as db
            db.register_symbol_cooldown(symbol, hours=24, motivo='STOP_LOSS_RECENTE')
        except Exception as err:
            # Fallback direto se manager falhar
            print(f"⚠️ [FEEDBACK LOOP] cooldown via manager falhou ({err}) — fallback SQL", flush=True)
            from src.database.manager import _execute_write
            bloqueio = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            sym = _normalize_symbol(symbol)

            def _op(cur, conn):
                cur.execute(
                    '''
                    INSERT INTO cooldown_moedas (symbol, motivo, bloqueado_ate)
                    VALUES (?, 'STOP_LOSS_RECENTE', ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        motivo = excluded.motivo,
                        bloqueado_ate = excluded.bloqueado_ate,
                        created_at = CURRENT_TIMESTAMP
                    ''',
                    (sym, bloqueio),
                )
                return True

            try:
                _execute_write('feedback_cooldown_fallback', _op)
            except Exception as err2:
                print(f"[ERRO FEEDBACK LOOP] cooldown: {err2}", flush=True)

    # --------------------------------------------------------------- RL weights
    def atualizar_inteligencia_ia(self, resultado: str) -> None:
        """
        +0.03 WIN / -0.03 LOSS nos 3 módulos, peso em [0.10, 0.60],
        assertividade = acertos / total_amostras * 100.
        """
        from src.database.manager import _execute_write

        resultado_u = str(resultado or '').upper()
        is_win = resultado_u in ('WIN', 'GANHOU', 'TAKE_PROFIT', 'TP')

        def _op(cur, conn):
            cur.execute(
                'SELECT modulo, peso, acertos, erros, total_amostras FROM pesos_ia_evolutivo'
            )
            rows = cur.fetchall()
            if not rows:
                for modulo in MODULOS_IA:
                    cur.execute(
                        '''
                        INSERT OR IGNORE INTO pesos_ia_evolutivo
                            (modulo, peso, acertos, erros, total_amostras, assertividade)
                        VALUES (?, ?, 0, 0, 0, 0.0)
                        ''',
                        (modulo, PESO_INICIAL),
                    )
                cur.execute(
                    'SELECT modulo, peso, acertos, erros, total_amostras FROM pesos_ia_evolutivo'
                )
                rows = cur.fetchall()

            for row in rows:
                modulo = row['modulo'] if hasattr(row, 'keys') else row[0]
                peso = float(row['peso'] if hasattr(row, 'keys') else row[1] or PESO_INICIAL)
                acertos = int(row['acertos'] if hasattr(row, 'keys') else row[2] or 0)
                erros = int(row['erros'] if hasattr(row, 'keys') else row[3] or 0)
                total = int(row['total_amostras'] if hasattr(row, 'keys') else row[4] or 0)
                novo_total = total + 1

                if is_win:
                    novos_acertos = acertos + 1
                    novos_erros = erros
                    novo_peso = min(PESO_MAX, peso + TAXA_APRENDIZADO)
                else:
                    novos_acertos = acertos
                    novos_erros = erros + 1
                    novo_peso = max(PESO_MIN, peso - TAXA_APRENDIZADO)

                nova_assert = round((novos_acertos / novo_total) * 100.0, 1) if novo_total else 0.0
                cur.execute(
                    '''
                    UPDATE pesos_ia_evolutivo
                    SET peso = ?, acertos = ?, erros = ?, total_amostras = ?,
                        assertividade = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE modulo = ?
                    ''',
                    (novo_peso, novos_acertos, novos_erros, novo_total, nova_assert, modulo),
                )
            return True

        try:
            _execute_write('atualizar_inteligencia_ia', _op)
            label = 'WIN' if is_win else 'LOSS'
            print(
                f"[APRENDIZADO CONCLUÍDO] Pesos das IAs e amostras atualizados após trade {label}.",
                flush=True,
            )
        except Exception as err:
            print(f"[ERRO FEEDBACK LOOP] atualizar_inteligencia_ia: {err}", flush=True)

    def consultar_metricas_dashboard(self) -> List[Dict[str, Any]]:
        """Dados limpos para o painel Render (desbloqueia 0 Amostras)."""
        from src.database.manager import _connect

        conn = None
        try:
            self.inicializar_tabelas()
            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                '''
                SELECT modulo, peso, acertos, erros, total_amostras, assertividade, updated_at
                FROM pesos_ia_evolutivo
                ORDER BY id ASC
                '''
            )
            rows = [dict(r) for r in cur.fetchall()]
            # Normaliza pesos para % no painel (soma ≈ 1.0 → percentuais)
            total_peso = sum(float(r.get('peso') or 0) for r in rows) or 1.0
            out = []
            for r in rows:
                peso = float(r.get('peso') or 0)
                out.append({
                    'modulo': r.get('modulo'),
                    'peso': round(peso, 4),
                    'peso_pct': round((peso / total_peso) * 100.0, 1),
                    'acertos': int(r.get('acertos') or 0),
                    'erros': int(r.get('erros') or 0),
                    'total_amostras': int(r.get('total_amostras') or 0),
                    'assertividade': float(r.get('assertividade') or 0),
                    'updated_at': r.get('updated_at'),
                })
            return out
        except Exception as err:
            print(f"⚠️ [FEEDBACK LOOP] consultar_metricas: {err}", flush=True)
            return []
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def resumo_aprendizado(self) -> Dict[str, Any]:
        """Agrega amostras/win-rate para learning_from_history do tribunal."""
        mods = self.consultar_metricas_dashboard()
        if not mods:
            return {
                'sample_size': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'summary': 'Feedback Loop aguardando primeira reconciliação Bybit.',
                'modulos': [],
            }
        # Usa o módulo com mais amostras como referência de contagem de ciclos
        amostras = max(int(m.get('total_amostras') or 0) for m in mods)
        acertos = max(int(m.get('acertos') or 0) for m in mods)
        wr = round((acertos / amostras) * 100.0, 1) if amostras else 0.0
        media_assert = round(
            sum(float(m.get('assertividade') or 0) for m in mods) / max(len(mods), 1),
            1,
        )
        return {
            'sample_size': amostras,
            'win_rate': wr,
            'total_pnl': 0.0,
            'assertividade_media': media_assert,
            'summary': (
                f'Feedback Loop: {amostras} ciclo(s) reconciliados — '
                f'win rate {wr:.0f}% · assertividade média {media_assert:.0f}%.'
                if amostras
                else 'Feedback Loop ativo — 0 amostras (aguardando fechamento Bybit).'
            ),
            'modulos': mods,
        }


_FEEDBACK_SINGLETON: FeedbackLoopEvolutivo | None = None
_FEEDBACK_LOCK = threading.Lock()


def get_feedback_loop() -> FeedbackLoopEvolutivo:
    global _FEEDBACK_SINGLETON
    if _FEEDBACK_SINGLETON is not None:
        return _FEEDBACK_SINGLETON
    with _FEEDBACK_LOCK:
        if _FEEDBACK_SINGLETON is None:
            _FEEDBACK_SINGLETON = FeedbackLoopEvolutivo()
        return _FEEDBACK_SINGLETON
