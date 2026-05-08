import os
import sys

os.environ.setdefault("ALLOW_ORDER_EXECUTION", "true")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main_web


class _InlineThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


class _FakeBroker:
    def __init__(self, label, calls):
        self._label = label
        self._calls = calls

    def execute_market_order(self, symbol, side, qty):
        self._calls.append(("order", self._label, symbol, side, round(float(qty), 8)))
        return {"id": f"ok-{self._label}"}

    def set_tp_sl_sniper(self, symbol, side, entry_price, position_qty):
        self._calls.append(("tp_sl", self._label, symbol, side))
        return True


def _run_case(side, expected_side):
    calls = []

    client_bybit = {
        "id": 1,
        "nome": "bybit-acc",
        "exchange": "bybit",
        "account_mode": "testnet",
        "saldo_base": 1000.0,
        "status": "ativo",
    }
    client_binance = {
        "id": 2,
        "nome": "binance-acc",
        "exchange": "binance",
        "account_mode": "testnet",
        "saldo_base": 1000.0,
        "status": "ativo",
    }

    main_web.APP_MODE = "testnet"
    main_web.threading.Thread = _InlineThread
    main_web._get_master_telegram_config = lambda: ("", "")
    main_web._reserve_signal_slot = lambda symbol: (True, "ok")
    main_web._release_signal_slot = lambda symbol: None
    main_web._get_registered_clients = lambda active_only=False: [client_bybit, client_binance]
    main_web._make_broker = lambda client: _FakeBroker(client.get("exchange"), calls)
    main_web._is_order_execution_enabled = lambda mode: True

    result = main_web.broadcast_ordem_global(
        "BTC/USDT:USDT",
        side,
        100.0,
        {"probabilidade": 70, "motivo": "teste"},
    )

    if not result or not result.get("accepted"):
        print(f"❌ broadcast_ordem_global deveria aceitar: {result}")
        raise SystemExit(1)

    # Bybit mantém :USDT
    expected_bybit = ("order", "bybit", "BTC/USDT:USDT", expected_side, 0.5)
    # Binance recebe símbolo sem sufixo
    expected_binance = ("order", "binance", "BTC/USDT", expected_side, 0.5)

    if expected_bybit not in calls:
        print(f"❌ chamada Bybit não encontrada.\nEsperado: {expected_bybit}\nCalls: {calls}")
        raise SystemExit(2)

    if expected_binance not in calls:
        print(f"❌ chamada Binance não encontrada.\nEsperado: {expected_binance}\nCalls: {calls}")
        raise SystemExit(3)

    return calls


if __name__ == "__main__":
    _run_case("COMPRAR", "buy")
    _run_case("VENDER", "sell")
    print("✅ Broadcast executa Bybit+Binance com símbolo/lado normalizados")
    raise SystemExit(0)

