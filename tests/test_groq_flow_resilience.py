# -*- coding: utf-8 -*-
"""Groq cloud removido — stubs locais + fluxo order-book Python."""

from src.intelligence.groq_client import (
    DEFAULT_GROQ_MODEL,
    classify_groq_error,
    get_groq_model_chain,
    groq_chat_completion,
    is_groq_in_cooldown,
)
from src.intelligence.order_flow_analyzer import analyze_order_book_flow


def test_groq_model_chain_defaults():
    chain = get_groq_model_chain('flow')
    assert chain[0] == 'local-python'
    assert DEFAULT_GROQ_MODEL == 'local-python'


def test_classify_groq_error_always_disabled():
    assert classify_groq_error(Exception('model_not_found')) == 'disabled'
    assert classify_groq_error(Exception('403')) == 'disabled'


def test_groq_chat_always_disabled():
    result = groq_chat_completion(messages=[{'role': 'user', 'content': 'hi'}], purpose='flow')
    assert result.get('ok') is False
    assert result.get('disabled') is True
    assert is_groq_in_cooldown() is False


def test_order_flow_uses_local_python():
    book = {
        'bids': [[100.0, 2.0], [99.5, 1.0]],
        'asks': [[100.5, 1.5], [101.0, 1.0]],
    }
    out = analyze_order_book_flow('BTCUSDT', order_book=book, signals={'trend': 'ALTA'})
    assert out.get('available') is True or 'score_fluxo' in out
    reason = str(out.get('reason') or '')
    assert 'local' in reason.lower() or 'python' in reason.lower()
