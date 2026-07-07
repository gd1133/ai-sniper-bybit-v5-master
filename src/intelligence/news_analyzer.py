"""Análise de notícias e sentimento de mercado com IA (Groq/Gemini) + fallbacks."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

try:
    from groq import Groq
except Exception:
    Groq = None

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL_SECS = 300


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _symbol_to_coin_id(symbol: str) -> str:
    raw = str(symbol or '').upper()
    raw = raw.replace('/USDT:USDT', '').replace('/USDT', '').replace(':USDT', '')
    return raw.replace('USDT', '').strip() or 'BTC'


def _fetch_coingecko_trending() -> list[str]:
    """Moedas em alta no mundo crypto (proxy de interesse dos investidores)."""
    try:
        rsp = requests.get(
            'https://api.coingecko.com/api/v3/search/trending',
            timeout=8,
        )
        if rsp.status_code != 200:
            return []
        data = rsp.json() or {}
        coins = []
        for item in (data.get('coins') or [])[:15]:
            coin = (item.get('item') or {})
            symbol = str(coin.get('symbol', '')).upper()
            if symbol:
                coins.append(symbol)
        return coins
    except Exception:
        return []


def _fetch_coingecko_sentiment(coin_id: str) -> dict:
    """Sentimento da comunidade CoinGecko (up/down votes)."""
    try:
        rsp = requests.get(
            f'https://api.coingecko.com/api/v3/coins/{coin_id.lower()}',
            params={'localization': 'false', 'tickers': 'false', 'community_data': 'true', 'developer_data': 'false'},
            timeout=8,
        )
        if rsp.status_code != 200:
            return {}
        data = rsp.json() or {}
        community = data.get('community_data') or {}
        sentiment_up = float(community.get('sentiment_votes_up_percentage', 50) or 50)
        market_cap_rank = int(data.get('market_cap_rank', 999) or 999)
        return {
            'sentiment_up_pct': sentiment_up,
            'market_cap_rank': market_cap_rank,
            'name': str(data.get('name', coin_id)),
        }
    except Exception:
        return {}


def _ai_analyze_with_groq(symbol: str, tech_summary: str, groq_key: str) -> dict | None:
    if not groq_key or Groq is None:
        return None
    try:
        client = Groq(api_key=groq_key)
        prompt = f"""Você é analista institucional de criptomoedas. Avalie {symbol} para trading de futuros.

Dados técnicos e de fluxo:
{tech_summary}

