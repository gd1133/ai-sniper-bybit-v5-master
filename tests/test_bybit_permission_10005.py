# -*- coding: utf-8 -*-
"""Testes ErrCode 10005 — permissões Trade / fail-fast leverage."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.broker.bybit_client import (
    AUTH_10005_MSG,
    BybitClient,
)

ROOT = Path(__file__).resolve().parents[1]


def test_check_api_key_trade_permissions_rejects_readonly():
    ok, err = BybitClient._check_api_key_trade_permissions({
        'readOnly': 1,
        'permissions': {'ContractTrade': ['Order', 'Position']},
    })
    assert ok is False
    assert err is not None
    assert 'Read-Only' in err or 'Trade' in err


def test_check_api_key_trade_permissions_rejects_missing_contract_order():
    ok, err = BybitClient._check_api_key_trade_permissions({
        'readOnly': 0,
        'permissions': {'ContractTrade': [], 'Spot': ['SpotTrade']},
    })
    assert ok is False
    assert 'Contract Trade' in (err or '')


def test_check_api_key_trade_permissions_accepts_contract_order():
    ok, err = BybitClient._check_api_key_trade_permissions({
        'readOnly': 0,
        'permissions': {'ContractTrade': ['Order', 'Position']},
    })
    assert ok is True
    assert err is None


def test_check_api_key_trade_permissions_accepts_derivatives_trade():
    ok, err = BybitClient._check_api_key_trade_permissions({
        'readOnly': 0,
        'permissions': {'ContractTrade': [], 'Derivatives': ['DerivativesTrade']},
    })
    assert ok is True
    assert err is None


def test_is_auth_error_detects_10005():
    client = BybitClient.__new__(BybitClient)
    msg = (
        "Permission denied, please check your API key permissions. "
        "(ErrCode: 10005) (ErrTime: 15:08:54)."
    )
    assert client._is_auth_error(msg) is True
    assert BybitClient._is_permission_denied_10005(msg) is True
    assert BybitClient._is_permission_denied_10005('retCode=10005') is True
    assert BybitClient._is_permission_denied_10005('network timeout') is False


def test_format_permission_denied_message_is_actionable():
    text = BybitClient.format_permission_denied_message(
        'Permission denied (ErrCode: 10005)'
    )
    assert 'Contract Trade' in text
    assert 'Render' in text
    assert AUTH_10005_MSG[:40] in text


def test_extract_bybit_ret_code_errcode_10005():
    client = BybitClient.__new__(BybitClient)
    code = client._extract_bybit_ret_code(
        "Permission denied, please check your API key permissions. (ErrCode: 10005)."
    )
    assert code == '10005'


def test_handle_v5_ret_code_10005_sets_auth_false():
    client = BybitClient.__new__(BybitClient)
    client.authenticated = True
    client.last_auth_error_code = None
    client.last_auth_error_message = None
    ok, err = client._handle_v5_ret_code(
        {'retCode': 10005, 'retMsg': 'Permission denied'},
        'set_leverage',
    )
    assert ok is False
    assert '10005' in err
    assert client.authenticated is False
    assert str(client.last_auth_error_code) == '10005'


def test_validate_keys_lightweight_rejects_readonly():
    client = BybitClient.__new__(BybitClient)
    client.authenticated = True
    client._api_key = 'test'
    client.exchange = SimpleNamespace(apiKey='testkey')
    session = MagicMock()
    session.get_api_key_information.return_value = {
        'retCode': 0,
        'result': {
            'readOnly': 1,
            'permissions': {'ContractTrade': ['Order', 'Position']},
        },
    }
    client.pybit_session = session

    result = client.validate_keys_lightweight()
    assert result['ok'] is False
    assert result['balance'] is None
    assert 'Trade' in (result['error'] or '')
    assert client.authenticated is False
    assert str(client.last_auth_error_code) == '10005'
    session.get_wallet_balance.assert_not_called()


def test_validate_keys_lightweight_rejects_no_contract_trade():
    client = BybitClient.__new__(BybitClient)
    client.authenticated = True
    client._api_key = 'test'
    client.exchange = SimpleNamespace(apiKey='abcd')
    session = MagicMock()
    session.get_api_key_information.return_value = {
        'retCode': 0,
        'result': {
            'readOnly': 0,
            'permissions': {'ContractTrade': [], 'Wallet': ['AccountTransfer']},
        },
    }
    client.pybit_session = session

    result = client.validate_keys_lightweight()
    assert result['ok'] is False
    assert 'Contract Trade' in (result['error'] or '')


def test_main_web_auth_helpers_in_source():
    src = (ROOT / 'main_web.py').read_text(encoding='utf-8')
    assert 'def _is_bybit_permission_denied_10005' in src
    assert 'def _is_bybit_auth_error' in src
    assert "'10005'" in src or '"10005"' in src
    assert 'ErrCode:' in src
    assert 'MSG_10005_OPS' in src
    assert 'api_permissao' in src
    assert 'Contract Trade' in src


def test_main_web_source_has_leverage_fail_fast_10005():
    src = (ROOT / 'main_web.py').read_text(encoding='utf-8')
    assert '_is_bybit_permission_denied_10005' in src
    assert 'ordem abortada' in src
    assert "source_label='set_leverage'" in src
    assert 'api_permissao' in src
    assert 'MSG_10005_OPS' in src
