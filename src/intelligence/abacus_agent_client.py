# -*- coding: utf-8 -*-
"""
Cliente Abacus Agent centralizado (getChatResponse) com fallback resiliente.

Objetivo:
- Não quebrar o robô quando API externa falhar.
- Retornar None silenciosamente quando credenciais não estiverem configuradas.
- Reaproveitar padrão de cooldown/retry usado no cliente Groq.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

DEFAULT_ABACUS_AGENT_API_URL = 'https://api.abacus.ai/api/v0/getChatResponse'
DEFAULT_ABACUS_AGENT_DEPLOYMENT_ID = 'b85816e70'

_abacus_cooldown_until: float = 0.0
_abacus_cooldown_reason: str = ''
_abacus_cooldown_logged_until: float = 0.0
_abacus_failure_streak: int = 0


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return int(default)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return float(default)


def is_abacus_agent_in_cooldown() -> bool:
    return time.time() < _abacus_cooldown_until


def get_abacus_agent_cooldown_info() -> dict[str, Any]:
    now = time.time()
    remaining = max(0.0, _abacus_cooldown_until - now)
    return {
        'in_cooldown': remaining > 0,
        'remaining_secs': round(remaining, 1),
        'reason': _abacus_cooldown_reason,
        'until': _abacus_cooldown_until,
    }


def _set_abacus_agent_cooldown(seconds: float, reason: str, *, error_msg: str = '') -> None:
    global _abacus_cooldown_until, _abacus_cooldown_reason, _abacus_cooldown_logged_until
    secs = max(30.0, float(seconds or 30.0))
    new_until = time.time() + secs
    if new_until <= _abacus_cooldown_until:
        return
    _abacus_cooldown_until = new_until
    _abacus_cooldown_reason = reason

    if time.time() >= _abacus_cooldown_logged_until:
        err_bit = f' — {error_msg[:140]}' if error_msg else ''
        print(
            f'⚠️ [ABACUS AGENT] Cooldown {secs:.0f}s ({reason}){err_bit} → fallback local',
            flush=True,
        )
        _abacus_cooldown_logged_until = new_until


def _log_abacus_agent_cooldown_skip(purpose: str) -> None:
    global _abacus_cooldown_logged_until
    if time.time() < _abacus_cooldown_logged_until:
        return
    info = get_abacus_agent_cooldown_info()
    print(
        f'⚠️ [ABACUS AGENT] {purpose}: cooldown ({info["reason"]}, '
        f'{info["remaining_secs"]:.0f}s) → fallback',
        flush=True,
    )
    _abacus_cooldown_logged_until = info['until']


def _strip_code_fences(text: str) -> str:
    raw = (text or '').strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.IGNORECASE)
    return raw.strip()


def _extract_first_balanced_json_object(text: str) -> str | None:
    source = text or ''
    start = source.find('{')
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(source)):
        ch = source[idx]

        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return source[start:idx + 1]

    return None


def extract_json_block(text: str) -> dict[str, Any] | None:
    cleaned = _strip_code_fences(text)
    if not cleaned:
        return None

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    obj_txt = _extract_first_balanced_json_object(cleaned)
    if not obj_txt:
        return None

    try:
        data = json.loads(obj_txt)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def normalize_abacus_decision_payload(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None

    normalized = dict(data)
    action = str(normalized.get('action', '')).strip().upper()
    aliases = {
        'WAIT': 'HOLD',
        'NEUTRAL': 'HOLD',
        'LONG': 'BUY',
        'SHORT': 'SELL',
        'COMPRAR': 'BUY',
        'VENDER': 'SELL',
    }
    action = aliases.get(action, action)
    if action:
        normalized['action'] = action

    for key in ('confidence', 'entry_price', 'stop_loss', 'take_profit_1', 'take_profit_2'):
        if key in normalized:
            normalized[key] = _to_float(normalized.get(key), 0.0)

    return normalized


def parse_abacus_agent_json_response(text: str) -> dict[str, Any] | None:
    payload = extract_json_block(text)
    if not payload:
        return None
    return normalize_abacus_decision_payload(payload)


def _extract_assistant_text(data: dict[str, Any]) -> str:
    root = data or {}
    payload = root.get('result')
    if not isinstance(payload, dict):
        payload = root.get('response')
    if not isinstance(payload, dict):
        payload = root

    messages = payload.get('messages') if isinstance(payload, dict) else None
    if isinstance(messages, list):
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            if msg.get('is_user') is False:
                txt = str(msg.get('text') or '').strip()
                if txt:
                    return txt

    segments = payload.get('segments') if isinstance(payload, dict) else None
    if isinstance(segments, list):
        parts: list[str] = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            if str(seg.get('type') or 'text').lower() != 'text':
                continue
            val = str(seg.get('segment') or seg.get('text') or '').strip()
            if val:
                parts.append(val)
        if parts:
            return '\n'.join(parts)

    return ''


def _classify_http_error(status_code: int) -> str:
    if status_code == 429:
        return 'rate_limit'
    if status_code in (401, 403):
        return 'auth'
    if status_code >= 500:
        return 'server'
    return 'http_error'


def _credentials() -> tuple[str, str, str]:
    api_key = str(os.getenv('ABACUS_AGENT_API_KEY') or '').strip()
    deployment_token = str(os.getenv('ABACUS_AGENT_DEPLOYMENT_TOKEN') or '').strip()
    deployment_id = str(
        os.getenv('ABACUS_AGENT_DEPLOYMENT_ID') or DEFAULT_ABACUS_AGENT_DEPLOYMENT_ID
    ).strip() or DEFAULT_ABACUS_AGENT_DEPLOYMENT_ID
    return api_key, deployment_token, deployment_id


def _mark_abacus_success() -> None:
    global _abacus_failure_streak
    _abacus_failure_streak = 0


def _mark_abacus_failure(reason: str, err: str = '') -> None:
    global _abacus_failure_streak
    _abacus_failure_streak += 1
    cooldown_secs = _env_float('ABACUS_AGENT_COOLDOWN_SECS', 600.0)
    _set_abacus_agent_cooldown(cooldown_secs, reason, error_msg=err)


def abacus_agent_chat(
    text: str,
    *,
    purpose: str = 'chat',
    timeout_secs: int | None = None,
    max_retries: int | None = None,
) -> str | None:
    """
    Chama o agente Abacus via getChatResponse.

    Retorno:
    - str com a última resposta do assistente, quando sucesso.
    - None em qualquer falha (sem exceptions para o chamador).
    """
    if not _env_bool('ABACUS_AGENT_ENABLED', True):
        return None

    api_key, deployment_token, deployment_id = _credentials()
    if not api_key and not deployment_token:
        return None

    if is_abacus_agent_in_cooldown():
        _log_abacus_agent_cooldown_skip(purpose)
        return None

    url = str(os.getenv('ABACUS_AGENT_API_URL') or DEFAULT_ABACUS_AGENT_API_URL).strip()
    timeout = float(timeout_secs if timeout_secs is not None else _env_float('ABACUS_AGENT_TIMEOUT_SECS', 30.0))
    retries = int(max_retries if max_retries is not None else _env_int('ABACUS_AGENT_MAX_RETRIES', 2))
    retries = max(0, retries)
    attempts = 1 + retries

    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['apiKey'] = api_key

    params: dict[str, str] = {}
    if deployment_token:
        params['deploymentToken'] = deployment_token
        params['deploymentId'] = deployment_id

    payload = {'messages': [{'is_user': True, 'text': str(text or '')}]}

    last_error = ''
    for attempt in range(attempts):
        try:
            resp = requests.post(
                url,
                headers=headers,
                params=params or None,
                json=payload,
                timeout=timeout,
            )
            if resp.status_code >= 400:
                err_type = _classify_http_error(resp.status_code)
                last_error = f'HTTP {resp.status_code}: {resp.text[:280]}'
                if resp.status_code in (401, 403):
                    _mark_abacus_failure('auth', last_error)
                    return None
                if attempt < attempts - 1:
                    time.sleep(min(2.0, 0.5 * (attempt + 1)))
                    continue
                _mark_abacus_failure(err_type, last_error)
                return None

            data = resp.json()
            answer = _extract_assistant_text(data)
            if answer:
                _mark_abacus_success()
                return answer

            last_error = 'Resposta sem mensagem do assistente'
            if attempt < attempts - 1:
                time.sleep(min(2.0, 0.5 * (attempt + 1)))
                continue
            _mark_abacus_failure('empty_response', last_error)
            return None
        except requests.Timeout:
            last_error = f'timeout>{timeout}s'
            if attempt < attempts - 1:
                time.sleep(min(2.0, 0.5 * (attempt + 1)))
                continue
            _mark_abacus_failure('timeout', last_error)
            return None
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < attempts - 1:
                time.sleep(min(2.0, 0.5 * (attempt + 1)))
                continue
            _mark_abacus_failure('network', last_error)
            return None
        except Exception as exc:
            last_error = str(exc)
            _mark_abacus_failure('unexpected', last_error)
            return None

    _mark_abacus_failure('unknown', last_error)
    return None
