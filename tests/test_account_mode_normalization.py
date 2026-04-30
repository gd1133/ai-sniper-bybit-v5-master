"""
Tests for account mode and operation mode normalization helpers in main_web.py:
  - _normalize_account_mode
  - _normalize_operation_mode
  - _is_testnet_account
  - _mode_balance_source
  - _is_order_execution_enabled
  - _filter_balance_items_for_operation_mode
  - _get_bybit_v5_base_url
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main_web


# ---------------------------------------------------------------------------
# _normalize_account_mode
# ---------------------------------------------------------------------------

def test_normalize_account_mode_explicit_strings():
    assert main_web._normalize_account_mode('testnet') == 'testnet'
    assert main_web._normalize_account_mode('real') == 'real'
    assert main_web._normalize_account_mode('TESTNET') == 'testnet'
    assert main_web._normalize_account_mode('REAL') == 'real'


def test_normalize_account_mode_bool_coercion():
    assert main_web._normalize_account_mode(True) == 'testnet'
    assert main_web._normalize_account_mode(False) == 'real'
    assert main_web._normalize_account_mode(1) == 'testnet'
    assert main_web._normalize_account_mode(0) == 'real'


def test_normalize_account_mode_string_bool():
    assert main_web._normalize_account_mode('true') == 'testnet'
    assert main_web._normalize_account_mode('false') == 'real'
    assert main_web._normalize_account_mode('1') == 'testnet'
    assert main_web._normalize_account_mode('0') == 'real'


def test_normalize_account_mode_unknown_defaults_to_testnet():
    assert main_web._normalize_account_mode(None) == 'testnet'
    assert main_web._normalize_account_mode('') == 'testnet'
    assert main_web._normalize_account_mode('paper') == 'testnet'
    assert main_web._normalize_account_mode('garbage') == 'testnet'


# ---------------------------------------------------------------------------
# _normalize_operation_mode
# ---------------------------------------------------------------------------

def test_normalize_operation_mode_valid():
    assert main_web._normalize_operation_mode('paper') == 'paper'
    assert main_web._normalize_operation_mode('testnet') == 'testnet'
    assert main_web._normalize_operation_mode('real') == 'real'


def test_normalize_operation_mode_test_alias():
    assert main_web._normalize_operation_mode('test') == 'paper'


def test_normalize_operation_mode_unknown_defaults_to_paper():
    assert main_web._normalize_operation_mode(None) == 'paper'
    assert main_web._normalize_operation_mode('') == 'paper'
    assert main_web._normalize_operation_mode('live') == 'paper'


# ---------------------------------------------------------------------------
# _is_testnet_account
# ---------------------------------------------------------------------------

def test_is_testnet_account_truthy():
    assert main_web._is_testnet_account('testnet') is True
    assert main_web._is_testnet_account(True) is True
    assert main_web._is_testnet_account('1') is True


def test_is_testnet_account_falsy():
    assert main_web._is_testnet_account('real') is False
    assert main_web._is_testnet_account(False) is False
    assert main_web._is_testnet_account('0') is False


# ---------------------------------------------------------------------------
# _mode_balance_source
# ---------------------------------------------------------------------------

def test_mode_balance_source_testnet():
    assert main_web._mode_balance_source('testnet') == 'broker_testnet_balance'


def test_mode_balance_source_real():
    assert main_web._mode_balance_source('real') == 'broker_real_balance'


def test_mode_balance_source_unknown_defaults_to_testnet_source():
    assert main_web._mode_balance_source(None) == 'broker_testnet_balance'
    assert main_web._mode_balance_source('') == 'broker_testnet_balance'


# ---------------------------------------------------------------------------
# _is_order_execution_enabled
# ---------------------------------------------------------------------------

def test_order_execution_disabled_in_paper_mode():
    assert main_web._is_order_execution_enabled('paper') is False


def test_order_execution_disabled_in_unknown_mode():
    assert main_web._is_order_execution_enabled(None) is False
    assert main_web._is_order_execution_enabled('') is False


def test_order_execution_enabled_in_testnet_and_real():
    """Execution is enabled for testnet/real only when ALLOW_ORDER_EXECUTION is True."""
    original = main_web.ALLOW_ORDER_EXECUTION
    original_real = main_web.ALLOW_REAL_TRADING
    try:
        main_web.ALLOW_ORDER_EXECUTION = True
        main_web.ALLOW_REAL_TRADING = True
        assert main_web._is_order_execution_enabled('testnet') is True
        assert main_web._is_order_execution_enabled('real') is True
    finally:
        main_web.ALLOW_ORDER_EXECUTION = original
        main_web.ALLOW_REAL_TRADING = original_real


def test_order_execution_blocked_when_flag_off():
    """Execution is blocked for testnet/real when ALLOW_ORDER_EXECUTION is False."""
    original = main_web.ALLOW_ORDER_EXECUTION
    try:
        main_web.ALLOW_ORDER_EXECUTION = False
        assert main_web._is_order_execution_enabled('testnet') is False
        assert main_web._is_order_execution_enabled('real') is False
    finally:
        main_web.ALLOW_ORDER_EXECUTION = original


# ---------------------------------------------------------------------------
# _filter_balance_items_for_operation_mode
# ---------------------------------------------------------------------------

def _make_items():
    return [
        {'id': 1, 'nome': 'Alice', 'saldo_real': 100.0, 'account_mode': 'testnet'},
        {'id': 2, 'nome': 'Bob', 'saldo_real': 200.0, 'account_mode': 'real'},
        {'id': 3, 'nome': 'Carol', 'saldo_real': 50.0, 'account_mode': 'testnet'},
    ]


def test_filter_real_mode_returns_only_real_clients():
    items = _make_items()
    filtered = main_web._filter_balance_items_for_operation_mode(items, 'real')
    assert all(i['account_mode'] == 'real' for i in filtered)
    assert len(filtered) == 1
    assert filtered[0]['nome'] == 'Bob'


def test_filter_testnet_mode_returns_only_testnet_clients():
    items = _make_items()
    filtered = main_web._filter_balance_items_for_operation_mode(items, 'testnet')
    assert all(i['account_mode'] == 'testnet' for i in filtered)
    assert len(filtered) == 2


def test_filter_paper_mode_returns_empty():
    items = _make_items()
    filtered = main_web._filter_balance_items_for_operation_mode(items, 'paper')
    assert filtered == []


def test_filter_empty_items_returns_empty():
    assert main_web._filter_balance_items_for_operation_mode([], 'real') == []
    assert main_web._filter_balance_items_for_operation_mode(None, 'testnet') == []


def test_filter_infers_account_mode_from_is_testnet_bool():
    items = [
        {'id': 10, 'is_testnet': True, 'saldo_real': 111.0},
        {'id': 11, 'is_testnet': False, 'saldo_real': 222.0},
    ]
    real_items = main_web._filter_balance_items_for_operation_mode(items, 'real')
    assert len(real_items) == 1
    assert real_items[0]['id'] == 11


# ---------------------------------------------------------------------------
# _get_bybit_v5_base_url
# ---------------------------------------------------------------------------

def test_get_bybit_v5_base_url_testnet():
    url = main_web._get_bybit_v5_base_url(True)
    assert 'testnet' in url


def test_get_bybit_v5_base_url_production():
    url = main_web._get_bybit_v5_base_url(False)
    assert 'testnet' not in url
    assert url.startswith('https://api.bybit.com')


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import traceback

    tests = [
        test_normalize_account_mode_explicit_strings,
        test_normalize_account_mode_bool_coercion,
        test_normalize_account_mode_string_bool,
        test_normalize_account_mode_unknown_defaults_to_testnet,
        test_normalize_operation_mode_valid,
        test_normalize_operation_mode_test_alias,
        test_normalize_operation_mode_unknown_defaults_to_paper,
        test_is_testnet_account_truthy,
        test_is_testnet_account_falsy,
        test_mode_balance_source_testnet,
        test_mode_balance_source_real,
        test_mode_balance_source_unknown_defaults_to_testnet_source,
        test_order_execution_disabled_in_paper_mode,
        test_order_execution_disabled_in_unknown_mode,
        test_order_execution_enabled_in_testnet_and_real,
        test_order_execution_blocked_when_flag_off,
        test_filter_real_mode_returns_only_real_clients,
        test_filter_testnet_mode_returns_only_testnet_clients,
        test_filter_paper_mode_returns_empty,
        test_filter_empty_items_returns_empty,
        test_filter_infers_account_mode_from_is_testnet_bool,
        test_get_bybit_v5_base_url_testnet,
        test_get_bybit_v5_base_url_production,
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

    print(f'\n✅ All {len(tests)} account mode normalization tests passed')
    raise SystemExit(0)
