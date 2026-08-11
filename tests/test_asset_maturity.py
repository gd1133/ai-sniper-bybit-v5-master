# -*- coding: utf-8 -*-
"""Maturidade: modo MODERADO exige 14 velas diárias (não 30)."""

from unittest.mock import MagicMock

from src.engine.asset_maturity import (
    MIN_DAILY_CANDLES,
    check_asset_maturity,
    min_dias_historico,
    verificar_idade_moeda,
)


def test_default_min_days_is_14():
    assert MIN_DAILY_CANDLES == 14
    assert min_dias_historico == 14


def test_snxx_29_days_allowed():
    broker = MagicMock()
    broker.count_daily_candles.return_value = 29
    out = check_asset_maturity(broker, 'SNXX/USDT')
    assert out['allowed'] is True
    assert out['candle_count'] == 29


def test_grvt_12_days_still_blocked():
    broker = MagicMock()
    broker.count_daily_candles.return_value = 12
    out = verificar_idade_moeda(broker, 'GRVT/USDT')
    assert out['allowed'] is False
    assert out['candle_count'] == 12
    assert '14' in out['reason']


def test_exactly_14_days_allowed():
    broker = MagicMock()
    broker.count_daily_candles.return_value = 14
    out = check_asset_maturity(broker, 'FOO/USDT')
    assert out['allowed'] is True
