# -*- coding: utf-8 -*-
"""Testes: tribunal_debate SQLite + sentinela engolfo."""

import pandas as pd

from src.database.tribunal_debate import (
    ensure_tribunal_debate_table,
    list_tribunal_debates,
    save_tribunal_debate,
)
from src.risk.trend_position_manager import detect_engulfing_reversal, decide_trend_action


def test_save_and_list_tribunal_debate():
    ensure_tribunal_debate_table()
    evidence = {
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'confidence': 72.5,
        'assertiveness': 61.0,
        'strategic_reason': 'Veredito de teste',
        'agents': [
            {'id': 'groq', 'label': 'Groq Tático', 'motivo': 'Timing ok', 'score': 70},
            {'id': 'analyst', 'label': 'Analista de Dados', 'motivo': 'SMC ok', 'score': 75},
            {'id': 'learner', 'label': 'Aprendizado Neural', 'motivo': 'Histórico +', 'score': 60},
            {'id': 'gemini', 'label': 'Gemini Estratégico', 'motivo': 'Macro neutra', 'score': 55},
        ],
        'dialogue': [
            {'speaker': 'consensus', 'label': 'Veredito', 'text': 'Comprar com 72%'},
        ],
    }
    row_id = save_tribunal_debate(evidence, ciclo='test')
    assert row_id
    rows = list_tribunal_debates(5)
    assert rows
    assert rows[0]['symbol'] in ('BTCUSDT', 'BTC/USDT', rows[0]['symbol'])
    assert rows[0].get('groq_parecer') or rows[0].get('agents')


def _df_bearish_engulf():
    # Histórico com volume baixo + engolfo bearish em volume alto
    rows = []
    for i in range(25):
        rows.append({'open': 100, 'high': 100.5, 'low': 99.5, 'close': 100.1, 'vol': 10})
    rows.append({'open': 100.0, 'high': 101.5, 'low': 99.8, 'close': 101.2, 'vol': 12})  # bullish
    rows.append({'open': 101.3, 'high': 101.4, 'low': 98.5, 'close': 98.8, 'vol': 45})   # bearish engulfs
    return pd.DataFrame(rows)


def test_detect_engulfing_reversal_long():
    df = _df_bearish_engulf()
    out = detect_engulfing_reversal(df, df, 'buy')
    assert out['triggered'] is True
    assert out['tipo'] == 'SAIDA_REVERSAO_TENDENCIA'


def test_decide_trend_be_threshold_defaults():
    # ROI 13% deve armar BE
    out = decide_trend_action(
        side='buy',
        roi_pct=13,
        entry_price=100,
        mark_price=100.7,
        breakeven_armed=False,
        trailing_armed=False,
    )
    assert out['action'] == 'ARM_BREAKEVEN'
