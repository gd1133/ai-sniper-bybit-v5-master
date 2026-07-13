"""
SMC estrutural — Order Blocks, zonas Premium/Discount e Liquidity Sweeps.

Camada incremental do Triplo Cérebro (Cérebro 1). Não substitui Fibonacci/SuperTrend;
fornece o Filtro Estrutural Macro da Confluência Absoluta.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _swing_range(df: pd.DataFrame, lookback: int = 40) -> tuple[float, float, float]:
    window = df.iloc[-lookback:] if len(df) >= lookback else df
    swing_high = float(window['high'].max())
    swing_low = float(window['low'].min())
    mid = swing_low + (swing_high - swing_low) * 0.5
    return swing_high, swing_low, mid


def _atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


def detect_liquidity_sweep(df: pd.DataFrame, lookback: int = 20) -> dict[str, Any]:
    """
    Pavio longo que captura stops além de máximo/mínimo recente e fecha de volta.
    """
    if df is None or len(df) < lookback + 2:
        return {'bullish_sweep': False, 'bearish_sweep': False, 'reason': 'dados insuficientes'}

    prior = df.iloc[-(lookback + 1):-1]
    last = df.iloc[-1]
    prior_high = float(prior['high'].max())
    prior_low = float(prior['low'].min())
    candle_range = max(float(last['high'] - last['low']), 1e-9)
    upper_wick = float(last['high'] - max(last['open'], last['close']))
    lower_wick = float(min(last['open'], last['close']) - last['low'])

    bullish_sweep = (
        float(last['low']) < prior_low
        and float(last['close']) > prior_low
        and (lower_wick / candle_range) >= 0.45
    )
    bearish_sweep = (
        float(last['high']) > prior_high
        and float(last['close']) < prior_high
        and (upper_wick / candle_range) >= 0.45
    )
    reason = []
    if bullish_sweep:
        reason.append('Liquidity Sweep de baixa (stops comprados) — pavio inferior longo')
    if bearish_sweep:
        reason.append('Liquidity Sweep de alta (stops vendidos) — pavio superior longo')
    return {
        'bullish_sweep': bullish_sweep,
        'bearish_sweep': bearish_sweep,
        'reason': ' | '.join(reason) if reason else 'sem sweep recente',
    }


def detect_order_blocks(df: pd.DataFrame, lookback: int = 60) -> dict[str, Any]:
    """
    Proxies institucionais de Order Block:
    - Bullish OB: última vela de venda antes de impulso de alta (≥ 1.5× ATR)
    - Bearish OB: última vela de compra antes de impulso de baixa
    """
    empty = {
        'bullish_ob': None,
        'bearish_ob': None,
        'in_bullish_ob': False,
        'in_bearish_ob': False,
        'zone': 'EQUILIBRIO',
        'in_discount': False,
        'in_premium': False,
    }
    if df is None or len(df) < 30:
        return empty

    work = df.iloc[-lookback:].copy().reset_index(drop=True)
    atr = _atr_series(work)
    price = float(work['close'].iloc[-1])
    swing_high, swing_low, mid = _swing_range(work, lookback=min(40, len(work)))
    in_discount = price <= mid
    in_premium = price >= mid
    zone = 'DISCOUNT' if in_discount and not in_premium else (
        'PREMIUM' if in_premium and not in_discount else 'EQUILIBRIO'
    )

    bullish_ob = None
    bearish_ob = None

    for i in range(2, len(work) - 1):
        body = float(work['close'].iloc[i] - work['open'].iloc[i])
        atr_i = float(atr.iloc[i] or 0) or 1e-9
        # Impulso de alta: corpo bullish forte
        if body >= 1.5 * atr_i:
            # OB = última vela bearish imediatamente antes do impulso
            for j in range(i - 1, max(-1, i - 4), -1):
                if float(work['close'].iloc[j]) < float(work['open'].iloc[j]):
                    low_j = float(work['low'].iloc[j])
                    high_j = float(work['high'].iloc[j])
                    bullish_ob = {'low': low_j, 'high': high_j, 'index': j}
                    break
        # Impulso de baixa
        if body <= -1.5 * atr_i:
            for j in range(i - 1, max(-1, i - 4), -1):
                if float(work['close'].iloc[j]) > float(work['open'].iloc[j]):
                    low_j = float(work['low'].iloc[j])
                    high_j = float(work['high'].iloc[j])
                    bearish_ob = {'low': low_j, 'high': high_j, 'index': j}
                    break

    in_bullish_ob = bool(
        bullish_ob and bullish_ob['low'] <= price <= bullish_ob['high'] * 1.002
    )
    in_bearish_ob = bool(
        bearish_ob and bearish_ob['low'] * 0.998 <= price <= bearish_ob['high']
    )

    # Fallback estrutural: zona de desconto/premium próxima ao swing (Triplo Cérebro SMC)
    if bullish_ob is None and in_discount:
        near_discount_base = abs(price - swing_low) / max(price, 1e-9) * 100 <= 3.0
        if near_discount_base:
            bullish_ob = {'low': swing_low, 'high': mid, 'index': -1, 'proxy': True}
            in_bullish_ob = True
    if bearish_ob is None and in_premium:
        near_premium_top = abs(price - swing_high) / max(price, 1e-9) * 100 <= 3.0
        if near_premium_top:
            bearish_ob = {'low': mid, 'high': swing_high, 'index': -1, 'proxy': True}
            in_bearish_ob = True

    return {
        'bullish_ob': bullish_ob,
        'bearish_ob': bearish_ob,
        'in_bullish_ob': in_bullish_ob,
        'in_bearish_ob': in_bearish_ob,
        'zone': zone,
        'in_discount': in_discount,
        'in_premium': in_premium,
        'swing_high': swing_high,
        'swing_low': swing_low,
        'equilibrium': mid,
        'price': price,
    }


def macro_trend_aligned(df_macro: pd.DataFrame | None, side: str, signals: dict | None = None) -> dict[str, Any]:
    """
    Alinha tendência macro (H1/H4 se disponível; senão SMA200 do timeframe ativo).
    """
    side_u = str(side or '').upper()
    is_long = side_u in ('BUY', 'COMPRAR', 'LONG')
    signals = signals or {}

    if df_macro is not None and len(df_macro) >= 50:
        close = df_macro['close']
        sma = close.rolling(window=min(200, len(close)), min_periods=20).mean()
        price = float(close.iloc[-1])
        sma_v = float(sma.iloc[-1])
        macro = 'ALTA' if price > sma_v * 1.005 else ('BAIXA' if price < sma_v * 0.995 else 'NEUTRO')
        source = 'H1/H4'
    else:
        macro = str(signals.get('trend', 'NEUTRO')).upper()
        source = 'SMA200_15m'

    ok = (is_long and macro == 'ALTA') or ((not is_long) and macro == 'BAIXA')
    return {'ok': ok, 'macro_trend': macro, 'source': source}


def filtro_estrutural_smc(
    df: pd.DataFrame,
    side: str,
    signals: dict | None = None,
    df_macro: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Filtro 1 — Cérebro 1 SMC:
    Long  → Bullish OB em Discount + macro ALTA
    Short → Bearish OB em Premium + macro BAIXA
    """
    side_u = str(side or '').upper()
    is_long = side_u in ('BUY', 'COMPRAR', 'LONG')
    structure = detect_order_blocks(df)
    macro = macro_trend_aligned(df_macro, side, signals)

    # Fib golden zone reforça o OB (Triplo Cérebro intacto)
    fib_ok = True
    if signals:
        fib_dist = float(signals.get('fib_distance_pct', 99) or 99)
        # tolerante: OB já é o principal; fib ≤ 5% ajuda mas não substitui
        if fib_dist <= 5.0:
            structure = {**structure, 'fib_support': True}
        else:
            structure = {**structure, 'fib_support': False}

    if is_long:
        ok = bool(structure['in_bullish_ob'] and structure['in_discount'] and macro['ok'])
        detail = (
            f"OB bullish={structure['in_bullish_ob']} discount={structure['in_discount']} "
            f"macro={macro['macro_trend']}({macro['source']})"
        )
    else:
        ok = bool(structure['in_bearish_ob'] and structure['in_premium'] and macro['ok'])
        detail = (
            f"OB bearish={structure['in_bearish_ob']} premium={structure['in_premium']} "
            f"macro={macro['macro_trend']}({macro['source']})"
        )

    return {
        'ok': ok,
        'detail': detail,
        'structure': structure,
        'macro': macro,
        'fib_ok': fib_ok,
    }
