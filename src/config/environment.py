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

    # Lê variáveis de ambiente com conversão estrita para booleano
    use_testnet_raw = os.getenv('USE_TESTNET', 'true' if default_use_testnet else 'false')
    allow_real_trading_raw = os.getenv('ALLOW_REAL_TRADING', 'true' if default_allow_real_trading else 'false')
    allow_order_execution_raw = os.getenv('ALLOW_ORDER_EXECUTION', 'true' if default_allow_order_execution else 'false')

    # Converte estritamente para booleano usando is_truthy()
    use_testnet = is_truthy(use_testnet_raw)
    allow_real_trading = is_truthy(allow_real_trading_raw)
    allow_order_execution = is_truthy(allow_order_execution_raw)

    # Log de diagnóstico da conversão
    print(f"🔧 [ENV CONFIG] ENVIRONMENT: {environment}")
    print(f"🔧 [ENV CONFIG] USE_TESTNET: '{use_testnet_raw}' -> {use_testnet}")
    print(f"🔧 [ENV CONFIG] ALLOW_REAL_TRADING: '{allow_real_trading_raw}' -> {allow_real_trading}")
    print(f"🔧 [ENV CONFIG] ALLOW_ORDER_EXECUTION: '{allow_order_execution_raw}' -> {allow_order_execution}")

    return EnvironmentConfig(
        name=environment,
        use_testnet=use_testnet,
        allow_real_trading=allow_real_trading,
        allow_order_execution=allow_order_execution,
        default_operation_mode=default_operation_mode,
    )
