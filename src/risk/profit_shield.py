# -*- coding: utf-8 -*-
"""
Trailing Profit Shield — Escada de Lucro (proteção dinâmica).

Problema: mirar +100% ROI @20x exige ~5% de preço; o mercado frequentemente
reverte após ~+50% ROI (~2.5% de preço) e transforma vitória em stop.

Solução (incremental, não remove TP/SL finais):
  1. Ordem abre com TP +100% ROI e SL −50% ROI (inalterado).
  2. Quando ROI unrealised >= 50%, move o Stop Loss na Bybit para travar
     ~+20% ROI (≈ +1% de preço @20x) — "vitória garantida" se reverter.
  3. Estado PROTEGIDO_50 evita reenviar set_trading_stop a cada ciclo.
"""

from __future__ import annotations

import os
import threading
from typing import Any


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == '':
        return default
    try:
        return float(str(raw).replace(',', '.'))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


# Gatilho: ROI da margem >= 50% → arma proteção
DEFAULT_SHIELD_TRIGGER_ROI = 50.0
# Lucro travado no SL movido: +20% ROI ≈ 1% de preço @20x
DEFAULT_SHIELD_LOCK_ROI = 20.0


def load_shield_trigger_roi() -> float:
    return abs(_env_float('PROFIT_SHIELD_TRIGGER_ROI', DEFAULT_SHIELD_TRIGGER_ROI))


def load_shield_lock_roi() -> float:
    return abs(_env_float('PROFIT_SHIELD_LOCK_ROI', DEFAULT_SHIELD_LOCK_ROI))


def profit_shield_enabled() -> bool:
    return _env_bool('ENABLE_PROFIT_SHIELD', True)


def compute_roi_pct_from_price(
    entry_price: float,
    mark_price: float,
    side: str,
    leverage: float = 20.0,
) -> float:
    """ROI % sobre margem ≈ variação de preço × alavancagem."""
    entry = float(entry_price or 0)
    mark = float(mark_price or 0)
    lev = max(float(leverage or 1), 1.0)
    if entry <= 0 or mark <= 0:
        return 0.0
    side_n = str(side or '').strip().lower()
    if side_n in ('buy', 'long', 'comprar'):
        price_pct = (mark - entry) / entry
    else:
        price_pct = (entry - mark) / entry
    return price_pct * 100.0 * lev


def compute_protected_sl_price(
    entry_price: float,
    side: str,
    leverage: float = 20.0,
    lock_roi_pct: float | None = None,
) -> float:
    """
    Preço de SL que trava lock_roi_pct de ROI na margem.

    @20x e lock=20% → movimento de preço = 20/20 = 1%
      Long:  entry * 1.01
      Short: entry * 0.99
    """
    entry = float(entry_price or 0)
    lev = max(float(leverage or 1), 1.0)
    lock = abs(float(lock_roi_pct if lock_roi_pct is not None else load_shield_lock_roi()))
    if entry <= 0:
        return 0.0
    move = (lock / 100.0) / lev
    side_n = str(side or '').strip().lower()
    if side_n in ('buy', 'long', 'comprar'):
        return entry * (1.0 + move)
    return entry * (1.0 - move)


class ProfitShieldRegistry:
    """Memória de posições já protegidas (client_id, symbol) — evita spam na API."""

    def __init__(self) -> None:
        self._armed: set[tuple[int, str]] = set()
        self._lock = threading.Lock()

    @staticmethod
    def _key(client_id: int, symbol: str) -> tuple[int, str]:
        return (int(client_id or 0), str(symbol or '').upper().replace('/', '').replace(':', ''))

    def is_protected(self, client_id: int, symbol: str) -> bool:
        with self._lock:
            return self._key(client_id, symbol) in self._armed

    def mark_protected(self, client_id: int, symbol: str) -> None:
        with self._lock:
            self._armed.add(self._key(client_id, symbol))

    def clear(self, client_id: int, symbol: str) -> None:
        with self._lock:
            self._armed.discard(self._key(client_id, symbol))

    def clear_client(self, client_id: int) -> None:
        with self._lock:
            self._armed = {k for k in self._armed if k[0] != int(client_id or 0)}