Responda APENAS em JSON válido:
{{
  "sentiment_score": 0-100,
  "global_trend": "BULLISH|BEARISH|NEUTRAL",
  "news_risk": "LOW|MEDIUM|HIGH",
  "investor_mood": "FOMO|FEAR|NEUTRAL|ACCUMULATION",
  "block_trade": false,
  "reason": "resumo em português de 1-2 frases"
}}"""
        rsp = client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.2,
            max_tokens=300,
        )
        text = (rsp.choices[0].message.content or '').strip()
        text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.IGNORECASE).strip()
        return json.loads(text)
    except Exception as exc:
        print(f'⚠️ [NEWS AI] Groq indisponível: {exc}', flush=True)
        return None


def _ai_analyze_with_gemini(symbol: str, tech_summary: str, gemini_key: str) -> dict | None:
    if not gemini_key:
        return None
    try:
        url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'gemini-2.0-flash:generateContent?key={gemini_key}'
        )
        prompt = f"""Analise o contexto de mercado de {symbol} para decisão de trading.
{tech_summary}
Retorne JSON: sentiment_score (0-100), global_trend (BULLISH/BEARISH/NEUTRAL), news_risk (LOW/MEDIUM/HIGH), investor_mood, block_trade (bool), reason (pt-BR)."""
        rsp = requests.post(
            url,
            json={'contents': [{'parts': [{'text': prompt}]}]},
            timeout=15,
        )
        if rsp.status_code != 200:
            return None
        text = (
            ((rsp.json() or {}).get('candidates') or [{}])[0]
            .get('content', {})
            .get('parts', [{}])[0]
            .get('text', '')
        )
        text = re.sub(r'^```json\s*|\s*```$', '', text.strip(), flags=re.IGNORECASE)
        return json.loads(text)
    except Exception as exc:
        print(f'⚠️ [NEWS AI] Gemini indisponível: {exc}', flush=True)
        return None


def analyze_news_sentiment(
    symbol: str,
    signals: dict,
    regime: dict | None = None,
    whale: dict | None = None,
) -> dict[str, Any]:
    """
    Combina trending global, sentimento CoinGecko e IA (Groq/Gemini).
    """
    if not _env_bool('ENABLE_NEWS_AI', True):
        return {
            'sentiment_score': 50.0,
            'global_trend': 'NEUTRAL',
            'news_risk': 'LOW',
            'investor_mood': 'NEUTRAL',
            'block_trade': False,
            'is_trending': False,
            'reason': 'Análise de notícias desativada',
            'source': 'disabled',
        }

    coin = _symbol_to_coin_id(symbol)
    cache_key = coin
    now = time.time()
    if cache_key in _CACHE and (now - _CACHE[cache_key][0]) < _CACHE_TTL_SECS:
        return _CACHE[cache_key][1]

    trending = _fetch_coingecko_trending()
    is_trending = coin in trending
    cg_data = _fetch_coingecko_sentiment(coin)

    score = 50.0
    reasons = []
    global_trend = 'NEUTRAL'
    news_risk = 'LOW'
    investor_mood = 'NEUTRAL'
    block_trade = False

    if is_trending:
        score += 20
        reasons.append(f'{coin} em alta no radar global dos investidores')
        investor_mood = 'FOMO'

    sentiment_up = float(cg_data.get('sentiment_up_pct', 50) or 50)
    if sentiment_up >= 65:
        score += 15
        global_trend = 'BULLISH'
        reasons.append(f'Sentimento positivo da comunidade ({sentiment_up:.0f}% bullish)')
    elif sentiment_up <= 35:
        score -= 15
        global_trend = 'BEARISH'
        news_risk = 'MEDIUM'
        reasons.append(f'Sentimento negativo ({sentiment_up:.0f}% bullish)')
        if str(signals.get('trend', '')).upper() == 'ALTA':
            block_trade = True
            reasons.append('Conflito: técnica alta vs sentimento negativo global')

    rank = int(cg_data.get('market_cap_rank', 999) or 999)
    if rank <= 20:
        score += 10
        reasons.append(f'Top {rank} market cap — liquidez institucional')

    tech_summary = (
        f"Symbol: {symbol}\n"
        f"Trend: {signals.get('trend')}\n"
        f"RSI: {signals.get('rsi')}\n"
        f"Volume ratio: {signals.get('volume_ratio')}\n"
        f"Regime: {(regime or {}).get('market_regime')} lateral={((regime or {}).get('is_lateral'))}\n"
        f"Whale score: {(whale or {}).get('whale_score')} aligned={(whale or {}).get('whale_aligned')}\n"
        f"Trending coins: {', '.join(trending[:5])}"
    )

    ai_result = None
    source = 'coingecko'
    groq_key = os.getenv('GROQ_API_KEY', '').strip()
    gemini_key = os.getenv('GEMINI_API_KEY', '').strip()

    if groq_key:
        ai_result = _ai_analyze_with_groq(symbol, tech_summary, groq_key)
        source = 'groq'
    if ai_result is None and gemini_key:
        ai_result = _ai_analyze_with_gemini(symbol, tech_summary, gemini_key)
        source = 'gemini'

    if ai_result:
        ai_score = float(ai_result.get('sentiment_score', 50) or 50)
        score = (score * 0.4) + (ai_score * 0.6)
        global_trend = str(ai_result.get('global_trend', global_trend)).upper()
        news_risk = str(ai_result.get('news_risk', news_risk)).upper()
        investor_mood = str(ai_result.get('investor_mood', investor_mood)).upper()
        if ai_result.get('block_trade'):
            block_trade = True
        ai_reason = str(ai_result.get('reason', '')).strip()
        if ai_reason:
            reasons.append(f'IA: {ai_reason}')

    trend = str(signals.get('trend', 'NEUTRO')).upper()
    if global_trend == 'BEARISH' and trend == 'ALTA':
        score -= 10
        news_risk = 'HIGH'
    elif global_trend == 'BULLISH' and trend == 'BAIXA':
        score -= 10
        news_risk = 'HIGH'

    result = {
        'sentiment_score': round(max(0.0, min(100.0, score)), 2),
        'global_trend': global_trend,
        'news_risk': news_risk,
        'investor_mood': investor_mood,
        'block_trade': block_trade,
        'is_trending': is_trending,
        'reason': ' | '.join(reasons) if reasons else 'Sem catalisadores de notícia relevantes',
        'source': source,
    }
    _CACHE[cache_key] = (now, result)
    return result
