import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import manager as db


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as tmpdir:
        original_db_path = db.DB_PATH
        try:
            db.DB_PATH = os.path.join(tmpdir, 'test_database.db')
            db.init_db()

            client_id = db.add_client({
                'nome': 'Cliente Real',
                'bybit_key': 'key',
                'bybit_secret': 'secret',
                'account_mode': 'real',
                'saldo_base': 250.0,
            })
            saved = db.get_client_by_id(client_id)
            if saved.get('account_mode') != 'real' or int(saved.get('is_testnet') or 0) != 0:
                print(f"❌ Persistência inválida para conta real: {saved}")
                raise SystemExit(1)

            db.update_client(client_id, {
                'nome': 'Cliente Testnet',
                'bybit_key': 'key',
                'bybit_secret': 'secret',
                'account_mode': 'testnet',
                'saldo_base': 150.0,
                'status': 'ativo',
            })
            updated = db.get_client_by_id(client_id)
            if updated.get('account_mode') != 'testnet' or int(updated.get('is_testnet') or 0) != 1:
                print(f"❌ Persistência inválida para conta testnet: {updated}")
                raise SystemExit(2)

            db.set_operation_mode('real')
            if db.get_operation_mode() != 'real':
                print(f"❌ APP_MODE não persistiu: {db.get_operation_mode()}")
                raise SystemExit(3)

            print('✅ Account mode e APP_MODE persistidos corretamente')
            raise SystemExit(0)
        finally:
            db.DB_PATH = original_db_path
