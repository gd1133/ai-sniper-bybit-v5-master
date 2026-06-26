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
            db.record_trade(
                client_id=1,
                pair='PIEVERSE/USDT:USDT',
                side='VENDER',
                pnl_pct=0.0,
                profit=0.0,
                closed_at='now',
                notes='broadcast test',
                status='open',
                entry_price=0.897,
            )
            latest = db.get_recent_trades(1)[0]
            saved_entry = float(latest.get('entry_price') or 0)
            if abs(saved_entry - 0.897) < 1e-9:
                print('✅ Entry price persisted correctly')
                raise SystemExit(0)
            print(f'❌ Entry price mismatch: {saved_entry}')
            raise SystemExit(2)
        finally:
            db.DB_PATH = original_db_path
