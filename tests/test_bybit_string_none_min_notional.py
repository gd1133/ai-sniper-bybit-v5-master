#!/usr/bin/env python3
"""
Test to verify that BybitClient handles string 'none' values in market limits correctly.
This test validates the fix for the decimal.InvalidOperation error when min_notional
returns string 'None' or 'none' (as might happen with some Bybit API responses).
"""
import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.broker import bybit_client


class _FakeExchange:
    """Mock exchange that returns string 'none' for min_notional (simulating problematic Bybit behavior)."""
    def __init__(self, cfg):
        self.cfg = cfg
        self.urls = {
            'api': {
                'public': 'https://api.bybit.com',
                'private': 'https://api.bybit.com',
            }
        }
        self.sandbox_enabled = False
        self.apiKey = cfg.get('apiKey', 'test_key')

    def set_sandbox_mode(self, enabled):
        self.sandbox_enabled = bool(enabled)

    def load_time_difference(self):
        pass

    def fetch_balance(self, params=None):
        return {'total': {'USDT': 25.5}}

    def fetch_ticker(self, symbol, params=None):
        return {'last': 87.05, 'symbol': symbol}  # SOL price from error log

    def load_markets(self):
        pass

    def market(self, symbol):
        """Returns market limits with string 'none' for min_notional (cost.min)."""
        return {
            'limits': {
                'amount': {'min': 0.1},
                'cost': {'min': 'none'}  # This is the problematic string that causes InvalidOperation
            },
            'precision': {
                'amount': 1  # 1 decimal place (0.1 step size)
            }
        }

    def amount_to_precision(self, symbol, amount):
        return f"{float(amount):.8f}"

    def create_order(self, symbol, order_type, side, qty, params=None):
        return {
            'id': 'test-order-123',
            'symbol': symbol,
            'type': order_type,
            'side': side,
            'amount': qty,
            'params': params or {},
        }

    def fetch_order(self, order_id, symbol, params=None):
        """Mock fetch_order to return complete order details."""
        return {
            'id': order_id,
            'symbol': symbol,
            'type': 'market',
            'side': 'buy',
            'price': 87.05,
            'amount': 0.1,
            'cost': 8.705,
            'filled': 0.1,
            'remaining': 0.0,
            'status': 'closed',
            'timestamp': 1234567890000,
            'datetime': '2009-02-13T23:31:30.000Z',
            'info': {
                'orderId': order_id,
                'symbol': symbol.replace('/', '').replace(':USDT', ''),
            }
        }


class _FakeCcxt:
    class BaseError(Exception):
        pass

    @staticmethod
    def bybit(cfg):
        return _FakeExchange(cfg)


class _FakeHTTP:
    __module__ = 'pybit.unified_trading'

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.endpoint = None
        self.place_order_calls = []

    def get_insurance(self, **kwargs):
        return {
            'retCode': 0,
            'retMsg': 'OK',
            'result': {'list': [{'coin': 'USDT'}]},
        }

    def place_order(self, **kwargs):
        self.place_order_calls.append(kwargs)
        return {
            'retCode': 0,
            'retMsg': 'OK',
            'result': {'orderId': 'test-order-id'},
        }


if __name__ == '__main__':
    original_ccxt = bybit_client._ccxt_instance
    original_http = bybit_client._pybit_http_class

    try:
        bybit_client._ccxt_instance = _FakeCcxt()
        bybit_client._pybit_http_class = _FakeHTTP

        print("🧪 Testing BybitClient with STRING 'none' min_notional...")

        client = bybit_client.BybitClient('key', 'secret', testnet=False)

        # Test execute_market_order with a symbol that has string 'none' for min_notional
        # This should NOT raise decimal.InvalidOperation anymore
        print("📤 Attempting to execute market order with string 'none' min_notional...")
        try:
            order = client.execute_market_order('SOL/USDT:USDT', 'buy', 0.1)
            print(f"📥 Order result: {order}")
        except Exception as e:
            print(f"❌ Exception raised: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise SystemExit(4)

        # Verify that the order was created successfully
        if not order or order.get('id') != 'test-order-id':
            print(f"❌ Ordem não foi criada corretamente: {order}")
            raise SystemExit(1)

        print("✅ BybitClient corretamente trata STRING 'none' em min_notional!")
        print("✅ Nenhum erro decimal.InvalidOperation foi gerado!")
        raise SystemExit(0)

    finally:
        bybit_client._ccxt_instance = original_ccxt
        bybit_client._pybit_http_class = original_http
