# -*- coding: utf-8 -*-
"""Porta 3: σ adaptativo por ADX médio do mercado (defaults moderados)."""

from src.engine import porta3_adaptive as p3


def setup_function():
    # Reset: ADX 28 (>= chop max 25) → σ tendência 1.25
    p3.set_market_avg_adx(28.0, samples=0)


def test_chop_uses_1_0_sigma():
    sigma = p3.set_market_avg_adx(15.0, samples=10)
    assert abs(sigma - 1.0) < 1e-9
    assert abs(p3.resolve_porta3_sigma() - 1.0) < 1e-9
    st = p3.porta3_status()
    assert st['regime'] == 'CHOP/CONSOLIDACAO'
    assert '1.0' in st['threshold_rule']


def test_trend_uses_1_25_sigma():
    sigma = p3.set_market_avg_adx(28.0, samples=10)
    assert abs(sigma - 1.25) < 1e-9
    assert abs(p3.resolve_porta3_sigma() - 1.25) < 1e-9
    st = p3.porta3_status()
    assert st['regime'] == 'TENDENCIA'


def test_boundary_adx_25_is_trend():
    # Regra: ADX < 25 → chop; ADX >= 25 → tendência
    assert abs(p3.set_market_avg_adx(24.99) - 1.0) < 1e-9
    assert abs(p3.set_market_avg_adx(25.0) - 1.25) < 1e-9


def test_update_from_samples_averages():
    sigma = p3.update_market_adx_from_samples([10, 12, 14, 16, 18])
    # média = 14 → chop → 1.0
    assert abs(sigma - 1.0) < 1e-9
    assert abs(p3.get_market_avg_adx() - 14.0) < 1e-9


def test_empty_samples_keeps_current():
    p3.set_market_avg_adx(12.0, samples=5)
    sigma = p3.update_market_adx_from_samples([])
    assert abs(sigma - 1.0) < 1e-9
    assert abs(p3.get_market_avg_adx() - 12.0) < 1e-9
