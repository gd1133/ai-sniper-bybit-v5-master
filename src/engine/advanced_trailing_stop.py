from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class TrailingStopSnapshot:
    side: str
    current_price: float
    activation_price: float
    callback_pct: float
    trailing_armed: bool
    floor_price: Optional[float]
    extreme_price: Optional[float]
    mobile_trigger_price: Optional[float]
    effective_trigger_price: Optional[float]
    should_close: bool
    close_reason: Optional[str]


class AdvancedTrailingStopMonitor:
    """
    Trailing stop avançado com piso de lucro garantido.

    Regras:
    1) Ativa apenas quando preço atinge ROI de 100% sobre a margem (100/leverage).
    2) Ao ativar, grava preço de ativação como piso de lucro.
    3) Após ativar, segue topo/fundo e calcula gatilho móvel por callback.
    4) Gatilho real respeita o piso (Long=max, Short=min).
    """

    def __init__(self, entry_price: float, leverage: float, side: str, callback_pct: float = 2.0) -> None:
        if entry_price <= 0:
            raise ValueError("entry_price must be greater than zero")
        if leverage <= 0:
            raise ValueError("leverage must be greater than zero")
        if callback_pct <= 0:
            raise ValueError("callback_pct must be greater than zero")

        self.entry_price = float(entry_price)
        self.leverage = float(leverage)
        self.side = self._normalize_side(side)
        self.callback_pct = float(callback_pct)
        self.callback_factor = self.callback_pct / 100.0
        self.activation_price = self._compute_activation_price(self.entry_price, self.leverage, self.side)

        self.trailing_armed: bool = False
        self.floor_price: Optional[float] = None
        self.extreme_price: Optional[float] = None
        self.mobile_trigger_price: Optional[float] = None
        self.effective_trigger_price: Optional[float] = None
        self.last_price: Optional[float] = None

    @staticmethod
    def _normalize_side(side: str) -> str:
        normalized = str(side or "").strip().lower()
        if normalized in {"buy", "long", "comprar"}:
            return "buy"
        if normalized in {"sell", "short", "vender"}:
            return "sell"
        raise ValueError(f"unsupported side: {side}")

    @staticmethod
    def _compute_activation_price(entry_price: float, leverage: float, side: str) -> float:
        variation = 1.0 / leverage
        if side == "buy":
            return entry_price * (1.0 + variation)
        return entry_price * (1.0 - variation)

    def update_price(self, current_price: float) -> TrailingStopSnapshot:
        price = float(current_price)
        if price <= 0:
            raise ValueError("current_price must be greater than zero")

        if not self.trailing_armed:
            if self._reached_activation(price):
                self.trailing_armed = True

            if self.trailing_armed:
                self.floor_price = self.activation_price
                self.extreme_price = price

        should_close = False
        reason = None

        if self.trailing_armed:
            self._update_extreme(price)
            self.mobile_trigger_price = self._build_mobile_trigger()
            self.effective_trigger_price = self._build_effective_trigger()
            should_close = self._is_exit_crossed(price, self.effective_trigger_price)
            if should_close:
                reason = "TRAILING_FLOOR_CALLBACK"

        snapshot = TrailingStopSnapshot(
            side=self.side,
            current_price=price,
            activation_price=self.activation_price,
            callback_pct=self.callback_pct,
            trailing_armed=self.trailing_armed,
            floor_price=self.floor_price,
            extreme_price=self.extreme_price,
            mobile_trigger_price=self.mobile_trigger_price,
            effective_trigger_price=self.effective_trigger_price,
            should_close=should_close,
            close_reason=reason,
        )
        self.last_price = price
        return snapshot

    def _update_extreme(self, price: float) -> None:
        if self.extreme_price is None:
            self.extreme_price = price
            return
        if self.side == "buy":
            self.extreme_price = max(self.extreme_price, price)
        else:
            self.extreme_price = min(self.extreme_price, price)

    def _build_mobile_trigger(self) -> Optional[float]:
        if self.extreme_price is None:
            return None
        if self.side == "buy":
            return self.extreme_price * (1.0 - self.callback_factor)
        return self.extreme_price * (1.0 + self.callback_factor)

    def _build_effective_trigger(self) -> Optional[float]:
        if self.floor_price is None or self.mobile_trigger_price is None:
            return None
        if self.side == "buy":
            return max(self.mobile_trigger_price, self.floor_price)
        return min(self.mobile_trigger_price, self.floor_price)

    def _is_exit_crossed(self, price: float, trigger: Optional[float]) -> bool:
        if trigger is None:
            return False
        if self.last_price is None:
            return False
        if self.side == "buy":
            return self.last_price > trigger and price <= trigger
        return self.last_price < trigger and price >= trigger

    def _reached_activation(self, price: float) -> bool:
        eps = max(1e-9, abs(self.activation_price) * 1e-9)
        if self.side == "buy":
            return price + eps >= self.activation_price
        return price - eps <= self.activation_price


def simulate_trailing_stop_example() -> List[Tuple[str, TrailingStopSnapshot]]:
    """
    Exemplo prático de atualização de ticker no tempo (Long e Short).
    Retorna snapshots para uso em logs, testes ou debug.
    """
    events: List[Tuple[str, TrailingStopSnapshot]] = []

    long_monitor = AdvancedTrailingStopMonitor(entry_price=100.0, leverage=10.0, side="Buy", callback_pct=2.0)
    for price in [100.0, 105.0, 110.0, 116.0, 114.0, 113.5]:
        snapshot = long_monitor.update_price(price)
        events.append(("long", snapshot))
        if snapshot.should_close:
            break

    short_monitor = AdvancedTrailingStopMonitor(entry_price=100.0, leverage=10.0, side="Sell", callback_pct=2.0)
    for price in [100.0, 95.0, 90.0, 84.0, 85.6, 86.0]:
        snapshot = short_monitor.update_price(price)
        events.append(("short", snapshot))
        if snapshot.should_close:
            break

    return events
