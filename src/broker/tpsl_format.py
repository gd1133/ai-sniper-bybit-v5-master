# -*- coding: utf-8 -*-
"""Formatação tickSize + validação de direção TP/SL (Bybit V5)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value).strip().replace(',', '.'))
    except Exception:
        return Decimal('0')


def tick_size_from_market(market: dict | None) -> Decimal:
    """Extrai tickSize do mercado CCXT / Bybit (priceFilter)."""
    market = market or {}
    info = market.get('info') if isinstance(market.get('info'), dict) else {}
    pf = info.get('priceFilter') or info.get('price_filter') or {}
    if not isinstance(pf, dict):
        pf = {}
    for key in ('tickSize', 'tick_size'):
        tick = _dec(pf.get(key))
        if tick > 0:
            return tick
    prec = market.get('precision') if isinstance(market.get('precision'), dict) else {}
    raw = prec.get('price')
    if isinstance(raw, int) and raw >= 0:
        return Decimal('1').scaleb(-raw)
    tick = _dec(raw)
    if 0 < tick < 1:
        return tick
    if tick >= 1:
        return Decimal('1').scaleb(-int(tick))
    return Decimal('0')


def format_price_tick(price: float | str | Decimal, tick_size: float | str | Decimal) -> str:
    """
    Arredonda ao tick e devolve STRING sem notação científica.
    Bybit V5 exige takeProfit/stopLoss como string decimal (ex.: '0.000123').
    """
    p = _dec(price)
    tick = _dec(tick_size)
    if p <= 0:
        return '0'
    if tick <= 0:
        text = format(p.normalize(), 'f')
        return text if '.' in text or 'e' not in text.lower() else format(p, 'f')
    steps = (p / tick).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    snapped = steps * tick
    decimals = max(0, -tick.as_tuple().exponent)
    return f"{snapped:.{decimals}f}"


def bump_tick(price_str: str, tick_size: float | str | Decimal, *, up: bool) -> str:
    tick = _dec(tick_size)
    if tick <= 0:
        return price_str
    p = _dec(price_str)
    nxt = p + tick if up else p - tick
    if nxt <= 0:
        nxt = tick
    return format_price_tick(nxt, tick)


def is_long_side(side: str) -> bool:
    return str(side or '').strip().lower() in {'buy', 'long', 'comprar'}


def validate_tp_sl_vs_entry(
    side: str,
    entry: float,
    tp: float | None,
    sl: float | None,
    tick_size: float | str | Decimal = 0,
) -> tuple[str | None, str | None, list[str]]:
    """
    Garante TP/SL do lado certo vs entrada.
    LONG: TP > entry, SL < entry | SHORT: TP < entry, SL > entry.
    Se o tick arredondar para o lado errado, empurra 1 tick.
    """
    notes: list[str] = []
    entry_f = float(entry or 0)
    tick = _dec(tick_size)
    tp_str = format_price_tick(tp, tick) if tp and float(tp) > 0 else None
    sl_str = format_price_tick(sl, tick) if sl and float(sl) > 0 else None
    long = is_long_side(side)

    if tp_str and entry_f > 0:
        tp_f = float(tp_str)
        if long and tp_f <= entry_f:
            tp_str = bump_tick(format_price_tick(entry_f, tick) if tick > 0 else str(entry_f), tick, up=True)
            notes.append(f'TP LONG ajustado > entrada ({tp_str})')
        if (not long) and tp_f >= entry_f:
            tp_str = bump_tick(format_price_tick(entry_f, tick) if tick > 0 else str(entry_f), tick, up=False)
            notes.append(f'TP SHORT ajustado < entrada ({tp_str})')

    if sl_str and entry_f > 0:
        sl_f = float(sl_str)
        if long and sl_f >= entry_f:
            sl_str = bump_tick(format_price_tick(entry_f, tick) if tick > 0 else str(entry_f), tick, up=False)
            notes.append(f'SL LONG ajustado < entrada ({sl_str})')
        if (not long) and sl_f <= entry_f:
            sl_str = bump_tick(format_price_tick(entry_f, tick) if tick > 0 else str(entry_f), tick, up=True)
            notes.append(f'SL SHORT ajustado > entrada ({sl_str})')

    return tp_str, sl_str, notes
