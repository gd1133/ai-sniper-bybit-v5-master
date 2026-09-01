# -*- coding: utf-8 -*-
"""
Monitor local de TP/SL para ordens SPOT.

Spot não aceita takeProfit/stopLoss inline como linear — o robô monitora
preço e envia ordem a mercado de saída quando TP ou SL é atingido.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_positions: dict[str, dict[str, Any]] = {}


def _key(client_id: int | str, symbol: str) -> str:
    return f'{client_id}:{to_v5(symbol)}'


def to_v5(symbol: str) -> str:
    from src.broker.symbol_utils import to_v5_symbol
    return to_v5_symbol(symbol)


def register_spot_position(
    *,
    client_id: int | str,
    symbol: str,
    side: str,
    qty: float,
    entry_price: float,
    tp_price: float | None = None,
    sl_price: float | None = None,
) -> None:
    side_norm = str(side or '').strip().lower()
    if side_norm not in ('buy', 'sell', 'comprar', 'vender', 'long', 'short'):
        side_norm = 'buy'
    is_long = side_norm in ('buy', 'comprar', 'long')
    with _lock:
        _positions[_key(client_id, symbol)] = {
            'client_id': client_id,
            'symbol': symbol,
            'side': 'buy' if is_long else 'sell',
            'qty': float(qty or 0),
            'entry_price': float(entry_price or 0),
            'tp_price': float(tp_price) if tp_price else None,
            'sl_price': float(sl_price) if sl_price else None,
            'registered_at': time.time(),
        }
    print(
        f'   🛡️ [SPOT TP/SL] Monitor local ativo {symbol} '
        f'entry={entry_price} TP={tp_price} SL={sl_price}',
        flush=True,
    )


def unregister_spot_position(client_id: int | str, symbol: str) -> None:
    with _lock:
        _positions.pop(_key(client_id, symbol), None)


def list_spot_positions() -> list[dict[str, Any]]:
    with _lock:
        return list(_positions.values())


def check_spot_exits(broker, client_id: int | str) -> None:
    """Avalia TP/SL local e envia ordem de saída a mercado se necessário."""
    if broker is None or not getattr(broker, 'is_spot_trading', lambda: False)():
        return

    with _lock:
        items = [
            (k, dict(v))
            for k, v in _positions.items()
            if str(v.get('client_id')) == str(client_id)
        ]

    for key, pos in items:
        symbol = pos['symbol']
        qty = float(pos.get('qty') or 0)
        if qty <= 0:
            with _lock:
                _positions.pop(key, None)
            continue

        try:
            mark = float(broker.get_last_price(symbol) or 0)
        except Exception:
            continue
        if mark <= 0:
            continue

        tp = pos.get('tp_price')
        sl = pos.get('sl_price')
        is_long = pos.get('side') == 'buy'
        hit_tp = tp and ((mark >= tp) if is_long else (mark <= tp))
        hit_sl = sl and ((mark <= sl) if is_long else (mark >= sl))

        if not hit_tp and not hit_sl:
            continue

        exit_side = 'sell' if is_long else 'buy'
        reason = 'TP' if hit_tp else 'SL'
        print(
            f'   🎯 [SPOT {reason}] {symbol} mark={mark:.6g} → saída {exit_side} qty={qty}',
            flush=True,
        )
        try:
            result = broker.execute_market_order(
                symbol, exit_side, qty, raise_on_error=False, strict_pct_sizing=True,
            )
            if result:
                with _lock:
                    _positions.pop(key, None)
        except Exception as exc:
            print(f'   ⚠️ [SPOT EXIT] Falha ao sair {symbol}: {exc}', flush=True)
