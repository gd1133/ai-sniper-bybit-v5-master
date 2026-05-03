# -*- coding: utf-8 -*-
"""
Motor Sniper V60.7 — Bybit API V5 | Modo Caçador
=================================================
Executa um loop de varredura autônoma sobre os pares USDT-Linear mais líquidos,
aplica os 5 filtros técnicos do Modo Caçador e envia ordens a mercado apenas
quando TODAS as condições são satisfeitas simultaneamente.

Regras de Negócio:
  • Entrada  : 5 % do saldo total em USDT (Conta Unificada — UTA)
  • Stop Loss: 3 % do preço de entrada
  • Take Profit: +10 % do preço de entrada (≡ +100 % sobre a margem com 10×)
  • Categoria: linear  |  Tipo: Market  |  Margem: Cross 10×
"""

import os
import sys
import time
from typing import Optional, Tuple

from dotenv import load_dotenv

# ── Configuração do ambiente ──────────────────────────────────────────────────
load_dotenv()

from src.config import (
    get_bybit_base_url,
    get_bybit_credentials,
    resolve_use_testnet,
    BYBIT_TESTNET_URL,
    BYBIT_PRODUCTION_URL,
)
from src.broker.bybit_client import BybitClient
from src.engine.indicators import IndicatorEngine

# ── Parâmetros globais do Modo Caçador ────────────────────────────────────────
LEVERAGE = 10                   # Alavancagem (Cross 10×)
ENTRY_PCT = 0.05                # 5 % do saldo como margem por operação
SL_PCT = 0.03                   # Stop Loss: 3 % do preço de entrada
TP_PCT = 0.10                   # Take Profit: +10 % de preço ≡ +100 % de margem

# Tolerâncias dos filtros técnicos
FIB_DISTANCE_THRESHOLD_PCT = 2.0    # Preço deve estar a ≤ 2 % do nível 0.618
VOLUME_RATIO_MIN = 1.0              # Volume acima da média de 20 períodos
SR_DISTANCE_THRESHOLD_PCT = 1.5     # Zona de S/R ≤ 1.5 % do preço atual

# Universo de símbolos escaneados (pares USDT-Linear perpetuos)
SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
    "XRP/USDT:USDT",
    "DOGE/USDT:USDT",
    "ADA/USDT:USDT",
    "AVAX/USDT:USDT",
]

SCAN_INTERVAL_SECS = 30         # Pausa entre ciclos de varredura
INTER_SYMBOL_DELAY_SECS = 0.5   # Respiro entre símbolos do mesmo ciclo


# ── Inicialização e conexão ───────────────────────────────────────────────────

def _resolve_endpoint() -> Tuple[bool, str]:
    """Determina o endpoint da Bybit com base em USE_TESTNET."""
    use_testnet = resolve_use_testnet()
    endpoint = BYBIT_TESTNET_URL if use_testnet else BYBIT_PRODUCTION_URL
    env_label = "TESTNET" if use_testnet else "PRODUÇÃO"
    print(f"🌐 [AMBIENTE] {env_label} → {endpoint}", flush=True)
    return use_testnet, endpoint


def _build_client(use_testnet: bool) -> Optional[BybitClient]:
    """Instancia o BybitClient e valida a conexão; retorna None se falhar."""
    api_key, api_secret = get_bybit_credentials()
    if not api_key or not api_secret:
        print(
            "❌ [CONFIGURAÇÃO] BYBIT_API_KEY e/ou BYBIT_API_SECRET não definidos no .env. "
            "Abortando.",
            flush=True,
        )
        return None

    client = BybitClient(api_key=api_key, api_secret=api_secret, testnet=use_testnet)
    ok, message = client.test_connection()
    if not ok:
        # Distingue explicitamente o erro 10003 (Chave Inválida / Permissão)
        if "10003" in message or "API key is invalid" in message.lower():
            print(
                "🔴 [ERRO 10003] Chave de API inválida ou sem permissão.\n"
                "   → Verifique se a chave é do ambiente correto (Testnet / Produção).\n"
                "   → Confirme que as permissões de 'Contrato' estão habilitadas na Bybit.",
                flush=True,
            )
        else:
            print(f"❌ [CONEXÃO] Falha na validação: {message}", flush=True)
        return None

    print(f"✅ [CONEXÃO] {message}", flush=True)
    return client


# ── Gestão de Risco: Saldo e Tamanho da Entrada ───────────────────────────────

def _get_uta_balance(client: BybitClient) -> Optional[float]:
    """
    Consulta o saldo total em USDT da Conta Unificada (UTA).
    Retorna None e exibe alerta se o saldo for ≤ 0 ou indisponível.
    """
    balance = client.get_balance()
    if balance is None:
        print(
            "⚠️  [SALDO] Não foi possível obter o saldo USDT. "
            "Verifique as credenciais e as permissões da API.",
            flush=True,
        )
        return None

    if balance <= 0:
        print(
            f"🚨 [SALDO] Saldo USDT insuficiente ({balance:.4f} USDT). "
            "Operação abortada.",
            flush=True,
        )
        return None

    print(f"💰 [SALDO UTA] {balance:.4f} USDT disponíveis", flush=True)
    return balance


