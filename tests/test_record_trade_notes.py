# Simple test to verify that record_trade normalizes notes to uppercase
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
            print('Initializing DB...')
            db.init_db()
            print('Inserting test trade with notes "teste lowerCase Note"...')
            db.record_trade(client_id=1, pair='TEST:USDT', side='COMPRAR', pnl_pct=0.0, profit=0.0, closed_at='now', notes='teste lowerCase Note', status='open')
            recent = db.get_recent_trades(5)
            if not recent:
                print('❌ No trades found after insert')
                raise SystemExit(1)
            latest = recent[0]
            print('Latest trade notes:', latest.get('notes'))
            if latest.get('notes') and latest.get('notes') == latest.get('notes').upper():
                print('✅ Notes normalized to uppercase OK')
                raise SystemExit(0)
            print('❌ Notes NOT normalized:', latest.get('notes'))
            raise SystemExit(2)
        finally:
            db.DB_PATH = original_db_path
