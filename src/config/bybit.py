import os
from typing import Any, Tuple

BYBIT_TESTNET_URL = 'https://api-testnet.bybit.com'
BYBIT_PRODUCTION_URL = 'https://api.bybit.com'
_TRUTHY_VALUES = {'1', 'true', 'yes', 'on'}


def _is_truthy(value: Any) -> bool:
    return str(value or '').strip().lower() in _TRUTHY_VALUES


def resolve_use_testnet(value: Any = None, *, default: bool = True) -> bool:
    if value is None:
        raw_value = os.getenv('USE_TESTNET', 'true' if default else 'false')
        return _is_truthy(raw_value)
    return _is_truthy(value) if isinstance(value, str) else bool(value)


def get_bybit_base_url(use_testnet: Any = None) -> str:
    return BYBIT_TESTNET_URL if resolve_use_testnet(use_testnet) else BYBIT_PRODUCTION_URL


def get_bybit_credentials() -> Tuple[str, str]:
    return (
        str(os.getenv('BYBIT_API_KEY') or '').strip(),
        str(os.getenv('BYBIT_API_SECRET') or '').strip(),
    )
