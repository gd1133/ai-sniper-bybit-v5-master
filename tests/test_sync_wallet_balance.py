"""
Testes para BybitClient.sync_wallet_balance e
SupabaseManager.sync_client_wallet_balance.

Cobre:
1. Sucesso com conta UNIFIED (totalWalletBalance)
2. Sucesso com conta UNIFIED (nível coin walletBalance)
3. Fallback UNIFIED → CONTRACT quando UNIFIED retorna retCode != 0
4. Falha imediata em erro de autenticação (retCode 10003, sem retry)
5. Falha imediata em erro HTTP 403 (sem retry)
6. Retry em falha transitória e sucesso na segunda tentativa
7. Timeout respeitado quando todas as tentativas falham
8. sync_client_wallet_balance atualiza status='ativo' com saldo correto
9. sync_client_wallet_balance atualiza status='erro_api' em falha
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.broker import bybit_client as bybit_module
from src.database.supabase_manager import SupabaseManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeExchange:
    def __init__(self):
        self.urls = {'api': {'public': 'https://api.bybit.com', 'private': 'https://api.bybit.com'}}
        self.sandbox_enabled = False

    def set_sandbox_mode(self, enabled):
        self.sandbox_enabled = bool(enabled)


class _FakeCcxt:
    @staticmethod
    def bybit(cfg):
        return _FakeExchange()


def _make_client(pybit_session, testnet=True):
    """Cria um BybitClient já autenticado com uma pybit_session falsa."""
    original_ccxt = bybit_module._ccxt_instance
    original_http = bybit_module._pybit_http_class
    original_env = os.environ.get('USE_TESTNET')

    bybit_module._ccxt_instance = _FakeCcxt()
    # Pybit class stub – never actually called during sync_wallet_balance
    bybit_module._pybit_http_class = type('_H', (), {
        '__module__': 'pybit.unified_trading',
        '__init__': lambda self, **kw: None,
    })

    try:
        os.environ['USE_TESTNET'] = 'true' if testnet else 'false'
        client = bybit_module.BybitClient('key', 'secret')
        client.pybit_session = pybit_session
        client.authenticated = True
        return client
    finally:
        bybit_module._ccxt_instance = original_ccxt
        bybit_module._pybit_http_class = original_http
        if original_env is None:
            os.environ.pop('USE_TESTNET', None)
        else:
            os.environ['USE_TESTNET'] = original_env


def _unified_ok(balance_value):
    return {
        'retCode': 0,
        'result': {
            'list': [{'totalWalletBalance': str(balance_value), 'coin': []}]
        },
    }


def _unified_ok_coin_level(balance_value):
    return {
        'retCode': 0,
        'result': {
            'list': [{
                'totalWalletBalance': None,
                'totalEquity': '',
                'coin': [{'coin': 'USDT', 'walletBalance': str(balance_value)}],
            }]
        },
    }


# ---------------------------------------------------------------------------
# Pybit session stubs
# ---------------------------------------------------------------------------

class _SuccessUnified:
    def get_wallet_balance(self, accountType, coin):
        if accountType == 'UNIFIED':
            return _unified_ok(543.21)
        return {'retCode': 10016, 'retMsg': 'account type not found'}


class _SuccessCoinLevel:
    def get_wallet_balance(self, accountType, coin):
        if accountType == 'UNIFIED':
            return _unified_ok_coin_level(111.11)
        return {'retCode': 10016, 'retMsg': 'account type not found'}


class _FallbackToContract:
    def get_wallet_balance(self, accountType, coin):
        if accountType == 'UNIFIED':
            return {'retCode': 10016, 'retMsg': 'account type not supported'}
        return _unified_ok(200.0)


class _AuthError10003:
    def get_wallet_balance(self, accountType, coin):
        return {'retCode': 10003, 'retMsg': 'Invalid API Key'}


class _AuthErrorHTTP403:
    def get_wallet_balance(self, accountType, coin):
        raise RuntimeError('HTTP 403 Forbidden')


class _TransientThenSuccess:
    def __init__(self):
        self._calls = 0

    def get_wallet_balance(self, accountType, coin):
        self._calls += 1
        if self._calls == 1:
            raise ConnectionError('connection reset')
        return _unified_ok(789.0)


class _AlwaysFail:
    def get_wallet_balance(self, accountType, coin):
        raise TimeoutError('request timed out')


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_success_total_wallet_balance():
    client = _make_client(_SuccessUnified())
    ok, balance, err = client.sync_wallet_balance()
    assert ok, f"Esperava sucesso, erro: {err}"
    assert balance == 543.21, f"Saldo incorreto: {balance}"
    assert err == '', f"Mensagem de erro inesperada: {err}"
    print("✅ [1] Sucesso com totalWalletBalance")


def test_success_coin_level_balance():
    client = _make_client(_SuccessCoinLevel())
    ok, balance, err = client.sync_wallet_balance()
    assert ok, f"Esperava sucesso, erro: {err}"
    assert balance == 111.11, f"Saldo incorreto: {balance}"
    print("✅ [2] Sucesso com walletBalance no nível coin")


def test_fallback_unified_to_contract():
    client = _make_client(_FallbackToContract())
    ok, balance, err = client.sync_wallet_balance(max_retries=1)
    assert ok, f"Esperava sucesso via CONTRACT, erro: {err}"
    assert balance == 200.0, f"Saldo incorreto: {balance}"
    print("✅ [3] Fallback UNIFIED → CONTRACT bem-sucedido")


def test_auth_error_10003_no_retry():
    class _Counting:
        def __init__(self):
            self._calls = 0
        def get_wallet_balance(self, accountType, coin):
            self._calls += 1
            return {'retCode': 10003, 'retMsg': 'Invalid API Key'}

    counting_session = _Counting()
    client = _make_client(counting_session)
    ok, balance, err = client.sync_wallet_balance(max_retries=3)
    assert not ok, "Esperava falha"
    assert balance is None
    assert not client.authenticated, "authenticated deveria ser False"
    assert counting_session._calls == 1, (
        f"Não deveria ter feito retry em erro 10003, chamadas: {counting_session._calls}"
    )
    print("✅ [4] retCode 10003 encerra imediatamente sem retry")


def test_auth_error_http_403_no_retry():
    class _CountingHTTP403:
        def __init__(self):
            self._calls = 0
        def get_wallet_balance(self, accountType, coin):
            self._calls += 1
            raise RuntimeError('HTTP 403 Forbidden')

    session = _CountingHTTP403()
    client = _make_client(session)
    ok, balance, err = client.sync_wallet_balance(max_retries=3)
    assert not ok, "Esperava falha"
    assert balance is None
    assert not client.authenticated, "authenticated deveria ser False"
    assert session._calls == 1, (
        f"Não deveria ter feito retry em HTTP 403, chamadas: {session._calls}"
    )
    print("✅ [5] Erro HTTP 403 encerra imediatamente sem retry")


def test_retry_on_transient_error():
    session = _TransientThenSuccess()
    client = _make_client(session)
    ok, balance, err = client.sync_wallet_balance(max_retries=3, retry_delay=0.01)
    assert ok, f"Esperava sucesso após retry, erro: {err}"
    assert balance == 789.0, f"Saldo incorreto: {balance}"
    assert session._calls == 2, f"Esperava 2 chamadas, fez {session._calls}"
    print("✅ [6] Retry em erro transitório e sucesso na segunda tentativa")


def test_timeout_respected():
    client = _make_client(_AlwaysFail())
    start = time.time()
    total_timeout = 0.3
    ok, balance, err = client.sync_wallet_balance(
        max_retries=10, retry_delay=0.05, total_timeout=total_timeout
    )
    elapsed = time.time() - start
    assert not ok, "Esperava falha por timeout"
    assert balance is None
    assert elapsed < total_timeout * 4, f"Não respeitou o timeout: {elapsed:.2f}s"
    print(f"✅ [7] Timeout respeitado ({elapsed:.2f}s para total_timeout={total_timeout}s)")


def test_supabase_sync_success():
    updates = []

    class _FakeTable:
        def update(self, payload):
            updates.append(dict(payload))
            return self
        def eq(self, col, val):
            return self
        def execute(self):
            pass

    class _FakeSupabaseClient:
        def table(self, name):
            return _FakeTable()

    class _FakeSuccessSession:
        def get_wallet_balance(self, accountType, coin):
            return _unified_ok(321.0)

    bybit_client = _make_client(_FakeSuccessSession())
    mgr = SupabaseManager.__new__(SupabaseManager)
    mgr.url = 'http://fake'
    mgr.key = 'fake-key'
    mgr.crypto_secret = 'fake-key'
    mgr.cipher = None
    mgr.cloud_enabled = True
    mgr.cloud_disable_reason = None
    mgr._last_error_log = 0
    mgr._error_count = 0
    mgr.client = _FakeSupabaseClient()

    result = mgr.sync_client_wallet_balance(42, bybit_client)

    assert result['success'], f"Esperava sucesso: {result}"
    assert result['balance'] == 321.0, f"Saldo incorreto: {result['balance']}"
    assert updates, "Nenhuma atualização foi enviada ao Supabase"
    assert updates[-1].get('status') == 'ativo', f"Status incorreto: {updates[-1]}"
    assert updates[-1].get('saldo_base') == 321.0, f"saldo_base incorreto: {updates[-1]}"
    print("✅ [8] sync_client_wallet_balance define status='ativo' e saldo_base corretos")


def test_supabase_sync_failure():
    updates = []

    class _FakeTable:
        def update(self, payload):
            updates.append(dict(payload))
            return self
        def eq(self, col, val):
            return self
        def execute(self):
            pass

    class _FakeSupabaseClient:
        def table(self, name):
            return _FakeTable()

    class _FailingSession:
        def get_wallet_balance(self, accountType, coin):
            raise RuntimeError('connection refused')

    bybit_client = _make_client(_FailingSession())
    mgr = SupabaseManager.__new__(SupabaseManager)
    mgr.url = 'http://fake'
    mgr.key = 'fake-key'
    mgr.crypto_secret = 'fake-key'
    mgr.cipher = None
    mgr.cloud_enabled = True
    mgr.cloud_disable_reason = None
    mgr._last_error_log = 0
    mgr._error_count = 0
    mgr.client = _FakeSupabaseClient()

    result = mgr.sync_client_wallet_balance(42, bybit_client)

    assert not result['success'], f"Esperava falha: {result}"
    assert result['balance'] is None
    assert updates, "Nenhuma atualização foi enviada ao Supabase"
    assert updates[-1].get('status') == 'erro_api', f"Status incorreto: {updates[-1]}"
    print("✅ [9] sync_client_wallet_balance define status='erro_api' em falha")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    tests = [
        test_success_total_wallet_balance,
        test_success_coin_level_balance,
        test_fallback_unified_to_contract,
        test_auth_error_10003_no_retry,
        test_auth_error_http_403_no_retry,
        test_retry_on_transient_error,
        test_timeout_respected,
        test_supabase_sync_success,
        test_supabase_sync_failure,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            print(f"❌ {t.__name__}: {exc}")
            failed += 1

    if failed:
        raise SystemExit(failed)
    raise SystemExit(0)