_REGISTRY = ProfitShieldRegistry()


def get_profit_shield_registry() -> ProfitShieldRegistry:
    return _REGISTRY


def apply_profit_shield_if_needed(
    broker: Any,
    *,
    client_id: int,
    symbol: str,
    side: str,
    entry_price: float,
    mark_price: float,
    leverage: float,
    unrealised_pnl: float | None = None,
    entry_margin: float | None = None,
) -> dict[str, Any]:
    """
    Se ROI >= gatilho e ainda não protegido → move SL na Bybit para lock ROI.
    Retorna dict com applied/skipped/reason.
    """
    result = {
        'applied': False,
        'skipped': True,
        'reason': '',
        'roi_pct': 0.0,
        'new_sl': 0.0,
        'status': 'AGUARDANDO_PROTECAO',
    }
    if not profit_shield_enabled():
        result['reason'] = 'shield desativado'
        return result

    reg = get_profit_shield_registry()
    if reg.is_protected(client_id, symbol):
        result['reason'] = 'já PROTEGIDO_50'
        result['status'] = 'PROTEGIDO_50'
        return result

    # Preferir ROI pela margem real (mesma métrica do monitor 100/50)
    roi = 0.0
    if entry_margin and float(entry_margin) > 0 and unrealised_pnl is not None:
        from src.risk.position_sizing import position_roi_pct
        roi = float(position_roi_pct(unrealised_pnl, entry_margin))
    else:
        roi = compute_roi_pct_from_price(entry_price, mark_price, side, leverage)

    result['roi_pct'] = round(roi, 2)
    trigger = load_shield_trigger_roi()
    if roi < trigger:
        result['reason'] = f'ROI {roi:.1f}% < gatilho {trigger:.0f}%'
        return result

    lock_roi = load_shield_lock_roi()
    new_sl = compute_protected_sl_price(entry_price, side, leverage, lock_roi)
    result['new_sl'] = new_sl
    if new_sl <= 0:
        result['reason'] = 'SL protegido inválido'
        return result

    # Atualiza só o Stop Loss; mantém Take Profit final (+100%) intacto
    ok = False
    try:
        if hasattr(broker, 'update_stop_loss_only'):
            ok = bool(broker.update_stop_loss_only(symbol, side, new_sl))
        elif hasattr(broker, 'pybit_session') and broker.pybit_session:
            side_n = str(side or '').strip().lower()
            pos_idx = 1 if side_n in ('buy', 'long', 'comprar') else 2
            v5_symbol = broker._normalize_v5_symbol(symbol) if hasattr(broker, '_normalize_v5_symbol') else symbol
            price_to_precision = getattr(getattr(broker, 'exchange', None), 'price_to_precision', None)
            sl_str = str(new_sl)
            if callable(price_to_precision):
                try:
                    sl_str = str(price_to_precision(symbol, float(new_sl)))
                except Exception:
                    sl_str = str(new_sl)
            rsp = broker.pybit_session.set_trading_stop(
                category='linear',
                symbol=v5_symbol,
                stopLoss=sl_str,
                positionIdx=pos_idx,
                tpslMode='Full',
            )
            ok, _err = broker._handle_v5_ret_code(rsp, 'set_trading_stop_shield')
    except Exception as exc:
        result['reason'] = f'erro API: {exc}'
        return result

    if not ok:
        result['reason'] = 'set_trading_stop falhou'
        return result

    reg.mark_protected(client_id, symbol)
    result['applied'] = True
    result['skipped'] = False
    result['reason'] = f'SL movido para {new_sl} (+{lock_roi:.0f}% ROI travado)'
    result['status'] = 'PROTEGIDO_50'

    # Best-effort: anota no SQLite local
    try:
        from src.database import manager as db
        if hasattr(db, 'mark_trade_profit_shield'):
            db.mark_trade_profit_shield(client_id, symbol, new_sl, roi)
    except Exception:
        pass

    return result
