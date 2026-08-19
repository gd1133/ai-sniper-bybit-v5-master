# -*- coding: utf-8 -*-
"""
Turtle Traders (Richard Dennis) — Donchian HH/LL 20 e 55.

Entrada: rompimento do Highest High / Lowest Low.
Saída de tendência: trail no LL de 20 períodos (long) ou HH de 10 (short).
Risco inicial: 2 × ATR(20) — aplicado em position_sizing.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def donchian_channels(df: pd.DataFrame, period: int) -> dict[str, float]:
    """HH / LL do período (vela atual incluída)."""
    empty = {'hh': 0.0, 'll': 0.0, 'period': int(period)}
    if df is None or len(df) < 2 or 'high' not in df.columns:
        return empty
    n = max(2, int(period))
    window = df.tail(n)
    return {
        'hh': _f(window['high'].max()),
        'll': _f(window['low'].min()),
        'period': n,
    }


def prior_donchian(df: pd.DataFrame, period: int) -> dict[str, float]:
    """HH / LL das N velas *anteriores* (exclui a barra atual — breakout clássico)."""
    empty = {'hh': 0.0, 'll': 0.0, 'period': int(period)}
    if df is None or len(df) < period + 1:
        return empty
    work = df.iloc[:-1].tail(int(period))
    return {
        'hh': _f(work['high'].max()),
        'll': _f(work['low'].min()),
        'period': int(period),
    }


def detect_turtle_breakout(df: pd.DataFrame) -> dict[str, Any]:
    """
    Sistema 1 (N=20) e Sistema 2 (N=55).
    BUY se close > HH anterior; SELL se close < LL anterior.
    """
    out = {
        'turtle_breakout': 'NONE',
        'turtle_period': 0,
        'hh_20': 0.0,
        'll_20': 0.0,
        'hh_55': 0.0,
        'll_55': 0.0,
        'reason': '',
    }
    if df is None or len(df) < 22:
        out['reason'] = 'histórico insuficiente para Turtle'
        return out

    last = df.iloc[-1]
    close = _f(last.get('close') if hasattr(last, 'get') else last['close'])
    d20 = prior_donchian(df, 20)
    d55 = prior_donchian(df, 55) if len(df) >= 56 else {'hh': 0.0, 'll': 0.0}
    out['hh_20'] = d20['hh']
    out['ll_20'] = d20['ll']
    out['hh_55'] = _f(d55.get('hh'))
    out['ll_55'] = _f(d55.get('ll'))

    if d20['hh'] > 0 and close > d20['hh']:
        out['turtle_breakout'] = 'BUY'
        out['turtle_period'] = 55 if (out['hh_55'] > 0 and close > out['hh_55']) else 20
        out['reason'] = (
            f'Turtle rompimento de ALTA close={close:.6g} > HH{out["turtle_period"]}='
            f'{out["hh_55"] if out["turtle_period"] == 55 else d20["hh"]:.6g}'
        )
        return out
    if d20['ll'] > 0 and close < d20['ll']:
        out['turtle_breakout'] = 'SELL'
        out['turtle_period'] = 55 if (out['ll_55'] > 0 and close < out['ll_55']) else 20
        out['reason'] = (
            f'Turtle rompimento de BAIXA close={close:.6g} < LL{out["turtle_period"]}='
            f'{out["ll_55"] if out["turtle_period"] == 55 else d20["ll"]:.6g}'
        )
        return out

    out['reason'] = 'sem rompimento Donchian 20/55'
    return out


def turtle_exit_stop(df: pd.DataFrame, side: str) -> dict[str, Any]:
    """
    Trailing Turtle (Dennis):
      LONG  → Lowest Low de 20 períodos (mais folga após o lucro correr)
      SHORT → Highest High de 10 períodos (saída no rompimento contrário)

    Não fecha a mercado aqui — devolve o preço de SL para a Bybit.
    """
    is_long = str(side or '').strip().lower() in ('buy', 'long', 'comprar')
    period = 20 if is_long else 10
    ch = donchian_channels(df, period)
    sl = ch['ll'] if is_long else ch['hh']
    return {
        'sl_price': sl,
        'period': period,
        'rule': f"{'LL' if is_long else 'HH'}{period} Turtle trail",
        'hh': ch['hh'],
        'll': ch['ll'],
    }
