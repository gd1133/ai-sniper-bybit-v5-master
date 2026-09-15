from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ai_brain.cerebro3_decisor import PositionGuard


def _build_df(closes, volumes):
    rows = []
    prev = float(closes[0])
    for i, close in enumerate(closes):
        close = float(close)
        open_ = prev
        high = max(open_, close) * 1.002
        low = min(open_, close) * 0.998
        rows.append(
            {
                'open': open_,
                'high': high,
                'low': low,
                'close': close,
                'vol': float(volumes[i]),
            }
        )
        prev = close
    return pd.DataFrame(rows)


def test_position_guard_level1_partial_and_breakeven():
    guard = PositionGuard()
    closes = [100 + i * 0.2 for i in range(40)]
    vols = [1000 + i * 8 for i in range(40)]
    df = _build_df(closes, vols)

    out = guard.evaluate_position_cycle(
        side='buy',
        entry_price=100.0,
        mark_price=102.0,
        roi_pct=2.0,
        df_5m=df,
        level1_done=False,
        level2_done=False,
    )

    assert out['action'] == 'PARTIAL_TP'
    assert out['tipo_execucao'] == 'PROFIT_LADDER_N1'
    assert abs(float(out['partial_fraction']) - 0.4) < 1e-9
    assert float(out['sl_price']) > 100.0


def test_position_guard_kill_switch_long():
    guard = PositionGuard()
    closes = [100 + i * 0.4 for i in range(30)] + [99.0, 98.8, 98.4, 98.0, 97.6]
    vols = [1000 for _ in range(30)] + [1800, 1900, 2000, 2200, 2500]
    df = _build_df(closes, vols)

    out = guard.evaluate_position_cycle(
        side='buy',
        entry_price=101.0,
        mark_price=97.8,
        roi_pct=-3.0,
        df_5m=df,
        level1_done=True,
        level2_done=False,
    )

    assert out['action'] == 'EARLY_EXIT'
    assert out['tipo_execucao'] == 'KILL_SWITCH_TECNICO'


def test_position_guard_level3_volume_exhaustion():
    guard = PositionGuard()
    closes = [100 + i * 0.25 for i in range(36)] + [109.0, 109.2, 109.3, 109.35]
    vols = [1200 + i * 10 for i in range(36)] + [2000, 1800, 1500, 1200]
    df = _build_df(closes, vols)

    out = guard.evaluate_position_cycle(
        side='buy',
        entry_price=100.0,
        mark_price=109.4,
        roi_pct=4.2,
        df_5m=df,
        level1_done=True,
        level2_done=True,
    )

    assert out['action'] == 'EARLY_EXIT'
    assert out['tipo_execucao'] == 'PROFIT_LADDER_N3'
