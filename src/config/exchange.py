import os
from typing import Tuple

SUPPORTED_EXCHANGES = {'bybit', 'binance'}


def normalize_exchange(value: str | None, *, default: str = 'bybit') -> str:
    raw = str(value or '').strip().lower()
    if raw in SUPPORTED_EXCHANGES:
        return raw
    return default


def get_default_exchange() -> str:
    """Exchange padrão do deploy (ex.: para scanner/preços públicos).

    Observação: cada cliente ainda pode ter sua própria exchange via banco.
    """
    return normalize_exchange(os.getenv('DEFAULT_EXCHANGE'), default='bybit')


def get_binance_credentials() -> Tuple[str, str]:
    return (
        str(os.getenv('BINANCE_API_KEY') or '').strip(),
        str(os.getenv('BINANCE_API_SECRET') or '').strip(),
    )


def get_exchange_credentials(exchange: str | None = None) -> Tuple[str, str]:
    exchange = normalize_exchange(exchange, default=get_default_exchange())
    if exchange == 'binance':
        return get_binance_credentials()

    from .bybit import get_bybit_credentials
    return get_bybit_credentials()

