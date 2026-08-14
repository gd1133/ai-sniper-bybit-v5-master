# -*- coding: utf-8 -*-
"""Testes do Analista Pessoal (entrada/saída)."""

from src.ai_brain.personal_analyst import refine_entry, refine_exit


def test_refine_entry_blocks_overbought_long():
    out = refine_entry(
        side='buy',
        probabilidade=70,
        signals={
            'trend': 'ALTA',
            'sinal_institucional': 'COMPRA_INSTITUCIONAL',
            'adx': 30,
            'volume_ratio': 2.0,
            'rsi': 78,
            'price': 100,
            'ema20': 99.5,
            'vwap': 99,
            'fib_distance_pct': 0.5,
        },
    )
    assert out['allowed'] is False
    assert 'RSI' in (out.get('abort_reason') or '')


def test_refine_entry_allows_healthy_long_with_boost():
    out = refine_entry(
        side='buy',
        probabilidade=62,
        signals={
            'trend': 'ALTA',
            'sinal_institucional': 'COMPRA_INSTITUCIONAL',
            'adx': 32,
            'volume_ratio': 2.2,
            'rsi': 52,
            'price': 100.2,
            'ema20': 100.0,
            'vwap': 99.8,
            'fib_distance_pct': 0.4,
            'money_flow_side': 'BUY',
        },
        intelligence_context={'whale_aligned': True, 'order_flow_bias': 'BUY'},
    )
    assert out['allowed'] is True
    assert out['probabilidade'] >= 62


def test_refine_exit_giveback_does_not_cut_healthy_pullback():
    """Recuo 45% → 20% NÃO fecha (precisa pico ≥100% e vela forte)."""
    out = refine_exit(
        side='buy',
        roi_pct=20,
        peak_roi_pct=45,
        trailing_armed=False,
    )
    assert out['suggest_early_exit'] is False
