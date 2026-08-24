# -*- coding: utf-8 -*-
"""Dump / queda livre + volume — entrada SHORT assertiva."""

import pandas as pd

from src.engine.asymmetric_sniper import detect_meltdown, evaluate_asymmetric_entry


def _dump_df(n=30, drop_steps=3, vol_last=300.0):
    rows = []
    px = 100.0
    for i in range(n - drop_steps):
        rows.append({
            'open': px, 'high': px + 0.2, 'low': px - 0.2, 'close': px + 0.05, 'vol': 80.0,
        })
        px += 0.05
    # Queda livre com volume
    for i in range(drop_steps):
        o = px
        c = px * (1 - 0.012)
        rows.append({
            'open': o, 'high': o + 0.05, 'low': c - 0.1, 'close': c,
            'vol': vol_last if i == drop_steps - 1 else 200.0,
        })
        px = c
    return pd.DataFrame(rows)


def test_freefall_with_volume_prefers_short():
    df = _dump_df(drop_steps=3, vol_last=400.0)
    melt = detect_meltdown(df, {'volume_ratio': 3.5, 'trend': 'BAIXA', 'supertrend_signal': -1})
    assert melt['meltdown'] is True
    assert melt['prefer_short'] is True
    assert melt['volume_on_dump'] is True
    assert melt['freefall'] is True or melt['second_red_entry'] is True or melt['strength'] > 40


def test_asymmetric_short_allows_meltdown():
    df = _dump_df(drop_steps=3, vol_last=400.0)
    signals = {
        'volume_ratio': 3.2,
        'trend': 'BAIXA',
        'supertrend_signal': -1,
        'strong_bearish_candle': True,
    }
    asym = evaluate_asymmetric_entry('sell', df, signals, intel_ctx={})
    assert asym['allowed'] is True
    assert asym['score_boost'] >= 18
