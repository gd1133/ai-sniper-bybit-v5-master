# -*- coding: utf-8 -*-
from src.broker.tpsl_format import format_price_tick, tick_size_from_market, validate_tp_sl_vs_entry
from src.risk.position_sizing import attach_exchange_tp, calculate_tp_sl_prices


def test_format_price_tick_no_scientific():
    s = format_price_tick(0.00012345, 0.00000001)
    assert 'e' not in s.lower()
    assert s.startswith('0.000123')


def test_tick_from_bybit_price_filter():
    market = {'info': {'priceFilter': {'tickSize': '0.01'}}}
    assert float(tick_size_from_market(market)) == 0.01


def test_long_tp_strictly_above_entry():
    tp, sl, notes = validate_tp_sl_vs_entry('buy', 100.0, 100.0, 97.5, tick_size=0.1)
    assert tp is not None and float(tp) > 100.0
    assert sl is not None and float(sl) < 100.0


def test_short_tp_strictly_below_entry():
    tp, sl, notes = validate_tp_sl_vs_entry('sell', 100.0, 100.0, 102.5, tick_size=0.1)
    assert tp is not None and float(tp) < 100.0
    assert sl is not None and float(sl) > 100.0


def test_calculate_tp_sl_direction_20x():
    tp, sl = calculate_tp_sl_prices(100.0, 'buy', 20)
    assert abs(tp - 105.0) < 1e-9
    assert abs(sl - 97.5) < 1e-9
    tp_s, sl_s = calculate_tp_sl_prices(100.0, 'sell', 20)
    assert abs(tp_s - 95.0) < 1e-9
    assert abs(sl_s - 102.5) < 1e-9


def test_attach_exchange_tp_default_on(monkeypatch):
    monkeypatch.delenv('ATTACH_EXCHANGE_TP', raising=False)
    assert attach_exchange_tp() is True
