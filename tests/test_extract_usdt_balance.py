"""
Tests for main_web._extract_unified_usdt_balance:
  - Normal response with walletBalance
  - Fallback to equity field
  - Fallback to usdValue field
  - retCode != 0 raises RuntimeError
  - Empty list returns 0.0
  - Missing USDT coin returns 0.0
  - Multiple accounts — first account used
  - Zero / string zero balance
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main_web


def _wallet(accounts):
    return {'retCode': 0, 'retMsg': 'OK', 'result': {'list': accounts}}


# ---------------------------------------------------------------------------
# Normal cases
# ---------------------------------------------------------------------------

def test_extracts_wallet_balance_usdt():
    payload = _wallet([{'coin': [{'coin': 'USDT', 'walletBalance': '321.45'}]}])
    assert abs(main_web._extract_unified_usdt_balance(payload) - 321.45) < 1e-9


def test_extracts_equity_when_wallet_balance_missing():
    payload = _wallet([{'coin': [{'coin': 'USDT', 'equity': '99.99'}]}])
    assert abs(main_web._extract_unified_usdt_balance(payload) - 99.99) < 1e-9


def test_extracts_usd_value_as_last_resort():
    payload = _wallet([{'coin': [{'coin': 'USDT', 'usdValue': '55.0'}]}])
    assert abs(main_web._extract_unified_usdt_balance(payload) - 55.0) < 1e-9


def test_wallet_balance_takes_priority_over_equity():
    payload = _wallet([{'coin': [{'coin': 'USDT', 'walletBalance': '200.0', 'equity': '300.0'}]}])
    assert abs(main_web._extract_unified_usdt_balance(payload) - 200.0) < 1e-9


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_ret_code_nonzero_raises_runtime_error():
    payload = {'retCode': 10003, 'retMsg': 'API key is invalid', 'result': {'list': []}}
    try:
        main_web._extract_unified_usdt_balance(payload)
        raise AssertionError('Expected RuntimeError was not raised')
    except RuntimeError as e:
        assert '10003' in str(e)


def test_empty_accounts_list_returns_zero():
    payload = _wallet([])
    assert main_web._extract_unified_usdt_balance(payload) == 0.0


def test_no_usdt_coin_returns_zero():
    payload = _wallet([{'coin': [{'coin': 'BTC', 'walletBalance': '0.5'}]}])
    assert main_web._extract_unified_usdt_balance(payload) == 0.0


def test_usdt_coin_with_none_balance_skips_and_returns_zero():
    payload = _wallet([{'coin': [{'coin': 'USDT', 'walletBalance': None, 'equity': None, 'usdValue': None}]}])
    assert main_web._extract_unified_usdt_balance(payload) == 0.0


def test_usdt_coin_with_empty_string_balance_skips():
    payload = _wallet([{'coin': [{'coin': 'USDT', 'walletBalance': '', 'equity': '0.0'}]}])
    assert main_web._extract_unified_usdt_balance(payload) == 0.0


def test_usdt_balance_zero_string_returns_zero():
    payload = _wallet([{'coin': [{'coin': 'USDT', 'walletBalance': '0.0'}]}])
    assert main_web._extract_unified_usdt_balance(payload) == 0.0


def test_multiple_accounts_uses_first():
    payload = _wallet([
        {'coin': [{'coin': 'USDT', 'walletBalance': '111.0'}]},
        {'coin': [{'coin': 'USDT', 'walletBalance': '999.0'}]},
    ])
    assert abs(main_web._extract_unified_usdt_balance(payload) - 111.0) < 1e-9


def test_mixed_coins_picks_usdt():
    payload = _wallet([{
        'coin': [
            {'coin': 'BTC', 'walletBalance': '1.0'},
            {'coin': 'USDT', 'walletBalance': '750.0'},
            {'coin': 'ETH', 'walletBalance': '3.0'},
        ]
    }])
    assert abs(main_web._extract_unified_usdt_balance(payload) - 750.0) < 1e-9


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import traceback

    tests = [
        test_extracts_wallet_balance_usdt,
        test_extracts_equity_when_wallet_balance_missing,
        test_extracts_usd_value_as_last_resort,
        test_wallet_balance_takes_priority_over_equity,
        test_ret_code_nonzero_raises_runtime_error,
        test_empty_accounts_list_returns_zero,
        test_no_usdt_coin_returns_zero,
        test_usdt_coin_with_none_balance_skips_and_returns_zero,
        test_usdt_coin_with_empty_string_balance_skips,
        test_usdt_balance_zero_string_returns_zero,
        test_multiple_accounts_uses_first,
        test_mixed_coins_picks_usdt,
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

    print(f'\n✅ All {len(tests)} balance extraction tests passed')
    raise SystemExit(0)
