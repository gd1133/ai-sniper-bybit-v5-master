import os
from dataclasses import dataclass
from typing import Any

TRUTHY_VALUES = {'1', 'true', 'yes', 'on'}
VALID_ENVIRONMENTS = {'development', 'production'}


def is_truthy(value: Any) -> bool:
    return str(value or '').strip().lower() in TRUTHY_VALUES


def get_environment_name() -> str:
    raw_value = str(os.getenv('ENVIRONMENT', 'development') or '').strip().lower()
    return raw_value if raw_value in VALID_ENVIRONMENTS else 'development'


@dataclass(frozen=True)
class EnvironmentConfig:
    name: str
    use_testnet: bool
    allow_real_trading: bool
    allow_order_execution: bool
    default_operation_mode: str


def get_environment_config() -> EnvironmentConfig:
    environment = get_environment_name()
    is_production = environment == 'production'

    default_use_testnet = not is_production
    default_allow_real_trading = is_production
    default_allow_order_execution = is_production
    default_operation_mode = 'real' if is_production else 'testnet'

    return EnvironmentConfig(
        name=environment,
        use_testnet=is_truthy(os.getenv('USE_TESTNET', 'true' if default_use_testnet else 'false')),
        allow_real_trading=is_truthy(
            os.getenv('ALLOW_REAL_TRADING', 'true' if default_allow_real_trading else 'false')
        ),
        allow_order_execution=is_truthy(
            os.getenv('ALLOW_ORDER_EXECUTION', 'true' if default_allow_order_execution else 'false')
        ),
        default_operation_mode=default_operation_mode,
    )
