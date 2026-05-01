"""
Tests for SupabaseManager encryption/decryption pipeline,
account mode normalization, payload preparation, row normalization,
update_client_validation_status, and _handle_cloud_error.

All tests use a fully mocked Supabase client — no real network calls.
"""
import os
import sys
import io
from contextlib import redirect_stdout

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.supabase_manager import SupabaseManager, _normalize_account_mode


# ---------------------------------------------------------------------------
# Helper: build a SupabaseManager without a real Supabase connection
# ---------------------------------------------------------------------------

def _make_manager(secret='test-secret') -> SupabaseManager:
    """Return a SupabaseManager with a known crypto secret and no live client."""
    os.environ['SUPABASE_CLIENTS_SECRET'] = secret
    os.environ.pop('SUPABASE_URL', None)
    os.environ.pop('SUPABASE_KEY', None)
    mgr = SupabaseManager()
    assert not mgr.is_available(), 'Manager should be offline when URL/KEY are missing'
    return mgr


# ---------------------------------------------------------------------------
# _normalize_account_mode (module-level helper)
# ---------------------------------------------------------------------------

def test_normalize_account_mode_explicit_strings():
    assert _normalize_account_mode('testnet') == 'testnet'
    assert _normalize_account_mode('real') == 'real'
    assert _normalize_account_mode('TESTNET') == 'testnet'
    assert _normalize_account_mode('REAL') == 'real'


def test_normalize_account_mode_bool_like_values():
    for v in [True, 1, '1', 'true', 'TRUE', 'True']:
        assert _normalize_account_mode(v) == 'testnet', f'Expected testnet for {v!r}'
    for v in [False, 0, '0', 'false', 'FALSE', 'False']:
        assert _normalize_account_mode(v) == 'real', f'Expected real for {v!r}'


def test_normalize_account_mode_unknown_defaults_to_testnet():
    assert _normalize_account_mode(None) == 'testnet'
    assert _normalize_account_mode('') == 'testnet'
    assert _normalize_account_mode('unknown') == 'testnet'
    assert _normalize_account_mode('paper') == 'testnet'


# ---------------------------------------------------------------------------
# Encryption / Decryption
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_round_trip():
    mgr = _make_manager()
    original = 'my-super-secret-key'
    encrypted = mgr._encrypt_field(original)
    assert encrypted != original
    assert str(encrypted).startswith('enc::')
    decrypted = mgr._decrypt_field(encrypted)
    assert decrypted == original


def test_encrypt_already_encrypted_is_idempotent():
    mgr = _make_manager()
    once = mgr._encrypt_field('api-key')
    twice = mgr._encrypt_field(once)
    assert once == twice


def test_decrypt_plain_value_is_returned_unchanged():
    mgr = _make_manager()
    assert mgr._decrypt_field('plain-text') == 'plain-text'


def test_encrypt_none_and_empty_return_as_is():
    mgr = _make_manager()
    assert mgr._encrypt_field(None) is None
    assert mgr._encrypt_field('') == ''


def test_decrypt_none_and_empty_return_as_is():
    mgr = _make_manager()
    assert mgr._decrypt_field(None) is None
    assert mgr._decrypt_field('') == ''


def test_decrypt_invalid_token_returns_empty_string():
    mgr = _make_manager()
    bogus = 'enc::NOT_VALID_TOKEN_AT_ALL'
    result = mgr._decrypt_field(bogus)
    assert result == ''


def test_no_cipher_encrypt_returns_value_unchanged():
    mgr = _make_manager()
    mgr.cipher = None
    assert mgr._encrypt_field('api-key') == 'api-key'


def test_no_cipher_decrypt_returns_empty_for_enc_prefixed():
    mgr = _make_manager()
    mgr.cipher = None
    assert mgr._decrypt_field('enc::something') == ''


# ---------------------------------------------------------------------------
# _protect_client_payload
# ---------------------------------------------------------------------------

def test_protect_client_payload_encrypts_sensitive_fields():
    mgr = _make_manager()
    payload = {
        'nome': 'Alice',
        'bybit_key': 'raw-key',
        'bybit_secret': 'raw-secret',
        'tg_token': 'tg-token',
        'tg_api_key': 'tg-api',
        'chat_id': 'chat-123',
    }
    protected = mgr._protect_client_payload(payload)
    assert protected['nome'] == 'Alice'
    for field in ('bybit_key', 'bybit_secret', 'tg_token', 'tg_api_key', 'chat_id'):
        assert str(protected[field]).startswith('enc::'), f'{field} should be encrypted'


