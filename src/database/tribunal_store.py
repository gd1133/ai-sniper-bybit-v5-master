# -*- coding: utf-8 -*-
"""
Persistência do Tribunal de IAs — alimenta os cards do Dashboard em tempo real.

Tabela ``tribunal_debate``: último veredito por símbolo (Groq / Analista / Neural).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _norm_symbol(symbol: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', str(symbol or '').upper().replace(':USDT', ''))


def ensure_tribunal_debate_table() -> None:
    from src.database.manager import _execute_write

    def _op(cur, conn):
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS tribunal_debate (
                symbol TEXT PRIMARY KEY,
                groq_score INTEGER DEFAULT 0,
                groq_action TEXT DEFAULT 'WAIT',
                groq_reason TEXT DEFAULT '',
                dados_score INTEGER DEFAULT 0,
                dados_action TEXT DEFAULT 'WAIT',
                dados_reason TEXT DEFAULT '',
                neural_score INTEGER DEFAULT 0,
                neural_action TEXT DEFAULT 'WAIT',
                neural_reason TEXT DEFAULT '',
                gemini_score INTEGER DEFAULT 0,
                gemini_action TEXT DEFAULT 'WAIT',
                gemini_reason TEXT DEFAULT '',
                side TEXT DEFAULT '',
                confidence REAL DEFAULT 0,
                raw_json TEXT DEFAULT '',
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_tribunal_ts ON tribunal_debate(timestamp)')
        return True

    try:
        _execute_write('ensure_tribunal_debate', _op)
    except Exception as err:
        print(f"⚠️ [TRIBUNAL DB] ensure table: {err}", flush=True)


def _agent_fields(agents: list, agent_id: str) -> tuple:
    for a in agents or []:
        if str(a.get('id') or '').lower() == agent_id:
            score = int(round(float(a.get('score') or a.get('assertiveness') or 0)))
            action = str(a.get('action') or 'WAIT').upper()
            reason = str(a.get('motivo') or a.get('reason') or '')[:500]
            return score, action, reason
    return 0, 'WAIT', ''


def save_tribunal_debate(
    symbol: str,
    *,
    agents: list | None = None,
    side: str = '',
    confidence: float = 0.0,
    evidence: dict | None = None,
    extra: dict | None = None,
) -> bool:
    """Upsert do debate mais recente do símbolo (cards do painel)."""
    from src.database.manager import _execute_write

    ensure_tribunal_debate_table()
    sym = _norm_symbol(symbol)
    if not sym:
        return False

    agents = list(agents or [])
    if evidence and not agents:
        agents = list(evidence.get('agents') or [])

    g_score, g_action, g_reason = _agent_fields(agents, 'groq')
    d_score, d_action, d_reason = _agent_fields(agents, 'analyst')
    n_score, n_action, n_reason = _agent_fields(agents, 'learner')
    gem_score, gem_action, gem_reason = _agent_fields(agents, 'gemini')

    # Fallbacks a partir do evidence bruto
    if evidence:
        if not g_reason:
            g_reason = str(evidence.get('tactical_reason') or '')[:500]
        if not d_reason:
            d_reason = str(evidence.get('local_reason') or '')[:500]
        if not n_reason:
            n_reason = str(evidence.get('learning_reason') or '')[:500]
        if not gem_reason:
            gem_reason = str(evidence.get('strategic_reason') or '')[:500]
        if not confidence:
            confidence = float(evidence.get('confidence') or evidence.get('assertiveness') or 0)
        if not side:
            side = str(evidence.get('side') or '')

    payload = {
        'symbol': sym,
        'agents': agents,
        'side': side,
        'confidence': confidence,
        'extra': extra or {},
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    try:
        raw_json = json.dumps(payload, ensure_ascii=False, default=str)[:8000]
    except Exception:
        raw_json = ''

    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    def _op(cur, conn):
        cur.execute(
            '''
            INSERT INTO tribunal_debate (
                symbol,
                groq_score, groq_action, groq_reason,
                dados_score, dados_action, dados_reason,
                neural_score, neural_action, neural_reason,
                gemini_score, gemini_action, gemini_reason,
                side, confidence, raw_json, timestamp
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
                groq_score=excluded.groq_score,
                groq_action=excluded.groq_action,
                groq_reason=excluded.groq_reason,
                dados_score=excluded.dados_score,
                dados_action=excluded.dados_action,
                dados_reason=excluded.dados_reason,
                neural_score=excluded.neural_score,
                neural_action=excluded.neural_action,
                neural_reason=excluded.neural_reason,
                gemini_score=excluded.gemini_score,
                gemini_action=excluded.gemini_action,
                gemini_reason=excluded.gemini_reason,
                side=excluded.side,
                confidence=excluded.confidence,
                raw_json=excluded.raw_json,
                timestamp=excluded.timestamp
            ''',
            (
                sym,
                g_score, g_action, g_reason,
                d_score, d_action, d_reason,
                n_score, n_action, n_reason,
                gem_score, gem_action, gem_reason,
                str(side or '').upper(),
                float(confidence or 0),
                raw_json,
                ts,
            ),
        )
        return True

    try:
        ok = bool(_execute_write('save_tribunal_debate', _op))
        if ok:
            print(
                f"🗳️ [TRIBUNAL DB] {sym} salvo — "
                f"Groq={g_score}/{g_action} Analista={d_score}/{d_action} Neural={n_score}/{n_action}",
                flush=True,
            )
        return ok
    except Exception as err:
        print(f"⚠️ [TRIBUNAL DB] save {sym}: {err}", flush=True)
        return False


def get_latest_tribunal(symbol: str | None = None) -> Optional[Dict[str, Any]]:
    from src.database.manager import _connect

    ensure_tribunal_debate_table()
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        if symbol:
            cur.execute(
                'SELECT * FROM tribunal_debate WHERE symbol = ? LIMIT 1',
                (_norm_symbol(symbol),),
            )
        else:
            cur.execute(
                'SELECT * FROM tribunal_debate ORDER BY timestamp DESC LIMIT 1'
            )
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception as err:
        print(f"⚠️ [TRIBUNAL DB] get_latest: {err}", flush=True)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def list_tribunal_debates(limit: int = 20) -> List[Dict[str, Any]]:
    from src.database.manager import _connect

    ensure_tribunal_debate_table()
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            'SELECT * FROM tribunal_debate ORDER BY timestamp DESC LIMIT ?',
            (max(1, int(limit)),),
        )
        return [dict(r) for r in cur.fetchall()]
    except Exception as err:
        print(f"⚠️ [TRIBUNAL DB] list: {err}", flush=True)
        return []
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def debate_row_to_agents(row: dict | None) -> list:
    """Converte linha SQLite nos 4 cards do frontend."""
    if not row:
        return []
    return [
        {
            'id': 'gemini',
            'label': 'Gemini Estratégico',
            'score': int(row.get('gemini_score') or 0),
            'action': str(row.get('gemini_action') or 'WAIT'),
            'motivo': str(row.get('gemini_reason') or 'Aguardando ciclo do radar...'),
            'weight': 25,
            'assertiveness': int(row.get('gemini_score') or 0),
            'provider': 'db',
            'role': 'Visão macro',
        },
        {
            'id': 'groq',
            'label': 'Groq Tático',
            'score': int(row.get('groq_score') or 0),
            'action': str(row.get('groq_action') or 'WAIT'),
            'motivo': str(row.get('groq_reason') or 'Aguardando ciclo do radar...'),
            'weight': 25,
            'assertiveness': int(row.get('groq_score') or 0),
            'provider': 'db',
            'role': 'Timing e execução',
            'samples': 0,
        },
        {
            'id': 'analyst',
            'label': 'Analista de Dados',
            'score': int(row.get('dados_score') or 0),
            'action': str(row.get('dados_action') or 'WAIT'),
            'motivo': str(row.get('dados_reason') or 'Aguardando ciclo do radar...'),
            'weight': 30,
            'assertiveness': int(row.get('dados_score') or 0),
            'provider': 'db',
            'role': 'SMC / estrutura',
        },
        {
            'id': 'learner',
            'label': 'Aprendizado Neural',
            'score': int(row.get('neural_score') or 0),
            'action': str(row.get('neural_action') or 'WAIT'),
            'motivo': str(row.get('neural_reason') or 'Aguardando ciclo do radar...'),
            'weight': 20,
            'assertiveness': int(row.get('neural_score') or 0),
            'provider': 'db',
            'role': 'Memória de entradas',
            'learning_notes': str(row.get('neural_reason') or '')[:180],
        },
    ]


def build_tribunal_status_payload() -> Dict[str, Any]:
    """Payload para GET /api/tribunal/status."""
    latest = get_latest_tribunal()
    recent = list_tribunal_debates(12)
    agents = debate_row_to_agents(latest)
    return {
        'status': 'ok',
        'symbol': (latest or {}).get('symbol') or '---',
        'side': (latest or {}).get('side') or '',
        'confidence': float((latest or {}).get('confidence') or 0),
        'timestamp': (latest or {}).get('timestamp'),
        'agents': agents,
        'cards': {
            'groq': {
                'score': (latest or {}).get('groq_score', 0),
                'action': (latest or {}).get('groq_action', 'WAIT'),
                'reason': (latest or {}).get('groq_reason', ''),
            },
            'analista': {
                'score': (latest or {}).get('dados_score', 0),
                'action': (latest or {}).get('dados_action', 'WAIT'),
                'reason': (latest or {}).get('dados_reason', ''),
            },
            'neural': {
                'score': (latest or {}).get('neural_score', 0),
                'action': (latest or {}).get('neural_action', 'WAIT'),
                'reason': (latest or {}).get('neural_reason', ''),
            },
        },
        'recent': [
            {
                'symbol': r.get('symbol'),
                'side': r.get('side'),
                'timestamp': r.get('timestamp'),
                'groq_score': r.get('groq_score'),
                'dados_score': r.get('dados_score'),
                'neural_score': r.get('neural_score'),
            }
            for r in recent
        ],
        'has_data': bool(latest),
    }
