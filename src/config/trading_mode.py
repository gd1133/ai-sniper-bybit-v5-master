# -*- coding: utf-8 -*-
"""TRADING_MODE global ou por investidor: linear (perp) | spot."""

from __future__ import annotations

import os
from typing import Any, Mapping

_VALID = frozenset({'linear', 'spot'})


def normalize_trading_mode(value: str | None) -> str:
    mode = str(value or 'spot').strip().lower()
    if mode in ('perp', 'perpetual', 'futures', 'swap'):
        return 'linear'
    if mode not in _VALID:
        return 'spot'
    return mode


def resolve_trading_mode(client: Mapping[str, Any] | None = None) -> str:
    """
    Resolve categoria de ordem Bybit V5.
    Prioridade: investidor.trading_mode → TRADING_MODE (env) → linear (default).

    Default LINEAR (FUTUROS/PERP): permite ganhar na COMPRA e na VENDA (short).
    Observação: se a conta/IP estiver sob restrição regulatória (ErrCode 10024),
    a própria Bybit bloqueia derivativos via API e o broker faz fallback
    automático para SPOT naquela sessão (ver _enable_spot_fallback).
    """
    if client:
        for key in ('trading_mode', 'TRADING_MODE', 'bybit_trading_mode'):
            raw = client.get(key)
            if raw:
                return normalize_trading_mode(str(raw))
    return normalize_trading_mode(os.getenv('TRADING_MODE', 'linear'))