def test_protect_client_payload_leaves_none_as_none():
    mgr = _make_manager()
    payload = {'bybit_key': None, 'bybit_secret': None}
    protected = mgr._protect_client_payload(payload)
    assert protected['bybit_key'] is None
    assert protected['bybit_secret'] is None


# ---------------------------------------------------------------------------
# _prepare_client_payload
# ---------------------------------------------------------------------------

def test_prepare_client_payload_testnet_account():
    mgr = _make_manager()
    client = {
        'nome': 'Bob',
        'bybit_key': 'k',
        'bybit_secret': 's',
        'account_mode': 'testnet',
        'saldo_base': 500.0,
    }
    payload = mgr._prepare_client_payload(client)
    assert payload['account_mode'] == 'testnet'
    assert payload['is_testnet'] is True
    assert payload['balance_source'] == 'broker_testnet_balance'
    assert payload['saldo_base'] == 500.0
    assert 'id' not in payload


def test_prepare_client_payload_real_account():
    mgr = _make_manager()
    client = {
        'nome': 'Carol',
        'bybit_key': 'k',
        'bybit_secret': 's',
        'account_mode': 'real',
        'saldo_base': 250.0,
        'id': 7,
    }
    payload = mgr._prepare_client_payload(client)
    assert payload['account_mode'] == 'real'
    assert payload['is_testnet'] is False
    assert payload['balance_source'] == 'broker_real_balance'
    assert payload['id'] == 7


def test_prepare_client_payload_derives_account_mode_from_is_testnet():
    mgr = _make_manager()
    client = {'nome': 'Dave', 'is_testnet': True, 'saldo_base': 0}
    payload = mgr._prepare_client_payload(client)
    assert payload['account_mode'] == 'testnet'
    assert payload['is_testnet'] is True


# ---------------------------------------------------------------------------
# _normalize_client_row
# ---------------------------------------------------------------------------

def test_normalize_client_row_decrypts_fields():
    mgr = _make_manager()
    enc_key = mgr._encrypt_field('real-key')
    enc_secret = mgr._encrypt_field('real-secret')
    row = {
        'bybit_key': enc_key,
        'bybit_secret': enc_secret,
        'tg_token': None,
        'tg_api_key': None,
        'chat_id': None,
        'saldo_base': '123.45',
        'is_testnet': True,
        'account_mode': 'testnet',
    }
    normalized = mgr._normalize_client_row(row)
    assert normalized['bybit_key'] == 'real-key'
    assert normalized['bybit_secret'] == 'real-secret'
    assert normalized['saldo_base'] == 123.45
    assert normalized['is_testnet'] == 1
    assert normalized['account_mode'] == 'testnet'
    assert normalized['balance_source'] == 'broker_testnet_balance'


def test_normalize_client_row_real_account():
    mgr = _make_manager()
    row = {
        'bybit_key': None,
        'bybit_secret': None,
        'tg_token': None,
        'tg_api_key': None,
        'chat_id': None,
        'saldo_base': '99.0',
        'is_testnet': False,
        'account_mode': 'real',
    }
    normalized = mgr._normalize_client_row(row)
    assert normalized['account_mode'] == 'real'
    assert normalized['is_testnet'] == 0
    assert normalized['balance_source'] == 'broker_real_balance'


def test_normalize_client_row_injects_balance_source_when_missing():
    mgr = _make_manager()
    row = {
        'bybit_key': None, 'bybit_secret': None, 'tg_token': None,
        'tg_api_key': None, 'chat_id': None,
        'account_mode': 'testnet', 'saldo_base': 0,
    }
    normalized = mgr._normalize_client_row(row)
    assert 'balance_source' in normalized
    assert normalized['balance_source'] == 'broker_testnet_balance'


# ---------------------------------------------------------------------------
# _handle_cloud_error — schema cache disables cloud
# ---------------------------------------------------------------------------

def test_handle_cloud_error_schema_cache_disables_cloud():
    mgr = _make_manager()
    mgr.cloud_enabled = True
    mgr._handle_cloud_error('test action', Exception('pgrst205: schema cache is invalid'))
    assert mgr.cloud_enabled is False
    assert 'tabela' in (mgr.cloud_disable_reason or '')


def test_handle_cloud_error_pgrst205_substring():
    mgr = _make_manager()
    mgr.cloud_enabled = True
    mgr._handle_cloud_error('test', Exception('PGRST205 something'))
    assert mgr.cloud_enabled is False