def _calculate_position_size(balance: float, price: float) -> Tuple[float, float]:
    """
    Calcula margem e quantidade da entrada com base nas regras do Modo Caçador.

    Retorna:
        margin_usdt : valor em USDT alocado como margem (5 % do saldo)
        qty         : número de contratos para o par
    """
    margin_usdt = round(balance * ENTRY_PCT, 4)
    notional = margin_usdt * LEVERAGE          # Valor nocional com alavancagem
    qty = notional / price
    return margin_usdt, qty


# ── Configuração de Alavancagem e Margem Cruzada ─────────────────────────────

def _set_cross_leverage(client: BybitClient, raw_symbol: str) -> bool:
    """
    Define margem Cross e alavancagem 10× via pybit V5.
    raw_symbol deve estar no formato limpo, ex: BTCUSDT.
    """
    if client.pybit_session is None:
        print(f"⚠️  [LEVERAGE] Sessão pybit indisponível para {raw_symbol}", flush=True)
        return False

    try:
        # Margem cruzada (tradeMode=0); isolada seria tradeMode=1
        client.pybit_session.switch_margin_mode(
            category="linear",
            symbol=raw_symbol,
            tradeMode=0,        # 0 = Cross Margin
            buyLeverage=str(LEVERAGE),
            sellLeverage=str(LEVERAGE),
        )
    except Exception as e:
        # A Bybit retorna erro se a margem já estiver no modo correto; pode-se ignorar
        err = str(e)
        if "margin mode is not modified" not in err.lower():
            print(f"⚠️  [LEVERAGE] switch_margin_mode: {err[:120]}", flush=True)

    try:
        client.pybit_session.set_leverage(
            category="linear",
            symbol=raw_symbol,
            buyLeverage=str(LEVERAGE),
            sellLeverage=str(LEVERAGE),
        )
        print(
            f"⚙️  [LEVERAGE] {raw_symbol}: Cross Margin, {LEVERAGE}× configurado.",
            flush=True,
        )
        return True
    except Exception as e:
        print(f"⚠️  [LEVERAGE] set_leverage falhou para {raw_symbol}: {e}", flush=True)
        return False


# ── Filtros do Modo Caçador ────────────────────────────────────────────────────

def _detect_pivot(df) -> bool:
    """
    Detecta um pivô relevante nas últimas 3 velas.
    Pivô de Alta : mínima[i-1] < mínima[i-2] e mínima[i-1] < mínima[i]  (suporte)
    Pivô de Baixa: máxima[i-1] > máxima[i-2] e máxima[i-1] > máxima[i]  (resistência)
    Retorna True se qualquer pivô foi detectado nas últimas 5 candles.
    """
    if len(df) < 3:
        return False
    for i in range(len(df) - 1, max(len(df) - 6, 1), -1):
        h_prev, h_cur, h_next = df['high'].iloc[i - 2], df['high'].iloc[i - 1], df['high'].iloc[i]
        l_prev, l_cur, l_next = df['low'].iloc[i - 2], df['low'].iloc[i - 1], df['low'].iloc[i]
        if h_cur > h_prev and h_cur > h_next:   # Pivô de máxima
            return True
        if l_cur < l_prev and l_cur < l_next:   # Pivô de mínima
            return True
    return False


def _is_near_sr_zone(signals: dict) -> bool:
    """
    Verifica se o preço está próximo de uma zona de Suporte/Resistência.
    Usa o nível de Fibonacci 0.618 como proxy de S/R institucional.
    """
    fib_distance_pct = float(signals.get('fib_distance_pct', 999) or 999)
    return fib_distance_pct <= SR_DISTANCE_THRESHOLD_PCT


