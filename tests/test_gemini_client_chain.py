# -*- coding: utf-8 -*-
"""Gemini cloud removido — stubs locais."""

from src.intelligence.gemini_client import (
    DEFAULT_GEMINI_MODEL,
    gemini_generate_content,
    get_gemini_api_key,
    get_gemini_model_chain,
)


def test_gemini_model_chain_defaults():
    chain = get_gemini_model_chain('chat')
    assert chain[0] == 'local-python'
    assert DEFAULT_GEMINI_MODEL == 'local-python'
    assert get_gemini_api_key() == ''


def test_gemini_generate_content_disabled():
    result = gemini_generate_content('hello', purpose='flow')
    assert result.get('ok') is False
    assert result.get('disabled') is True
    assert 'local' in str(result.get('error') or '').lower() or 'removido' in str(result.get('error') or '').lower()
