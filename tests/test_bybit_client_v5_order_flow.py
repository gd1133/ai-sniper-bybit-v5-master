import io
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.broker import bybit_client

TEST_QTY_WITH_HIGH_PRECISION = 2.6649367268590924


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
        self.amount_to_precision_calls = []
        self.apiKey = cfg.get('apiKey', 'test_key')

    def set_sandbox_mode(self, enabled):
        self.sandbox_enabled = bool(enabled)

    def load_time_difference(self):
        pass

    def fetch_balance(self, params=None):
        return {'total': {'USDT': 25.5}}

    def fetch_ticker(self, symbol, params=None):
        return {'last': 50000.0, 'symbol': symbol}

    def load_markets(self):
        pass

    def market(self, symbol):
        return {
            'limits': {
                'amount': {'min': 0.001},
                'cost': {'min': 5.0}
            },
            'precision': {
                'amount': 2
            }
        }

    def amount_to_precision(self, symbol, amount):
        self.amount_to_precision_calls.append((symbol, amount))
        return f"{float(amount):.2f}"

    def create_order(self, symbol, order_type, side, qty, params=None):
        return {
            'id': 'ccxt-fallback',
            'symbol': symbol,
            'type': order_type,
            'side': side,
            'amount': qty,
            'params': params or {},
        }

    def fetch_order(self, order_id, symbol, params=None):
        """Mock fetch_order para retornar detalhes completos da ordem."""
        return {
            'id': order_id,
            'symbol': symbol,
            'type': 'market',
            'side': 'buy',
            'price': 50000.0,
            'amount': 2.67,
            'cost': 133500.0,
            'filled': 2.67,
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

    class InsufficientFunds(BaseError):
        pass

    class InvalidOrder(BaseError):
        pass

    class AuthenticationError(BaseError):
        pass

    class PermissionDenied(BaseError):
        pass

    class ExchangeNotAvailable(BaseError):
        pass

    class NetworkError(BaseError):
        pass

    class RateLimitExceeded(BaseError):
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
        self.set_leverage_calls = []
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

    def set_leverage(self, **kwargs):
        self.set_leverage_calls.append(kwargs)
        return {
            'retCode': 0,
            'retMsg': 'OK',
            'result': {},
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


class _AlreadyConfiguredLeverageHTTP(_FakeHTTP):
    __module__ = 'pybit.unified_trading'

    def set_leverage(self, **kwargs):
        self.set_leverage_calls.append(kwargs)
        raise Exception('leverage not modified')


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

        order = client.execute_market_order('BTC/USDT:USDT', 'buy', TEST_QTY_WITH_HIGH_PRECISION, leverage=20)
        if not order or order.get('id') != 'oid-123' or order.get('route') != 'v5/order/create':
            print(f"❌ Ordem V5 inválida: {order}")
            raise SystemExit(2)

        # Verificar que a ordem tem detalhes completos (não apenas orderId)
        if order.get('price') is None or order.get('amount') is None or order.get('status') is None:
            print(f"❌ Ordem V5 deveria ter detalhes completos após fetch_order: {order}")
            raise SystemExit(11)

        order_call = client.pybit_session.place_order_calls[-1]
        if order_call.get('category') != 'linear' or order_call.get('symbol') != 'BTCUSDT' or order_call.get('side') != 'Buy':
            print(f"❌ Payload V5 incorreto: {order_call}")
            raise SystemExit(3)
        expected_qty = client.exchange.amount_to_precision('BTC/USDT:USDT', TEST_QTY_WITH_HIGH_PRECISION)
        if order_call.get('qty') != expected_qty:
            print(f"❌ Quantidade normalizada incorreta: esperado {expected_qty}, recebido {order_call.get('qty')}")
            raise SystemExit(10)

        leverage_call = client.pybit_session.set_leverage_calls[-1]
        if leverage_call.get('category') != 'linear':
            print(f"❌ Categoria de alavancagem incorreta: {leverage_call}")
            raise SystemExit(12)
        if leverage_call.get('buyLeverage') != '20':
            print(f"❌ buyLeverage incorreto: {leverage_call}")
            raise SystemExit(13)
        if leverage_call.get('sellLeverage') != '20':
            print(f"❌ sellLeverage incorreto: {leverage_call}")
            raise SystemExit(14)
        if leverage_call.get('symbol') != 'BTCUSDT':
            print(f"❌ Payload de alavancagem incorreto: {leverage_call}")
            raise SystemExit(15)

        insurance_call = client.pybit_session.insurance_calls[-1]
        if insurance_call.get('coin') != 'USDT':
            print(f"❌ Consulta insurance incorreta: {insurance_call}")
            raise SystemExit(4)

        bybit_client._pybit_http_class = _AlreadyConfiguredLeverageHTTP
        already_configured_client = bybit_client.BybitClient('key', 'secret', testnet=False)
        repeated_leverage_order = already_configured_client.execute_market_order('BTC/USDT:USDT', 'buy', 0.25, leverage=40)
        if repeated_leverage_order is None:
            print("❌ Ordem deveria continuar quando a Bybit responder que a alavancagem já está configurada")
            raise SystemExit(16)

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

        strict_client = bybit_client.BybitClient('key', 'secret', testnet=False)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            try:
                strict_client.execute_market_order('BTC/USDT:USDT', 'buy', 0.25, raise_on_error=True)
            except RuntimeError as exc:
                raw_error = str(exc)
            else:
                print('❌ raise_on_error=True deveria propagar retCode bruto da Bybit')
                raise SystemExit(7)

        if 'API key is invalid' not in raw_error:
            print(f"❌ Erro bruto inesperado com raise_on_error=True: {raw_error}")
            raise SystemExit(8)

        print('✅ Fluxo V5 de ordem, insurance e retCode 10003 OK')
        raise SystemExit(0)
    finally:
        bybit_client._ccxt_instance = original_ccxt
        bybit_client._pybit_http_class = original_http
