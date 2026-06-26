import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import get_environment_config


if __name__ == '__main__':
    original_environment = os.environ.get('ENVIRONMENT')
    original_use_testnet = os.environ.get('USE_TESTNET')
    original_allow_real = os.environ.get('ALLOW_REAL_TRADING')
    original_allow_exec = os.environ.get('ALLOW_ORDER_EXECUTION')

    try:
        os.environ['ENVIRONMENT'] = 'development'
        os.environ.pop('USE_TESTNET', None)
        os.environ.pop('ALLOW_REAL_TRADING', None)
        os.environ.pop('ALLOW_ORDER_EXECUTION', None)

        development = get_environment_config()
        if development.name != 'development':
            print(f"❌ ENVIRONMENT development incorreto: {development}")
            raise SystemExit(1)
        if development.use_testnet is not True or development.allow_real_trading is not False or development.allow_order_execution is not False:
            print(f"❌ Defaults de development incorretos: {development}")
            raise SystemExit(2)
        if development.default_operation_mode != 'testnet':
            print(f"❌ Modo padrão de development incorreto: {development.default_operation_mode}")
            raise SystemExit(3)

        os.environ['ENVIRONMENT'] = 'production'
        production = get_environment_config()
        if production.name != 'production':
            print(f"❌ ENVIRONMENT production incorreto: {production}")
            raise SystemExit(4)
        if production.use_testnet is not False or production.allow_real_trading is not True or production.allow_order_execution is not True:
            print(f"❌ Defaults de production incorretos: {production}")
            raise SystemExit(5)
        if production.default_operation_mode != 'real':
            print(f"❌ Modo padrão de production incorreto: {production.default_operation_mode}")
            raise SystemExit(6)

        os.environ['ALLOW_ORDER_EXECUTION'] = 'false'
        override = get_environment_config()
        if override.allow_order_execution is not False:
            print(f"❌ Override explícito não respeitado: {override}")
            raise SystemExit(7)

        print('✅ ENVIRONMENT centraliza os defaults com overrides opcionais')
        raise SystemExit(0)
    finally:
        if original_environment is None:
            os.environ.pop('ENVIRONMENT', None)
        else:
            os.environ['ENVIRONMENT'] = original_environment

        if original_use_testnet is None:
            os.environ.pop('USE_TESTNET', None)
        else:
            os.environ['USE_TESTNET'] = original_use_testnet

        if original_allow_real is None:
            os.environ.pop('ALLOW_REAL_TRADING', None)
        else:
            os.environ['ALLOW_REAL_TRADING'] = original_allow_real

        if original_allow_exec is None:
            os.environ.pop('ALLOW_ORDER_EXECUTION', None)
        else:
            os.environ['ALLOW_ORDER_EXECUTION'] = original_allow_exec
