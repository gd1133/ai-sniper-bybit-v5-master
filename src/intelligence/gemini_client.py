# -*- coding: utf-8 -*-
"""
Cliente Gemini centralizado — endpoint v1beta + cadeia de modelos estáveis.

Evita HTTP 404 em cascata tentando: gemini-2.0-flash → gemini-1.5-flash → gemini-flash-latest.
"""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_GEMINI_MODEL = 'gemini-2.0-flash'
DEFAULT_GEMINI_FALLBACK_CHAIN = (
    'gemini-2.0-flash',
    'gemini-1.5-flash',
    'gemini-flash-latest',
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def get_gemini_api_key() -> str:
    return str(os.getenv('GEMINI_API_KEY') or '').strip()


def get_gemini_model_chain(purpose: str = 'chat') -> list[str]:
    env_map = {
        'chat': 'GEMINI_CHAT_MODEL',
        'flow': 'GEMINI_FLOW_MODEL',
        'macro': 'GEMINI_MACRO_MODEL',
        'c3': 'GEMINI_C3_MODEL',
    }
    primary_env = env_map.get(purpose, 'GEMINI_CHAT_MODEL')
    primary = (
        os.getenv(primary_env, '').strip()
        or os.getenv('GEMINI_CHAT_MODEL', '').strip()
        or DEFAULT_GEMINI_MODEL
    )
    # Remapeia IDs inválidos comuns
    aliases = {
        'gemini-pro': 'gemini-1.5-flash',
        'gemini-1.0-pro': 'gemini-1.5-flash',
        'gemini-1.5-pro': 'gemini-1.5-flash',
    }
    primary = aliases.get(primary, primary)
    chain = [primary]
    for fb in DEFAULT_GEMINI_FALLBACK_CHAIN:
        if fb not in chain:
            chain.append(fb)
    return chain


def gemini_generate_content(
    prompt: str,
    *,
    purpose: str = 'chat',
    temperature: float = 0.15,
    max_tokens: int = 280,
) -> dict[str, Any]:
    """
    generateContent via v1beta. Retorna dict {ok, text, model, error} — nunca levanta.
    """
    key = get_gemini_api_key()
    if not key:
        return {'ok': False, 'text': None, 'model': None, 'error': 'GEMINI_API_KEY ausente'}

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
            if rsp.status_code == 404:
                print(f'⚠️ [GEMINI] `{model}` HTTP 404 — próximo modelo', flush=True)
                last_err = f'404 {model}'
                continue
            if rsp.status_code != 200:
                last_err = f'HTTP {rsp.status_code} {model}'
                print(f'⚠️ [GEMINI] {purpose} {last_err}', flush=True)
                continue
            parts = (rsp.json().get('candidates') or [{}])[0].get('content', {}).get('parts') or []
            text = ' '.join(str(p.get('text', '')) for p in parts).strip()
            if not text:
                last_err = f'resposta vazia {model}'
                continue
            return {'ok': True, 'text': text, 'model': model, 'error': None}
        except Exception as exc:
            last_err = str(exc)
            print(f'⚠️ [GEMINI] {purpose} falhou em `{model}`: {exc}', flush=True)
            continue

    return {'ok': False, 'text': None, 'model': None, 'error': last_err}
