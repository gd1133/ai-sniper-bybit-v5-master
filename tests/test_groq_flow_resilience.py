# -*- coding: utf-8 -*-
"""Testes de resiliência Groq — modelo, fallback e continuidade com hard-gates OK."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _disable_c3_solo(monkeypatch):
    """Estes testes validam fluxo Groq/C1/C2 — fora do modo C3 solo."""
    monkeypatch.setenv('C3_SOLO_MODE', 'false')


def test_groq_model_chain_defaults():
    from src.intelligence.groq_client import get_groq_model_chain, DEFAULT_GROQ_MODEL

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop('GROQ_FLOW_MODEL', None)
        os.environ.pop('GROQ_MODEL', None)
        os.environ.pop('GROQ_FALLBACK_MODELS', None)
        chain = get_groq_model_chain('flow')
        assert chain[0] == DEFAULT_GROQ_MODEL
        assert chain[0] == 'openai/gpt-oss-120b'
        assert 'llama-3.3-70b-versatile' not in chain
        assert 'openai/gpt-oss-20b' in chain
        assert 'qwen/qwen3.6-27b' in chain
        assert 'llama3-70b-8192' not in chain


def test_deprecated_llama_model_is_remapped():
    from src.intelligence.groq_client import get_groq_model_chain

    with patch.dict(os.environ, {'GROQ_FLOW_MODEL': 'llama3-70b-8192'}):
        chain = get_groq_model_chain('flow')
        assert chain[0] == 'openai/gpt-oss-120b'


def test_classify_groq_error_model_not_found():
    from src.intelligence.groq_client import classify_groq_error

    exc = Exception("Error code: 404 - model_not_found")
    assert classify_groq_error(exc) == 'model_not_found'


def test_groq_chat_tries_fallback_on_404():
    from src.intelligence import groq_client

    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs.get('model'))
        if kwargs.get('model') == 'openai/gpt-oss-120b':
            raise Exception('404 model_not_found')
        rsp = MagicMock()
        rsp.choices = [MagicMock(message=MagicMock(content='{"score_fluxo": 0.5}'))]
        return rsp

    mock_client = MagicMock()
    mock_client.chat.completions.create = fake_create

    with patch.dict(os.environ, {
        'GROQ_API_KEY': 'test-key',
        'GROQ_FLOW_MODEL': 'openai/gpt-oss-120b',
        'GROQ_FALLBACK_MODELS': 'openai/gpt-oss-20b',
    }):
        with patch.object(groq_client, 'Groq', return_value=mock_client):
            result = groq_client.groq_chat_completion(
                messages=[{'role': 'user', 'content': 'test'}],
                purpose='flow',
            )
    assert result['ok'] is True
    assert 'openai/gpt-oss-120b' in calls
    assert 'openai/gpt-oss-20b' in calls


def test_groq_cooldown_blocks_repeat_calls():
    from src.intelligence import groq_client

    groq_client._groq_cooldown_until = 0.0
    groq_client._groq_cooldown_logged_until = 0.0
    groq_client.set_groq_cooldown(3600, 'TPD esgotado', error_msg='429 tokens per day')

    with patch.dict(os.environ, {'GROQ_API_KEY': 'test-key'}):
        with patch.object(groq_client, 'Groq') as mock_groq_cls:
            result = groq_client.groq_chat_completion(
                messages=[{'role': 'user', 'content': 'test'}],
                purpose='flow',
            )
    assert result['ok'] is False
    assert result.get('cooldown') is True
    assert groq_client.is_groq_in_cooldown() is True
    mock_groq_cls.assert_not_called()
    groq_client._groq_cooldown_until = 0.0
    groq_client._groq_cooldown_logged_until = 0.0


def test_groq_tpd_sets_long_cooldown():
    from src.intelligence.groq_client import cooldown_secs_for_rate_limit, is_groq_tpd_error

    exc = Exception(
        "Error code: 429 - Rate limit reached for service tier 'on_demand' "
        "on tokens per day (TPD): Limit 2000"
    )
    assert is_groq_tpd_error(exc) is True
    assert cooldown_secs_for_rate_limit(exc) >= 3600.0


def test_order_flow_skips_groq_without_hard_gates():
    from src.intelligence.order_flow_analyzer import analyze_order_book_flow

    order_book = {
        'bids': [['1.0', '100'], ['0.99', '50']],
        'asks': [['1.01', '30'], ['1.02', '20']],
    }
    signals = {'trend': 'ALTA', 'volume_ratio': 1.8}

    with patch.dict(os.environ, {'GROQ_API_KEY': 'k', 'ENABLE_GROQ_FLOW_AI': 'true'}):
        with patch(
            'src.intelligence.order_flow_analyzer.groq_chat_completion',
        ) as mock_groq:
            flow = analyze_order_book_flow(
                'BTC/USDT',
                order_book=order_book,
                signals=signals,
                hard_gates_approved=False,
            )
    mock_groq.assert_not_called()
    assert flow.get('available') is True
    assert flow.get('groq_degraded') is True


def test_order_flow_fallback_when_groq_fails():
    from src.intelligence.order_flow_analyzer import analyze_order_book_flow

    order_book = {
        'bids': [['1.0', '100'], ['0.99', '50']],
        'asks': [['1.01', '30'], ['1.02', '20']],
    }
    signals = {'trend': 'ALTA', 'volume_ratio': 1.8, 'sinal_institucional': 'COMPRA'}

    with patch.dict(os.environ, {'GROQ_API_KEY': 'k', 'ENABLE_GROQ_FLOW_AI': 'true'}):
        with patch(
            'src.intelligence.order_flow_analyzer._call_groq_flow',
            return_value=None,
        ):
            with patch(
                'src.intelligence.order_flow_analyzer._gemini_flow_fallback',
                return_value=None,
            ):
                flow = analyze_order_book_flow(
                    'ONDO/USDT',
                    order_book=order_book,
                    signals=signals,
                    hard_gates_approved=True,
                )

    assert flow.get('available') is True
    assert flow.get('groq_degraded') is True
    assert flow.get('source') in ('local_order_book', 'technical_gates', 'local_volume')


def test_market_intel_allows_entry_when_groq_degraded_no_hard_veto():
    from src.intelligence.market_intelligence import MarketIntelligence
    import pandas as pd

    mi = MarketIntelligence()
    df = pd.DataFrame({'close': [1, 2, 3, 4, 5]})
    signals = {
        'trend': 'ALTA',
        'sinal_institucional': 'COMPRA',
        'is_lateral': False,
        'volume_ratio': 2.0,
        'adx': 30,
    }
    degraded_flow = {
        'score_fluxo': 0.1,
        'forca_agressao': 40,
        'source': 'local_order_book',
        'available': True,
        'groq_degraded': True,
    }

    with patch('src.intelligence.market_intelligence.detect_market_regime') as mock_regime:
        mock_regime.return_value = {
            'market_regime': 'TRENDING',
            'regime_label': 'Tendência',
            'is_lateral': False,
            'adx': 30,
            'choppiness': 40,
            'lateral_score': 30,
            'amplitude_lateral': False,
            'bollinger_expanding': True,
        }
        with patch('src.intelligence.market_intelligence.analyze_whale_activity') as mock_whale:
            mock_whale.return_value = {
                'whale_score': 60,
                'whale_aligned': True,
                'reasons': [],
            }
            with patch('src.intelligence.market_intelligence.analyze_news_sentiment') as mock_news:
                mock_news.return_value = {
                    'headlines': [],
                    'global_trend': 'NEUTRAL',
                    'news_risk': 'LOW',
                    'reason': 'ok',
                    'source': 'web',
                    'ai_status': 'disabled',
                }
                with patch('src.intelligence.market_intelligence.analyze_order_book_flow') as mock_flow:
                    mock_flow.return_value = degraded_flow
                    with patch('src.intelligence.market_intelligence.analyze_gemini_macro_news') as mock_gem:
                        mock_gem.return_value = {
                            'score_sentimento_noticias': 0.0,
                            'filtro_noticia_travar_bot': False,
                            'impacto_volatilidade': 'BAIXO',
                        }
                        ctx = mi.evaluate('ONDO/USDT', df, signals)

    assert ctx.get('groq_flow_degraded') is True
    assert ctx.get('allow_entry') is True
    assert ctx.get('ai_assistants_unavailable') is False
    assert ctx.get('autonomous_mode') is False