def _apply_hunter_filters(signals: dict, df) -> Tuple[bool, dict]:
    """
    Aplica os 5 filtros técnicos do Modo Caçador.

    Retorna:
        all_pass : True somente se TODOS os 5 filtros forem aprovados
        status   : dicionário com o resultado individual de cada filtro
    """
    trend = signals.get('trend', 'NEUTRO')
    supertrend = int(signals.get('supertrend_signal', 0))
    fib_dist = float(signals.get('fib_distance_pct', 999) or 999)
    vol_ratio = float(signals.get('volume_ratio', 0) or 0)

    # ── Filtro 1: SMA — Tendência alinhada ────────────────────────────────────
    f1_sma = trend in ("ALTA", "BAIXA")

    # ── Filtro 2: Pivô e SuperTrend ───────────────────────────────────────────
    supertrend_aligned = (
        (trend == "ALTA" and supertrend == 1) or
        (trend == "BAIXA" and supertrend == -1)
    )
    pivot_detected = _detect_pivot(df)
    f2_pivot_st = supertrend_aligned and pivot_detected

    # ── Filtro 3: Retração de Fibonacci ───────────────────────────────────────
    f3_fib = fib_dist <= FIB_DISTANCE_THRESHOLD_PCT

    # ── Filtro 4: Volume acima da média do período ────────────────────────────
    f4_volume = vol_ratio >= VOLUME_RATIO_MIN

    # ── Filtro 5: Zona de Suporte/Resistência ─────────────────────────────────
    f5_sr = _is_near_sr_zone(signals)

    status = {
        "F1_SMA_Tendencia":       f1_sma,
        "F2_Pivo_SuperTrend":     f2_pivot_st,
        "F3_Fibonacci_0618":      f3_fib,
        "F4_Volume_Acima_Media":  f4_volume,
        "F5_Suporte_Resistencia": f5_sr,
    }
    all_pass = all(status.values())
    return all_pass, status


def _log_filter_status(symbol: str, signals: dict, status: dict, all_pass: bool):
    """Exibe no console o status detalhado de cada indicador antes da entrada."""
    icon = "✅" if all_pass else "❌"
    print(f"\n{'═' * 60}", flush=True)
    print(
        f"{icon} [MODO CAÇADOR] {symbol} | "
        f"Tendência={signals.get('trend')} | "
        f"Preço={signals.get('price', 0):.4f} USDT",
        flush=True,
    )
    print(f"   RSI={signals.get('rsi', 0):.1f}  ATR={signals.get('atr', 0):.4f}  "
          f"Vol/Média={signals.get('volume_ratio', 0):.2f}×  "
          f"Fib_dist={signals.get('fib_distance_pct', 0):.2f}%",
          flush=True)
    for name, passed in status.items():
        mark = "✅" if passed else "❌"
        print(f"   {mark} {name}", flush=True)
    if all_pass:
        print("   🎯 TODOS OS FILTROS APROVADOS — AGUARDANDO EXECUÇÃO", flush=True)
    else:
        blocked = [k for k, v in status.items() if not v]
        print(f"   ⛔ Bloqueado por: {', '.join(blocked)}", flush=True)
    print(f"{'═' * 60}\n", flush=True)


# ── Execução de Ordens ────────────────────────────────────────────────────────

def _build_tp_sl_prices(side: str, entry_price: float) -> Tuple[float, float]:
    """
    Calcula os preços absolutos de TP e SL.

    Protocolo 100/3:
      TP = +10 % de preço → +100 % de margem a 10×
      SL = -3 % de preço  (trava institucional)
    """
    if side.upper() in ("BUY", "COMPRAR", "LONG"):
        tp = round(entry_price * (1 + TP_PCT), 8)
        sl = round(entry_price * (1 - SL_PCT), 8)
    else:  # SELL / SHORT
        tp = round(entry_price * (1 - TP_PCT), 8)
        sl = round(entry_price * (1 + SL_PCT), 8)
    return tp, sl


def _set_tp_sl(client: BybitClient, raw_symbol: str, tp_price: float, sl_price: float):
    """
    Define TP e SL na posição aberta via pybit V5 (set_trading_stop).
    Fallback silencioso: a posição permanece aberta sem proteção automática.
    """
    if client.pybit_session is None:
        print("⚠️  [TP/SL] Sessão pybit indisponível; TP/SL não configurado.", flush=True)
        return

    try:
        rsp = client.pybit_session.set_trading_stop(
            category="linear",
            symbol=raw_symbol,
            takeProfit=str(tp_price),
            stopLoss=str(sl_price),
        )
        ok, err = client._handle_v5_ret_code(rsp, "v5/position/trading-stop")
        if ok:
            print(
                f"🛡️  [TP/SL SETADO] TP={tp_price:.4f}  SL={sl_price:.4f}",
                flush=True,
            )
        else:
            print(f"⚠️  [TP/SL] {err}", flush=True)
    except Exception as e:
        print(f"⚠️  [TP/SL] Exceção ao setar proteção: {e}", flush=True)


