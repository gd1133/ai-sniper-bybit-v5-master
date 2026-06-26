import asyncio
import os

from src.bybit_bot_environment import (
    BYBIT_PRODUCTION_URL,
    BYBIT_TESTNET_URL,
    BybitBotEnvironment,
)


class _FakeHTTP:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.endpoint = None
        self._prices = {
            "BTCUSDT": [100.0, 101.0, 104.0],
            "ETHUSDT": [100.0, 99.0, 96.0],
            "SOLUSDT": [100.0, 102.0, 100.0],
            "DOGEUSDT": [100.0, 98.0, 100.0],
            "XRPUSDT": [100.0, 101.0, 104.0],
        }
        self._cursor = {symbol: 0 for symbol in self._prices}

    def get_tickers(self, category, symbol):
        assert category == "linear"
        prices = self._prices[symbol]
        idx = self._cursor[symbol]
        price = prices[idx] if idx < len(prices) else prices[-1]
        self._cursor[symbol] = idx + 1
        return {"result": {"list": [{"lastPrice": str(price)}]}}


class _FakeWebSocket:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _set_shared_creds():
    os.environ["LIVE_API_KEY"] = "live-key"
    os.environ["LIVE_API_SECRET"] = "live-secret"
    os.environ["TESTNET_API_KEY"] = "test-key"
    os.environ["TESTNET_API_SECRET"] = "test-secret"


def test_fail_safe_defaults_to_testnet(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    _set_shared_creds()

    env = BybitBotEnvironment(http_class=_FakeHTTP, websocket_class=_FakeWebSocket)

    assert env.environment == "testnet"
    assert env.is_testnet is True
    assert env.api_key == "test-key"
    assert env.api_secret == "test-secret"
    assert env.base_url == BYBIT_TESTNET_URL

    http_session = env.get_http_session()
    ws_session = env.get_websocket_session()
    assert http_session.kwargs["testnet"] is True
    assert ws_session.kwargs["testnet"] is True
    assert http_session.endpoint == BYBIT_TESTNET_URL


def test_production_uses_live_credentials(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    _set_shared_creds()

    env = BybitBotEnvironment(http_class=_FakeHTTP, websocket_class=_FakeWebSocket)
    http_session = env.get_http_session()
    ws_session = env.get_websocket_session()

    assert env.environment == "production"
    assert env.is_testnet is False
    assert env.api_key == "live-key"
    assert env.api_secret == "live-secret"
    assert env.base_url == BYBIT_PRODUCTION_URL
    assert http_session.kwargs["testnet"] is False
    assert ws_session.kwargs["testnet"] is False
    assert http_session.endpoint == BYBIT_PRODUCTION_URL


def test_parallel_simulation_runs_five_symbols_with_2_to_1(monkeypatch):
    monkeypatch.setenv("ENV", "testnet")
    _set_shared_creds()

    env = BybitBotEnvironment(
        stop_loss_pct=0.01,
        reward_risk_ratio=2.0,
        http_class=_FakeHTTP,
        websocket_class=_FakeWebSocket,
    )

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]
    results = asyncio.run(env.run_parallel_simulation(symbols, iterations=3, poll_interval=0))

    assert len(results) == 5
    assert {result.symbol for result in results} == set(symbols)
    assert all(result.reward_risk_ratio == 2.0 for result in results)
    assert {result.reason for result in results} == {"take_profit", "stop_loss"}
