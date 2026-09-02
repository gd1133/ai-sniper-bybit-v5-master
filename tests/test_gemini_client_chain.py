# -*- coding: utf-8 -*-
"""Cadeia Gemini v1beta — evita 404 em cascata."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch


def test_gemini_model_chain_defaults():
    from src.intelligence.gemini_client import DEFAULT_GEMINI_MODEL, get_gemini_model_chain

    with patch.dict(os.environ, {}, clear=False):
        for key in (
            'GEMINI_CHAT_MODEL', 'GEMINI_FLOW_MODEL',
            'GEMINI_MACRO_MODEL', 'GEMINI_C3_MODEL',
        ):
            os.environ.pop(key, None)
        chain = get_gemini_model_chain('chat')
    assert chain[0] == DEFAULT_GEMINI_MODEL
    assert chain[0] == 'gemini-2.0-flash'
    assert 'gemini-1.5-flash' in chain


def test_gemini_404_falls_through_to_next_model():
    from src.intelligence.gemini_client import gemini_generate_content

    rsp_404 = MagicMock(status_code=404)
    rsp_ok = MagicMock(status_code=200)
    rsp_ok.json.return_value = {
        'candidates': [{'content': {'parts': [{'text': 'ok'}]}}],
    }

    with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}):
        with patch('src.intelligence.gemini_client.requests.post', side_effect=[rsp_404, rsp_ok]) as mock_post:
            result = gemini_generate_content('hello', purpose='chat')
    assert result['ok'] is True
    assert result['text'] == 'ok'
    assert result['model'] == 'gemini-1.5-flash'
    assert mock_post.call_count == 2
