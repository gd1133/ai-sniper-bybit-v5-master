"""Análise de notícias e sentimento de mercado com IA (Groq/Gemini) + fallbacks."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import urllib.parse

import requests

try:
    from groq import Groq
except Exception:
    Groq = None

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL_SECS = 300
_GROQ_FAIL_STREAK = 0


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _symbol_to_coin_id(symbol: str) -> str:
    raw = str(symbol or '').upper()
    raw = raw.replace('/USDT:USDT', '').replace('/USDT', '').replace(':USDT', '')
    return raw.replace('USDT', '').strip() or 'BTC'


def _scrapers_enabled() -> bool:
    """Scrapers externos OFF por padrão — não atrasam o ciclo técnico."""
    return _env_bool('ENABLE_NEWS_SCRAPERS', False) and _env_bool('ENABLE_NEWS_AI', False)


def _fetch_coingecko_trending() -> list[str]:
    """Moedas em alta no mundo crypto (proxy de interesse dos investidores)."""
    if not _scrapers_enabled():
        return []
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
    if not _scrapers_enabled():
        return {}
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


def _neutral_degraded_payload(reason: str) -> dict:
    """Sentimento neutro quando a IA cloud está em cooldown/degradada — nunca bloqueia."""
    return {
        'sentiment_score': 50,
        'global_trend': 'NEUTRAL',
        'news_risk': 'LOW',
        'investor_mood': 'NEUTRAL',
        'block_trade': False,
        'reason': reason,
        'ai_status': 'degradado',
        '_degraded': True,
    }


def _ai_analyze_with_groq(symbol: str, tech_summary: str, groq_key: str) -> dict | None:
    global _GROQ_FAIL_STREAK
    from src.intelligence.groq_client import get_groq_cooldown_info, is_groq_in_cooldown

    if not groq_key or Groq is None:
        return None
    now = time.time()
    in_cooldown = is_groq_in_cooldown()
    cooldown_info = get_groq_cooldown_info()
    # #region agent log
    try:
        from src.debug_agent_log import agent_dbg
        agent_dbg('B', 'news_analyzer.py:_ai_analyze_with_groq', 'groq_call_attempt', {
            'symbol': str(symbol)[:40],
            'cooldown_until': cooldown_info.get('until', 0),
            'in_cooldown': in_cooldown,
            'fail_streak': _GROQ_FAIL_STREAK,
        })
    except Exception:
        pass
    # #endregion
    # Cooldown: retorna NEUTRO (assistente degradado) — não erro/bloqueio
    if in_cooldown:
        return _neutral_degraded_payload(
            f'Groq em cooldown — sentimento NEUTRO para {symbol} (assistente degradado)'
        )
    try:
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
        from src.intelligence.groq_client import groq_chat_completion, log_groq_degraded
        result = groq_chat_completion(
            messages=[{'role': 'user', 'content': prompt}],
            purpose='news',
            temperature=0.2,
            max_tokens=300,
        )
        if not result.get('ok'):
            if not result.get('cooldown'):
                log_groq_degraded('NEWS AI', result, symbol=symbol)
            raise RuntimeError(result.get('error') or 'Groq news indisponível')
        text = (result.get('content') or '').strip()
        text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.IGNORECASE).strip()
        _GROQ_FAIL_STREAK = 0
        return json.loads(text)
    except Exception as exc:
        err = str(exc)
        is_429 = '429' in err or 'rate_limit' in err.lower() or 'cooldown' in err.lower()
        _GROQ_FAIL_STREAK += 1
        # Cooldown global é definido em groq_client.groq_chat_completion
        # #region agent log
        try:
            from src.debug_agent_log import agent_dbg
            from src.intelligence.groq_client import get_groq_cooldown_info
            agent_dbg('A', 'news_analyzer.py:_ai_analyze_with_groq', 'groq_call_failed', {
                'symbol': str(symbol)[:40],
                'is_429': is_429,
                'fail_streak': _GROQ_FAIL_STREAK,
                'cooldown_until': get_groq_cooldown_info().get('until', 0),
                'err_prefix': err[:120],
            })
        except Exception:
            pass
        # #endregion
        print(f'⚠️ [NEWS AI] Groq indisponível: {exc}', flush=True)
        return None


def _ai_analyze_with_gemini(symbol: str, tech_summary: str, gemini_key: str) -> dict | None:
    if not gemini_key:
        return None
    try:
        from src.intelligence.gemini_client import gemini_generate_content
        prompt = f"""Analise o contexto de mercado de {symbol} para decisão de trading.
{tech_summary}
Retorne JSON: sentiment_score (0-100), global_trend (BULLISH/BEARISH/NEUTRAL), news_risk (LOW/MEDIUM/HIGH), investor_mood, block_trade (bool), reason (pt-BR)."""
        result = gemini_generate_content(prompt, purpose='macro', temperature=0.2, max_tokens=280)
        if not result.get('ok'):
            return None
        text = re.sub(r'^```json\s*|\s*```$', '', (result.get('text') or '').strip(), flags=re.IGNORECASE)
        return json.loads(text)
    except Exception as exc:
        print(f'⚠️ [NEWS AI] Gemini indisponível: {exc}', flush=True)
        return None


def _fetch_web_headlines(coin: str, limit: int = 6) -> list[dict]:
    """
    Busca manchetes reais na web (Google News RSS) sobre a tendência da moeda.
    Desligado por padrão (ENABLE_NEWS_SCRAPERS / ENABLE_NEWS_AI).
    """
    if not _scrapers_enabled():
        return []
    headlines: list[dict] = []
    queries = [
        f'{coin} cryptocurrency OR crypto OR bitcoin OR USDT',
        f'{coin} crypto price trend',
    ]
    for q in queries:
        try:
            url = (
                'https://news.google.com/rss/search?'
                f'q={urllib.parse.quote(q)}&hl=en-US&gl=US&ceid=US:en'
            )
            rsp = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0 SniperBot/1.0'})
            if rsp.status_code != 200 or not rsp.text:
                continue
            # Parse RSS leve sem dependência externa
            items = re.findall(
                r'<item>\s*<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>',
                rsp.text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            for title in items:
                clean = re.sub(r'<[^>]+>', '', title).strip()
                clean = clean.replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
                if clean and clean.lower() not in {h['title'].lower() for h in headlines}:
                    headlines.append({'title': clean[:180], 'source': 'google_news'})
                if len(headlines) >= limit:
                    return headlines
        except Exception:
            continue
    return headlines


def _score_headlines_bias(headlines: list[dict], coin: str) -> tuple[float, str, list[str]]:
    """Heurística local de viés bullish/bearish nas manchetes (para Cérebro 3)."""
    if not headlines:
        return 0.0, 'NEUTRAL', []

    bull_kw = (
        'surge', 'soar', 'rally', 'bull', 'gain', 'pump', 'break', 'breakship',
        'adoption', 'record', 'high', 'upgrade', 'listing', 'unlock demand',
        'alta', 'sobe', 'valoriz', 'compra',
    )
    bear_kw = (
        'crash', 'dump', 'plunge', 'bear', 'hack', 'ban', 'sec lawsuit', 'fraud',
        'liquidation', 'collapse', 'down', 'selloff', 'risk', 'warning',
        'queda', 'cai', 'desvaloriz', 'fraude', 'hacke',
    )
    bull = 0
    bear = 0
    notes = []
    for h in headlines:
        t = str(h.get('title', '')).lower()
        if any(k in t for k in bull_kw):
            bull += 1
        if any(k in t for k in bear_kw):
            bear += 1
    delta = (bull - bear) * 8.0
    if bull > bear:
        notes.append(f'Web news {coin}: {bull} manchetes bullish vs {bear} bearish')
        return delta, 'BULLISH', notes
    if bear > bull:
        notes.append(f'Web news {coin}: {bear} manchetes bearish vs {bull} bullish')
        return delta, 'BEARISH', notes
    notes.append(f'Web news {coin}: {len(headlines)} manchetes sem viés claro')
    return 0.0, 'NEUTRAL', notes
def analyze_news_sentiment(
    symbol: str,
    signals: dict,
    regime: dict | None = None,
    whale: dict | None = None,
) -> dict[str, Any]:
    """Notícias cloud removidas — retorno neutro para o C3 Python local."""
    return {
        'sentiment_score': 50.0,
        'global_trend': 'NEUTRAL',
        'news_risk': 'LOW',
        'investor_mood': 'NEUTRAL',
        'block_trade': False,
        'is_trending': False,
        'reason': 'Notícias cloud removidas — Cérebro 3 decide só com técnica Python',
        'source': 'local_python',
        'ai_unavailable': False,
        'cloud_ai_degraded': False,
        'ai_status': 'removed',
        'headlines': [],
        'web_news_bias': 'NEUTRAL',
    }
