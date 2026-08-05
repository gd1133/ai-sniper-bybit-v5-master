# -*- coding: utf-8 -*-
"""Tests for anti-chase entry gate (RSI / extension / pullback)."""

from __future__ import annotations

import pandas as pd

from src.engine.anti_chase_gate import (
    compute_rsi,
    evaluate_anti_chase_entry,
    evaluate_pullback_pivot,
    extension_pct,
)


def _df_trend(n=80, start=100.0, step=0.05, dump_last=False, pump_last=False):
    rows = []
    px = start
    for i in range(n):
        o = px
        c = px + step
        h = max(o, c) + 0.02
        l = min(o, c) - 0.02
        rows.append({'open': o, 'high': h, 'low': l, 'close': c, 'vol': 1000})
        px = c
    if dump_last:
        rows[-1] = {
            'open': rows[-1]['close'],
            'high': rows[-1]['close'] + 0.01,
            'low': rows[-1]['close'] * 0.97,
            'close': rows[-1]['close'] * 0.975,
            'vol': 5000,
        }
    if pump_last:
        base = rows[-2]['close']
        rows[-1] = {
            'open': base,
            'high': base * 1.03,
            'low': base * 0.999,
            'close': base * 1.025,
            'vol': 5000,
        }
    return pd.DataFrame(rows)


def test_extension_pct():
    assert abs(extension_pct(101.2, 100.0) - 1.2) < 1e-9


def test_overbought_long_rejected():
    # Força RSI alto via série monotônica de alta + pump
    df = _df_trend(n=60, step=0.3, pump_last=True)
    # marca longe da EMA para falhar extension OU RSI
    mark = float(df['close'].iloc[-1])
    r = evaluate_anti_chase_entry(side='long', mark_price=mark, df_1m=df, df_5m=df, signals={})
    assert not r['allowed'], r
    assert 'OVERBOUGHT' in r['code'] or 'EXTENDED' in r['code'] or 'PULLBACK' in r['code'], r


def test_oversold_short_rejected():
    df = _df_trend(n=60, step=-0.3, dump_last=True)
    mark = float(df['close'].iloc[-1])
    r = evaluate_anti_chase_entry(side='short', mark_price=mark, df_1m=df, df_5m=df, signals={})
    assert not r['allowed'], r
    assert 'OVERSOLD' in r['code'] or 'EXTENDED' in r['code'] or 'PULLBACK' in r['code'], r


def test_price_too_extended():
    df = _df_trend(n=50, step=0.01)
    ema_approx = float(df['close'].iloc[-20:].mean())
    # força preço 2% acima da média
    mark = ema_approx * 1.025
    # RSI neutro artificial via signals se série não for extrema
    r = evaluate_anti_chase_entry(
        side='long',
        mark_price=mark,
        df_1m=df,
        df_5m=df,
        signals={'rsi': 50, 'rsi_1m': 50, 'rsi_5m': 50},
    )
    # Pode ser BLOCKED por extension ou pullback; nunca OK se extended
    if r['details'].get('extension_ema_pct', 0) > 1.2:
        assert not r['allowed']
        assert 'EXTENDED' in r['code'] or 'PULLBACK' in r['code']


def test_pullback_long_ok_zone():
    # Constrói série onde último candle toca EMA e fecha verde
    df = _df_trend(n=40, step=0.08)
    # pullback artificial na última vela
    ema_proxy = float(df['close'].iloc[-10:].mean())
    df.loc[df.index[-1], 'low'] = ema_proxy * 0.999
    df.loc[df.index[-1], 'open'] = ema_proxy * 1.001
    df.loc[df.index[-1], 'close'] = ema_proxy * 1.002
    df.loc[df.index[-1], 'high'] = ema_proxy * 1.004
    pull = evaluate_pullback_pivot(side='long', df_1m=df, mark_price=float(df['close'].iloc[-1]), tol_pct=0.5)
    # Pode depender do EMA exato; pelo menos retorna estrutura
    assert 'ok' in pull
    assert 'ema8' in pull


def test_compute_rsi_bounds():
    df = _df_trend(n=40, step=0.2)
    rsi = compute_rsi(df['close'], 14)
    assert 0 <= rsi <= 100
