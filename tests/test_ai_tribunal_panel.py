"""Testes do Tribunal de IAs (4 cards + assertividade + velas)."""

from __future__ import annotations

import pandas as pd

from src.ai_brain.tribunal_panel import build_ai_tribunal_evidence, build_candle_study
from src.ai_brain.validator import GroqValidator


def _df(n=60):
    rows = []
    price = 100.0
    for i in range(n):
        o = price
        c = price + 0.3
        rows.append({'ts': i, 'open': o, 'high': c + 0.5, 'low': o - 0.4, 'close': c, 'vol': 1000 + i})
        price = c
    return pd.DataFrame(rows)


def test_consensus_returns_four_agents():
    tech = {
        'trend': 'ALTA',
        'supertrend_signal': 1,
        'rsi': 55,
        'volume_ratio': 2.0,
        'fib_distance_pct': 1.0,
        'candle_body_ratio': 70,
        'range_expansion': 1.5,
        'adx': 28,
    }
    res = GroqValidator().consensus_predict(tech, 'BTC/USDT:USDT', intelligence_context={
        'allow_entry': True,
        'intelligence_score': 70,
        'timing_score': 80,
        'whale_aligned': True,
        'summary': 'Fluxo institucional ok',
        'global_trend': 'BULLISH',
    })
    assert 'agents' in res
    ids = [a['id'] for a in res['agents']]
    assert ids == ['gemini', 'groq', 'analyst', 'learner']


def test_tribunal_evidence_has_dialogue_and_candles():
    df = _df()
    consensus = GroqValidator().consensus_predict(
        {
            'trend': 'ALTA',
            'supertrend_signal': 1,
            'rsi': 58,
            'volume_ratio': 2.2,
            'fib_distance_pct': 0.8,
            'candle_body_ratio': 65,
            'range_expansion': 1.4,
            'price': float(df['close'].iloc[-1]),
            'fib_618': 98.0,
            'sma_200': 95.0,
            'adx': 30,
        },
        'ETH/USDT:USDT',
        intelligence_context={'allow_entry': True, 'intelligence_score': 72, 'timing_score': 85, 'summary': 'ok', 'global_trend': 'NEUTRAL'},
    )
    evidence = build_ai_tribunal_evidence(
        symbol='ETH/USDT:USDT',
        side='BUY',
        tech_data={
            'trend': 'ALTA',
            'volume_ratio': 2.2,
            'fib_distance_pct': 0.8,
            'price': float(df['close'].iloc[-1]),
            'fib_618': 98.0,
            'sma_200': 95.0,
            'adx': 30,
            'strong_bullish_candle': True,
        },
        consensus=consensus,
        intelligence_context={'allow_entry': True, 'intelligence_score': 72, 'timing_score': 85, 'global_trend': 'NEUTRAL', 'whale_score': 60},
        df=df,
        learning_stats={'total_trades': 8, 'wins': 5, 'win_rate': 62.5, 'total_pnl': 12.0, 'summary': 'Histórico positivo'},
    )
    assert len(evidence['agents']) == 4
    assert len(evidence['dialogue']) >= 4
    assert evidence['candle_study']['candles']
    assert evidence['assertiveness'] > 0
    assert evidence['side'] == 'COMPRA'


def test_candle_study_notes():
    study = build_candle_study(_df(), {'trend': 'ALTA', 'volume_ratio': 2.5, 'fib_distance_pct': 1.0, 'adx': 25, 'price': 110, 'fib_618': 108, 'sma_200': 100})
    assert any('Volume' in n or 'Clímax' in n for n in study['study_notes'])
