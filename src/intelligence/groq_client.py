# -*- coding: utf-8 -*-
"""
Cliente Groq centralizado — modelos ativos oficiais + cadeia de fallback.

Principal: llama-3.3-70b-versatile
Fallback:  llama-3.1-8b-instant
IDs aposentados (llama3-70b-8192, llama3-8b-8192, mixtral) são remapeados.
"""

from __future__ import annotations

import datetime
import os
import re
import time
from typing import Any

try:
    from groq import Groq
except Exception:
    Groq = None

DEFAULT_GROQ_MODEL = 'llama-3.3-70b-versatile'
DEFAULT_GROQ_FALLBACK_CHAIN = (
    'llama-3.3-70b-versatile',
    'llama-3.1-8b-instant',
)

# Remapeia IDs mortos / aliases → modelos ativos oficiais (evita HTTP 400/404 em cascata)
_DEPRECATED_GROQ_MODELS = {
    'llama3-70b-8192': 'llama-3.3-70b-versatile',
    'llama3-8b-8192': 'llama-3.1-8b-instant',
    'mixtral-8x7b-32768': 'llama-3.1-8b-instant',
    'llama-3.1-70b-versatile': 'llama-3.3-70b-versatile',
    'llama-3.1-70b-specdec': 'llama-3.3-70b-versatile',
    'openai/gpt-oss-20b': 'llama-3.1-8b-instant',
    'openai/gpt-oss-120b': 'llama-3.3-70b-versatile',
    'gpt-oss-20b': 'llama-3.1-8b-instant',
    'gpt-oss-120b': 'llama-3.3-70b-versatile',
    'qwen/qwen3.6-27b': 'llama-3.1-8b-instant',
}

_groq_cooldown_until: float = 0.0
_groq_cooldown_reason: str = ''
_groq_cooldown_logged_until: float = 0.0


