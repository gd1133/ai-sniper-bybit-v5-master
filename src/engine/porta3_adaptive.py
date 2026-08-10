# -*- coding: utf-8 -*-
"""
Porta 3 adaptativa — multiplica σ do volume conforme volatilidade do mercado (ADX médio).

  • ADX médio (top N) < 20  → consolidação → 1.4σ (mais sensível)
  • ADX médio >= 20         → tendência    → 1.8σ (padrão)

Thread-safe; atualizado a cada ciclo do radar.
"""

from __future__ import annotations

import os
import threading
from typing import Iterable

_lock = threading.Lock()
_market_avg_adx: float = 25.0
_last_sigma: float = 1.8
_sample_count: int = 0


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


SIGMA_TREND = _env_float('PORTA3_VOL_SIGMA', 1.8)
SIGMA_CHOP = _env_float('PORTA3_VOL_SIGMA_CHOP', 1.4)
ADX_CHOP_MAX = _env_float('PORTA3_ADX_CHOP_MAX', 20.0)


def set_market_avg_adx(adx: float, samples: int = 0) -> float:
    """Persiste ADX médio do mercado (top coins) e devolve o σ vigente."""
    global _market_avg_adx, _last_sigma, _sample_count
    try:
        val = float(adx)
    except (TypeError, ValueError):
        val = 25.0
    with _lock:
        _market_avg_adx = val
        _sample_count = int(samples or 0)
        _last_sigma = SIGMA_CHOP if val < ADX_CHOP_MAX else SIGMA_TREND
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


def resolve_porta3_sigma() -> float:
    """σ vigente para o rastreador institucional / Porta 3."""
    with _lock:
        adx = float(_market_avg_adx)
        sigma = SIGMA_CHOP if adx < ADX_CHOP_MAX else SIGMA_TREND
        return float(sigma)


def porta3_status() -> dict:
    with _lock:
        adx = float(_market_avg_adx)
        sigma = SIGMA_CHOP if adx < ADX_CHOP_MAX else SIGMA_TREND
        regime = 'CHOP/CONSOLIDACAO' if adx < ADX_CHOP_MAX else 'TENDENCIA'
        return {
            'market_avg_adx': round(adx, 2),
            'sigma': round(sigma, 2),
            'regime': regime,
            'samples': int(_sample_count),
            'threshold_rule': f'media_vol + ({sigma} * std_vol)',
        }
