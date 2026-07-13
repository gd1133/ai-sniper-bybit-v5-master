"""Garante que short assertivo não passa com vela de subida."""

from __future__ import annotations

import pandas as pd

from src.engine.chart_structure import assertive_structure_entry


def _df_with_bull_and_bear():
    # Série com LH/LL (baixa) mas última vela forte de alta
    rows = []
    price = 100.0
    for i in range(40):
        o = price
        # tendência de baixa geral
        c = price - 0.4
        rows.append({
            'open': o, 'high': o + 0.2, 'low': c - 0.3, 'close': c, 'vol': 1000 + i,
        })
        price = c
    # última vela forte de SUBIDA (conflito com short)
    rows[-1] = {
        'open': price, 'high': price + 3.0, 'low': price - 0.1,
        'close': price + 2.8, 'vol': 5000,
    }
    return pd.DataFrame(rows)


def test_assertive_short_blocked_by_bullish_candle():
    df = _df_with_bull_and_bear()
    ok, reasons = assertive_structure_entry(
        'sell',
        df,
        {'trend': 'BAIXA', 'money_flow_side': 'WAIT', 'whale_aligned': True, 'volume_ratio': 2.0},
    )
    assert ok is False
    joined = ' '.join(reasons).upper()
    assert 'SUBIDA' in joined or 'DESCIDA' in joined or 'CONFLITA' in joined or 'PIVÔ' in joined or 'ESTRUTURA' in joined
