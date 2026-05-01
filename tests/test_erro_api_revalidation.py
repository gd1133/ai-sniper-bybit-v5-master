"""
Tests for the erro_api / re-validation cycle in main_web.validar_e_salvar_cliente:

  - A testnet account that fails Bybit auth receives status='erro_api'
  - A real account that fails Bybit auth receives status='erro_api'
  - After a failure, re-validating with correct credentials sets status='ativo'
  - saldo_base is preserved from existing_client when API call fails
  - saldo_base comes from Bybit response on success
  - account_mode and balance_source are set correctly for both testnet and real
  - client_payload=None skips persistence (_save_client_everywhere is not called)
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main_web


# ---------------------------------------------------------------------------
# Fake Bybit HTTP helpers
# ---------------------------------------------------------------------------

class _SuccessHTTP:
    def __init__(self, balance='500.00', **kwargs):
        self._balance = balance

    def get_wallet_balance(self, **kwargs):
        return {
            'retCode': 0,
            'result': {
                'list': [{'coin': [{'coin': 'USDT', 'walletBalance': self._balance}]}]
            },
        }


class _FailHTTP:
    def __init__(self, **kwargs):
        pass

    def get_wallet_balance(self, **kwargs):
        raise RuntimeError('HTTP 401 Unauthorized')


class _BadRetCodeHTTP:
    def __init__(self, **kwargs):
        pass

    def get_wallet_balance(self, **kwargs):
        return {'retCode': 10003, 'retMsg': 'API key is invalid', 'result': {'list': []}}


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _patch(http_class, captured):
    original_http = main_web.BybitV5HTTP
    original_recv = main_web._compute_safe_recv_window
    original_save = main_web._save_client_everywhere

    main_web.BybitV5HTTP = http_class
    main_web._compute_safe_recv_window = lambda url: 15000
    main_web._save_client_everywhere = lambda payload: (
        captured.append(dict(payload)) or ({**payload, 'id': 99}, True, True)
    )
    return original_http, original_recv, original_save


def _restore(original_http, original_recv, original_save):
    main_web.BybitV5HTTP = original_http
    main_web._compute_safe_recv_window = original_recv
    main_web._save_client_everywhere = original_save


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_testnet_failure_sets_erro_api_status():
    captured = []
    orig = _patch(lambda **kw: _FailHTTP(**kw), captured)
    try:
        result = main_web.validar_e_salvar_cliente(
            'bad-key', 'bad-secret', True,
            client_payload={'nome': 'Paula'},
        )
        assert result['valid'] is False
        assert captured[-1]['status'] == 'erro_api'
        assert captured[-1]['account_mode'] == 'testnet'
    finally:
        _restore(*orig)


def test_real_account_failure_sets_erro_api_status():
    captured = []
    orig = _patch(lambda **kw: _FailHTTP(**kw), captured)
    try:
        result = main_web.validar_e_salvar_cliente(
            'bad-key', 'bad-secret', False,
            client_payload={'nome': 'Givaldo'},
        )
        assert result['valid'] is False
        assert captured[-1]['status'] == 'erro_api'
        assert captured[-1]['account_mode'] == 'real'
    finally:
        _restore(*orig)


def test_bad_ret_code_sets_erro_api():
    captured = []
    orig = _patch(lambda **kw: _BadRetCodeHTTP(**kw), captured)
    try:
        result = main_web.validar_e_salvar_cliente(
            'key', 'secret', True,
            client_payload={'nome': 'Test'},
        )
        assert result['valid'] is False
        assert captured[-1]['status'] == 'erro_api'
    finally:
        _restore(*orig)


def test_success_sets_ativo_status():
    captured = []
    orig = _patch(lambda **kw: _SuccessHTTP(**kw), captured)
    try:
        result = main_web.validar_e_salvar_cliente(
            'good-key', 'good-secret', True,
            client_payload={'nome': 'GoodUser'},
        )
        assert result['valid'] is True
        assert captured[-1]['status'] == 'ativo'
    finally:
        _restore(*orig)


def test_revalidation_changes_erro_api_to_ativo():
    """Simulate Paula fixing her keys: status goes from erro_api -> ativo."""
    captured = []
    existing = {'id': 13, 'nome': 'Paula', 'saldo_base': 1000.0, 'status': 'erro_api'}

    # First call — failure
    orig = _patch(lambda **kw: _FailHTTP(**kw), captured)
    try:
        failed = main_web.validar_e_salvar_cliente(
            'bad-key', 'bad-secret', True,
            client_payload={'nome': 'Paula'},
            client_id=13,
            existing_client=existing,
        )
        assert failed['valid'] is False
        assert captured[-1]['status'] == 'erro_api'
    finally:
        _restore(*orig)

    # Second call — success with corrected keys
    orig = _patch(lambda **kw: _SuccessHTTP(balance='1000.00', **kw), captured)
    try:
        ok = main_web.validar_e_salvar_cliente(
            'correct-key', 'correct-secret', True,
            client_payload={'nome': 'Paula'},
            client_id=13,
            existing_client=existing,
        )
        assert ok['valid'] is True
        assert captured[-1]['status'] == 'ativo'
        assert abs(ok['balance'] - 1000.0) < 1e-9
    finally:
        _restore(*orig)


def test_saldo_base_preserved_from_existing_client_on_failure():
    captured = []
    existing = {'id': 13, 'nome': 'Paula', 'saldo_base': 777.0}
    orig = _patch(lambda **kw: _FailHTTP(**kw), captured)
    try:
        result = main_web.validar_e_salvar_cliente(
            'bad', 'bad', True,
            client_payload={'nome': 'Paula'},
            client_id=13,
            existing_client=existing,
        )
        assert result['valid'] is False
        assert abs(float(captured[-1].get('saldo_base', 0)) - 777.0) < 1e-9
    finally:
        _restore(*orig)


def test_saldo_base_comes_from_broker_on_success():
    captured = []
    orig = _patch(lambda **kw: _SuccessHTTP(balance='321.45', **kw), captured)
    try:
        result = main_web.validar_e_salvar_cliente(
            'key', 'secret', False,
            client_payload={'nome': 'Investor'},
        )
        assert result['valid'] is True
        assert abs(result['balance'] - 321.45) < 1e-9
        assert abs(float(captured[-1]['saldo_base']) - 321.45) < 1e-9
    finally:
        _restore(*orig)


def test_balance_source_is_testnet_for_testnet_account():
    captured = []
    orig = _patch(lambda **kw: _SuccessHTTP(**kw), captured)
    try:
        main_web.validar_e_salvar_cliente(
            'k', 's', True,
            client_payload={'nome': 'T'},
        )
        assert captured[-1]['balance_source'] == 'broker_testnet_balance'
    finally:
        _restore(*orig)


def test_balance_source_is_real_for_real_account():
    captured = []
    orig = _patch(lambda **kw: _SuccessHTTP(**kw), captured)
    try:
        main_web.validar_e_salvar_cliente(
            'k', 's', False,
            client_payload={'nome': 'R'},
        )
        assert captured[-1]['balance_source'] == 'broker_real_balance'
    finally:
        _restore(*orig)


def test_no_client_payload_skips_persistence():
    """When client_payload=None, _save_client_everywhere must NOT be called."""
    calls = []
    original_save = main_web._save_client_everywhere
    original_http = main_web.BybitV5HTTP
    original_recv = main_web._compute_safe_recv_window

    try:
        main_web._save_client_everywhere = lambda p: (calls.append(p) or ({}, False, False))
        main_web.BybitV5HTTP = lambda **kw: _SuccessHTTP(**kw)
        main_web._compute_safe_recv_window = lambda url: 15000

        result = main_web.validar_e_salvar_cliente('k', 's', True, client_payload=None)
        assert calls == [], '_save_client_everywhere should NOT be called when client_payload=None'
        assert result['record'] is None
    finally:
        main_web._save_client_everywhere = original_save
        main_web.BybitV5HTTP = original_http
        main_web._compute_safe_recv_window = original_recv


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import traceback

    tests = [
        test_testnet_failure_sets_erro_api_status,
        test_real_account_failure_sets_erro_api_status,
        test_bad_ret_code_sets_erro_api,
        test_success_sets_ativo_status,
        test_revalidation_changes_erro_api_to_ativo,
        test_saldo_base_preserved_from_existing_client_on_failure,
        test_saldo_base_comes_from_broker_on_success,
        test_balance_source_is_testnet_for_testnet_account,
        test_balance_source_is_real_for_real_account,
        test_no_client_payload_skips_persistence,
    ]

    failed = 0
    for fn in tests:
        try:
            fn()
            print(f'✅ {fn.__name__}')
        except Exception:
            print(f'❌ {fn.__name__}')
            traceback.print_exc()
            failed += 1

    if failed:
        print(f'\n{failed} test(s) FAILED')
        raise SystemExit(1)

    print(f'\n✅ All {len(tests)} erro_api revalidation tests passed')
    raise SystemExit(0)
