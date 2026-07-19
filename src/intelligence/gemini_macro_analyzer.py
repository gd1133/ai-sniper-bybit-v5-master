# -*- coding: utf-8 -*-
"""
Subsistema Gemini — inteligência macro e sentimento de notícias.

Incremental: convive com analyze_news_sentiment() (não substitui).
JSON estrito para o Cérebro 3 (peso ~10%).
filtro_noticia_travar_bot é INFORMÁTIVO por padrão (assistente);
hard-veto só com ALLOW_NEWS_HARD_VETO=true.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 180.0

GEMINI_MACRO_SYSTEM = """Você é o subsistema de inteligência macro e análise de sentimento do Motor Sniper. Sua função é ler o bloco de notícias textuais fornecido e avaliar o impacto fundamentalista no mercado de criptomoedas nas próximas horas.

Retorne EXCLUSIVAMENTE um objeto JSON válido, sem markdown ou blocos de código, com a seguinte estrutura:
{
  "score_sentimento_noticias": -1.0 a 1.0,
  "impacto_volatilidade": "ALTO"/"MEDIO"/"BAIXO",
  "narrativa_dominante": "string curta descrevendo o gatilho atual do mercado",
  "filtro_noticia_travar_bot": true/false
}"""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _neutral_macro(reason: str = 'macro neutro') -> dict[str, Any]:
    return {
        'score_sentimento_noticias': 0.0,
        'impacto_volatilidade': 'BAIXO',
        'narrativa_dominante': reason,
        'filtro_noticia_travar_bot': False,
        'source': 'neutral',
        'available': False,
    }


def _parse_macro_json(text: str) -> dict | None:
    text = (text or '').strip()
    text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(text)
    except Exception:
        m = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    try:
        score = float(data.get('score_sentimento_noticias', 0) or 0)
        score = max(-1.0, min(1.0, score))
        impacto = str(data.get('impacto_volatilidade', 'BAIXO') or 'BAIXO').upper()
        if impacto not in ('ALTO', 'MEDIO', 'BAIXO'):
            impacto = 'BAIXO'
        return {
            'score_sentimento_noticias': score,
            'impacto_volatilidade': impacto,
            'narrativa_dominante': str(data.get('narrativa_dominante', '') or '')[:180],
            'filtro_noticia_travar_bot': bool(data.get('filtro_noticia_travar_bot', False)),
            'source': 'gemini',
            'available': True,
        }
    except (TypeError, ValueError):
        return None


def analyze_gemini_macro_news(
    symbol: str,
    headlines: list | None = None,
    news_blob: str = '',
    signals: dict | None = None,
) -> dict[str, Any]:
    """
    Gemini macro JSON. Se ENABLE_GEMINI_MACRO_AI=false ou sem chave → neutro.
    """
    if not _env_bool('ENABLE_GEMINI_MACRO_AI', True):
        return _neutral_macro('Gemini macro desativado')

    gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not gemini_key:
        return _neutral_macro('GEMINI_API_KEY ausente')

    titles = []
    for h in (headlines or [])[:8]:
        if isinstance(h, dict):
            t = str(h.get('title') or '').strip()
            if t:
                titles.append(t)
        elif h:
            titles.append(str(h)[:120])

    blob = news_blob.strip() or '\n'.join(f'- {t}' for t in titles) or '- (sem manchetes)'
    cache_key = f"{symbol}:{hash(blob) % 10_000_000}"
    now = time.time()
    if cache_key in _CACHE and (now - _CACHE[cache_key][0]) < _CACHE_TTL:
        return _CACHE[cache_key][1]

    sig = signals or {}
    user_payload = (
        f'{GEMINI_MACRO_SYSTEM}\n\n'
        f'Símbolo: {symbol}\n'
        f'Tendência técnica: {sig.get("trend")}\n'
        f'Regime: {sig.get("market_regime")}\n'
        f'Bloco de notícias:\n{blob}'
    )
    try:
        model = os.getenv('GEMINI_MACRO_MODEL', 'gemini-2.0-flash')
        url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'{model}:generateContent?key={gemini_key}'
        )
        rsp = requests.post(
            url,
            json={
                'contents': [{'parts': [{'text': user_payload}]}],
                'generationConfig': {'temperature': 0.15, 'maxOutputTokens': 280},
            },
            timeout=15,
        )
        if rsp.status_code != 200:
            out = _neutral_macro(f'Gemini HTTP {rsp.status_code}')
            _CACHE[cache_key] = (now, out)
            return out
        text = (
            ((rsp.json() or {}).get('candidates') or [{}])[0]
            .get('content', {})
            .get('parts', [{}])[0]
            .get('text', '')
        )
        parsed = _parse_macro_json(text)
        if parsed:
            # Hard-veto só se explicitamente permitido (preserva regra assistente)
            if parsed.get('filtro_noticia_travar_bot') and not _env_bool('ALLOW_NEWS_HARD_VETO', False):
                parsed['filtro_noticia_travar_bot_sugerido'] = True
                parsed['filtro_noticia_travar_bot'] = False
                parsed['narrativa_dominante'] = (
                    f"{parsed.get('narrativa_dominante', '')} "
                    f"[alerta sistêmico — soft, hard-veto off]"
                ).strip()
            _CACHE[cache_key] = (now, parsed)
            return parsed
    except Exception as exc:
        print(f'⚠️ [GEMINI MACRO] indisponível: {exc}', flush=True)

    out = _neutral_macro('Gemini parse/ falha — neutro')
    _CACHE[cache_key] = (now, out)
    return out
