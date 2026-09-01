# -*- coding: utf-8 -*-
"""Helpers: C1/C2 e portões pós-C3 são consultivos — Cérebro 3 decide execução."""

from __future__ import annotations

import os


def post_c3_advisory_enabled() -> bool:
    """Default true: TIMING / ASSIMÉTRICO / ANTI-CHASE / SuperTrend não abortam ordem."""
    return str(os.getenv('POST_C3_GATES_ADVISORY', 'true')).strip().lower() in {
        '1', 'true', 'yes', 'on',
    }


def advisory_wrap(ok: bool, reasons: list[str], *, prefix: str = 'consultivo') -> tuple[bool, list[str]]:
    """Se consultivo, converte bloqueio em payload informativo (ok=True)."""
    if ok or not post_c3_advisory_enabled():
        return ok, reasons
    tagged = [f'[{prefix}] {r}' if not str(r).startswith('[') else str(r) for r in reasons]
    return True, tagged