def _remap_groq_model(model: str) -> str:
    key = (model or '').strip()
    replacement = _DEPRECATED_GROQ_MODELS.get(key)
    if replacement:
        print(
            f'⚠️ [GROQ] modelo aposentado `{key}` → `{replacement}`',
            flush=True,
        )
        return replacement
    return key or DEFAULT_GROQ_MODEL


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def get_groq_model_chain(purpose: str = 'flow') -> list[str]:
    """
    Cadeia de modelos ativos (primário + fallbacks, sem duplicatas).
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
        fb = _remap_groq_model(fb)
        if fb and fb not in chain:
            chain.append(fb)
    return chain


def classify_groq_error(exc: BaseException) -> str:
    err = str(exc).lower()
    if '404' in err or 'model_not_found' in err or 'does not exist' in err:
        return 'model_not_found'
    if '400' in err and ('model' in err or 'invalid' in err):
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


def is_groq_tpd_error(exc: BaseException | str) -> bool:
    err = str(exc).lower()
    return any(
        token in err
        for token in (
            'tokens per day',
            'tpd',
            'token per day',
            'per day (tpd)',
            'daily token',
        )
    )


def cooldown_secs_for_rate_limit(exc: BaseException) -> float:
    if is_groq_tpd_error(exc):
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        midnight = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        return max(3600.0, (midnight - now).total_seconds())
    default = float(os.getenv('GROQ_RATE_LIMIT_COOLDOWN_SECS', '180') or 180)
    return extract_rate_limit_wait(exc, default_secs=default)


def is_groq_in_cooldown() -> bool:
    return time.time() < _groq_cooldown_until


def get_groq_cooldown_info() -> dict[str, Any]:
    now = time.time()
    remaining = max(0.0, _groq_cooldown_until - now)
    return {
        'in_cooldown': remaining > 0,
        'remaining_secs': round(remaining, 1),
        'reason': _groq_cooldown_reason,
        'until': _groq_cooldown_until,
    }


def set_groq_cooldown(seconds: float, reason: str, *, error_msg: str = '') -> None:
    global _groq_cooldown_until, _groq_cooldown_reason, _groq_cooldown_logged_until
    secs = max(60.0, float(seconds or 60.0))
    new_until = time.time() + secs
    if new_until <= _groq_cooldown_until:
        return
    _groq_cooldown_until = new_until
    _groq_cooldown_reason = reason
    if time.time() >= _groq_cooldown_logged_until:
        err_bit = f' — {error_msg[:140]}' if error_msg else ''
        print(
            f'⚠️ [GROQ] Cooldown global {secs / 3600:.1f}h ({reason}){err_bit} '
            f'→ fallback local até reset',
            flush=True,
        )
        _groq_cooldown_logged_until = new_until


def _log_groq_cooldown_skip(purpose: str) -> None:
    global _groq_cooldown_logged_until
    if time.time() < _groq_cooldown_logged_until:
        return
    info = get_groq_cooldown_info()
    print(
        f'⚠️ [GROQ] {purpose}: API em cooldown ({info["reason"]}, '
        f'{info["remaining_secs"]:.0f}s restantes) → fallback Gemini/local',
        flush=True,
    )
    _groq_cooldown_logged_until = info['until']


def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
    parts = []
    for msg in messages or []:
        role = str(msg.get('role') or 'user').upper()
        content = str(msg.get('content') or '').strip()
        if content:
            parts.append(f'{role}:\n{content}')
    return '\n\n'.join(parts)


def _gemini_chat_fallback(
    messages: list[dict[str, str]],
    *,
    purpose: str = 'flow',
    temperature: float = 0.1,
    max_tokens: int = 220,
) -> dict[str, Any] | None:
    """Fallback Gemini (v1beta + cadeia) quando Groq retorna 400/404 / rate-limit."""
    if not _env_bool('ENABLE_GEMINI_FLOW_FALLBACK', True):
        return None
    if not os.getenv('GEMINI_API_KEY', '').strip():
        return None
    try:
        from src.intelligence.gemini_client import gemini_generate_content
        gem_purpose = 'c3' if purpose == 'tribunal' else ('macro' if purpose == 'news' else 'flow')
        result = gemini_generate_content(
            _messages_to_prompt(messages),
            purpose=gem_purpose,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not result.get('ok'):
            print(
                f"⚠️ [GEMINI] {purpose} sem resposta útil ({result.get('error')}) — C3 técnico",
                flush=True,
            )
            return None
        model = result.get('model') or 'gemini'
        print(f'✅ [GEMINI] {purpose} respondeu via {model} (Groq indisponível)', flush=True)
        return {
            'ok': True,
            'content': result.get('text'),
            'model': f'gemini:{model}',
            'error_type': None,
            'error': None,
            'models_tried': [f'gemini:{model}'],
            'gemini_fallback': True,
        }
    except Exception as exc:
        print(f'⚠️ [GEMINI] {purpose} fallback falhou: {exc}', flush=True)
        return None


def groq_chat_completion(
    messages: list[dict[str, str]],
    *,
    purpose: str = 'flow',
    temperature: float = 0.1,
    max_tokens: int = 220,
) -> dict[str, Any]:
    """
    Chama Groq com cadeia de modelos ativos. Nunca propaga exceção.
    """
    groq_key = os.getenv('GROQ_API_KEY', '').strip()
    if not groq_key or Groq is None:
        # Tenta Gemini direto se Groq key ausente
        gemini_result = _gemini_chat_fallback(
            messages, purpose=purpose, temperature=temperature, max_tokens=max_tokens,
        )
        if gemini_result and gemini_result.get('ok'):
            return gemini_result
        return {
            'ok': False,
            'content': None,
            'model': None,
            'error_type': 'no_client',
            'error': 'GROQ_API_KEY ausente ou pacote groq indisponível',
            'models_tried': [],
        }

    if is_groq_in_cooldown():
        _log_groq_cooldown_skip(purpose)
        gemini_result = _gemini_chat_fallback(
            messages, purpose=purpose, temperature=temperature, max_tokens=max_tokens,
        )
        if gemini_result and gemini_result.get('ok'):
            return gemini_result
        info = get_groq_cooldown_info()
        return {
            'ok': False,
            'content': None,
            'model': None,
            'error_type': 'rate_limit',
            'error': f'Groq em cooldown ({info["reason"]})',
            'models_tried': [],
            'cooldown': True,
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
            if last_type == 'rate_limit':
                wait_secs = cooldown_secs_for_rate_limit(exc)
                reason = 'TPD esgotado' if is_groq_tpd_error(exc) else 'rate_limit RPM'
                set_groq_cooldown(wait_secs, reason, error_msg=str(exc))
                break
            print(
                f'⚠️ [GROQ] {purpose} falhou em `{model}` ({last_type}): {str(exc)[:180]}',
                flush=True,
            )
            if last_type == 'connection':
                set_groq_cooldown(
                    float(os.getenv('GROQ_CONNECTION_COOLDOWN_SECS', '90') or 90),
                    'connection',
                    error_msg=str(exc),
                )
                break
            continue

    gemini_result = _gemini_chat_fallback(
        messages,
        purpose=purpose,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if gemini_result and gemini_result.get('ok'):
        return gemini_result

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
    sym = f' {symbol}' if symbol else ''
    err_type = result.get('error_type') or 'unknown'
    err = (result.get('error') or '')[:200]
    tried = ', '.join(result.get('models_tried') or [])
    print(
        f'⚠️ [{tag}]{sym} Groq degradado ({err_type}): {err} '
        f'| modelos tentados: {tried or "n/d"} → fallback técnico',
        flush=True,
    )
