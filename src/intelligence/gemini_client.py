# -*- coding: utf-8 -*-
"""
Stub local — Gemini cloud REMOVIDO desta versão.

O robô opera 100% com agentes Python (Cérebro 3 quantitativo).
Mantém a API pública para não quebrar imports do radar/testes.
"""

from __future__ import annotations

from typing import Any

DEFAULT_GEMINI_MODEL = 'local-python'
DEFAULT_GEMINI_FALLBACK_CHAIN = ('local-python',)


def get_gemini_api_key() -> str:
    return ''


def get_gemini_model_chain(purpose: str = 'chat') -> list[str]:
    return [DEFAULT_GEMINI_MODEL]


def gemini_generate_content(
    prompt: str,
    *,
    purpose: str = 'chat',
    temperature: float = 0.2,
    max_tokens: int = 512,
    use_cache: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    return {
        'ok': False,
        'error': 'Gemini removido — motor 100% Python local',
        'text': '',
        'model': DEFAULT_GEMINI_MODEL,
        'disabled': True,
    }
