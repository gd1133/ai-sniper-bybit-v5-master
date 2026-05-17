import importlib
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import manager as db


class _FakeBroker:
    def __init__(self):
        self.execute_calls = []
        self.tp_sl_calls = []

    def pre_flight_check(self, symbol, side, qty):
        return True, 'OK', 'Pré-voo aprovado'

    def execute_market_order(self, symbol, side, qty, raise_on_error=False):
        self.execute_calls.append({
            'symbol': symbol,
            'side': side,
            'qty': qty,
            'raise_on_error': raise_on_error,
        })
        return {'id': 'order-123', 'orderId': 'order-123'}

    def set_tp_sl_sniper(self, symbol, side, entry_price, qty):
        self.tp_sl_calls.append({
            'symbol': symbol,
            'side': side,
            'entry_price': entry_price,
            'qty': qty,
        })
        return True


if __name__ == '__main__':
    original_db_path = db.DB_PATH
    original_module = sys.modules.pop('main_web', None)
    original_allow_real = os.environ.get('ALLOW_REAL_TRADING')
    original_use_testnet = os.environ.get('USE_TESTNET')

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            db.DB_PATH = os.path.join(tmpdir, 'broadcast_real_order_flow.db')
            os.environ['ALLOW_REAL_TRADING'] = 'true'
            os.environ['USE_TESTNET'] = 'false'

            main_web = importlib.import_module('main_web')
            broker = _FakeBroker()

            original_get_clients = main_web._get_registered_clients
            original_make_broker = main_web._make_broker
            original_requests_post = main_web.requests.post
            original_allow_exec = main_web.ALLOW_ORDER_EXECUTION
            original_allow_real_runtime = main_web.ALLOW_REAL_TRADING
            original_use_testnet_runtime = main_web.USE_TESTNET
            original_app_mode = main_web.APP_MODE

            try:
                main_web._get_registered_clients = lambda active_only=False: [
                    {'nome': 'Cliente Alpha', 'saldo_base': 1000.0, 'exchange': 'bybit'}
                ]
                main_web._make_broker = lambda client: broker
                main_web.requests.post = lambda *args, **kwargs: None
                main_web.ALLOW_ORDER_EXECUTION = True
                main_web.ALLOW_REAL_TRADING = True
                main_web.USE_TESTNET = False
                main_web.APP_MODE = 'real'

                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    main_web._process_client_orders_background(
                        'BTC/USDT:USDT',
                        'BUY',
                        50000.0,
                        91,
                        'Teste de broadcast real',
                    )
                output = stdout.getvalue()
            finally:
                main_web._get_registered_clients = original_get_clients
                main_web._make_broker = original_make_broker
                main_web.requests.post = original_requests_post
                main_web.ALLOW_ORDER_EXECUTION = original_allow_exec
                main_web.ALLOW_REAL_TRADING = original_allow_real_runtime
                main_web.USE_TESTNET = original_use_testnet_runtime
                main_web.APP_MODE = original_app_mode

            if not broker.execute_calls:
                print('❌ O broker fake deveria receber uma ordem real')
                raise SystemExit(1)

            execute_call = broker.execute_calls[-1]
            expected_qty = round((1000.0 * 0.15) / 50000.0, 8)
            if round(execute_call['qty'], 8) != expected_qty:
                print(f"❌ Quantidade inválida para 15% da banca: {execute_call}")
                raise SystemExit(2)

            if execute_call['raise_on_error'] is not True:
                print(f"❌ raise_on_error deveria ser True no modo real: {execute_call}")
                raise SystemExit(3)

            if '🔮 Enviando Ordem Real: Cliente=Cliente Alpha | Margem=150.0 | Par=BTC/USDT:USDT' not in output:
                print(f"❌ Log detalhado do payload não encontrado: {output}")
                raise SystemExit(4)

            print('✅ Broadcast real força 15% da banca e desativa fallback silencioso')
            raise SystemExit(0)
        finally:
            db.DB_PATH = original_db_path
            sys.modules.pop('main_web', None)
            if original_module is not None:
                sys.modules['main_web'] = original_module

            if original_allow_real is None:
                os.environ.pop('ALLOW_REAL_TRADING', None)
            else:
                os.environ['ALLOW_REAL_TRADING'] = original_allow_real

            if original_use_testnet is None:
                os.environ.pop('USE_TESTNET', None)
            else:
                os.environ['USE_TESTNET'] = original_use_testnet
