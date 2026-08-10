# -*- coding: utf-8 -*-
"""
Persistência dos cards do Tribunal de Debate (Groq / Analista / Neural / Gemini).

Tabela: tribunal_debate em ./data/database.db
Usada por /api/status e /api/tribunal/status.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def ensure_tribunal_debate_table() -> None:
    from src.database.manager import _execute_write

    def _op(cur, conn):
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tribunal_debate'"
        )
        exists = cur.fetchone() is not None
        need_recreate = False
        if exists:
            cur.execute('PRAGMA table_info(tribunal_debate)')
            cols = {str(r[1]) for r in cur.fetchall()}
            required = {
                'ciclo', 'groq_parecer', 'analyst_parecer', 'learner_parecer',
                'agents_json', 'created_at',
            }
            if not required.issubset(cols):
                need_recreate = True
                cur.execute('DROP TABLE IF EXISTS tribunal_debate')

        if (not exists) or need_recreate:
            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS tribunal_debate (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT DEFAULT '',
                    ciclo TEXT DEFAULT 'scan',
                    confidence REAL DEFAULT 0,
                    assertiveness REAL DEFAULT 0,
                    veredito TEXT DEFAULT '',
                    groq_parecer TEXT DEFAULT '',
                    groq_score REAL DEFAULT 0,
                    analyst_parecer TEXT DEFAULT '',
                    analyst_score REAL DEFAULT 0,
                    learner_parecer TEXT DEFAULT '',
                    learner_score REAL DEFAULT 0,
                    gemini_parecer TEXT DEFAULT '',
                    gemini_score REAL DEFAULT 0,
                    agents_json TEXT DEFAULT '[]',
                    dialogue_json TEXT DEFAULT '[]',
                    evidence_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_tribunal_debate_created '
            'ON tribunal_debate(created_at DESC)'
        )
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_tribunal_debate_symbol '
            'ON tribunal_debate(symbol)'
        )
        return True

    try:
        _execute_write('ensure_tribunal_debate_table', _op)
    except Exception as err:
        print(f"⚠️ [TRIBUNAL DB] ensure table: {err}", flush=True)


def _agent_by_id(agents: list, agent_id: str) -> dict:
    for a in agents or []:
        if isinstance(a, dict) and str(a.get('id') or '') == agent_id:
            return a
    return {}


def save_tribunal_debate(
    evidence: dict | None,
    *,
    ciclo: str = 'scan',
) -> int | None:
    """
    Persiste um ciclo de debate. Retorna id inserido ou None.
    """
    if not isinstance(evidence, dict) or not evidence:
        return None

    ensure_tribunal_debate_table()
    from src.database.manager import _execute_write

    agents = list(evidence.get('agents') or [])
    groq = _agent_by_id(agents, 'groq')
    analyst = _agent_by_id(agents, 'analyst')
    learner = _agent_by_id(agents, 'learner')
    gemini = _agent_by_id(agents, 'gemini')
    dialogue = evidence.get('dialogue') or []
    veredito = ''
    for item in reversed(dialogue):
        if isinstance(item, dict) and item.get('speaker') == 'consensus':
            veredito = str(item.get('text') or '')
            break
    if not veredito:
        veredito = str(evidence.get('strategic_reason') or evidence.get('summary') or '')[:800]

    symbol = str(evidence.get('symbol') or '---')
    side = str(evidence.get('side') or '')
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    payload = (
        symbol,
        side,
        str(ciclo or 'scan')[:40],
        float(evidence.get('confidence') or 0),
        float(evidence.get('assertiveness') or 0),
        veredito[:1200],
        str(groq.get('motivo') or '')[:1200],
        float(groq.get('score') or 0),
        str(analyst.get('motivo') or '')[:1200],
        float(analyst.get('score') or 0),
        str(learner.get('motivo') or learner.get('learning_notes') or '')[:1200],
        float(learner.get('score') or 0),
        str(gemini.get('motivo') or '')[:1200],
        float(gemini.get('score') or 0),
        json.dumps(agents, ensure_ascii=False, default=str)[:12000],
        json.dumps(dialogue, ensure_ascii=False, default=str)[:12000],
        json.dumps(
            {
                'symbol': symbol,
                'side': side,
                'confidence': evidence.get('confidence'),
                'assertiveness': evidence.get('assertiveness'),
                'candle_study': evidence.get('candle_study'),
                'learning_from_history': evidence.get('learning_from_history'),
            },
            ensure_ascii=False,
            default=str,
        )[:20000],
        ts,
    )

    def _op(cur, conn):
        cur.execute(
            '''
            INSERT INTO tribunal_debate (
                symbol, side, ciclo, confidence, assertiveness, veredito,
                groq_parecer, groq_score,
                analyst_parecer, analyst_score,
                learner_parecer, learner_score,
                gemini_parecer, gemini_score,
                agents_json, dialogue_json, evidence_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            payload,
        )
        return int(cur.lastrowid or 0)

    try:
        row_id = _execute_write('save_tribunal_debate', _op)
        # Mantém só os últimos 200 debates (disco do Render)
        def _prune(cur, conn):
            cur.execute(
                '''
                DELETE FROM tribunal_debate WHERE id NOT IN (
                    SELECT id FROM tribunal_debate ORDER BY id DESC LIMIT 200
                )
                '''
            )
            return True

        try:
            _execute_write('prune_tribunal_debate', _prune)
        except Exception:
            pass
        print(
            f"⚖️ [TRIBUNAL DB] salvo id={row_id} {symbol} {side} ciclo={ciclo}",
            flush=True,
        )
        return int(row_id or 0) or None
    except Exception as err:
        print(f"⚠️ [TRIBUNAL DB] save falhou: {err}", flush=True)
        return None


def list_tribunal_debates(limit: int = 20) -> list[dict[str, Any]]:
    """Lista debates recentes (mais novos primeiro)."""
    ensure_tribunal_debate_table()
    from src.database.manager import _connect

    lim = max(1, min(int(limit or 20), 100))
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT id, symbol, side, ciclo, confidence, assertiveness, veredito,
                   groq_parecer, groq_score, analyst_parecer, analyst_score,
                   learner_parecer, learner_score, gemini_parecer, gemini_score,
                   agents_json, dialogue_json, evidence_json, created_at
            FROM tribunal_debate
            ORDER BY id DESC
            LIMIT ?
            ''',
            (lim,),
        )
        rows = cur.fetchall()
        out = []
        for r in rows:
            item = dict(r) if hasattr(r, 'keys') else {}
            if not item and r is not None:
                continue
            for key in ('agents_json', 'dialogue_json', 'evidence_json'):
                raw = item.get(key)
                if isinstance(raw, str) and raw:
                    try:
                        item[key.replace('_json', '')] = json.loads(raw)
                    except Exception:
                        item[key.replace('_json', '')] = []
                elif key == 'evidence_json':
                    item['evidence'] = {}
            # Cards prontos para o frontend
            item['agents'] = item.get('agents') or [
                {
                    'id': 'groq',
                    'label': 'Groq Tático',
                    'motivo': item.get('groq_parecer'),
                    'score': item.get('groq_score'),
                },
                {
                    'id': 'analyst',
                    'label': 'Analista de Dados',
                    'motivo': item.get('analyst_parecer'),
                    'score': item.get('analyst_score'),
                },
                {
                    'id': 'learner',
                    'label': 'Aprendizado Neural',
                    'motivo': item.get('learner_parecer'),
                    'score': item.get('learner_score'),
                },
                {
                    'id': 'gemini',
                    'label': 'Gemini Estratégico',
                    'motivo': item.get('gemini_parecer'),
                    'score': item.get('gemini_score'),
                },
            ]
            item['dialogue'] = item.get('dialogue') or []
            out.append(item)
        return out
    except Exception as err:
        print(f"⚠️ [TRIBUNAL DB] list: {err}", flush=True)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def latest_tribunal_debate() -> dict[str, Any] | None:
    rows = list_tribunal_debates(1)
    return rows[0] if rows else None
