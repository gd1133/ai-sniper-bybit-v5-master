# -*- coding: utf-8 -*-
"""
Defaults de estrutura / entradas (modo moderado — mais oportunidades).

Todos os valores podem ser sobrescritos por env no Render.
"""

from __future__ import annotations

import os


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == '':
        return float(default)
    try:
        return float(str(raw).replace(',', '.'))
    except (TypeError, ValueError):
        return float(default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == '':
        return bool(default)
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on', 'sim'}


# ADX mínimo para liberar estrutura (modo rápido — mais entradas)
STRUCTURE_ADX_MIN = _env_float('STRUCTURE_ADX_MIN', 16.0)

# Score soft de lateralidade (subir = menos skip lateral)
LATERAL_SCORE_BLOCK = _env_float('LATERAL_SCORE_BLOCK', 68.0)

# BB expandindo como trava dura? Default OFF no modo moderado
STRUCTURE_REQUIRE_BB_EXPAND = _env_bool('STRUCTURE_REQUIRE_BB_EXPAND', False)

# Multiplicador de spread do candle vs média
PORTA3_SPREAD_MULT = _env_float('PORTA3_SPREAD_MULT', 1.1)

# Amplitude % abaixo = acumulação (abaixar = menos bloqueio)
DEFAULT_AMPLITUDE_PCT_MAX = _env_float('LATERAL_AMPLITUDE_PCT', 0.24)
