# -*- coding: utf-8 -*-
"""Spot cash TP/SL ×2/×0.5 + sizing 5% + payload spot."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.risk.position_sizing import (
    calculate_spot_cash_tp_sl,
    calculate_tp_sl_prices,
    calcular_tamanho_posicao,
    evaluate_spot_cash_price_exit,
)
from src.broker.bybit_client import BybitClient


def test_sizing_5pct_cash_1x():
    # Banca 1000 → MI=50 → nocional=50 → qty=50/50000=0.001
    s = calcular_tamanho_posicao(1000.0, 1.0, 50000.0, pct_banca=0.05)
    assert abs(s['margem_inicial'] - 50.0) < 1e-6
    assert abs(s['valor_posicao_usdt'] - 50.0) < 1e-6
    assert abs(s['quantidade'] - 0.001) < 1e-9


def test_sizing_3pct_after_stop():
    s = calcular_tamanho_posicao(1000.0, 1.0, 50000.0, pct_banca=0.03)
    assert abs(s['margem_inicial'] - 30.0) < 1e-6


def test_spot_cash_long_tp_sl_times_2_and_half():
    dyn = calculate_spot_cash_tp_sl(100.0, 'buy')
    assert abs(dyn['tp_price'] - 200.0) < 1e-9
    assert abs(dyn['sl_price'] - 50.0) < 1e-9
    assert '×2' in dyn['rule']


def test_spot_cash_short_tp_sl():
    dyn = calculate_spot_cash_tp_sl(100.0, 'sell')
    assert abs(dyn['tp_price'] - 50.0) < 1e-9
    assert abs(dyn['sl_price'] - 200.0) < 1e-9


def test_spot_cash_price_exit_long():
    motivo, pnl = evaluate_spot_cash_price_exit(200.0, 100.0, 'buy')
    assert motivo == 'TAKE_PROFIT'
    assert abs(pnl - 100.0) < 1e-6
    motivo, pnl = evaluate_spot_cash_price_exit(50.0, 100.0, 'buy')
    assert motivo == 'STOP_LOSS'
    assert abs(pnl - (-50.0)) < 1e-6
    assert evaluate_spot_cash_price_exit(100.0, 100.0, 'buy')[0] is None


def test_spot_cash_price_exit_short():
    assert evaluate_spot_cash_price_exit(50.0, 100.0, 'sell')[0] == 'TAKE_PROFIT'
    assert evaluate_spot_cash_price_exit(200.0, 100.0, 'sell')[0] == 'STOP_LOSS'


def test_spot_sell_payload_has_is_leverage_buy_does_not():
    client = BybitClient.__new__(BybitClient)
    sell_payload, _ = client._build_v5_market_payload(
        'spot', 'BTC/USDT', 'sell', '0.001', None, None,
    )
    assert sell_payload['category'] == 'spot'
    assert sell_payload.get('isLeverage') == 1
    assert 'positionIdx' not in sell_payload

    buy_payload, _ = client._build_v5_market_payload(
        'spot', 'BTC/USDT', 'buy', '0.001', None, None,
    )
    assert buy_payload['category'] == 'spot'
    assert 'isLeverage' not in buy_payload
    assert 'tpslMode' not in buy_payload


def test_spot_tpsl_payload_strips_futures_fields_on_entry():
    client = BybitClient.__new__(BybitClient)
    payload, applied = client._build_v5_market_payload(
        'spot', 'ETH/USDT', 'buy', '0.01', '4000', '1000',
    )
    assert applied is False
    assert 'takeProfit' not in payload
    assert 'stopLoss' not in payload


def test_margin_roi_prices_still_work_at_10x():
    tp, sl = calculate_tp_sl_prices(100.0, 'buy', 10.0)
    assert abs(tp - 110.0) < 1e-9
    assert abs(sl - 95.0) < 1e-9
