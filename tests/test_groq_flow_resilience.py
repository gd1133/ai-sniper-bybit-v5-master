# -*- coding: utf-8 -*-
"""Testes de resiliência Groq — modelo, fallback e continuidade com hard-gates OK."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


def test_groq_model_chain_defaults():
    from src.intelligence.groq_client import get_groq_model_chain, DEFAULT_GROQ_MODEL

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop('GROQ_FLOW_MODEL', None)
        os.environ.pop('GROQ_MODEL', None)
        os.environ.pop('GROQ_FALLBACK_MODELS', None)
        chain = get_groq_model_chain('flow')
    assert chain[0] == DEFAULT_GROQ_MODEL
    assert chain[0] == 'openai/gpt-oss-120b'
    assert 'openai/gpt-oss-20b' in chain
    # IDs aposentados NÃO devem aparecer direto na cadeia
    assert 'llama3-70b-8192' not in chain
    assert 'llama3-8b-8192' not in chain
    assert 'mixtral-8x7b-32768' not in chain
    assert 'llama-3.3-70b-versatile' not in chain
    assert 'llama-3.1-8b-instant' not in chain


def test_deprecated_llama3_remapped():
    from src.intelligence.groq_client import get_groq_model_chain

    with patch.dict(os.environ, {'GROQ_FLOW_MODEL': 'llama3-70b-8192'}):
        chain = get_groq_model_chain('flow')
        assert chain[0] == 'openai/gpt-oss-120b'

    with patch.dict(os.environ, {'GROQ_FLOW_MODEL': 'llama-3.3-70b-versatile'}):
        chain = get_groq_model_chain('flow')
        assert chain[0] == 'openai/gpt-oss-120b'

    with patch.dict(os.environ, {'GROQ_FLOW_MODEL': 'llama-3.1-8b-instant'}):
        chain = get_groq_model_chain('flow')
        assert chain[0] == 'openai/gpt-oss-20b'

    with patch.dict(os.environ, {'GROQ_FLOW_MODEL': 'mixtral-8x7b-32768'}):
        chain = get_groq_model_chain('flow')
        assert chain[0] == 'openai/gpt-oss-20b'


def test_classify_groq_error_model_not_found():
    from src.intelligence.groq_client import classify_groq_error

    exc = Exception("Error code: 404 - model_not_found")
    assert classify_groq_error(exc) == 'model_not_found'


def test_classify_groq_error_no_access():
    from src.intelligence.groq_client import classify_groq_error

    exc = Exception("Error code: 403 - permission denied, you do not have access")
    assert classify_groq_error(exc) == 'no_access'


def test_groq_chat_tries_fallback_on_404():
    from src.intelligence import groq_client

    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs.get('model'))
        if kwargs.get('model') == 'bad-model':
            raise Exception('404 model_not_found')
        rsp = MagicMock()
        rsp.choices = [MagicMock(message=MagicMock(content='{"score_fluxo": 0.5}'))]
        return rsp

    mock_client = MagicMock()
    mock_client.chat.completions.create = fake_create

    with patch.dict(os.environ, {
        'GROQ_API_KEY': 'test-key',
        'GROQ_FLOW_MODEL': 'bad-model',
        'GROQ_FALLBACK_MODELS': 'openai/gpt-oss-20b',
        'ENABLE_GEMINI_FLOW_FALLBACK': 'false',
    }):
        import importlib
        importlib.reload(groq_client)
        with patch.object(groq_client, 'Groq', return_value=mock_client):
            result = groq_client.groq_chat_completion(
                [{'role': 'user', 'content': 'test'}],
                purpose='flow',
            )
    assert result.get('ok') is True
    assert 'openai/gpt-oss-20b' in result.get('model', '')


def test_groq_key_disabled_after_all_no_access():
    """Se todos os modelos retornam 403, _groq_key_disabled fica True."""
    from src.intelligence import groq_client

    def fake_create(**kwargs):
        raise Exception("403 permission denied")

    mock_client = MagicMock()
    mock_client.chat.completions.create = fake_create

    with patch.dict(os.environ, {
        'GROQ_API_KEY': 'test-key',
        'GROQ_FLOW_MODEL': 'openai/gpt-oss-120b',
        'GROQ_FALLBACK_MODELS': 'openai/gpt-oss-20b',
        'ENABLE_GEMINI_FLOW_FALLBACK': 'false',
    }):
        import importlib
        importlib.reload(groq_client)
        groq_client._groq_key_disabled = False  # reset
        with patch.object(groq_client, 'Groq', return_value=mock_client):
            result = groq_client.groq_chat_completion(
                [{'role': 'user', 'content': 'test'}],
                purpose='flow',
            )
    assert result.get('ok') is False
    assert groq_client._groq_key_disabled is True


def test_groq_chat_completion_flow_with_hard_gates_ok():
    """Pipeline de flow não trava quando Groq indisponível (hard-gates OK)."""
    from src.intelligence import groq_client

    def fake_create(**kwargs):
        raise Exception("404 model_not_found")

    mock_client = MagicMock()
    mock_client.chat.completions.create = fake_create

    with patch.dict(os.environ, {
        'GROQ_API_KEY': 'test-key',
        'ENABLE_GEMINI_FLOW_FALLBACK': 'false',
    }):
        import importlib
        importlib.reload(groq_client)
        groq_client._groq_key_disabled = False
        with patch.object(groq_client, 'Groq', return_value=mock_client):
            result = groq_client.groq_chat_completion(
                [{'role': 'user', 'content': 'test'}],
                purpose='flow',
            )
    # Deve retornar sem lançar exceção; ok=False é aceitável (fallback local C3)
    assert isinstance(result, dict)
    assert 'ok' in result


def test_market_intelligence_module_importable():
    """market_intelligence importa sem exceção mesmo com keys ausentes."""
    import importlib
    with patch.dict(os.environ, {
        'GROQ_API_KEY': '',
        'GEMINI_API_KEY': '',
        'ENABLE_NEWS_AI': 'false',
        'ENABLE_GEMINI_MACRO_AI': 'false',
    }):
        from src.intelligence import market_intelligence
        importlib.reload(market_intelligence)
        assert hasattr(market_intelligence, 'MarketIntelligence')
