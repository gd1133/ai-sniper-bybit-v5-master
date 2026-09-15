# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any

import requests
import pytest

from src.intelligence import abacus_agent_client as client


class _DummyResponse:
    def __init__(self, status_code: int = 200, payload: dict[str, Any] | None = None, text: str = ''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _reset_abacus_state():
    client._abacus_cooldown_until = 0.0
    client._abacus_cooldown_reason = ''
    client._abacus_cooldown_logged_until = 0.0
    client._abacus_failure_streak = 0


def _set_base_env(monkeypatch):
    monkeypatch.setenv('ABACUS_AGENT_ENABLED', 'true')
    monkeypatch.setenv('ABACUS_AGENT_API_URL', 'https://api.abacus.ai/api/v0/getChatResponse')
    monkeypatch.setenv('ABACUS_AGENT_DEPLOYMENT_ID', 'b85816e70')
    monkeypatch.setenv('ABACUS_AGENT_TIMEOUT_SECS', '1')
    monkeypatch.setenv('ABACUS_AGENT_MAX_RETRIES', '0')
    monkeypatch.setenv('ABACUS_AGENT_COOLDOWN_SECS', '60')


def test_extract_json_block_with_code_fence():
    text = '```json\n{"action":"WAIT","confidence":"0.8"}\n```'
    parsed = client.extract_json_block(text)
    assert parsed is not None
    assert parsed['action'] == 'WAIT'


def test_parse_response_accepts_result_and_response_keys(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv('ABACUS_AGENT_API_KEY', 'k_test')
    monkeypatch.delenv('ABACUS_AGENT_DEPLOYMENT_TOKEN', raising=False)

    def fake_post(*args, **kwargs):
        return _DummyResponse(
            payload={
                'success': True,
                'result': {
                    'messages': [
                        {'is_user': True, 'text': 'oi'},
                        {'is_user': False, 'text': '```json\n{"action":"WAIT"}\n```'},
                    ]
                },
            }
        )

    monkeypatch.setattr(client.requests, 'post', fake_post)
    text = client.abacus_agent_chat('teste_result')
    assert text is not None
    parsed = client.parse_abacus_agent_json_response(text)
    assert parsed is not None
    assert parsed['action'] == 'HOLD'

    def fake_post_response(*args, **kwargs):
        return _DummyResponse(
            payload={
                'success': True,
                'response': {
                    'messages': [
                        {'is_user': False, 'text': '{"action":"LONG","confidence":0.61}'},
                    ]
                },
            }
        )

    monkeypatch.setattr(client.requests, 'post', fake_post_response)
    text2 = client.abacus_agent_chat('teste_response')
    assert text2 is not None
    parsed2 = client.parse_abacus_agent_json_response(text2)
    assert parsed2 is not None
    assert parsed2['action'] == 'BUY'


def test_without_credentials_returns_none_without_request(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.delenv('ABACUS_AGENT_API_KEY', raising=False)
    monkeypatch.delenv('ABACUS_AGENT_DEPLOYMENT_TOKEN', raising=False)

    def fail_post(*args, **kwargs):
        raise AssertionError('Não deveria chamar rede sem credenciais')

    monkeypatch.setattr(client.requests, 'post', fail_post)
    assert client.abacus_agent_chat('no-creds') is None


def test_http_error_sets_cooldown_and_returns_none(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv('ABACUS_AGENT_API_KEY', 'k_test')

    def fake_post(*args, **kwargs):
        return _DummyResponse(status_code=500, payload={}, text='server error')

    monkeypatch.setattr(client.requests, 'post', fake_post)
    out = client.abacus_agent_chat('http-fail')
    assert out is None
    assert client.is_abacus_agent_in_cooldown() is True


def test_timeout_returns_none(monkeypatch):
    _set_base_env(monkeypatch)
    monkeypatch.setenv('ABACUS_AGENT_API_KEY', 'k_test')

    def fake_post(*args, **kwargs):
        raise requests.Timeout('timeout')

    monkeypatch.setattr(client.requests, 'post', fake_post)
    out = client.abacus_agent_chat('timeout-fail')
    assert out is None
