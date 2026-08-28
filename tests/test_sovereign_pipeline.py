# -*- coding: utf-8 -*-
"""Testes do pipeline soberano C1/C2 consultivo + C3 decisor."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def test_gates_advisory_never_blocks():
    from src.engine.context_enrichment import evaluate_gates_advisory, compute_volume_score

    signals = {
        'adx': 12,
        'is_lateral': True,
        'big_player_ativo': False,
        'volume_ratio': 0.8,
        'sinal_institucional': 'NEUTRO',
    }
    out = evaluate_gates_advisory(signals)
    assert out['allowed'] is True
    assert out['advisory_only'] is True
    assert out['volume_score'] == 'Baixo'
    assert compute_volume_score({'volume_ratio': 2.0, 'big_player_ativo': True}) == 'Institucional'


def test_operational_abort_low_liquidity():
    from src.engine.context_enrichment import check_operational_abort
    import pandas as pd

    df = pd.DataFrame({'close': [1.0] * 60})
    out = check_operational_abort(ticker={'quoteVolume': 1000}, df=df)
    assert out['abort'] is True

    out_ok = check_operational_abort(ticker={'quoteVolume': 5_000_000}, df=df)
    assert out_ok['abort'] is False


def test_cerebro3_local_fallback_range_bounce():
    from src.ai_brain.cerebro3_decisor import decide_entry

    context = {
        'price': 100.0,
        'gates_advisory': {'is_lateral': True, 'volume_score': 'Normal'},
        'cerebro1': {
            'trend': {'macro': 'NEUTRO', 'short': 'NEUTRO'},
            'structure': {'adx': 15, 'is_lateral': True},
            'momentum': {'rsi': 28},
            'levels': {'near_support': True},
            'volatility_volume': {'atr': 1.2},
        },
        'cerebro2': {},
    }
    with patch.dict(os.environ, {'ENABLE_CEREBRO3_LLM': 'false'}):
        dec = decide_entry(context)
    assert dec['action'] == 'BUY'
    assert dec['strategy_type'] == 'RANGE_BOUNCE'
    assert dec['confidence'] >= 0.55


def test_c3_fallback_pengu_oversold():
    """RSI 28 lateral — não deve ficar preso em 35% WAIT."""
    from src.ai_brain.cerebro3_decisor import decide_entry

    context = {
        'price': 0.01,
        'gates_advisory': {'is_lateral': True, 'volume_score': 'Baixo'},
        'cerebro1': {
            'trend': {'macro': 'NEUTRO', 'short': 'NEUTRO', 'supertrend_signal': 0},
            'structure': {'adx': 16, 'is_lateral': True},
            'momentum': {'rsi': 28},
            'levels': {'near_support': False},
            'volatility_volume': {'atr': 0.0002},
        },
        'cerebro2': {},
    }
    with patch.dict(os.environ, {'ENABLE_CEREBRO3_LLM': 'false'}):
        dec = decide_entry(context)
    assert dec['action'] == 'BUY'
    assert dec['probabilidade'] >= 55.0


def test_dump_lane_inverts_buy_to_short():
    from src.ai_brain.cerebro3_decisor import apply_dump_lane_override

    res = {'decisao': 'BUY', 'probabilidade': 45, 'cerebro3_decision': {}}
    signals = {
        'meltdown': True,
        'meltdown_strength': 62,
        'price': 1.0,
        'vwap': 1.02,
        'pivot_high': 1.015,
    }
    out = apply_dump_lane_override(res, signals, 45.0)
    assert out['inverted'] is True
    assert out['side'] == 'sell'
    assert out['prob'] >= 55.0


def test_anti_chase_soft_when_c3_high_confidence():
    from src.engine.anti_chase_gate import evaluate_anti_chase_entry
    import pandas as pd
    import numpy as np

    n = 80
    closes = np.linspace(100, 130, n)
    df = pd.DataFrame({
        'open': closes,
        'high': closes + 1,
        'low': closes - 1,
        'close': closes,
    })
    anti = evaluate_anti_chase_entry(
        side='buy',
        mark_price=130.0,
        df_1m=df,
        df_5m=df,
        signals={'price': 130.0, 'rsi': 72, 'atr_pct': 1.5},
        c3_confidence_pct=58.0,
    )
    assert anti.get('allowed') is True
    assert anti.get('soft_override') is True


def test_sovereign_predict_no_neutro_block():
    from src.ai_brain.validator import GroqValidator

    v = GroqValidator()
    tech = {
        'trend': 'NEUTRO',
        'short_trend': 'ALTA',
        'adx': 18,
        'is_lateral': True,
        'price': 50.0,
        'volume_ratio': 1.1,
        'rsi': 45,
        'pivot_low': 48,
        'pivot_high': 52,
        'near_pivot_support': True,
    }
    with patch.dict(os.environ, {'ADVISORY_GATES': 'true', 'ENABLE_CEREBRO3_LLM': 'false'}):
        res = v.consensus_predict(tech, 'TEST/USDT', intelligence_context={'allow_entry': True})
    assert 'decisao' in res
    assert res.get('brains', {}).get('cerebro3') == 'leader'
