# -*- coding: utf-8 -*-
"""
Cliente Groq centralizado — modelos válidos, cadeia de fallback e classificação de erros.

Evita abortar ordens quando um modelo é descontinuado (404) ou há rate-limit (429).
"""

from __future__ import annotations

import os
import re
from typing import Any

try:
    from groq import Groq
except Exception:
    Groq = None

# Groq desligou llama-3.3-70b-versatile e llama-3.1-8b-instant em 16/08/2026.
# Fontes: https://console.groq.com/docs/deprecations e /docs/models
DEFAULT_GROQ_MODEL = 'openai/gpt-oss-20b'
DEFAULT_GROQ_FALLBACK_CHAIN = (
    'openai/gpt-oss-20b',
    'qwen/qwen3.6-27b',
    'openai/gpt-oss-120b',
)
_DEPRECATED_GROQ_MODELS = {
    'llama-3.3-70b-versatile': DEFAULT_GROQ_MODEL,
    'llama-3.1-70b-versatile': DEFAULT_GROQ_MODEL,
    'llama-3.1-8b-instant': DEFAULT_GROQ_MODEL,
    'llama-3.1-70b-specdec': DEFAULT_GROQ_MODEL,
    'llama3-70b-8192': DEFAULT_GROQ_MODEL,
    'llama3-8b-8192': DEFAULT_GROQ_MODEL,
}


def _remap_groq_model(model: str) -> str:
    key = (model or '').strip()
    replacement = _DEPRECATED_GROQ_MODELS.get(key)
    if replacement:
        print(
            f'⚠️ [GROQ] modelo descontinuado `{key}` → `{replacement}`',
            flush=True,
        )
        return replacement
    return key


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def get_groq_model_chain(purpose: str = 'flow') -> list[str]:
    """
    Retorna cadeia de modelos a tentar (primário + fallbacks, sem duplicatas).
    purpose: 'flow' | 'news' | 'tribunal'
    """
    env_map = {
        'flow': 'GROQ_FLOW_MODEL',
        'news': 'GROQ_NEWS_MODEL',
        'tribunal': 'GROQ_TRIBUNAL_MODEL',
    }
    primary_env = env_map.get(purpose, 'GROQ_FLOW_MODEL')
    primary = _remap_groq_model(
        os.getenv(primary_env, '').strip()
        or os.getenv('GROQ_MODEL', '').strip()
        or DEFAULT_GROQ_MODEL
    )
    chain: list[str] = [primary]
    extra = os.getenv('GROQ_FALLBACK_MODELS', '').strip()
    if extra:
        for m in extra.split(','):
            m = _remap_groq_model(m.strip())
            if m and m not in chain:
                chain.append(m)
    for fb in DEFAULT_GROQ_FALLBACK_CHAIN:
        if fb not in chain:
            chain.append(fb)
    return chain


def classify_groq_error(exc: BaseException) -> str:
    """Classifica erro Groq: model_not_found | rate_limit | connection | other."""
    err = str(exc).lower()
    if '404' in err or 'model_not_found' in err or 'does not exist' in err:
        return 'model_not_found'
    if '429' in err or 'rate_limit' in err or 'rate limit' in err:
        return 'rate_limit'
    if any(x in err for x in ('connection', 'timeout', 'timed out', 'connect', 'network')):
        return 'connection'
    return 'other'


def extract_rate_limit_wait(exc: BaseException, default_secs: float = 180.0) -> float:
    err = str(exc)
    m = re.search(r'try again in\s+(\d+)m([\d.]+)s', err, flags=re.IGNORECASE)
    if m:
        return max(60.0, int(m.group(1)) * 60 + float(m.group(2)))
    m2 = re.search(r'try again in\s+([\d.]+)s', err, flags=re.IGNORECASE)
    if m2:
        return max(60.0, float(m2.group(1)))
    return default_secs


def groq_chat_completion(
    messages: list[dict[str, str]],
    *,
    purpose: str = 'flow',
    temperature: float = 0.1,
    max_tokens: int = 220,
) -> dict[str, Any]:
    """
    Chama Groq com cadeia de modelos. Nunca propaga exceção — retorna dict padronizado.

    Returns:
        {
            'ok': bool,
            'content': str | None,
            'model': str | None,
            'error_type': str | None,
            'error': str | None,
            'models_tried': list[str],
        }
    """
    groq_key = os.getenv('GROQ_API_KEY', '').strip()
    if not groq_key or Groq is None:
        return {
            'ok': False,
            'content': None,
            'model': None,
            'error_type': 'no_client',
            'error': 'GROQ_API_KEY ausente ou pacote groq indisponível',
            'models_tried': [],
        }

    models = get_groq_model_chain(purpose)
    last_err: BaseException | None = None
    last_type = 'other'
    client = Groq(api_key=groq_key)

    for model in models:
        try:
            create_kwargs = {
                'model': model,
                'messages': messages,
                'temperature': temperature,
                'max_tokens': max_tokens,
            }
            try:
                rsp = client.chat.completions.create(
                    **create_kwargs,
                    include_reasoning=False,
                )
            except TypeError:
                rsp = client.chat.completions.create(**create_kwargs)
            msg = rsp.choices[0].message
            content = (getattr(msg, 'content', None) or '').strip()
            if not content:
                content = (getattr(msg, 'reasoning', None) or '').strip()
            if not content:
                last_type = 'other'
                last_err = RuntimeError(f'resposta vazia de {model}')
                continue
            return {
                'ok': True,
                'content': content,
                'model': model,
                'error_type': None,
                'error': None,
                'models_tried': models[: models.index(model) + 1],
            }
        except Exception as exc:
            last_err = exc
            last_type = classify_groq_error(exc)
            print(
                f'⚠️ [GROQ] {purpose} falhou em `{model}` ({last_type}): {str(exc)[:180]}',
                flush=True,
            )
            # 404 → tenta próximo modelo; 429/connection → para cadeia (cooldown)
            if last_type in ('rate_limit', 'connection'):
                break
            continue

    err_msg = str(last_err) if last_err else 'Groq indisponível'
    return {
        'ok': False,
        'content': None,
        'model': None,
        'error_type': last_type,
        'error': err_msg,
        'models_tried': models,
    }


def log_groq_degraded(tag: str, result: dict[str, Any], *, symbol: str = '') -> None:
    """Log diagnóstico claro — aviso sem abortar execução."""
    sym = f' {symbol}' if symbol else ''
    err_type = result.get('error_type') or 'unknown'
    err = (result.get('error') or '')[:200]
    tried = ', '.join(result.get('models_tried') or [])
    print(
        f'⚠️ [{tag}]{sym} Groq degradado ({err_type}): {err} '
        f'| modelos tentados: {tried or "n/d"} → fallback técnico',
        flush=True,
    )