def test_handle_cloud_error_non_critical_does_not_disable_cloud():
    mgr = _make_manager()
    mgr.cloud_enabled = True
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        mgr._handle_cloud_error('test', Exception('some random network error'))
    assert mgr.cloud_enabled is True
    assert 'Erro ao' in stdout.getvalue()


# ---------------------------------------------------------------------------
# update_client_validation_status — offline (cloud unavailable)
# ---------------------------------------------------------------------------

def test_update_client_validation_status_returns_false_when_offline():
    mgr = _make_manager()
    assert not mgr.is_available()
    result = mgr.update_client_validation_status(1, ok=True)
    assert result is False


# ---------------------------------------------------------------------------
# update_client_validation_status — with mocked Supabase client
# ---------------------------------------------------------------------------

class _MockTable:
    """Minimal mock that records update/select calls."""

    def __init__(self):
        self.updates = []
        self.eq_filter = None

    def update(self, data):
        self.updates.append(dict(data))
        return self

    def eq(self, col, val):
        self.eq_filter = (col, val)
        return self

    def execute(self):
        return type('R', (), {'data': [{'id': self.eq_filter[1]}]})()


class _MockSupabaseClient:
    def __init__(self):
        self._table = _MockTable()

    def table(self, name):
        return self._table


def _make_online_manager(secret='test-secret') -> SupabaseManager:
    mgr = _make_manager(secret)
    mock_client = _MockSupabaseClient()
    mgr.client = mock_client
    mgr.cloud_enabled = True
    return mgr


def test_update_client_validation_status_sets_ativo_on_success():
    mgr = _make_online_manager()
    result = mgr.update_client_validation_status(13, ok=True)
    assert result is True
    table = mgr.client._table
    first_update = table.updates[0]
    assert first_update['status'] == 'ativo'


def test_update_client_validation_status_sets_erro_api_on_failure():
    mgr = _make_online_manager()
    result = mgr.update_client_validation_status(13, ok=False, error_message='HTTP 403')
    assert result is True
    table = mgr.client._table
    first_update = table.updates[0]
    assert first_update['status'] == 'erro_api'


def test_update_client_validation_status_clears_error_on_success():
    mgr = _make_online_manager()
    mgr.update_client_validation_status(13, ok=True)
    table = mgr.client._table
    # Subsequent updates (for error fields) should set them to None
    error_field_updates = [u for u in table.updates if any(
        k in u for k in ('api_error', 'error_message', 'last_error')
    )]
    for upd in error_field_updates:
        for field in ('api_error', 'error_message', 'last_error'):
            if field in upd:
                assert upd[field] is None, f'{field} should be None on success'


if __name__ == '__main__':
    import traceback

    tests = [
        test_normalize_account_mode_explicit_strings,
        test_normalize_account_mode_bool_like_values,
        test_normalize_account_mode_unknown_defaults_to_testnet,
        test_encrypt_decrypt_round_trip,
        test_encrypt_already_encrypted_is_idempotent,
        test_decrypt_plain_value_is_returned_unchanged,
        test_encrypt_none_and_empty_return_as_is,
        test_decrypt_none_and_empty_return_as_is,
        test_decrypt_invalid_token_returns_empty_string,
        test_no_cipher_encrypt_returns_value_unchanged,
        test_no_cipher_decrypt_returns_empty_for_enc_prefixed,
        test_protect_client_payload_encrypts_sensitive_fields,
        test_protect_client_payload_leaves_none_as_none,
        test_prepare_client_payload_testnet_account,
        test_prepare_client_payload_real_account,
        test_prepare_client_payload_derives_account_mode_from_is_testnet,
        test_normalize_client_row_decrypts_fields,
        test_normalize_client_row_real_account,
        test_normalize_client_row_injects_balance_source_when_missing,
        test_handle_cloud_error_schema_cache_disables_cloud,
        test_handle_cloud_error_pgrst205_substring,
        test_handle_cloud_error_non_critical_does_not_disable_cloud,
        test_update_client_validation_status_returns_false_when_offline,
        test_update_client_validation_status_sets_ativo_on_success,
        test_update_client_validation_status_sets_erro_api_on_failure,
        test_update_client_validation_status_clears_error_on_success,
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

    print(f'\n✅ All {len(tests)} SupabaseManager tests passed')
    raise SystemExit(0)
