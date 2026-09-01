# -*- coding: utf-8 -*-
"""Cliente Gemini com cadeia de modelos — evita HTTP 404 por IDs descontinuados."""

from __future__ import annotations

import os
from typing import Any

import requests

# Aliases estáveis (sem versão fixa) + fallbacks explícitos
DEFAULT_GEMINI_MODELS = (
    'gemini-flash-latest',
    'gemini-3.5-flash',
    'gemini-3.7-flash',
    'gemini-2.5-flash',
)

_RETIRED_GEMINI_MODELS = {
    'gemini-2.0-flash': 'gemini-flash-latest',
    'gemini-2.0-flash-001': 'gemini-flash-latest',
    'gemini-1.5-flash': 'gemini-flash-latest',
    'gemini-1.5-flash-latest': 'gemini-flash-latest',
    'gemini-1.5-pro': 'gemini-flash-latest',
}


def _remap_gemini_model(model: str) -> str:
    key = (model or '').strip()
    return _RETIRED_GEMINI_MODELS.get(key, key)


def get_gemini_model_chain() -> list[str]:
    primary = (
        os.getenv('GEMINI_CHAT_MODEL', '').strip()
        or os.getenv('GEMINI_FLOW_MODEL', '').strip()
        or os.getenv('GEMINI_MACRO_MODEL', '').strip()
        or os.getenv('GEMINI_C3_MODEL', '').strip()
        or 'gemini-flash-latest'
    )
    chain: list[str] = [_remap_gemini_model(primary)]
    for fb in DEFAULT_GEMINI_MODELS:
        fb = _remap_gemini_model(fb)
        if fb and fb not in chain:
            chain.append(fb)
    return chain


def gemini_generate_text(
    prompt: str,
    *,
    purpose: str = 'flow',
    temperature: float = 0.15,
    max_tokens: int = 280,
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    Tenta generateContent em cadeia de modelos.
    Retorna: {ok, text, model, status_code, error}
    """
    key = (api_key or os.getenv('GEMINI_API_KEY', '')).strip()
    if not key:
        return {'ok': False, 'text': '', 'model': None, 'status_code': 0, 'error': 'no_key'}

    last_status = 0
    last_err = ''
    for model in get_gemini_model_chain():
        url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'{model}:generateContent?key={key}'
        )
        try:
            rsp = requests.post(
                url,
                json={
                    'contents': [{'parts': [{'text': prompt}]}],
                    'generationConfig': {
                        'temperature': float(temperature),
                        'maxOutputTokens': int(max_tokens),
                    },
                },
                timeout=18,
            )
            last_status = rsp.status_code
            if rsp.status_code != 200:
                last_err = rsp.text[:200]
                continue
            parts = (rsp.json().get('candidates') or [{}])[0].get('content', {}).get('parts') or []
            text = ' '.join(str(p.get('text', '')) for p in parts).strip()
            if text:
                return {'ok': True, 'text': text, 'model': model, 'status_code': 200, 'error': None}
            last_err = 'resposta vazia'
        except Exception as exc:
            last_err = str(exc)
            continue

    return {
        'ok': False,
        'text': '',
        'model': None,
        'status_code': last_status,
        'error': last_err or 'Gemini indisponível',
    }
