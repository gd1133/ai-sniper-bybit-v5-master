# -*- coding: utf-8 -*-
"""
Porta 3 adaptativa — multiplica σ do volume conforme ADX (mercado ou ativo).

Modo ENTRADA RÁPIDA (defaults):
  • ADX < 15              → consolidação      → 1.15σ
  • 15 <= ADX < 25        → tendência moderada → 1.0σ
  • ADX >= 25             → tendência forte    → 0.85σ

Em tendência forte o robô fica assertivo: μ+1.0σ basta (antes 1.5σ cegava o radar).
Thread-safe; atualizado a cada ciclo do radar.
"""

from __future__ import annotations

import os
import threading
from typing import Iterable, Optional

_lock = threading.Lock()
_market_avg_adx: float = 22.0
_last_sigma: float = 1.0
_sample_count: int = 0


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Degraus ENTRADA RÁPIDA (podem sobrescrever via env no Render)
SIGMA_CONSOLIDATION = _env_float('PORTA3_SIGMA_CONSOLIDATION', 1.15)
SIGMA_MODERATE = _env_float('PORTA3_SIGMA_MODERATE', 1.0)
SIGMA_STRONG = _env_float('PORTA3_SIGMA_STRONG', 0.85)

ADX_CONSOLIDATION_MAX = _env_float('PORTA3_ADX_CONSOLIDATION_MAX', 15.0)
ADX_MODERATE_MAX = _env_float('PORTA3_ADX_MODERATE_MAX', 25.0)

# Compat: aliases legados (não usados como valor único travado)
SIGMA_TREND = SIGMA_STRONG
SIGMA_CHOP = SIGMA_CONSOLIDATION
ADX_CHOP_MAX = ADX_MODERATE_MAX


def sigma_for_adx(adx: float) -> float:
    """Mapeia um valor de ADX → σ da Porta 3 (modo MODERADO)."""
    try:
        val = float(adx)
    except (TypeError, ValueError):
        val = float(ADX_MODERATE_MAX)
    if val != val:  # NaN
        val = float(ADX_MODERATE_MAX)

    if val < ADX_CONSOLIDATION_MAX:
        return float(SIGMA_CONSOLIDATION)
    if val < ADX_MODERATE_MAX:
        return float(SIGMA_MODERATE)
    return float(SIGMA_STRONG)


def _regime_label(adx: float) -> str:
    if adx < ADX_CONSOLIDATION_MAX:
        return 'CONSOLIDACAO'
    if adx < ADX_MODERATE_MAX:
        return 'TENDENCIA_MODERADA'
    return 'TENDENCIA_FORTE'


def set_market_avg_adx(adx: float, samples: int = 0) -> float:
    """Persiste ADX médio do mercado (top coins) e devolve o σ vigente."""
    global _market_avg_adx, _last_sigma, _sample_count
    try:
        val = float(adx)
    except (TypeError, ValueError):
        val = 22.0
    with _lock:
        _market_avg_adx = val
        _sample_count = int(samples or 0)
        _last_sigma = sigma_for_adx(val)
        return _last_sigma


def update_market_adx_from_samples(adx_values: Iterable[float]) -> float:
    """Calcula média dos ADXs coletados (ex.: top 10) e atualiza o σ."""
    vals = []
    for v in adx_values or []:
        try:
            n = float(v)
            if n == n and n > 0:
                vals.append(n)
        except (TypeError, ValueError):
            continue
    if not vals:
        return resolve_porta3_sigma()
    avg = sum(vals) / len(vals)
    return set_market_avg_adx(avg, samples=len(vals))


def get_market_avg_adx() -> float:
    with _lock:
        return float(_market_avg_adx)


def resolve_porta3_sigma(adx: Optional[float] = None) -> float:
    """
    σ vigente para o rastreador institucional / Porta 3.
    Se ``adx`` for passado, usa esse valor (ex.: ADX do ativo);
    senão usa o ADX médio do mercado.
    """
    if adx is not None:
        return sigma_for_adx(adx)
    with _lock:
        return sigma_for_adx(_market_avg_adx)


def porta3_status() -> dict:
    with _lock:
        adx = float(_market_avg_adx)
        sigma = sigma_for_adx(adx)
        regime = _regime_label(adx)
        return {
            'market_avg_adx': round(adx, 2),
            'sigma': round(sigma, 2),
            'regime': regime,
            'samples': int(_sample_count),
            'threshold_rule': f'media_vol + ({sigma} * std_vol)',
            'tiers': {
                'consolidation': {'adx_lt': ADX_CONSOLIDATION_MAX, 'sigma': SIGMA_CONSOLIDATION},
                'moderate': {
                    'adx_gte': ADX_CONSOLIDATION_MAX,
                    'adx_lt': ADX_MODERATE_MAX,
                    'sigma': SIGMA_MODERATE,
                },
                'strong': {'adx_gte': ADX_MODERATE_MAX, 'sigma': SIGMA_STRONG},
            },
        }
