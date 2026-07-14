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
_GROQ_COOLDOWN_UNTIL = 0.0  # instrumentation / future cooldown gate
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
    global _GROQ_FAIL_STREAK, _GROQ_COOLDOWN_UNTIL
    if not groq_key or Groq is None:
        return None
    now = time.time()
    in_cooldown = now < _GROQ_COOLDOWN_UNTIL
    # #region agent log
    try:
        from src.debug_agent_log import agent_dbg
        agent_dbg('B', 'news_analyzer.py:_ai_analyze_with_groq', 'groq_call_attempt', {
            'symbol': str(symbol)[:40],
            'cooldown_until': _GROQ_COOLDOWN_UNTIL,
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
        _GROQ_FAIL_STREAK = 0
        return json.loads(text)
    except Exception as exc:
        err = str(exc)
        is_429 = '429' in err or 'rate_limit' in err.lower()
        _GROQ_FAIL_STREAK += 1
        if is_429:
            # ~3 min default; tenta extrair "try again in XmYs" se existir
            wait_secs = 180.0
            m = re.search(r'try again in\s+(\d+)m([\d.]+)s', err, flags=re.IGNORECASE)
            if m:
                wait_secs = int(m.group(1)) * 60 + float(m.group(2))
            else:
                m2 = re.search(r'try again in\s+([\d.]+)s', err, flags=re.IGNORECASE)
                if m2:
                    wait_secs = float(m2.group(1))
            _GROQ_COOLDOWN_UNTIL = time.time() + max(60.0, wait_secs)
        # #region agent log
        try:
            from src.debug_agent_log import agent_dbg
            agent_dbg('A', 'news_analyzer.py:_ai_analyze_with_groq', 'groq_call_failed', {
                'symbol': str(symbol)[:40],
                'is_429': is_429,
                'fail_streak': _GROQ_FAIL_STREAK,
                'cooldown_until': _GROQ_COOLDOWN_UNTIL,
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


def _fetch_web_headlines(coin: str, limit: int = 6) -> list[dict]:
    """
    Busca manchetes reais na web (Google News RSS) sobre a tendência da moeda.
    Sem API key — falha silenciosa se offline.
    """
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
    """
    Combina trending global, sentimento CoinGecko, manchetes web e IA (Groq/Gemini).
    """
    # Desligado por padrão: notícias atrasam o radar e NÃO devem travar entradas.
    if not _env_bool('ENABLE_NEWS_AI', False):
        return {
            'sentiment_score': 50.0,
            'global_trend': 'NEUTRAL',
            'news_risk': 'LOW',
            'investor_mood': 'NEUTRAL',
            'block_trade': False,
            'is_trending': False,
            'reason': 'Análise de notícias desativada — Cérebro 3 decide só com técnica',
            'source': 'disabled',
            'ai_unavailable': False,
            'cloud_ai_degraded': False,
            'ai_status': 'disabled',
            'headlines': [],
            'web_news_bias': 'NEUTRAL',
        }

    coin = _symbol_to_coin_id(symbol)
    cache_key = coin
    now = time.time()
    if cache_key in _CACHE and (now - _CACHE[cache_key][0]) < _CACHE_TTL_SECS:
        return _CACHE[cache_key][1]

    trending = _fetch_coingecko_trending()
    is_trending = coin in trending
    cg_data = _fetch_coingecko_sentiment(coin)
    headlines = _fetch_web_headlines(coin)
    web_delta, web_bias, web_notes = _score_headlines_bias(headlines, coin)

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

    # Manchetes web → Cérebro 3
    score += web_delta
    reasons.extend(web_notes)
    if web_bias == 'BULLISH' and global_trend == 'NEUTRAL':
        global_trend = 'BULLISH'
    elif web_bias == 'BEARISH':
        if global_trend == 'NEUTRAL':
            global_trend = 'BEARISH'
        news_risk = 'HIGH' if news_risk == 'LOW' else news_risk
        if str(signals.get('trend', '')).upper() == 'ALTA' and web_delta <= -8:
            block_trade = True
            reasons.append('Conflito: tendência técnica de alta vs notícias web negativas')

    headline_block = '\n'.join(f'- {h["title"]}' for h in headlines[:5]) or '- (sem manchetes)'
    tech_summary = (
        f"Symbol: {symbol}\n"
        f"Trend: {signals.get('trend')}\n"
        f"RSI: {signals.get('rsi')}\n"
        f"Volume ratio: {signals.get('volume_ratio')}\n"
        f"Heat: {signals.get('heat_score')} bias={signals.get('heat_bias')}\n"
        f"Regime: {(regime or {}).get('market_regime')} lateral={((regime or {}).get('is_lateral'))}\n"
        f"Whale score: {(whale or {}).get('whale_score')} aligned={(whale or {}).get('whale_aligned')}\n"
        f"Trending coins: {', '.join(trending[:5])}\n"
        f"Web headlines:\n{headline_block}"
    )

    ai_result = None
    source = 'coingecko+web' if headlines else 'coingecko'
    ai_unavailable = False
    cloud_attempted = False
    cloud_degraded = False
    ai_status = 'ok'
    groq_key = os.getenv('GROQ_API_KEY', '').strip()
    gemini_key = os.getenv('GEMINI_API_KEY', '').strip()

    if groq_key:
        cloud_attempted = True
        ai_result = _ai_analyze_with_groq(symbol, tech_summary, groq_key)
        if ai_result is not None and not ai_result.get('_degraded'):
            source = 'groq+web'
        elif ai_result is not None and ai_result.get('_degraded'):
            cloud_degraded = True
            ai_status = 'degradado'
            source = 'web_local' if headlines else 'local_sentiment'
    if (ai_result is None or ai_result.get('_degraded')) and gemini_key:
        cloud_attempted = True
        gemini_result = _ai_analyze_with_gemini(symbol, tech_summary, gemini_key)
        if gemini_result is not None:
            ai_result = gemini_result
            cloud_degraded = False
            ai_status = 'ok'
            source = 'gemini+web'

    if cloud_attempted and (ai_result is None or ai_result.get('_degraded')):
        # Cloud (Groq/Gemini) em cooldown/falha — NEUTRO, NUNCA bloqueia.
        # Cérebro 3 permanece soberano na decisão técnica.
        cloud_degraded = True
        ai_status = 'degradado'
        source = 'web_local' if headlines else 'local_sentiment'
        reasons.append('Cloud news (Groq/Gemini) indisponível — sentimento NEUTRO (assistente)')
        ai_unavailable = False
        # #region agent log
        try:
            from src.debug_agent_log import agent_dbg
            agent_dbg('A', 'news_analyzer.py:analyze_news_sentiment', 'set_ai_unavailable', {
                'symbol': str(symbol)[:40],
                'has_headlines': bool(headlines),
                'source': source,
                'fail_streak': _GROQ_FAIL_STREAK,
                'ai_unavailable': False,
                'cloud_degraded': True,
                'ai_status': 'degradado',
            })
        except Exception:
            pass
        # #endregion

    if ai_result and not ai_result.get('_degraded') and not cloud_degraded:
        ai_score = float(ai_result.get('sentiment_score', 50) or 50)
        score = (score * 0.4) + (ai_score * 0.6)
        global_trend = str(ai_result.get('global_trend', global_trend)).upper()
        news_risk = str(ai_result.get('news_risk', news_risk)).upper()
        investor_mood = str(ai_result.get('investor_mood', investor_mood)).upper()
        # Assistente: block_trade da IA cloud NUNCA vira veto de entrada
        ai_reason = str(ai_result.get('reason', '')).strip()
        if ai_reason:
            reasons.append(f'IA: {ai_reason}')
        if ai_result.get('block_trade'):
            reasons.append('IA sugeriu cautela (informativo — sem bloqueio)')

    # Cooldown / degradação: força NEUTRO e libera trade
    if cloud_degraded or ai_status == 'degradado' or (now < _GROQ_COOLDOWN_UNTIL and not gemini_key):
        global_trend = 'NEUTRAL'
        investor_mood = 'NEUTRAL'
        news_risk = 'LOW'
        score = 50.0
        block_trade = False
        ai_status = 'degradado'
        cloud_degraded = True

    trend = str(signals.get('trend', 'NEUTRO')).upper()
    if not cloud_degraded and not ai_unavailable:
        if global_trend == 'BEARISH' and trend == 'ALTA':
            score -= 10
            news_risk = 'HIGH'
        elif global_trend == 'BULLISH' and trend == 'BAIXA':
            score -= 10
            news_risk = 'HIGH'

    # Assistente de notícias: nunca bloqueia entradas — Cérebro 3 decide
    block_trade = False

    result = {
        'sentiment_score': round(max(0.0, min(100.0, score)), 2),
        'global_trend': global_trend,
        'news_risk': news_risk,
        'investor_mood': investor_mood,
        'block_trade': block_trade,
        'is_trending': is_trending,
        'reason': ' | '.join(reasons) if reasons else 'Sem catalisadores de notícia relevantes',
        'source': source,
        'ai_unavailable': ai_unavailable,
        'cloud_ai_degraded': cloud_degraded,
        'ai_status': ai_status,
        'headlines': headlines[:6],
        'web_news_bias': 'NEUTRAL' if cloud_degraded else web_bias,
    }
    _CACHE[cache_key] = (now, result)
    return result
