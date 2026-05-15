import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.broker import binance_client


class _FakeExchange:
    def __init__(self, cfg):
        self.cfg = cfg
        self.urls = cfg.get('urls', {
            'api': {
                'public': 'https://api.binance.com',
                'private': 'https://api.binance.com',
            },
            'fapi': {
                'public': 'https://fapi.binance.com',
                'private': 'https://fapi.binance.com',
            },
        })
        self.options = dict(cfg.get('options', {}))
        self.public_hosts_tried = []
        self.sandbox_enabled = False

    def set_sandbox_mode(self, enabled):
        self.sandbox_enabled = bool(enabled)

    def fetch_tickers(self):
        public_url = self.urls['api']['public']
        self.public_hosts_tried.append(public_url)
        if 'api3.binance.com' not in public_url:
            raise Exception('451 Unavailable For Legal Reasons')
        return {'BTC/USDT': {'last': 100000.0}}


class _FakeCcxt:
    @staticmethod
    def binanceusdm(cfg):
        return _FakeExchange(cfg)


if __name__ == '__main__':
    original_ccxt = binance_client._ccxt_instance
    try:
        binance_client._ccxt_instance = _FakeCcxt()

        client = binance_client.BinanceClient(testnet=False)
        expected_initial_urls = {
            'public': 'https://api1.binance.com/sapi/v1',
            'private': 'https://api1.binance.com/sapi/v1',
        }
        if client.exchange.cfg.get('urls', {}).get('api') != expected_initial_urls:
            print(f"❌ URLs iniciais incorretas: {client.exchange.cfg.get('urls')}")
            raise SystemExit(1)

        ok, message = client.test_connection()
        if not ok:
            print(f"❌ Conexão pública deveria funcionar após rotação: {message}")
            raise SystemExit(2)

        if client.active_endpoint != 'https://api3.binance.com':
            print(f"❌ Endpoint ativo deveria terminar em api3: {client.active_endpoint}")
            raise SystemExit(3)

        expected_hosts = [
            'https://api1.binance.com/sapi/v1',
            'https://api2.binance.com/sapi/v1',
            'https://api3.binance.com/sapi/v1',
        ]
        if client.exchange.public_hosts_tried != expected_hosts:
            print(f"❌ Rotação incorreta: {client.exchange.public_hosts_tried}")
            raise SystemExit(4)

        if client.exchange.urls.get('fapi', {}).get('public') != 'https://fapi.binance.com':
            print(f"❌ Endpoint futures não deveria mudar: {client.exchange.urls}")
            raise SystemExit(5)

        print('✅ Binance alterna automaticamente entre api1/api2/api3 em HTTP 451')
        raise SystemExit(0)
    finally:
        binance_client._ccxt_instance = original_ccxt