import importlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import manager as db


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as tmpdir:
        original_db_path = db.DB_PATH
        original_module = sys.modules.pop('main_web', None)
        try:
            db.DB_PATH = os.path.join(tmpdir, 'test_database.db')
            main_web = importlib.import_module('main_web')

            original_fetch = main_web._fetch_active_client_balances
            original_mode = main_web.APP_MODE
            original_test_mode = main_web.TEST_MODE_ENABLED
            original_state = dict(main_web.central_state)

            sample_items = [
                {"id": 1, "nome": "Cliente Testnet", "saldo_real": 111.11, "account_mode": "testnet", "is_testnet": True},
                {"id": 2, "nome": "Cliente Real", "saldo_real": 222.22, "account_mode": "real", "is_testnet": False},
            ]

            try:
                main_web._fetch_active_client_balances = lambda force=False: {
                    "items": sample_items,
                    "total": 333.33,
                    "timestamp": 0,
                }

                main_web.APP_MODE = 'real'
                main_web.TEST_MODE_ENABLED = False
                main_web.central_state['balance'] = 1000.0
                main_web._refresh_real_balance_state(force=True)

                if main_web.central_state['balance'] != 222.22:
                    print(f"❌ Modo REAL deveria usar apenas saldo real: {main_web.central_state['balance']}")
                    raise SystemExit(1)

                real_items = main_web.central_state.get('real_client_balances', [])
                if len(real_items) != 1 or real_items[0].get('account_mode') != 'real':
                    print(f"❌ Modo REAL deveria expor apenas clientes reais: {real_items}")
                    raise SystemExit(2)

                main_web._fetch_active_client_balances = lambda force=False: {
                    "items": [sample_items[0]],
                    "total": 111.11,
                    "timestamp": 0,
                }
                main_web.central_state['balance'] = 999.99
                main_web._refresh_real_balance_state(force=True)

                if main_web.central_state['balance'] != 0.0:
                    print(f"❌ Modo REAL não pode reaproveitar saldo de teste: {main_web.central_state['balance']}")
                    raise SystemExit(3)

                print('✅ Dashboard separa corretamente saldo REAL e TESTNET')
                raise SystemExit(0)
            finally:
                main_web._fetch_active_client_balances = original_fetch
                main_web.APP_MODE = original_mode
                main_web.TEST_MODE_ENABLED = original_test_mode
                main_web.central_state.clear()
                main_web.central_state.update(original_state)
        finally:
            db.DB_PATH = original_db_path
            sys.modules.pop('main_web', None)
            if original_module is not None:
                sys.modules['main_web'] = original_module
