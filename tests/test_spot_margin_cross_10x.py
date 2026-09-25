# -*- coding: utf-8 -*-
"""Spot Margin Cross 10x — sizing, TP/SL preços e payload isLeverage."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.risk.position_sizing import (
    calculate_fixed_roi_tp_sl,
    calculate_tp_sl_prices,
    calcular_tamanho_posicao,
    evaluate_price_level_exit,
)
from src.broker.bybit_client import BybitClient


def test_sizing_5pct_times_10x():
    # Banca 1000 → MI=50 → nocional=500 → qty=500/50000=0.01
    s = calcular_tamanho_posicao(1000.0, 10.0, 50000.0, pct_banca=0.05)
    assert abs(s['margem_inicial'] - 50.0) < 1e-6
    assert abs(s['valor_posicao_usdt'] - 500.0) < 1e-6
    assert abs(s['quantidade'] - 0.01) < 1e-9


def test_sizing_3pct_after_stop():
    s = calcular_tamanho_posicao(1000.0, 10.0, 50000.0, pct_banca=0.03)
    assert abs(s['margem_inicial'] - 30.0) < 1e-6
    assert abs(s['valor_posicao_usdt'] - 300.0) < 1e-6


def test_long_tp_sl_prices_at_10x():
    tp, sl = calculate_tp_sl_prices(100.0, 'buy', 10.0)
    assert abs(tp - 110.0) < 1e-9  # +10%
    assert abs(sl - 95.0) < 1e-9   # -5%


def test_short_tp_sl_prices_at_10x():
    tp, sl = calculate_tp_sl_prices(100.0, 'sell', 10.0)
    assert abs(tp - 90.0) < 1e-9   # -10%
    assert abs(sl - 105.0) < 1e-9  # +5%


def test_fixed_roi_helper():
    dyn = calculate_fixed_roi_tp_sl(100.0, 'buy', 10.0)
    assert abs(dyn['tp_price'] - 110.0) < 1e-9
    assert abs(dyn['sl_price'] - 95.0) < 1e-9
    assert '10x' in dyn['rule']


def test_price_level_exit_long_tp_sl():
    motivo, _ = evaluate_price_level_exit(110.0, 100.0, 'buy', 10.0)
    assert motivo == 'TAKE_PROFIT'
    motivo, _ = evaluate_price_level_exit(95.0, 100.0, 'buy', 10.0)
    assert motivo == 'STOP_LOSS'
    motivo, _ = evaluate_price_level_exit(100.0, 100.0, 'buy', 10.0)
    assert motivo is None


def test_price_level_exit_short():
    motivo, _ = evaluate_price_level_exit(90.0, 100.0, 'sell', 10.0)
    assert motivo == 'TAKE_PROFIT'
    motivo, _ = evaluate_price_level_exit(105.0, 100.0, 'sell', 10.0)
    assert motivo == 'STOP_LOSS'


def test_spot_payload_has_is_leverage_no_futures_params():
    client = BybitClient.__new__(BybitClient)
    payload, tp_sl = client._build_v5_market_payload(
        'spot', 'BTC/USDT', 'sell', '0.001', '90000', '95000',
    )
    assert payload['category'] == 'spot'
    assert payload.get('isLeverage') == 1
    assert 'positionIdx' not in payload
    assert 'tpslMode' not in payload
    assert 'takeProfit' not in payload
    assert 'stopLoss' not in payload
    assert tp_sl is False
    assert payload['symbol'] == 'BTCUSDT'
    assert payload['side'] == 'Sell'


def test_linear_payload_keeps_position_idx():
    client = BybitClient.__new__(BybitClient)
    payload, tp_sl = client._build_v5_market_payload(
        'linear', 'BTC/USDT:USDT', 'buy', '0.001', '110000', '95000',
    )
    assert payload['category'] == 'linear'
    assert payload.get('positionIdx') == 1
    assert payload.get('tpslMode') == 'Full'
    assert 'isLeverage' not in payload
