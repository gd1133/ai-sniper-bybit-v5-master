import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main_web


class _FakeBybitHTTP:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def get_wallet_balance(self, **kwargs):
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "coin": [
                            {"coin": "USDT", "walletBalance": "321.45"}
                        ]
                    }
                ]
            },
        }


if __name__ == '__main__':
    original_http = main_web.BybitV5HTTP
    original_compute_recv = main_web._compute_safe_recv_window
    original_save = main_web._save_client_everywhere
    original_ensure_broker_class = main_web._ensure_broker_class
    original_env = os.environ.get('USE_TESTNET')

    captured_payloads = []

    try:
        os.environ['USE_TESTNET'] = 'true'
        main_web.BybitV5HTTP = _FakeBybitHTTP
        main_web._compute_safe_recv_window = lambda base_url: 15000
        main_web._save_client_everywhere = lambda payload: (captured_payloads.append(dict(payload)) or ({**payload, 'id': 9}, True, True))

        success = main_web.validar_e_salvar_cliente(
            'key',
            'secret',
            None,
            client_payload={'nome': 'Cliente Testnet'},
        )

        if not success.get('valid'):
            print(f"❌ Validação esperada como sucesso: {success}")
            raise SystemExit(1)

        if success.get('balance') != 321.45:
            print(f"❌ Saldo inválido retornado: {success.get('balance')}")
            raise SystemExit(2)

        saved_payload = captured_payloads[-1]
        if saved_payload.get('status') != 'ativo' or saved_payload.get('account_mode') != 'testnet':
            print(f"❌ Payload salvo incorreto no sucesso: {saved_payload}")
            raise SystemExit(3)

        class _FailingBybitHTTP:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def get_wallet_balance(self, **kwargs):
                raise RuntimeError('HTTP 403 Forbidden')

        main_web.BybitV5HTTP = _FailingBybitHTTP
        failure = main_web.validar_e_salvar_cliente(
            'key',
            'secret',
            False,
            client_payload={'nome': 'Cliente Real'},
            existing_client={'saldo_base': 777.0},
        )

        if failure.get('valid'):
            print(f"❌ Falha esperada como inválida: {failure}")
            raise SystemExit(4)

        failed_payload = captured_payloads[-1]
        if failed_payload.get('status') != 'erro_api' or float(failed_payload.get('saldo_base') or 0) != 777.0:
            print(f"❌ Payload salvo incorreto na falha: {failed_payload}")
            raise SystemExit(5)

        class _InvalidKeyBybitHTTP:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def get_wallet_balance(self, **kwargs):
                raise RuntimeError('retCode 10003: invalid api_key')

        class _FakeBinanceBroker:
            def __init__(self, api_key, api_secret, testnet=False):
                self.api_key = api_key
                self.api_secret = api_secret
                self.testnet = testnet

            def test_connection(self):
                return True, 'OK'

            def get_balance(self):
                return 123.45

        def _fake_ensure_broker_class(exchange='bybit'):
            normalized = main_web._normalize_exchange(exchange) or 'bybit'
            if normalized == 'binance':
                return _FakeBinanceBroker
            return original_ensure_broker_class(exchange)

        main_web._ensure_broker_class = _fake_ensure_broker_class
        main_web.BybitV5HTTP = _InvalidKeyBybitHTTP

        auto = main_web.validar_e_salvar_cliente(
            'key',
            'secret',
            False,
            client_payload={'nome': 'Cliente Auto'},  # exchange omitido -> default Bybit
        )

        if not auto.get('valid') or auto.get('exchange') != 'binance':
            print(f"❌ Esperado auto-detect Binance: {auto}")
            raise SystemExit(6)

        auto_payload = captured_payloads[-1]
        if auto_payload.get('exchange') != 'binance' or auto_payload.get('status') != 'ativo':
            print(f"❌ Payload salvo incorreto no auto-detect: {auto_payload}")
            raise SystemExit(7)

        print('✅ validar_e_salvar_cliente integrado corretamente')
        raise SystemExit(0)
    finally:
        main_web.BybitV5HTTP = original_http
        main_web._compute_safe_recv_window = original_compute_recv
        main_web._save_client_everywhere = original_save
        main_web._ensure_broker_class = original_ensure_broker_class
        if original_env is None:
            os.environ.pop('USE_TESTNET', None)
        else:
            os.environ['USE_TESTNET'] = original_env
