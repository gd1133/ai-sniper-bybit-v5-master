# -*- coding: utf-8 -*-
"""Modo Cérebro 3 solo — C1/C2 fora da operação; C3 absorve tendência + volume + decisão."""

from __future__ import annotations

import os


def is_c3_solo_mode() -> bool:
    """
    True: sem chamadas Groq/Gemini de C1/C2; C3 unificado (local + aprendizado).
    Desligar no Render: C3_SOLO_MODE=false
    """
    raw = os.getenv('C3_SOLO_MODE', 'true')
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}
