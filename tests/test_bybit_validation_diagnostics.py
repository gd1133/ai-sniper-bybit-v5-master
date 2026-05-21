import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pybit.exceptions import InvalidRequestError

import main_web


class _FailingBybitHTTP:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def get_wallet_balance(self, **kwargs):
        raise InvalidRequestError(
            request='GET /v5/account/wallet-balance: accountType=UNIFIED&coin=USDT',
            message='Permission denied',
            status_code=10005,
            time='00:00:00',
            resp_headers={'content-type': 'application/json'},
        )


def test_friendly_bybit_error_handles_permission_and_ip_diagnostics():
    permission_message = main_web._friendly_bybit_error(
        'Permission denied',
        'real',
        status_code=200,
        response_body='{"retCode":10005,"retMsg":"Permission denied"}',
    )
    assert 'permissões suficientes' in permission_message

    ip_message = main_web._friendly_bybit_error(
        'HTTP 401',
        'real',
        status_code=200,
        response_body='{"retCode":10010,"retMsg":"Unmatched IP"}',
    )
    assert 'IP do servidor não autorizado' in ip_message


def test_validar_e_salvar_cliente_logs_exact_bybit_status_and_body(monkeypatch, capsys):
    captured_payloads = []

    monkeypatch.setattr(main_web, 'BybitV5HTTP', _FailingBybitHTTP)
    monkeypatch.setattr(main_web, '_compute_safe_recv_window', lambda base_url: 15000)
    monkeypatch.setattr(
        main_web,
        '_save_client_everywhere',
        lambda payload: (captured_payloads.append(dict(payload)) or ({**payload, 'id': 17}, False, True)),
    )
    monkeypatch.setattr(
        main_web,
        '_probe_bybit_wallet_balance_error',
        lambda *args, **kwargs: {
            'status_code': 200,
            'response_body': '{"retCode":10005,"retMsg":"Permission denied"}',
        },
    )

    result = main_web.validar_e_salvar_cliente(
        'key',
        'secret',
        False,
        client_payload={'nome': 'Cliente Diagnóstico'},
        existing_client={'saldo_base': 77.0},
    )

    captured = capsys.readouterr()

    assert result['valid'] is False
    assert result['api_error_status'] == 200
    assert result['api_error_response'] == '{"retCode":10005,"retMsg":"Permission denied"}'
    assert 'permissões suficientes' in result['msg']
    assert captured_payloads[-1]['status'] == 'erro_api'
    assert float(captured_payloads[-1]['saldo_base']) == 77.0
    assert 'status_code=200' in captured.out
    assert 'response_body={"retCode":10005,"retMsg":"Permission denied"}' in captured.out
