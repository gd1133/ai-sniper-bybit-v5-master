# -*- coding: utf-8 -*-
"""
Stub local — Groq cloud REMOVIDO desta versão.

O robô opera 100% com agentes Python (Cérebro 3 quantitativo).
Mantém a API pública para não quebrar imports do radar/testes.
"""

from __future__ import annotations

from typing import Any

Groq = None

DEFAULT_GROQ_MODEL = 'local-python'
DEFAULT_GROQ_FALLBACK_CHAIN = ('local-python',)


def get_groq_model_chain(purpose: str = 'flow') -> list[str]:
    return [DEFAULT_GROQ_MODEL]


def classify_groq_error(exc: BaseException) -> str:
    return 'disabled'


def extract_rate_limit_wait(exc: BaseException, default_secs: float = 180.0) -> float:
    return float(default_secs)


def is_groq_tpd_error(exc: BaseException | str) -> bool:
    return False


def cooldown_secs_for_rate_limit(exc: BaseException) -> float:
    return 0.0


def is_groq_in_cooldown() -> bool:
    return False


def get_groq_cooldown_info() -> dict[str, Any]:
    return {
        'active': False,
        'remaining_secs': 0.0,
        'reason': 'groq_removed',
        'until': 0.0,
    }


def set_groq_cooldown(seconds: float, reason: str, *, error_msg: str = '') -> None:
    return None


def log_groq_degraded(context: str, result: dict, symbol: str = '') -> None:
    return None


def groq_chat_completion(
    messages: list[dict[str, str]] | None = None,
    *,
    purpose: str = 'flow',
    temperature: float = 0.1,
    max_tokens: int = 150,
    **kwargs: Any,
) -> dict[str, Any]:
    return {
        'ok': False,
        'error': 'Groq removido — motor 100% Python local',
        'content': '',
        'model': DEFAULT_GROQ_MODEL,
        'cooldown': False,
        'disabled': True,
    }
