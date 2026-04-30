import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.broker import bybit_client


class _FakeExchange:
    def __init__(self, cfg):
        self.cfg = cfg
        self.urls = {
            'api': {
                'public': 'https://api.bybit.com',
                'private': 'https://api.bybit.com',
            }
        }
        self.sandbox_enabled = False

    def set_sandbox_mode(self, enabled):
        self.sandbox_enabled = bool(enabled)

    def fetch_balance(self, params=None):
        return {'total': {'USDT': 25.5}}

    def create_order(self, symbol, order_type, side, qty, params=None):
        return {
            'id': 'ccxt-fallback',
            'symbol': symbol,
            'type': order_type,
            'side': side,
            'amount': qty,
            'params': params or {},
        }


class _FakeCcxt:
    @staticmethod
    def bybit(cfg):
        return _FakeExchange(cfg)


class _FakeHTTP:
    __module__ = 'pybit.unified_trading'

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.endpoint = None
        self.place_order_calls = []
        self.insurance_calls = []

    def get_insurance(self, **kwargs):
        self.insurance_calls.append(kwargs)
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
            'result': {'orderId': 'oid-123'},
        }


class _AuthFailingHTTP(_FakeHTTP):
    __module__ = 'pybit.unified_trading'

    def place_order(self, **kwargs):
        self.place_order_calls.append(kwargs)
        return {
            'retCode': 10003,
            'retMsg': 'API key is invalid',
            'result': {},
        }


if __name__ == '__main__':
    original_ccxt = bybit_client._ccxt_instance
    original_http = bybit_client._pybit_http_class

    try:
        bybit_client._ccxt_instance = _FakeCcxt()
        bybit_client._pybit_http_class = _FakeHTTP

        client = bybit_client.BybitClient('key', 'secret', testnet=False)
        ok, message = client.test_connection()
        if not ok or 'Fundo de seguros OK' not in message:
            print(f"❌ test_connection deveria validar fundo de seguros: ok={ok} message={message}")
            raise SystemExit(1)

        order = client.execute_market_order('BTC/USDT:USDT', 'buy', 0.25)
        if not order or order.get('id') != 'oid-123' or order.get('route') != 'v5/order/create':
            print(f"❌ Ordem V5 inválida: {order}")
            raise SystemExit(2)

        order_call = client.pybit_session.place_order_calls[-1]
        if order_call.get('category') != 'linear' or order_call.get('symbol') != 'BTCUSDT' or order_call.get('side') != 'Buy':
            print(f"❌ Payload V5 incorreto: {order_call}")
            raise SystemExit(3)

        insurance_call = client.pybit_session.insurance_calls[-1]
        if insurance_call.get('coin') != 'USDT':
            print(f"❌ Consulta insurance incorreta: {insurance_call}")
            raise SystemExit(4)

        bybit_client._pybit_http_class = _AuthFailingHTTP
        auth_client = bybit_client.BybitClient('key', 'secret', testnet=False)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            failed_order = auth_client.execute_market_order('BTC/USDT:USDT', 'buy', 0.25)
        output = stdout.getvalue()

        if failed_order is not None:
            print(f"❌ Ordem com retCode=10003 deveria falhar: {failed_order}")
            raise SystemExit(5)
        if bybit_client.AUTH_10003_ALERT not in output:
            print(f"❌ Alerta de autenticação não foi impresso: {output}")
            raise SystemExit(6)

        print('✅ Fluxo V5 de ordem, insurance e retCode 10003 OK')
        raise SystemExit(0)
    finally:
        bybit_client._ccxt_instance = original_ccxt
        bybit_client._pybit_http_class = original_http
