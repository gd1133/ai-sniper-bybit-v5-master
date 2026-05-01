"""
Advanced tests for src/database/manager.py:
  - normalize_account_mode / normalize_operation_mode edge cases
  - close_trade updates the correct row
  - delete_client cascades to associated trades
  - upsert_client_local creates or updates depending on whether the id exists
  - get_open_trades filters by status correctly
  - get_last_closed_trade returns the most recent closed trade
  - get_config / set_config round-trip
  - get_test_balance / set_test_balance
  - is_test_mode_enabled
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import manager as db


def _setup_db(tmpdir):
    db.DB_PATH = os.path.join(tmpdir, 'test_advanced.db')
    db.init_db()


# ---------------------------------------------------------------------------
# normalize_account_mode
# ---------------------------------------------------------------------------

def test_normalize_account_mode_valid():
    assert db.normalize_account_mode('testnet') == 'testnet'
    assert db.normalize_account_mode('real') == 'real'


def test_normalize_account_mode_bool_coercion():
    assert db.normalize_account_mode(True) == 'testnet'
    assert db.normalize_account_mode(False) == 'real'
    assert db.normalize_account_mode(1) == 'testnet'
    assert db.normalize_account_mode(0) == 'real'


def test_normalize_account_mode_string_bool():
    assert db.normalize_account_mode('true') == 'testnet'
    assert db.normalize_account_mode('false') == 'real'
    assert db.normalize_account_mode('1') == 'testnet'
    assert db.normalize_account_mode('0') == 'real'


def test_normalize_account_mode_unknown_defaults_to_testnet():
    assert db.normalize_account_mode(None) == 'testnet'
    assert db.normalize_account_mode('') == 'testnet'
    assert db.normalize_account_mode('paper') == 'testnet'


# ---------------------------------------------------------------------------
# normalize_operation_mode
# ---------------------------------------------------------------------------

def test_normalize_operation_mode_valid():
    assert db.normalize_operation_mode('paper') == 'paper'
    assert db.normalize_operation_mode('testnet') == 'testnet'
    assert db.normalize_operation_mode('real') == 'real'


def test_normalize_operation_mode_test_alias():
    assert db.normalize_operation_mode('test') == 'paper'


def test_normalize_operation_mode_unknown_defaults_to_paper():
    assert db.normalize_operation_mode(None) == 'paper'
    assert db.normalize_operation_mode('') == 'paper'
    assert db.normalize_operation_mode('live') == 'paper'


# ---------------------------------------------------------------------------
# close_trade
# ---------------------------------------------------------------------------

def test_close_trade_updates_row():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            client_id = db.add_client({'nome': 'Tester', 'account_mode': 'real'})
            db.record_trade(
                client_id=client_id,
                pair='ETH/USDT:USDT',
                side='COMPRAR',
                pnl_pct=0.0,
                profit=0.0,
                closed_at='',
                notes='open note',
                status='open',
                entry_price=1800.0,
            )
            open_trades = db.get_open_trades()
            assert len(open_trades) == 1
            trade_id = open_trades[0]['id']

            result = db.close_trade(
                trade_id=trade_id,
                pnl_pct=2.5,
                profit=25.0,
                closed_at='2025-01-01T00:00:00',
                notes='closed by test',
            )
            assert result is True

            recent = db.get_recent_trades(10)
            closed = [t for t in recent if t['id'] == trade_id][0]
            assert closed['status'] == 'closed'
            assert abs(float(closed['pnl_pct']) - 2.5) < 1e-9
            assert closed['notes'] == 'CLOSED BY TEST'
        finally:
            db.DB_PATH = original_path


# ---------------------------------------------------------------------------
# delete_client — cascades to trades
# ---------------------------------------------------------------------------

def test_delete_client_removes_associated_trades():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            client_id = db.add_client({'nome': 'ToDelete', 'account_mode': 'testnet'})
            db.record_trade(
                client_id=client_id,
                pair='BTC/USDT:USDT',
                side='VENDER',
                pnl_pct=0.0,
                profit=0.0,
                closed_at='now',
                status='open',
            )
            # Confirm trade exists
            assert any(t['client_id'] == client_id for t in db.get_recent_trades(50))

            deleted = db.delete_client(client_id)
            assert deleted is True

            # Client should be gone
            assert db.get_client_by_id(client_id) is None

            # Trades for this client should also be gone
            remaining = [t for t in db.get_recent_trades(50) if t.get('client_id') == client_id]
            assert remaining == [], f'Expected no trades after delete, got {remaining}'
        finally:
            db.DB_PATH = original_path


def test_delete_nonexistent_client_returns_true():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            # Deleting a non-existent id should not raise and should succeed
            result = db.delete_client(99999)
            assert result is True
        finally:
            db.DB_PATH = original_path


# ---------------------------------------------------------------------------
# upsert_client_local
# ---------------------------------------------------------------------------

def test_upsert_client_local_creates_new_when_no_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            result = db.upsert_client_local({'nome': 'NewClient', 'account_mode': 'real'})
            assert result  # truthy = new id

            all_clients = db.get_all_clients()
            assert any(c['nome'] == 'NewClient' for c in all_clients)
        finally:
            db.DB_PATH = original_path


def test_upsert_client_local_updates_existing_when_id_present():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            cid = db.add_client({'nome': 'Original', 'account_mode': 'testnet', 'saldo_base': 100.0})

            result = db.upsert_client_local({'id': cid, 'nome': 'Updated', 'account_mode': 'real', 'saldo_base': 200.0})
            assert result is True

            updated = db.get_client_by_id(cid)
            assert updated['nome'] == 'Updated'
            assert updated['account_mode'] == 'real'
            assert abs(float(updated['saldo_base']) - 200.0) < 1e-9
        finally:
            db.DB_PATH = original_path


def test_upsert_client_local_inserts_with_explicit_id_when_not_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            result = db.upsert_client_local({'id': 42, 'nome': 'Explicit', 'account_mode': 'testnet'})
            assert result

            saved = db.get_client_by_id(42)
            assert saved is not None
            assert saved['nome'] == 'Explicit'
        finally:
            db.DB_PATH = original_path


# ---------------------------------------------------------------------------
# get_open_trades
# ---------------------------------------------------------------------------

def test_get_open_trades_returns_only_open():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            client_id = db.add_client({'nome': 'TraderA', 'account_mode': 'real'})
            db.record_trade(client_id=client_id, pair='X/USDT', side='COMPRAR',
                            pnl_pct=0, profit=0, closed_at='', status='open')
            db.record_trade(client_id=client_id, pair='Y/USDT', side='VENDER',
                            pnl_pct=1.0, profit=10.0, closed_at='2025-01-01', status='closed')

            open_trades = db.get_open_trades()
            assert len(open_trades) == 1
            assert open_trades[0]['pair'] == 'X/USDT'
        finally:
            db.DB_PATH = original_path


def test_get_open_trades_returns_empty_when_none_open():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            client_id = db.add_client({'nome': 'TraderB', 'account_mode': 'real'})
            db.record_trade(client_id=client_id, pair='Z/USDT', side='COMPRAR',
                            pnl_pct=0, profit=0, closed_at='2025-01-01', status='closed')
            open_trades = db.get_open_trades()
            assert open_trades == []
        finally:
            db.DB_PATH = original_path


# ---------------------------------------------------------------------------
# get_last_closed_trade
# ---------------------------------------------------------------------------

def test_get_last_closed_trade_returns_most_recent():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            client_id = db.add_client({'nome': 'TraderC', 'account_mode': 'real'})
            db.record_trade(client_id=client_id, pair='FIRST/USDT', side='COMPRAR',
                            pnl_pct=1.0, profit=10.0, closed_at='2025-01-01', status='closed')
            db.record_trade(client_id=client_id, pair='SECOND/USDT', side='VENDER',
                            pnl_pct=2.0, profit=20.0, closed_at='2025-01-02', status='closed')

            last = db.get_last_closed_trade(client_id)
            assert last is not None
            assert last['pair'] == 'SECOND/USDT'
        finally:
            db.DB_PATH = original_path


def test_get_last_closed_trade_returns_none_when_no_closed():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            client_id = db.add_client({'nome': 'TraderD', 'account_mode': 'testnet'})
            db.record_trade(client_id=client_id, pair='OPEN/USDT', side='COMPRAR',
                            pnl_pct=0, profit=0, closed_at='', status='open')
            last = db.get_last_closed_trade(client_id)
            assert last is None
        finally:
            db.DB_PATH = original_path


# ---------------------------------------------------------------------------
# get_config / set_config
# ---------------------------------------------------------------------------

def test_get_config_returns_default_when_key_absent():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            value = db.get_config('NONEXISTENT_KEY', 'default-val')
            assert value == 'default-val'
        finally:
            db.DB_PATH = original_path


def test_set_and_get_config_round_trip():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            db.set_config('MY_KEY', 'hello')
            assert db.get_config('MY_KEY') == 'hello'

            db.set_config('MY_KEY', 'world')
            assert db.get_config('MY_KEY') == 'world'
        finally:
            db.DB_PATH = original_path


# ---------------------------------------------------------------------------
# get_test_balance / set_test_balance
# ---------------------------------------------------------------------------

def test_get_test_balance_default_is_1000():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            assert db.get_test_balance() == 1000.0
        finally:
            db.DB_PATH = original_path


def test_set_test_balance_persists():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            db.set_test_balance(2500.0)
            assert db.get_test_balance() == 2500.0
        finally:
            db.DB_PATH = original_path


# ---------------------------------------------------------------------------
# is_test_mode_enabled
# ---------------------------------------------------------------------------

def test_is_test_mode_enabled_default_is_false():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            assert db.is_test_mode_enabled() is False
        finally:
            db.DB_PATH = original_path


def test_enable_test_mode_changes_flag():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            _setup_db(tmpdir)
            db.enable_test_mode()
            assert db.is_test_mode_enabled() is True
        finally:
            db.DB_PATH = original_path


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import traceback

    tests = [
        test_normalize_account_mode_valid,
        test_normalize_account_mode_bool_coercion,
        test_normalize_account_mode_string_bool,
        test_normalize_account_mode_unknown_defaults_to_testnet,
        test_normalize_operation_mode_valid,
        test_normalize_operation_mode_test_alias,
        test_normalize_operation_mode_unknown_defaults_to_paper,
        test_close_trade_updates_row,
        test_delete_client_removes_associated_trades,
        test_delete_nonexistent_client_returns_true,
        test_upsert_client_local_creates_new_when_no_id,
        test_upsert_client_local_updates_existing_when_id_present,
        test_upsert_client_local_inserts_with_explicit_id_when_not_found,
        test_get_open_trades_returns_only_open,
        test_get_open_trades_returns_empty_when_none_open,
        test_get_last_closed_trade_returns_most_recent,
        test_get_last_closed_trade_returns_none_when_no_closed,
        test_get_config_returns_default_when_key_absent,
        test_set_and_get_config_round_trip,
        test_get_test_balance_default_is_1000,
        test_set_test_balance_persists,
        test_is_test_mode_enabled_default_is_false,
        test_enable_test_mode_changes_flag,
    ]

    failed = 0
    for fn in tests:
        try:
            fn()
            print(f'✅ {fn.__name__}')
        except Exception:
            print(f'❌ {fn.__name__}')
            traceback.print_exc()
            failed += 1

    if failed:
        print(f'\n{failed} test(s) FAILED')
        raise SystemExit(1)

    print(f'\n✅ All {len(tests)} database manager tests passed')
    raise SystemExit(0)
