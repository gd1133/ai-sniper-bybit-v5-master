import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import manager as db


if __name__ == '__main__':
    original_db_path = db.DB_PATH
    original_env = os.environ.get('RISK_PER_TRADE_PCT')
    original_module = sys.modules.pop('main_web', None)

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            db.DB_PATH = os.path.join(tmpdir, 'risk_test.db')

            os.environ.pop('RISK_PER_TRADE_PCT', None)
            main_web = importlib.import_module('main_web')

            if main_web._format_risk_per_trade_pct() != '5%':
                print(f"❌ Percentual padrão deveria ser 5%: {main_web._format_risk_per_trade_pct()}")
                raise SystemExit(1)

            if round(main_web._calculate_order_margin(24.99), 2) != 1.25:
                print(f"❌ Margem para saldo 24.99 inválida: {main_web._calculate_order_margin(24.99)}")
                raise SystemExit(2)

            if round(main_web._calculate_order_margin(28.02), 2) != 1.40:
                print(f"❌ Margem para saldo 28.02 inválida: {main_web._calculate_order_margin(28.02)}")
                raise SystemExit(3)

            sys.modules.pop('main_web', None)
            os.environ['RISK_PER_TRADE_PCT'] = '20'
            main_web = importlib.import_module('main_web')

            if round(main_web._calculate_order_margin(50), 2) != 10.00:
                print(f"❌ Override por ambiente não aplicado: {main_web._calculate_order_margin(50)}")
                raise SystemExit(4)

            print('✅ RISK_PER_TRADE_PCT controla a margem por ordem com fallback de 5%')
            raise SystemExit(0)
        finally:
            db.DB_PATH = original_db_path
            sys.modules.pop('main_web', None)
            if original_module is not None:
                sys.modules['main_web'] = original_module

            if original_env is None:
                os.environ.pop('RISK_PER_TRADE_PCT', None)
            else:
                os.environ['RISK_PER_TRADE_PCT'] = original_env
