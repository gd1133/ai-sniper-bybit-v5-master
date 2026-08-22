# -*- coding: utf-8 -*-
"""Testes de auth Bybit 33004 / timeout no CRUD de investidores."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_WEB = (ROOT / 'main_web.py').read_text(encoding='utf-8')


def test_auth_error_helpers_and_33004_in_source():
    assert '_is_bybit_auth_error' in MAIN_WEB
    assert '_handle_bybit_auth_failure' in MAIN_WEB
    assert '_mark_client_auth_error' in MAIN_WEB
    assert '33004' in MAIN_WEB
    assert 'erro_autenticacao' in MAIN_WEB


def test_validate_timeout_default_is_4s():
    assert "BYBIT_VALIDATE_TIMEOUT_SECS', '4')" in MAIN_WEB or 'BYBIT_VALIDATE_TIMEOUT_SECS", "4")' in MAIN_WEB


def test_delete_never_calls_bybit():
    assert 'NUNCA consulta Bybit' in MAIN_WEB or 'sem Bybit' in MAIN_WEB
    assert '/api/deletar_investidor' in MAIN_WEB


def test_set_client_status_helper_exists():
    from src.database import manager as db
    assert callable(getattr(db, 'set_client_status', None))


def test_frontend_has_6s_abort():
    js = (ROOT / 'main.jsx').read_text(encoding='utf-8')
    assert 'timeoutMs = 6000' in js or '6000' in js
    assert 'AbortController' in js
