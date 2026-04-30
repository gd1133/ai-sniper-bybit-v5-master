import os
import sys

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


class _FakeCcxt:
    @staticmethod
    def bybit(cfg):
        return _FakeExchange(cfg)


class _FakeHTTP:
    __module__ = 'pybit.unified_trading'

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.endpoint = None


if __name__ == '__main__':
    original_ccxt = bybit_client._ccxt_instance
    original_http = bybit_client._pybit_http_class
    original_env = os.environ.get('USE_TESTNET')

    try:
        bybit_client._ccxt_instance = _FakeCcxt()
        bybit_client._pybit_http_class = _FakeHTTP

        os.environ['USE_TESTNET'] = 'true'
        testnet_client = bybit_client.BybitClient('key', 'secret')
        if testnet_client.active_endpoint != 'https://api-testnet.bybit.com':
            print(f"❌ Endpoint testnet incorreto: {testnet_client.active_endpoint}")
            raise SystemExit(1)
        if any(url != 'https://api-testnet.bybit.com' for url in testnet_client.exchange.urls['api'].values()):
            print(f"❌ URLs CCXT testnet incorretas: {testnet_client.exchange.urls}")
            raise SystemExit(2)
        if testnet_client.exchange.cfg.get('options', {}).get('defaultSubType') != 'linear':
            print(f"❌ defaultSubType deveria ser linear: {testnet_client.exchange.cfg}")
            raise SystemExit(8)
        if not testnet_client.exchange.sandbox_enabled:
            print("❌ Sandbox deveria estar ativo em USE_TESTNET=true")
            raise SystemExit(3)
        if testnet_client.pybit_session.endpoint != 'https://api-testnet.bybit.com':
            print(f"❌ Endpoint pybit testnet incorreto: {testnet_client.pybit_session.endpoint}")
            raise SystemExit(4)
        if testnet_client.pybit_api_version != 'v5' or 'pybit.unified_trading' not in testnet_client.pybit_sdk_module:
            print(f"❌ pybit deveria estar configurado para V5: version={testnet_client.pybit_api_version} module={testnet_client.pybit_sdk_module}")
            raise SystemExit(9)

        prod_client = bybit_client.BybitClient('key', 'secret', testnet=False)
        if prod_client.active_endpoint != 'https://api.bybit.com':
            print(f"❌ Endpoint produção incorreto: {prod_client.active_endpoint}")
            raise SystemExit(5)
        if any(url != 'https://api.bybit.com' for url in prod_client.exchange.urls['api'].values()):
            print(f"❌ URLs CCXT produção incorretas: {prod_client.exchange.urls}")
            raise SystemExit(6)
        if prod_client.pybit_session.endpoint != 'https://api.bybit.com':
            print(f"❌ Endpoint pybit produção incorreto: {prod_client.pybit_session.endpoint}")
            raise SystemExit(7)

        print('✅ Endpoint Bybit segue USE_TESTNET sem redundância')
        raise SystemExit(0)
    finally:
        bybit_client._ccxt_instance = original_ccxt
        bybit_client._pybit_http_class = original_http
        if original_env is None:
            os.environ.pop('USE_TESTNET', None)
        else:
            os.environ['USE_TESTNET'] = original_env
