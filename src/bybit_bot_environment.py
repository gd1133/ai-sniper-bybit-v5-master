import asyncio
import os
from dataclasses import dataclass
from typing import Any, Callable

BYBIT_PRODUCTION_URL = "https://api.bybit.com"
BYBIT_TESTNET_URL = "https://api-testnet.bybit.com"


@dataclass(frozen=True)
class SimulatedExit:
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    reason: str
    pnl_pct: float
    reward_risk_ratio: float


class BybitBotEnvironment:
    """
    Gerencia isolamento de ambiente (produção/testnet) e simulação assíncrona.
    """

    def __init__(
        self,
        *,
        env: str | None = None,
        stop_loss_pct: float = 0.01,
        reward_risk_ratio: float = 2.0,
        http_class: Callable[..., Any] | None = None,
        websocket_class: Callable[..., Any] | None = None,
    ) -> None:
        raw_env = str(env if env is not None else os.getenv("ENV", "")).strip().lower()
        self.environment = "production" if raw_env == "production" else "testnet"
        self.is_testnet = self.environment != "production"

        key_name = "TESTNET_API_KEY" if self.is_testnet else "LIVE_API_KEY"
        secret_name = "TESTNET_API_SECRET" if self.is_testnet else "LIVE_API_SECRET"
        self.api_key = str(os.getenv(key_name, "")).strip()
        self.api_secret = str(os.getenv(secret_name, "")).strip()

        if not self.api_key or not self.api_secret:
            raise ValueError(
                f"Credenciais ausentes para {self.environment}: defina {key_name} e {secret_name}."
            )

        self.base_url = BYBIT_TESTNET_URL if self.is_testnet else BYBIT_PRODUCTION_URL
        self.stop_loss_pct = abs(float(stop_loss_pct))
        self.reward_risk_ratio = float(reward_risk_ratio)
        self.take_profit_pct = self.stop_loss_pct * self.reward_risk_ratio

        self._http_class = http_class
        self._websocket_class = websocket_class
        self.http_session = None
        self.ws_session = None

    def _load_http_class(self) -> Callable[..., Any]:
        if self._http_class is not None:
            return self._http_class
        from pybit.unified_trading import HTTP

        return HTTP

    def _load_websocket_class(self) -> Callable[..., Any]:
        if self._websocket_class is not None:
            return self._websocket_class
        from pybit.unified_trading import WebSocket

        return WebSocket

    def get_http_session(self):
        if self.http_session is None:
            http_cls = self._load_http_class()
            self.http_session = http_cls(
                testnet=self.is_testnet,
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            if hasattr(self.http_session, "endpoint"):
                self.http_session.endpoint = self.base_url
        return self.http_session

    def get_websocket_session(self, channel_type: str = "linear"):
        if self.ws_session is None:
            ws_cls = self._load_websocket_class()
            self.ws_session = ws_cls(
                testnet=self.is_testnet,
                channel_type=channel_type,
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
        return self.ws_session

    async def get_last_price(self, symbol: str) -> float:
        session = self.get_http_session()
        response = await asyncio.to_thread(
            session.get_tickers,
            category="linear",
            symbol=symbol,
        )
        ticker_list = ((response or {}).get("result") or {}).get("list") or []
        if not ticker_list:
            raise ValueError(f"Ticker vazio para {symbol}")
        return float(ticker_list[0]["lastPrice"])

    def _calculate_exit(self, side: str, entry_price: float, last_price: float) -> tuple[str | None, float]:
        side_normalized = str(side).strip().lower()
        if side_normalized == "buy":
            stop_price = entry_price * (1 - self.stop_loss_pct)
            take_price = entry_price * (1 + self.take_profit_pct)
            if last_price <= stop_price:
                return "stop_loss", -(self.stop_loss_pct * 100)
            if last_price >= take_price:
                return "take_profit", self.take_profit_pct * 100
            return None, 0.0
        if side_normalized != "sell":
            raise ValueError(f"Lado inválido para simulação: {side}")
        stop_price = entry_price * (1 + self.stop_loss_pct)
        take_price = entry_price * (1 - self.take_profit_pct)
        if last_price >= stop_price:
            return "stop_loss", -(self.stop_loss_pct * 100)
        if last_price <= take_price:
            return "take_profit", self.take_profit_pct * 100
        return None, 0.0

    async def run_symbol_simulation(
        self,
        symbol: str,
        *,
        iterations: int = 30,
        poll_interval: float = 1.0,
    ) -> list[SimulatedExit]:
        last_price = None
        open_side = None
        entry_price = 0.0
        exits: list[SimulatedExit] = []

        for _ in range(iterations):
            current_price = await self.get_last_price(symbol)

            if open_side is None and last_price is not None:
                open_side = "buy" if current_price >= last_price else "sell"
                entry_price = current_price
            elif open_side is not None:
                reason, pnl_pct = self._calculate_exit(open_side, entry_price, current_price)
                if reason is not None:
                    exits.append(
                        SimulatedExit(
                            symbol=symbol,
                            side=open_side,
                            entry_price=entry_price,
                            exit_price=current_price,
                            reason=reason,
                            pnl_pct=pnl_pct,
                            reward_risk_ratio=self.reward_risk_ratio,
                        )
                    )
                    open_side = None

            last_price = current_price
            await asyncio.sleep(poll_interval)

        return exits

    async def run_parallel_simulation(
        self,
        symbols: list[str],
        *,
        iterations: int = 30,
        poll_interval: float = 1.0,
    ) -> list[SimulatedExit]:
        # Requisito do modo agressivo do Motor Sniper V60.7: 5 moedas simultâneas.
        if len(symbols) != 5:
            raise ValueError("A simulação paralela exige exatamente 5 moedas.")

        tasks = [
            asyncio.create_task(
                self.run_symbol_simulation(symbol, iterations=iterations, poll_interval=poll_interval)
            )
            for symbol in symbols
        ]
        per_symbol_results = await asyncio.gather(*tasks)
        return [exit_event for symbol_results in per_symbol_results for exit_event in symbol_results]


async def run_testnet_example() -> list[SimulatedExit]:
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]
    bot_env = BybitBotEnvironment(env="testnet", stop_loss_pct=0.01, reward_risk_ratio=2.0)
    bot_env.get_http_session()
    bot_env.get_websocket_session()
    return await bot_env.run_parallel_simulation(symbols, iterations=30, poll_interval=1.0)


if __name__ == "__main__":
    asyncio.run(run_testnet_example())
