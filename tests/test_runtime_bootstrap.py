import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import main_web


class _FakeThread:
    started_targets = []

    def __init__(self, target=None, args=(), daemon=None, **kwargs):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        _FakeThread.started_targets.append((getattr(self.target, '__name__', str(self.target)), self.args, self.daemon))


class _FakeCloudDb:
    def sync_clients(self, db):
        return None


if __name__ == '__main__':
    original_thread = main_web.threading.Thread
    original_started = main_web.RUNTIME_STARTED
    original_cloud_db = main_web.cloud_db

    try:
        _FakeThread.started_targets = []
        main_web.threading.Thread = _FakeThread
        main_web.RUNTIME_STARTED = False
        main_web.cloud_db = _FakeCloudDb()

        first = main_web.start_runtime_services()
        second = main_web.start_runtime_services()

        if first is not True or second is not False:
            print(f"❌ start_runtime_services deveria ser idempotente: first={first} second={second}")
            raise SystemExit(1)

        started = [item[0] for item in _FakeThread.started_targets]
        expected = ['sniper_worker_loop', '_monitor_sl_tp_automatico', '_simulate_pnl_oscillation', 'sync_clients']
        if started != expected:
            print(f"❌ Threads iniciadas incorretamente: {started}")
            raise SystemExit(2)

        print('✅ Runtime bootstrap inicia uma única vez no WSGI')
        raise SystemExit(0)
    finally:
        main_web.threading.Thread = original_thread
        main_web.RUNTIME_STARTED = original_started
        main_web.cloud_db = original_cloud_db