def _execute_sniper_entry(
    client: BybitClient,
    symbol: str,
    side: str,
    qty: float,
    entry_price: float,
    margin_usdt: float,
):
    """
    Executa a entrada sniper:
      1. Configura margem Cross + alavancagem 10×.
      2. Envia ordem de mercado.
      3. Define TP e SL imediatamente após a execução.
    """
    raw_symbol = client._normalize_v5_symbol(symbol)
    normalized_side = "buy" if side == "ALTA" else "sell"

    print(
        f"\n🔥 [ENTRADA SNIPER] {symbol} | Lado={normalized_side.upper()} | "
        f"Qty={qty:.6f} | Margem={margin_usdt:.4f} USDT | Alavancagem={LEVERAGE}×",
        flush=True,
    )

    # 1. Cross Margin + Leverage
    _set_cross_leverage(client, raw_symbol)

    # 2. Ordem a Mercado
    order = client.execute_market_order(symbol, normalized_side, round(qty, 6))
    if order is None:
        print("❌ [ENTRADA] Ordem não executada.", flush=True)
        return

    print(f"✅ [ORDEM CONFIRMADA] ID={order.get('id')} | {order}", flush=True)

    # 3. TP / SL
    tp_price, sl_price = _build_tp_sl_prices(normalized_side, entry_price)
    print(
        f"   📍 Entrada: {entry_price:.4f}  "
        f"✅ TP: {tp_price:.4f} (+{TP_PCT * 100:.0f}% preço → +100% margem)  "
        f"❌ SL: {sl_price:.4f} (-{SL_PCT * 100:.0f}%)",
        flush=True,
    )
    _set_tp_sl(client, raw_symbol, tp_price, sl_price)


# ── Loop Principal de Varredura ───────────────────────────────────────────────

def _scan_symbol(client: BybitClient, symbol: str, balance: float):
    """
    Analisa um símbolo e, se todos os filtros forem aprovados, executa a entrada.
    """
    # 1. Busca dados OHLCV
    df = client.fetch_ohlcv(symbol, timeframe="15m")
    if df is None or len(df) < 20:
        print(f"⚠️  [SCAN] {symbol}: dados insuficientes, pulando.", flush=True)
        return

    # 2. Calcula indicadores técnicos
    engine = IndicatorEngine(df)
    signals = engine.get_signals()

    # 3. Filtros do Modo Caçador (todos os 5 devem passar)
    all_pass, filter_status = _apply_hunter_filters(signals, df)
    _log_filter_status(symbol, signals, filter_status, all_pass)

    if not all_pass:
        return  # Aguarda próximo ciclo

    # 4. Determina o lado da operação
    trend = signals.get('trend')
    side = trend  # "ALTA" → buy | "BAIXA" → sell

    # 5. Calcula tamanho da posição
    price = signals.get('price', 0.0)
    if price <= 0:
        print(f"⚠️  [SCAN] {symbol}: preço inválido ({price}), pulando.", flush=True)
        return

    margin_usdt, qty = _calculate_position_size(balance, price)
    print(
        f"📐 [DIMENSIONAMENTO] Saldo={balance:.4f} | "
        f"Entrada=5% → Margem={margin_usdt:.4f} USDT | "
        f"Nocional={margin_usdt * LEVERAGE:.4f} USDT | "
        f"Qty={qty:.6f}",
        flush=True,
    )

    # 6. Executa a entrada
    _execute_sniper_entry(client, symbol, side, qty, price, margin_usdt)


def sniper_loop(client: BybitClient):
    """Loop principal do Motor Sniper V60.7."""
    cycle = 0
    print("🚀 [SNIPER V60.7] Motor iniciado. Pressione Ctrl+C para parar.\n", flush=True)

    while True:
        cycle += 1
        print(f"🔍 [CICLO {cycle}] Iniciando varredura de {len(SYMBOLS)} pares...", flush=True)

        # Atualiza saldo a cada ciclo para refletir variações da banca
        balance = _get_uta_balance(client)
        if balance is None:
            print(f"⏸️  [CICLO {cycle}] Saldo indisponível; aguardando {SCAN_INTERVAL_SECS}s.", flush=True)
            time.sleep(SCAN_INTERVAL_SECS)
            continue

        for symbol in SYMBOLS:
            try:
                _scan_symbol(client, symbol, balance)
            except Exception as e:
                print(f"❌ [ERRO] {symbol}: {e}", flush=True)
            time.sleep(INTER_SYMBOL_DELAY_SECS)

        print(
            f"⏳ [CICLO {cycle}] Varredura concluída. Próximo ciclo em {SCAN_INTERVAL_SECS}s.\n",
            flush=True,
        )
        time.sleep(SCAN_INTERVAL_SECS)


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    print("=" * 60, flush=True)
    print("  Motor Sniper V60.7 | Bybit API V5 | Modo Caçador", flush=True)
    print("=" * 60, flush=True)

    # 1. Resolve o ambiente (testnet / produção) via USE_TESTNET
    use_testnet, _ = _resolve_endpoint()

    # 2. Instancia e valida o cliente (inclui tratamento do erro 10003)
    client = _build_client(use_testnet)
    if client is None:
        sys.exit(1)

    # 3. Inicia o loop do sniper
    try:
        sniper_loop(client)
    except KeyboardInterrupt:
        print("\n👋 [SNIPER] Interrompido pelo operador. Encerrando.", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
