# -*- coding: utf-8 -*-
"""Feedback Loop: sessão Bybit soft-fail + log de tabelas 1× no startup."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import src.learning.feedback_loop as fb_mod
from src.learning.feedback_loop import FeedbackLoopEvolutivo


class TestGetClosedPnlSoftFail:
    def test_bybit_client_returns_empty_when_session_unavailable(self):
        from src.broker.bybit_client import BybitClient

        client = object.__new__(BybitClient)
        client._api_key = ''
        client._api_secret = ''
        client.pybit_session = None
        client.exchange = None
        client.testnet = False
        client.is_demo = False
        client.active_endpoint = 'https://api.bybit.com'
        client._session_lock = __import__('threading').Lock()
        client.authenticated = False

        with patch.object(client, 'ensure_private_session', return_value=False):
            assert client.get_closed_pnl() == []

    def test_fetch_closed_pnl_never_raises_without_keys(self, tmp_path):
        fb_mod._TABLES_STARTUP_LOGGED = True
        loop = FeedbackLoopEvolutivo(db_path=str(tmp_path / 't.db'))
        loop._tables_ready = True

        with patch.object(loop, '_resolve_credentials', return_value=('', '')):
            with patch.object(loop, '_warn_session_unavailable') as warn:
                rows = loop._fetch_closed_pnl('', '', broker=None)
        assert rows == []
        warn.assert_called_once()

    def test_fetch_closed_pnl_uses_broker_then_soft_fails(self, tmp_path):
        fb_mod._TABLES_STARTUP_LOGGED = True
        loop = FeedbackLoopEvolutivo(db_path=str(tmp_path / 't.db'))
        loop._tables_ready = True

        broker = MagicMock()
        broker.ensure_private_session.return_value = False
        broker.get_closed_pnl.return_value = []
        broker.authenticated = False
        broker.pybit_session = None
        broker.session = None
        broker.exchange = None
        broker._api_key = ''
        broker._api_secret = ''

        with patch.dict(os.environ, {'BYBIT_API_KEY': '', 'BYBIT_API_SECRET': ''}, clear=False):
            with patch.object(loop, '_resolve_credentials', return_value=('', '')):
                with patch.object(loop, '_warn_session_unavailable'):
                    rows = loop._fetch_closed_pnl('', '', broker=broker)
        assert rows == []

    def test_fetch_closed_pnl_ccxt_fallback(self, tmp_path):
        fb_mod._TABLES_STARTUP_LOGGED = True
        loop = FeedbackLoopEvolutivo(db_path=str(tmp_path / 't.db'))
        loop._tables_ready = True

        expected = [{'symbol': 'BTCUSDT', 'closedPnl': '1.5', 'orderId': '1'}]
        with patch.object(loop, '_resolve_credentials', return_value=('k', 's')):
            with patch.object(loop, '_get_standalone_http', side_effect=RuntimeError('pybit down')):
                with patch.object(loop, '_fetch_closed_pnl_via_ccxt', return_value=expected):
                    rows = loop._fetch_closed_pnl('k', 's', broker=None)
        assert rows == expected

    def test_sincronizar_does_not_surface_session_raise(self, tmp_path):
        fb_mod._TABLES_STARTUP_LOGGED = True
        loop = FeedbackLoopEvolutivo(db_path=str(tmp_path / 't.db'))
        loop._tables_ready = True
        loop._last_sync_ts = 0.0

        broker = MagicMock()
        broker.ensure_private_session.return_value = False
        # Simula comportamento antigo que levantava RuntimeError
        broker.get_closed_pnl.side_effect = RuntimeError(
            'sessão Bybit indisponível para get_closed_pnl'
        )
        broker.authenticated = False
        broker.pybit_session = None
        broker.session = None
        broker.exchange = None

        with patch.object(loop, 'ensure_live_broker', return_value=broker):
            with patch.object(loop, '_resolve_credentials', return_value=('', '')):
                result = loop.sincronizar_trades_fechados(broker=broker, force=True)
        assert result.get('processed', 0) == 0
        assert 'falha get_closed_pnl' not in ' '.join(result.get('errors') or [])

    def test_sincronizar_session_error_is_soft_skip(self, tmp_path, capsys):
        fb_mod._TABLES_STARTUP_LOGGED = True
        loop = FeedbackLoopEvolutivo(db_path=str(tmp_path / 't.db'))
        loop._tables_ready = True
        loop._last_sync_ts = 0.0
        loop._last_session_warn_ts = 0.0

        with patch.object(loop, 'ensure_live_broker', return_value=None):
            with patch.object(
                loop,
                '_fetch_closed_pnl',
                side_effect=RuntimeError('sessão Bybit indisponível para get_closed_pnl'),
            ):
                result = loop.sincronizar_trades_fechados(force=True)
        assert result.get('skipped_session') is True
        out = capsys.readouterr().out
        assert 'falha get_closed_pnl' not in out
        assert 'closed_pnl adiado' in out or result.get('skipped_session')


class TestTablesStartupLogOnce:
    def test_tables_log_only_once_across_instances(self, tmp_path, capsys):
        fb_mod._TABLES_STARTUP_LOGGED = False

        def _fake_write(name, fn):
            class Cur:
                def execute(self, *a, **k):
                    return None

                def fetchall(self):
                    return []

            class Conn:
                pass

            return fn(Cur(), Conn())

        with patch('src.database.manager._execute_write', side_effect=_fake_write):
            FeedbackLoopEvolutivo(db_path=str(tmp_path / 'a.db'))
            FeedbackLoopEvolutivo(db_path=str(tmp_path / 'b.db'))

        out = capsys.readouterr().out
        assert out.count('Tabelas operacoes / pesos_ia_evolutivo prontas') == 1
