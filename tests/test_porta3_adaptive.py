# -*- coding: utf-8 -*-
"""Porta 3: σ adaptativo por ADX (modo ASSERTIVO: 1.3 / 1.15 / 1.0)."""

from src.engine import porta3_adaptive as p3


def setup_function():
    p3.set_market_avg_adx(22.0, samples=0)


def test_consolidation_uses_1_3_sigma():
    sigma = p3.set_market_avg_adx(12.0, samples=10)
    assert abs(sigma - 1.3) < 1e-9
    assert abs(p3.resolve_porta3_sigma() - 1.3) < 1e-9
    st = p3.porta3_status()
    assert st['regime'] == 'CONSOLIDACAO'
    assert '1.3' in st['threshold_rule']


def test_moderate_uses_1_15_sigma():
    # ADX 21.31 / 23.69 — caso dos logs Render
    sigma = p3.set_market_avg_adx(21.31, samples=10)
    assert abs(sigma - 1.15) < 1e-9
    assert abs(p3.resolve_porta3_sigma() - 1.15) < 1e-9
    st = p3.porta3_status()
    assert st['regime'] == 'TENDENCIA_MODERADA'


def test_strong_uses_1_0_sigma():
    sigma = p3.set_market_avg_adx(28.0, samples=10)
    assert abs(sigma - 1.0) < 1e-9
    assert abs(p3.resolve_porta3_sigma() - 1.0) < 1e-9
    st = p3.porta3_status()
    assert st['regime'] == 'TENDENCIA_FORTE'


def test_boundaries():
    assert abs(p3.sigma_for_adx(14.99) - 1.3) < 1e-9
    assert abs(p3.sigma_for_adx(15.0) - 1.15) < 1e-9
    assert abs(p3.sigma_for_adx(24.99) - 1.15) < 1e-9
    assert abs(p3.sigma_for_adx(25.0) - 1.0) < 1e-9


def test_resolve_accepts_local_adx():
    p3.set_market_avg_adx(30.0, samples=5)  # mercado forte → 1.0
    # Ativo local em tendência moderada → 1.15
    assert abs(p3.resolve_porta3_sigma(21.31) - 1.15) < 1e-9


def test_update_from_samples_averages():
    sigma = p3.update_market_adx_from_samples([10, 12, 14, 16, 18])
    # média = 14 → consolidação → 1.3
    assert abs(sigma - 1.3) < 1e-9
    assert abs(p3.get_market_avg_adx() - 14.0) < 1e-9


def test_empty_samples_keeps_current():
    p3.set_market_avg_adx(12.0, samples=5)
    sigma = p3.update_market_adx_from_samples([])
    assert abs(sigma - 1.3) < 1e-9
    assert abs(p3.get_market_avg_adx() - 12.0) < 1e-9
