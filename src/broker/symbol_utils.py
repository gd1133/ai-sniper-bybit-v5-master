# -*- coding: utf-8 -*-
"""Formatação de símbolos Bybit V5 — linear (perp) vs spot."""

from __future__ import annotations


def strip_contract_suffix(symbol: str) -> str:
    s = str(symbol or '').strip().upper()
    return s.replace(':USDT', '')


def to_v5_symbol(symbol: str) -> str:
    """BTC/USDT:USDT → BTCUSDT"""
    return strip_contract_suffix(symbol).replace('/', '')


def to_ccxt_symbol(symbol: str, *, spot: bool = False) -> str:
    """
    CCXT:
      spot  → NEAR/USDT
      linear → NEAR/USDT:USDT (swap)
    """
    s = strip_contract_suffix(symbol)
    if '/' not in s and s.endswith('USDT') and len(s) > 4:
        s = f'{s[:-4]}/USDT'
    if not spot and '/USDT' in s and ':USDT' not in s:
        return f'{s}:USDT'
    return s


def is_regulatory_10024(message) -> bool:
    s = str(message or '').lower()
    return (
        '10024' in s
        or 'regulatory restriction' in s
        or 'not available to you due to regulatory' in s
    )
