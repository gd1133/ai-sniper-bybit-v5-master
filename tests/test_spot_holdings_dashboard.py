# -*- coding: utf-8 -*-
"""Spot holdings da Unified viram trades ativos no dashboard (não get_positions linear)."""

from unittest.mock import MagicMock

from src.broker.bybit_client import BybitClient


def test_fetch_spot_holdings_maps_eth_and_ignores_usdt_dust():
    client = object.__new__(BybitClient)
    client.trading_mode = 'spot'
    client._derivatives_restricted = False
    client.pybit_session = MagicMock()
    client.pybit_session.get_wallet_balance.return_value = {
        'retCode': 0,
        'result': {
            'list': [{
                'coin': [
                    {'coin': 'USDT', 'walletBalance': '3.69', 'usdValue': '3.69'},
                    {
                        'coin': 'ETH',
                        'walletBalance': '0.00999',
                        'availableToWithdraw': '0.00999',
                        'usdValue': '35.00',
                    },
                    {'coin': 'DOGE', 'walletBalance': '1', 'usdValue': '0.12'},
                ]
            }]
        },
    }
    client._handle_v5_ret_code = MagicMock(return_value=(True, ''))
    client.get_last_price = MagicMock(return_value=3503.5)
    client.get_order_category = lambda: 'spot'
    client.is_spot_trading = lambda: True

    holdings = client.fetch_spot_holdings(min_notional=5.0)
    coins = {h['coin'] for h in holdings}
    assert 'ETH' in coins
    assert 'USDT' not in coins
    assert 'DOGE' not in coins
    eth = next(h for h in holdings if h['coin'] == 'ETH')
    assert eth['symbol'] == 'ETH/USDT'
    assert abs(eth['size'] - 0.00999) < 1e-9
    assert eth['side'] == 'COMPRAR'
    assert eth['category'] == 'spot'


def test_spot_base_coin_normalizes_pair():
    assert BybitClient._spot_base_coin('ETH/USDT') == 'ETH'
    assert BybitClient._spot_base_coin('ETH/USDT:USDT') == 'ETH'
    assert BybitClient._spot_base_coin('ETHUSDT') == 'ETH'
