# -*- coding: utf-8 -*-
"""TRADING_MODE global ou por investidor: linear (perp) | spot."""

from __future__ import annotations

import os
from typing import Any, Mapping

_VALID = frozenset({'linear', 'spot'})


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def allow_derivatives() -> bool:
    """Derivativos (linear/perp) só com permissão explícita no ambiente."""
    return _env_bool('ALLOW_DERIVATIVES', False)


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
    Prioridade: investidor.trading_mode → TRADING_MODE (env) → spot (default).

    Default SPOT: contas/IPs sob restrição regulatória (ErrCode 10024) não
    operam linear/perp via API.

    Linear só é honrado se ALLOW_DERIVATIVES=true.
    """
    mode = 'spot'
    if client:
        for key in ('trading_mode', 'TRADING_MODE', 'bybit_trading_mode'):
            raw = client.get(key)
            if raw:
                mode = normalize_trading_mode(str(raw))
                break
        else:
            mode = normalize_trading_mode(os.getenv('TRADING_MODE', 'spot'))
    else:
        mode = normalize_trading_mode(os.getenv('TRADING_MODE', 'spot'))

    if mode == 'linear' and not allow_derivatives():
        return 'spot'
    return mode
