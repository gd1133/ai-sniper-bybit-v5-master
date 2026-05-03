#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor Sniper V60.7 — Bybit V5 API
Modo Caçador: Integração segura com Conta de Negociação Unificada (UTA)

Regras de negócio:
  • Entrada  : 5 % da banca como margem por operação
  • Leverage : 10x em modo Cross Margin
  • Stop Loss: 3 % de variação de preço (= 30 % da margem com 10x)
  • Take Profit: 100 % do lucro sobre a margem (= 10 % de variação de preço)
  • 5 filtros simultâneos: SMA, Pivô + SuperTrend, Fibonacci 0.618, Volume, S/R
"""

import math
import os
import sys
import time
import logging

from dotenv import load_dotenv

# ─── Carrega variáveis de ambiente ───────────────────────────────────────────
load_dotenv()

from src.config import (
    BYBIT_PRODUCTION_URL,
    BYBIT_TESTNET_URL,
    get_bybit_credentials,
    resolve_use_testnet,
)
from src.broker.bybit_client import BybitClient
from src.engine.indicators import IndicatorEngine

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SNIPER] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("sniper")

# =============================================================================
# PARÂMETROS DE RISCO — Modo Caçador
# =============================================================================
ENTRY_PCT       = 0.05   # 5 % da banca como margem por entrada
SL_PCT          = 0.03   # Stop Loss: 3 % de variação de preço
LEVERAGE        = 10     # Alavancagem 10x (Cross Margin)
# Com 10x, TP de 100 % sobre a margem equivale a 10 % de variação de preço.
TP_PRICE_PCT    = 1.0 / LEVERAGE  # 0.10 → +10 % (Long) / −10 % (Short)

# =============================================================================
# CONFIGURAÇÃO DOS ATIVOS E CICLO
# =============================================================================
TIMEFRAME       = "15"   # Velas de 15 minutos (parâmetro nativo Bybit V5)
SYMBOLS         = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
LOOP_INTERVAL   = 60     # Segundos entre ciclos de varredura

# =============================================================================
# THRESHOLDS DOS FILTROS TÉCNICOS
# =============================================================================
VOLUME_RATIO_MIN = 1.5   # Volume ≥ 1,5× a média móvel de 20 períodos
FIB_ZONE_MAX_PCT = 2.0   # Distância máxima do nível Fibonacci 0.618 (%)
SR_ZONE_MAX_PCT  = 1.5   # Distância máxima de zona de Suporte/Resistência (%)
PIVOT_WINDOW     = 5     # Períodos para identificação de pivôs locais


# =============================================================================
# FUNÇÕES AUXILIARES — Indicadores Adicionais
# =============================================================================

def _detect_pivot(df, window=PIVOT_WINDOW):
    """
    Detecta se o candle ``window`` posições antes do final formou um pivô local.

    Em tendência de ALTA buscamos pivot_low (retração comprada).
    Em tendência de BAIXA buscamos pivot_high (rejeição de resistência).

    Retorna:
        pivot_high (bool): pivô de alta confirmado
        pivot_low  (bool): pivô de baixa confirmado
    """
    if len(df) < 2 * window + 1:
        return False, False

    idx    = len(df) - window - 1   # candle "congelado" com janela à direita
    highs  = df["high"].values
    lows   = df["low"].values

    pivot_high = (
        all(highs[idx] >= highs[idx - window : idx]) and
        all(highs[idx] >= highs[idx + 1 : idx + window + 1])
    )
    pivot_low = (
        all(lows[idx] <= lows[idx - window : idx]) and
        all(lows[idx] <= lows[idx + 1 : idx + window + 1])
    )

    return pivot_high, pivot_low


def _detect_sr_zone(df, current_price, tolerance_pct=SR_ZONE_MAX_PCT, window=PIVOT_WINDOW):
    """
    Verifica se o preço atual está próximo a uma zona de Suporte ou Resistência
    definida pelos pivôs detectados no histórico de candles.

    Retorna:
        near_sr    (bool): True se dentro da tolerância de algum nível S/R
        zone_label (str) : descrição do nível mais próximo
    """
    if len(df) < 2 * window + 1:
        return False, "dados insuficientes"

    highs = df["high"].values
    lows  = df["low"].values
    sr_levels = []

    for i in range(window, len(df) - window):
        if all(highs[i] >= highs[i - window : i]) and all(highs[i] >= highs[i + 1 : i + window + 1]):
            sr_levels.append(("R", highs[i]))
        if all(lows[i] <= lows[i - window : i]) and all(lows[i] <= lows[i + 1 : i + window + 1]):
            sr_levels.append(("S", lows[i]))

    # Verifica os 10 níveis mais recentes (mais relevantes)
    for label, level in sr_levels[-10:]:
        dist_pct = abs(current_price - level) / current_price * 100
        if dist_pct <= tolerance_pct:
            zone_name = "Suporte" if label == "S" else "Resistência"
            return True, f"{zone_name} @ {level:.4f} (dist {dist_pct:.2f}%)"

    return False, "sem zona próxima"


def _round_qty(qty_raw, step=0.001):
    """Arredonda a quantidade para baixo no step size mínimo do contrato."""
    return math.floor(qty_raw / step) * step


# =============================================================================
# INICIALIZAÇÃO DO CLIENTE
# =============================================================================

def _init_client():
    """
    Cria o BybitClient com base em USE_TESTNET:
      • True  → https://api-testnet.bybit.com
      • False → https://api.bybit.com

    recv_window=20000 já está configurado internamente no BybitClient para
    evitar timeouts.  O tratamento do erro 10003 (Chave Inválida / Permissão)
    também é gerenciado pelo cliente com log claro no console.
    """
    use_testnet         = resolve_use_testnet()
    endpoint            = BYBIT_TESTNET_URL if use_testnet else BYBIT_PRODUCTION_URL
    api_key, api_secret = get_bybit_credentials()

    log.info("=" * 60)
    log.info("🎯  Motor Sniper V60.7 — Bybit V5 API  (Modo Caçador)")
    log.info("=" * 60)
    log.info(f"📡 Ambiente  : {'TESTNET' if use_testnet else 'PRODUÇÃO'}")
    log.info(f"🌐 Endpoint  : {endpoint}")
    log.info(f"🔑 API Key   : {(api_key[:6] + '***') if api_key else '— NÃO DEFINIDA —'}")
    log.info(f"⚙️  Leverage  : {LEVERAGE}x | Margem: Cross | Entrada: {ENTRY_PCT*100:.0f}% banca")
    log.info(f"🛑 SL: {SL_PCT*100:.0f}% de variação | 🎯 TP: {TP_PRICE_PCT*100:.0f}% de variação (100% margem)")

    return BybitClient(api_key=api_key, api_secret=api_secret, testnet=use_testnet)


# =============================================================================
# CONFIGURAÇÃO DE ALAVANCAGEM E MODO DE MARGEM
# =============================================================================

def _configure_symbol(client, symbol):
    """
    Configura margem cruzada (Cross, tradeMode=0) e alavancagem de 10x
    via pybit V5 antes de cada entrada.

    Códigos de retorno não-fatais que são ignorados:
      • 110026 — já está em modo Cross
      • 110043 — alavancagem não mudou
    """
    session   = client.pybit_session
    v5_symbol = client._normalize_v5_symbol(symbol)

    if session is None:
        log.warning(f"[CONFIG] Sessão pybit indisponível para {symbol}. Pulando configuração.")
        return False

    # Modo Cross Margin (tradeMode=0)
    try:
        rsp = session.switch_margin_mode(
            category="linear",
            symbol=v5_symbol,
            tradeMode=0,                  # 0 = Cross Margin
            buyLeverage=str(LEVERAGE),
            sellLeverage=str(LEVERAGE),
        )
        ok, msg = client._handle_v5_ret_code(rsp, f"switch_margin_mode({v5_symbol})")
        if not ok and "110026" not in msg:
            log.warning(f"[CONFIG] Margem Cross: {msg}")
    except Exception as exc:
        log.warning(f"[CONFIG] switch_margin_mode({v5_symbol}): {exc}")

    # Alavancagem 10x
    try:
        rsp = session.set_leverage(
            category="linear",
            symbol=v5_symbol,
            buyLeverage=str(LEVERAGE),
            sellLeverage=str(LEVERAGE),
        )
        ok, msg = client._handle_v5_ret_code(rsp, f"set_leverage({v5_symbol})")
        if not ok and "110043" not in msg:
            log.error(f"[CONFIG] set_leverage({v5_symbol}): {msg}")
            return False
    except Exception as exc:
        log.error(f"[CONFIG] set_leverage({v5_symbol}): {exc}")
        return False

    log.info(f"[CONFIG] {v5_symbol}: Cross margin, {LEVERAGE}x leverage OK")
    return True


# =============================================================================
# TAKE PROFIT / STOP LOSS
# =============================================================================

def _set_trading_stop(client, symbol, side, entry_price):
    """
    Define TP e SL na posição aberta via pybit V5 set_trading_stop.

    Long  → TP = entrada × 1.10 | SL = entrada × 0.97
    Short → TP = entrada × 0.90 | SL = entrada × 1.03
    """
    session   = client.pybit_session
    v5_symbol = client._normalize_v5_symbol(symbol)
    v5_side   = client._normalize_v5_side(side)

    if session is None:
        log.warning("[TP/SL] Sessão pybit indisponível. TP/SL não configurado.")
        return False

    if v5_side == "Buy":
        tp_price = round(entry_price * (1 + TP_PRICE_PCT), 4)
        sl_price = round(entry_price * (1 - SL_PCT), 4)
    else:
        tp_price = round(entry_price * (1 - TP_PRICE_PCT), 4)
        sl_price = round(entry_price * (1 + SL_PCT), 4)

    log.info(f"🛡️  [TP/SL] {v5_symbol} {'LONG' if v5_side == 'Buy' else 'SHORT'}")
    log.info(f"   📍 Entrada : ${entry_price:.4f}")
    log.info(f"   ✅ TP      : ${tp_price:.4f}  (+{TP_PRICE_PCT*100:.0f}% preço = +100% margem)")
    log.info(f"   ❌ SL      : ${sl_price:.4f}  (-{SL_PCT*100:.0f}% preço)")

    try:
        rsp = session.set_trading_stop(
            category="linear",
            symbol=v5_symbol,
            takeProfit=str(tp_price),
            stopLoss=str(sl_price),
            tpTriggerBy="MarkPrice",
            slTriggerBy="MarkPrice",
            positionIdx=0,       # 0 = one-way mode (compatível com UTA)
        )
        ok, msg = client._handle_v5_ret_code(rsp, "set_trading_stop")
        if not ok:
            log.error(f"❌ [TP/SL] Falhou: {msg}")
            return False
        log.info("✅ [TP/SL] Configurado com sucesso.")
        return True
    except Exception as exc:
        log.error(f"❌ [TP/SL] Exceção: {exc}")
        return False


# =============================================================================
# FILTROS — MODO CAÇADOR (5 condições simultâneas)
# =============================================================================

def _run_hunter_filters(df, signals, symbol):
    """
    Aplica os 5 filtros do Modo Caçador e imprime o status de cada um.

    Retorna:
        approved  (bool): True somente se TODOS os 5 filtros estiverem OK
        direction (str) : 'buy' ou 'sell' conforme a tendência identificada
    """
    price        = signals["price"]
    trend        = signals["trend"]
    st_signal    = signals["supertrend_signal"]
    fib_dist_pct = signals["fib_distance_pct"]
    vol_ratio    = signals["volume_ratio"]

    # ── Filtro 1: SMA — Tendência Alinhada ────────────────────────────────
    f1_ok     = trend in ("ALTA", "BAIXA")
    direction = "buy" if trend == "ALTA" else "sell"
    f1_status = (
        f"{'✅' if f1_ok else '❌'} [F1] SMA: tendência={trend} | "
        f"preço={price:.4f} | sma200={signals['sma_200']:.4f}"
    )

    # ── Filtro 2: Pivô + SuperTrend ───────────────────────────────────────
    pivot_high, pivot_low = _detect_pivot(df)
    # ALTA: queremos pivot_low (retração comprada) + SuperTrend bullish
    # BAIXA: queremos pivot_high (rejeição de topo) + SuperTrend bearish
    pivot_aligned = (trend == "ALTA" and pivot_low) or (trend == "BAIXA" and pivot_high)
    st_aligned    = (trend == "ALTA" and st_signal == 1) or (trend == "BAIXA" and st_signal == -1)
    f2_ok         = pivot_aligned and st_aligned
    f2_status     = (
        f"{'✅' if f2_ok else '❌'} [F2] Pivô+SuperTrend: "
        f"pivot_high={pivot_high} pivot_low={pivot_low} "
        f"st_signal={st_signal} st_alinhado={st_aligned}"
    )

    # ── Filtro 3: Fibonacci 0.618 — Zona de Retração ──────────────────────
    f3_ok     = fib_dist_pct <= FIB_ZONE_MAX_PCT
    f3_status = (
        f"{'✅' if f3_ok else '❌'} [F3] Fibonacci 0.618: "
        f"nível={signals['fib_618']:.4f} | dist={fib_dist_pct:.2f}% "
        f"(limite={FIB_ZONE_MAX_PCT}%)"
    )

    # ── Filtro 4: Volume Acima da Média ────────────────────────────────────
    f4_ok     = vol_ratio >= VOLUME_RATIO_MIN
    f4_status = (
        f"{'✅' if f4_ok else '❌'} [F4] Volume: "
        f"ratio={vol_ratio:.2f}x (mínimo={VOLUME_RATIO_MIN}x) | "
        f"tendência={signals['volume_trend']}"
    )

    # ── Filtro 5: Suporte / Resistência ───────────────────────────────────
    near_sr, sr_label = _detect_sr_zone(df, price)
    f5_ok     = near_sr
    f5_status = f"{'✅' if f5_ok else '❌'} [F5] S/R: {sr_label}"

    # ── Relatório no Console ───────────────────────────────────────────────
    log.info(f"── Filtros Modo Caçador ▶ {symbol} ──────────────────────")
    log.info(f1_status)
    log.info(f2_status)
    log.info(f3_status)
    log.info(f4_status)
    log.info(f5_status)

    approved = f1_ok and f2_ok and f3_ok and f4_ok and f5_ok
    verdict  = "🟢 TODOS OS FILTROS APROVADOS — SINAL DE ENTRADA" if approved else "🔴 AGUARDANDO — filtros insuficientes"
    log.info(f"── Resultado: {verdict} ──────────────────────────────────")

    return approved, direction


# =============================================================================
# CICLO DE VARREDURA
# =============================================================================

def run_sniper_cycle(client):
    """
    Executa um ciclo completo de varredura:
      1. Obtém saldo USDT da carteira UTA.
      2. Calcula o valor de cada entrada (5 % da banca).
      3. Para cada símbolo: busca OHLCV, calcula indicadores,
         aplica filtros e (se aprovado) executa ordem + TP/SL.
    """
    # ── Saldo UTA ─────────────────────────────────────────────────────────
    balance = client.get_balance()
    if balance is None or balance <= 0:
        log.warning(
            "⚠️  [SALDO] Saldo USDT insuficiente ou indisponível na carteira UTA. "
            "Ciclo abortado."
        )
        return

    entry_margin = balance * ENTRY_PCT
    log.info(
        f"💰 Saldo UTA: ${balance:.2f} USDT | "
        f"Entrada: ${entry_margin:.2f} USDT ({ENTRY_PCT*100:.0f}% da banca)"
    )

    for symbol in SYMBOLS:
        log.info(f"\n{'─'*55}")
        log.info(f"🔍 Analisando: {symbol}")

        # Dados OHLCV (250 candles de 15 min)
        df = client.fetch_ohlcv(symbol, timeframe=TIMEFRAME)
        if df is None or len(df) < 250:
            log.warning(f"[{symbol}] Dados insuficientes ({len(df) if df is not None else 0} candles). Pulando.")
            continue

        # Indicadores Técnicos
        engine  = IndicatorEngine(df)
        signals = engine.get_signals()

        price = signals["price"]
        if price <= 0:
            log.warning(f"[{symbol}] Preço inválido ({price}). Pulando.")
            continue

        # ── 5 Filtros do Modo Caçador ──────────────────────────────────
        approved, direction = _run_hunter_filters(df, signals, symbol)
        if not approved:
            continue

        # ── Configuração de Alavancagem e Modo de Margem ───────────────
        if not _configure_symbol(client, symbol):
            log.error(f"[{symbol}] Falha ao configurar margem/leverage. Pulando entrada.")
            continue

        # ── Cálculo de Quantidade ──────────────────────────────────────
        # qty = (margem × alavancagem) / preço  [contratos na moeda base]
        qty_raw = (entry_margin * LEVERAGE) / price
        qty     = _round_qty(qty_raw)
        if qty <= 0:
            log.warning(f"[{symbol}] Quantidade calculada inválida ({qty_raw:.6f} → {qty}). Pulando.")
            continue

        log.info(
            f"🎯 [ENTRADA] {symbol} | Lado={direction.upper()} | "
            f"Preço≈${price:.4f} | Qty={qty} | Margem=${entry_margin:.2f} USDT"
        )

        # ── Execução da Ordem a Mercado ────────────────────────────────
        # Categoria: "linear" (Futuros Perpétuos USDT)
        # Tipo: "Market"
        order = client.execute_market_order(symbol, direction, qty)
        if order is None:
            log.error(f"❌ [{symbol}] Ordem de mercado falhou.")
            continue

        order_id = order.get("id") or order.get("orderId") or "—"
        log.info(f"✅ [ORDEM] ID={order_id} | {symbol} | {direction.upper()} | Qty={qty}")

        # Aguarda 1 s para preço de preenchimento ser atualizado
        time.sleep(1)
        fill_price = client.get_last_price(symbol) or price

        # ── Take Profit e Stop Loss ────────────────────────────────────
        _set_trading_stop(client, symbol, direction, fill_price)


# =============================================================================
# PONTO DE ENTRADA
# =============================================================================

def main():
    """Ponto de entrada do Motor Sniper V60.7."""
    client = _init_client()

    # Valida conectividade com a Bybit (inclui tratamento de erro 10003)
    ok, msg = client.test_connection()
    if not ok:
        log.error(f"❌ [CONEXÃO] Falha ao conectar com a Bybit: {msg}")
        # Erro 10003 (Chave Inválida / Permissão) é detectado e logado
        # internamente pelo BybitClient com alerta detalhado.
        sys.exit(1)

    log.info(f"✅ [CONEXÃO] {msg}")
    log.info(
        f"\n🏹 Modo Caçador ATIVO | Ativos: {', '.join(SYMBOLS)} | "
        f"Timeframe: {TIMEFRAME}m | Ciclo: {LOOP_INTERVAL}s\n"
    )

    while True:
        try:
            run_sniper_cycle(client)
        except KeyboardInterrupt:
            log.info("\n⛔ Motor Sniper encerrado pelo usuário.")
            break
        except Exception as exc:
            log.error(f"❌ [CICLO] Erro inesperado: {exc}")

        log.info(f"⏳ Aguardando {LOOP_INTERVAL}s para o próximo ciclo...\n")
        time.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    main()
