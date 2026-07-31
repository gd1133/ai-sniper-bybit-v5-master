# -*- coding: utf-8 -*-
"""Histórico de decisões da IA (gestão viva) — Dashboard ao vivo."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def ensure_historico_decisoes_table() -> None:
    from src.database.manager import _execute_write

    def _op(cur, conn):
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS historico_decisoes_ia (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                motivo_saida TEXT DEFAULT '',
                pnl_garantido_pct REAL DEFAULT 0,
                tipo_execucao TEXT DEFAULT '',
                action_payload TEXT DEFAULT '',
                client_id INTEGER DEFAULT 0,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_decisoes_ts ON historico_decisoes_ia(timestamp)'
        )
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_decisoes_symbol ON historico_decisoes_ia(symbol)'
        )
        return True

    try:
        _execute_write('ensure_historico_decisoes', _op)
    except Exception as err:
        print(f'⚠️ [DECISÕES IA] ensure table: {err}', flush=True)


def record_ia_decision(
    symbol: str,
    *,
    motivo_saida: str = '',
    pnl_garantido_pct: float = 0.0,
    tipo_execucao: str = '',
    action_payload: str = '',
    client_id: int = 0,
) -> bool:
    from src.database.manager import _execute_write

    ensure_historico_decisoes_table()
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    sym = str(symbol or '').upper().replace('/', '').replace(':USDT', '')

    def _op(cur, conn):
        cur.execute(
            '''
            INSERT INTO historico_decisoes_ia
                (symbol, motivo_saida, pnl_garantido_pct, tipo_execucao, action_payload, client_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                sym,
                str(motivo_saida or '')[:800],
                float(pnl_garantido_pct or 0),
                str(tipo_execucao or '')[:80],
                str(action_payload or '')[:120],
                int(client_id or 0),
                ts,
            ),
        )
        return True

    try:
        ok = bool(_execute_write('record_ia_decision', _op))
        if ok:
            print(
                f'🧾 [DECISÕES IA] {sym} | {tipo_execucao} | {action_payload} | '
                f'PnL~{pnl_garantido_pct:.1f}% — {str(motivo_saida)[:100]}',
                flush=True,
            )
        return ok
    except Exception as err:
        print(f'⚠️ [DECISÕES IA] record: {err}', flush=True)
        return False


def list_ia_decisions(limit: int = 30) -> List[Dict[str, Any]]:
    from src.database.manager import _connect

    ensure_historico_decisoes_table()
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT * FROM historico_decisoes_ia
            ORDER BY id DESC
            LIMIT ?
            ''',
            (max(1, int(limit)),),
        )
        return [dict(r) for r in cur.fetchall()]
    except Exception as err:
        print(f'⚠️ [DECISÕES IA] list: {err}', flush=True)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
