# -*- coding: utf-8 -*-
"""Bybit 10024 → fallback SPOT e modelos Groq atualizados."""

from unittest.mock import MagicMock, patch

import pytest

from src.broker.bybit_client import BybitClient
from src.config.trading_mode import normalize_trading_mode, resolve_trading_mode


def test_normalize_trading_mode_aliases():
    assert normalize_trading_mode('perp') == 'linear'
    assert normalize_trading_mode('spot') == 'spot'
    assert normalize_trading_mode('invalid') == 'linear'


def test_resolve_trading_mode_per_client():
    assert resolve_trading_mode({'trading_mode': 'spot'}) == 'spot'
    with patch.dict('os.environ', {'TRADING_MODE': 'linear'}, clear=False):
        assert resolve_trading_mode({}) == 'linear'


def test_regulatory_error_detection():
    assert BybitClient._is_regulatory_restriction_error('retCode=10024 regulatory restrictions')
    assert not BybitClient._is_regulatory_restriction_error('retCode=10006')


def test_spot_payload_no_position_idx():
    client = object.__new__(BybitClient)
    client.trading_mode = 'spot'
    client._derivatives_restricted = False
    client._normalize_v5_symbol = lambda s: str(s).replace('/', '')
    client._normalize_v5_side = lambda s: 'Buy' if str(s).lower() == 'buy' else 'Sell'

    payload, tp_applied = client._build_v5_market_payload(
        'spot', 'BTC/USDT', 'buy', '0.01', '90000', '80000',
    )
    assert payload['category'] == 'spot'
    assert 'positionIdx' not in payload
    assert 'takeProfit' not in payload
    assert tp_applied is False
    assert payload.get('marketUnit') == 'baseCoin'


def test_linear_payload_has_position_idx():
    client = object.__new__(BybitClient)
    client.trading_mode = 'linear'
    client._derivatives_restricted = False
    client._normalize_v5_symbol = lambda s: str(s).replace('/', '')
    client._normalize_v5_side = lambda s: 'Buy' if str(s).lower() == 'buy' else 'Sell'

    payload, tp_applied = client._build_v5_market_payload(
        'linear', 'BTC/USDT', 'buy', '0.01', '90000', '80000',
    )
    assert payload['category'] == 'linear'
    assert payload['positionIdx'] == 1
    assert tp_applied is True


def test_execute_market_order_retries_spot_on_10024():
    client = object.__new__(BybitClient)
    client.authenticated = True
    client.trading_mode = 'linear'
    client._derivatives_restricted = False
    client.exchange = MagicMock()
    client._normalize_order_qty = MagicMock(return_value='0.01')
    client._format_tpsl_prices = MagicMock(return_value=(None, None))
    client.get_last_price = MagicMock(return_value=100.0)
    client._handle_v5_ret_code = MagicMock(
        side_effect=[
            (False, 'retCode=10024 regulatory restrictions'),
            (True, ''),
        ]
    )
    client.fetch_order_details = MagicMock(return_value={'id': '1', 'price': 100})
    client._normalize_v5_symbol = lambda s: 'BTCUSDT'
    client._normalize_v5_side = lambda s: 'Buy'
    client._enable_spot_fallback = BybitClient._enable_spot_fallback.__get__(client, BybitClient)
    client.get_order_category = BybitClient.get_order_category.__get__(client, BybitClient)
    client.is_spot_trading = BybitClient.is_spot_trading.__get__(client, BybitClient)
    client._build_v5_market_payload = BybitClient._build_v5_market_payload.__get__(client, BybitClient)
    client._is_regulatory_restriction_error = BybitClient._is_regulatory_restriction_error

    session = MagicMock()
    session.place_order.return_value = {'retCode': 0, 'result': {'orderId': 'abc'}}
    client.pybit_session = session

    result = client.execute_market_order('BTC/USDT', 'buy', 0.01)
    assert result is not None
    assert client.trading_mode == 'spot'
    assert session.place_order.call_count == 2
    assert session.place_order.call_args_list[1][1]['category'] == 'spot'


def test_groq_default_models():
    from src.intelligence.groq_client import DEFAULT_GROQ_MODEL, get_groq_model_chain

    with patch.dict('os.environ', {}, clear=False):
        for key in ('GROQ_FLOW_MODEL', 'GROQ_MODEL', 'GROQ_FALLBACK_MODELS'):
            import os
            os.environ.pop(key, None)
        chain = get_groq_model_chain('flow')
    assert chain[0] == 'openai/gpt-oss-120b'
    assert DEFAULT_GROQ_MODEL == 'openai/gpt-oss-120b'
    assert 'openai/gpt-oss-20b' in chain
    assert 'llama3-70b-8192' not in chain
    assert 'llama-3.3-70b-versatile' not in chain


def test_cautious_gate_advisory_never_blocks():
    from src.engine.cautious_entry_gate import cautious_entry_gate
    import pandas as pd

    df = pd.DataFrame({
        'open': [100, 99, 98],
        'high': [101, 100, 99],
        'low': [99, 98, 97],
        'close': [99, 98, 97],
        'volume': [1000, 1000, 1000],
    })
    signals = {'trend': 'BAIXA', 'supertrend_signal': 1, 'rsi': 50, 'atr': 1, 'volume_ratio': 1}
    ok, reasons = cautious_entry_gate('buy', df, signals)
    assert ok is True
    assert any('consultivo' in r.lower() or 'C1' in r for r in reasons)
