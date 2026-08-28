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
    assert dec['action'] in ('BUY', 'SELL', 'HOLD')
    assert dec['strategy_type'] == 'RANGE_BOUNCE'
    assert 0 <= dec['confidence'] <= 1.0


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
