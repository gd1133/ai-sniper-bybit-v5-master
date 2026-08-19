# -*- coding: utf-8 -*-
"""
Fibonacci Exponencial — swings via EMA de máximas/mínimas (não high/low crus).

Retração 0.618 para zona de entrada.
Extensões alternadas 100% e 161.8% para TP parcial e TP total.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def exponential_fib_levels(df: pd.DataFrame, lookback: int = 20, ema_span: int = 8) -> dict[str, Any]:
    """
    Swing exponencial das últimas ``lookback`` barras.

    LONG (impulso de alta): alvos acima do swing high.
    SHORT (impulso de baixa): alvos abaixo do swing low.
    """
    empty = {
        'exp_high': 0.0,
        'exp_low': 0.0,
        'exp_range': 0.0,
        'fib_exp_382': 0.0,
        'fib_exp_500': 0.0,
        'fib_exp_618': 0.0,
        'fib_ext_100_up': 0.0,
        'fib_ext_1618_up': 0.0,
        'fib_ext_100_down': 0.0,
        'fib_ext_1618_down': 0.0,
        'fib_depth': 0.0,
        'fib_618': 0.0,
    }
    if df is None or len(df) < 8 or 'high' not in df.columns:
        return empty

    n = min(int(lookback), len(df))
    work = df.tail(max(n, ema_span + 2)).copy()
    ema_h = work['high'].astype(float).ewm(span=int(ema_span), adjust=False).mean()
    ema_l = work['low'].astype(float).ewm(span=int(ema_span), adjust=False).mean()
    exp_high = _f(ema_h.tail(n).max())
    exp_low = _f(ema_l.tail(n).min())
    rng = max(exp_high - exp_low, 0.0)
    close = _f(work['close'].iloc[-1])
    if rng <= 0:
        return empty

    depth = max(0.0, min(1.0, (exp_high - close) / rng))
    fib_618 = exp_high - rng * 0.618
    return {
        'exp_high': exp_high,
        'exp_low': exp_low,
        'exp_range': rng,
        'fib_exp_382': exp_high - rng * 0.382,
        'fib_exp_500': exp_high - rng * 0.500,
        'fib_exp_618': fib_618,
        'fib_618': fib_618,
        'fib_ext_100_up': exp_high,
        'fib_ext_1618_up': exp_low + rng * 1.618,
        'fib_ext_100_down': exp_low,
        'fib_ext_1618_down': exp_high - rng * 1.618,
        'fib_depth': depth,
    }


def fib_targets_for_side(levels: dict, side: str) -> dict[str, float]:
    """TP1 = extensão 100%, TP2 = 161.8% no sentido da posição."""
    is_long = str(side or '').strip().lower() in ('buy', 'long', 'comprar')
    if is_long:
        return {
            'tp1': _f(levels.get('fib_ext_100_up')),
            'tp2': _f(levels.get('fib_ext_1618_up')),
        }
    return {
        'tp1': _f(levels.get('fib_ext_100_down')),
        'tp2': _f(levels.get('fib_ext_1618_down')),
    }


def fib_distance_pct(price: float, fib_618: float) -> float:
    price = _f(price)
    fib_618 = _f(fib_618)
    if price <= 0:
        return 999.0
    return abs(price - fib_618) / price * 100.0
