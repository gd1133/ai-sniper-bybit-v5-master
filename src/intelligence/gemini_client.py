# -*- coding: utf-8 -*-
"""
Cliente Gemini centralizado — endpoint v1beta + cadeia de modelos estáveis.

Cadeia 2026: gemini-2.5-flash → gemini-2.0-flash → gemini-1.5-flash
Cache em memória por par (TTL 120 s) — evita estouro de RPM (HTTP 429).
Erros 429/404 são silenciosos; o chamador recebe ok=False e usa fallback local.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

DEFAULT_GEMINI_MODEL = 'gemini-2.5-flash'
DEFAULT_GEMINI_FALLBACK_CHAIN = (
    'gemini-2.5-flash',
    'gemini-2.0-flash',
    'gemini-1.5-flash',
)

# Cache {cache_key: (timestamp, result_dict)}
_GEMINI_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_GEMINI_CACHE_TTL = float(os.getenv('GEMINI_CACHE_TTL_SECS', '120') or 120)

# Se 429 ocorrer, espera até este timestamp antes de tentar de novo
_gemini_rate_limit_until: float = 0.0


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def get_gemini_api_key() -> str:
    return str(os.getenv('GEMINI_API_KEY') or '').strip()


def get_gemini_model_chain(purpose: str = 'chat') -> list[str]:
    env_map = {
        'chat':  'GEMINI_CHAT_MODEL',
        'flow':  'GEMINI_FLOW_MODEL',
        'macro': 'GEMINI_MACRO_MODEL',
        'c3':    'GEMINI_C3_MODEL',
    }
    primary_env = env_map.get(purpose, 'GEMINI_CHAT_MODEL')
    primary = (
        os.getenv(primary_env, '').strip()
        or os.getenv('GEMINI_CHAT_MODEL', '').strip()
        or DEFAULT_GEMINI_MODEL
    )
    # Remapeia IDs antigos
    aliases = {
        'gemini-pro':      'gemini-1.5-flash',
        'gemini-1.0-pro':  'gemini-1.5-flash',
        'gemini-1.5-pro':  'gemini-1.5-flash',
        'gemini-flash-latest': 'gemini-2.5-flash',
    }
    primary = aliases.get(primary, primary)
    chain = [primary]
    for fb in DEFAULT_GEMINI_FALLBACK_CHAIN:
        if fb not in chain:
            chain.append(fb)
    return chain


def _cache_key(prompt: str, purpose: str) -> str:
    """Chave de cache baseada no propósito + hash leve do prompt."""
    return f'{purpose}:{hash(prompt) % 10_000_000}'


def gemini_generate_content(
    prompt: str,
    *,
    purpose: str = 'chat',
    temperature: float = 0.15,
    max_tokens: int = 280,
    cache_key_extra: str = '',
) -> dict[str, Any]:
    """
    generateContent via v1beta.
    Retorna {ok, text, model, error} — nunca levanta exceção.
    Aplica cache TTL 120 s por (purpose + hash-prompt) para evitar estouro de RPM.
    Erros 429/404 são silenciosos (sem blocos de warning).
    """
    global _gemini_rate_limit_until

    key = get_gemini_api_key()
    if not key:
        return {'ok': False, 'text': None, 'model': None, 'error': 'GEMINI_API_KEY ausente'}

    # Verifica cache
    ck = _cache_key(prompt + cache_key_extra, purpose)
    now = time.time()
    cached = _GEMINI_CACHE.get(ck)
    if cached and (now - cached[0]) < _GEMINI_CACHE_TTL:
        result = dict(cached[1])
        result['from_cache'] = True
        return result

    # Rate limit ativo → retorna falha silenciosa
    if now < _gemini_rate_limit_until:
        return {'ok': False, 'text': None, 'model': None, 'error': 'gemini_rate_limited', 'cached': False}

    last_err = 'sem resposta'
    for model in get_gemini_model_chain(purpose):
        try:
            url = (
                'https://generativelanguage.googleapis.com/v1beta/models/'
                f'{model}:generateContent?key={key}'
            )
            rsp = requests.post(
                url,
                json={
                    'contents': [{'parts': [{'text': prompt}]}],
                    'generationConfig': {
                        'temperature': float(temperature),
                        'maxOutputTokens': int(max_tokens),
                    },
                },
                timeout=15,
            )
            if rsp.status_code == 429:
                # Rate limit: back-off 120 s, silencioso
                _gemini_rate_limit_until = now + _GEMINI_CACHE_TTL
                last_err = '429'
                break  # sem logs; apenas para de tentar
            if rsp.status_code == 404:
                last_err = f'404 {model}'
                continue  # tenta próximo modelo, sem log
            if rsp.status_code != 200:
                last_err = f'HTTP {rsp.status_code} {model}'
                continue
            parts = (rsp.json().get('candidates') or [{}])[0].get('content', {}).get('parts') or []
            text = ' '.join(str(p.get('text', '')) for p in parts).strip()
            if not text:
                last_err = f'vazia {model}'
                continue
            result = {'ok': True, 'text': text, 'model': model, 'error': None, 'from_cache': False}
            _GEMINI_CACHE[ck] = (now, result)
            return result
        except Exception as exc:
            last_err = str(exc)[:80]
            continue

    return {'ok': False, 'text': None, 'model': None, 'error': last_err, 'from_cache': False}
