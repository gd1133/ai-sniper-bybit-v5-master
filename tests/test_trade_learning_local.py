from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import manager as db


def test_trade_learning_stats_multiplier_up_and_down(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        original_path = db.DB_PATH
        try:
            db.DB_PATH = os.path.join(tmpdir, 'learning.db')
            db.init_db()

            setup = 'BTCUSDT|TREND'
            timeframe = '15m'

            # 8/10 wins => 80% => +15%
            for i in range(10):
                db.record_trade_learning(
                    setup_name=setup,
                    timeframe=timeframe,
                    rsi_entry=55 + i,
                    adx_entry=25,
                    volume_ratio=1.4,
                    win=1 if i < 8 else 0,
                    pnl_pct=2.0 if i < 8 else -1.0,
                )

            stats_up = db.get_trade_learning_stats(setup, timeframe, limit=20)
            assert stats_up['sample_size'] == 10
            assert stats_up['win_rate_pct'] == 80.0
            assert abs(float(stats_up['qty_multiplier']) - 1.15) < 1e-9
            assert stats_up['decision'] == 'aggressive_up'

            # Novo setup ruim: 3/10 wins => 30% => reduz para 0.5
            setup_bad = 'ETHUSDT|RANGE_BOUNCE'
            for i in range(10):
                db.record_trade_learning(
                    setup_name=setup_bad,
                    timeframe=timeframe,
                    rsi_entry=48,
                    adx_entry=15,
                    volume_ratio=0.9,
                    win=1 if i < 3 else 0,
                    pnl_pct=1.0 if i < 3 else -1.5,
                )

            stats_down = db.get_trade_learning_stats(setup_bad, timeframe, limit=20)
            assert stats_down['sample_size'] == 10
            assert stats_down['win_rate_pct'] == 30.0
            assert abs(float(stats_down['qty_multiplier']) - 0.5) < 1e-9
            assert stats_down['decision'] == 'defensive_down'

            # Modo discard
            monkeypatch.setenv('TRADE_LEARNING_LOW_WIN_MODE', 'discard')
            stats_discard = db.get_trade_learning_stats(setup_bad, timeframe, limit=20)
            assert stats_discard['decision'] == 'discard_signal'
            assert float(stats_discard['qty_multiplier']) == 0.0
        finally:
            db.DB_PATH = original_path
