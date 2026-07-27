# -*- coding: utf-8 -*-
"""
Sentinela de Posição Ativa — saída antecipada por reversão institucional.

A cada ciclo (fechamento M15 aproximado / poll), para cada posição aberta:
  LONG  → vela vermelha forte (spread > 2× MA, volume > 2.5× MA) dispara debate
          de emergência (Groq + Analista + Neural). ≥2 EXIT/REVERSAL → fecha a mercado.
  SHORT → lógica invertida (vela verde gigante + volume anômalo).
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

SPREAD_MULT = float(os.getenv('SENTINEL_SPREAD_MULT', '2.0'))
VOLUME_MULT = float(os.getenv('SENTINEL_VOLUME_MULT', '2.5'))
POLL_SECS = float(os.getenv('SENTINEL_POLL_SECS', '45'))
TF = str(os.getenv('SENTINEL_TIMEFRAME', '15m'))


def _f(v, default=0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def detect_institutional_reversal_candle(df, side: str) -> dict[str, Any]:
    """Detecta dump (LONG) ou pump (SHORT) institucional na última vela."""
    side_n = str(side or '').lower()
    out = {
        'triggered': False,
        'kind': '',
        'spread_ratio': 0.0,
        'volume_ratio': 0.0,
        'reason': '',
    }
    if df is None or len(df) < 25:
        out['reason'] = 'histórico insuficiente'
        return out

    last = df.iloc[-1]
    o, h, l, c = _f(last['open']), _f(last['high']), _f(last['low']), _f(last['close'])
    spread = max(h - l, 0.0)
    spreads = (df['high'].astype(float) - df['low'].astype(float)).iloc[:-1].tail(20)
    spread_ma = float(spreads.mean()) if len(spreads) else 0.0
    vols = df['vol'].astype(float).iloc[:-1].tail(20)
    vol_ma = float(vols.mean()) if len(vols) else 0.0
    vol_now = _f(last['vol'])
    spread_ratio = (spread / spread_ma) if spread_ma > 0 else 0.0
    vol_ratio = (vol_now / vol_ma) if vol_ma > 0 else 0.0
    out['spread_ratio'] = round(spread_ratio, 2)
    out['volume_ratio'] = round(vol_ratio, 2)

    is_red = c < o
    is_green = c > o
    body_pct = (abs(c - o) / max(spread, 1e-12)) * 100.0

    if side_n in ('buy', 'long', 'comprar'):
        if is_red and spread_ratio >= SPREAD_MULT and vol_ratio >= VOLUME_MULT and body_pct >= 45:
            out['triggered'] = True
            out['kind'] = 'DUMP_INSTITUCIONAL'
            out['reason'] = (
                f'Dump: vela VERMELHA FORTE spread×{spread_ratio:.1f} vol×{vol_ratio:.1f} '
                f'corpo={body_pct:.0f}%'
            )
            return out
    elif side_n in ('sell', 'short', 'vender'):
        if is_green and spread_ratio >= SPREAD_MULT and vol_ratio >= VOLUME_MULT and body_pct >= 45:
            out['triggered'] = True
            out['kind'] = 'PUMP_INSTITUCIONAL'
            out['reason'] = (
                f'Pump: vela VERDE FORTE spread×{spread_ratio:.1f} vol×{vol_ratio:.1f} '
                f'corpo={body_pct:.0f}%'
            )
            return out

    out['reason'] = 'sem reversão institucional'
    return out


def emergency_ai_debate(
    symbol: str,
    side: str,
    candle_info: dict,
    signals: dict | None = None,
) -> dict[str, Any]:
    """
    Debate de emergência local (3 votos): Groq tático, Analista, Neural.
    Cada um retorna HOLD | EXIT | REVERSAL.
    """
    signals = signals or {}
    side_n = str(side or '').lower()
    is_long = side_n in ('buy', 'long', 'comprar')
    spread_r = _f(candle_info.get('spread_ratio'))
    vol_r = _f(candle_info.get('volume_ratio'))
    rsi = _f(signals.get('rsi'), 50)
    trend = str(signals.get('trend') or '').upper()
    st = int(signals.get('supertrend_signal') or 0)

    votes = []

    # Groq Tático — timing / volume
    if vol_r >= VOLUME_MULT and spread_r >= SPREAD_MULT:
        g_action = 'EXIT'
        g_reason = f'Volume anômalo ×{vol_r:.1f} + spread ×{spread_r:.1f} — sair agora'
        g_score = 85
    elif vol_r >= 2.0:
        g_action = 'REVERSAL'
        g_reason = 'Pressão de volume sugerindo inversão'
        g_score = 70
    else:
        g_action = 'HOLD'
        g_reason = 'Volume ainda não justifica saída de emergência'
        g_score = 40
    votes.append({'id': 'groq', 'label': 'Groq Tático', 'action': g_action, 'motivo': g_reason, 'score': g_score})

    # Analista de Dados — estrutura / tendência
    structure_against = (is_long and (trend == 'BAIXA' or st == -1)) or (
        (not is_long) and (trend == 'ALTA' or st == 1)
    )
    if structure_against and spread_r >= SPREAD_MULT:
        a_action = 'REVERSAL'
        a_reason = f'Estrutura virou contra a posição (trend={trend}, ST={st})'
        a_score = 80
    elif candle_info.get('triggered'):
        a_action = 'EXIT'
        a_reason = 'Vela institucional contra a posição — risco de continuação'
        a_score = 75
    else:
        a_action = 'HOLD'
        a_reason = 'Estrutura ainda não confirma saída'
        a_score = 45
    votes.append({'id': 'analyst', 'label': 'Analista de Dados', 'action': a_action, 'motivo': a_reason, 'score': a_score})

    # Aprendizado Neural — RSI / memória de dump
    if is_long and rsi < 45 and candle_info.get('triggered'):
        n_action = 'EXIT'
        n_reason = f'RSI={rsi:.0f} em dump — histórico favorece corte rápido'
        n_score = 78
    elif (not is_long) and rsi > 55 and candle_info.get('triggered'):
        n_action = 'EXIT'
        n_reason = f'RSI={rsi:.0f} em pump contra short — corte rápido'
        n_score = 78
    elif candle_info.get('triggered'):
        n_action = 'REVERSAL'
        n_reason = 'Padrão de reversão semelhante a perdas anteriores'
        n_score = 68
    else:
        n_action = 'HOLD'
        n_reason = 'Sem padrão de perda iminente na memória'
        n_score = 42
    votes.append({'id': 'learner', 'label': 'Aprendizado Neural', 'action': n_action, 'motivo': n_reason, 'score': n_score})

    exit_votes = sum(1 for v in votes if v['action'] in ('EXIT', 'REVERSAL'))
    should_exit = exit_votes >= 2
    return {
        'should_exit': should_exit,
        'exit_votes': exit_votes,
        'votes': votes,
        'summary': (
            f"Debate emergência {symbol}: {exit_votes}/3 pedem EXIT/REVERSAL"
            + (' → FECHAR' if should_exit else ' → MANTER')
        ),
    }


class SentinelaPosicaoAtiva:
    """Loop daemon que vigia posições abertas e fecha em dump/pump institucional."""

    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_candle_key: dict[str, str] = {}
        self._lock = threading.Lock()

    def start(self, cycle_fn: Callable[[], None] | None = None) -> None:
        if self._thread and self._thread.is_alive():
            return

        def _run():
            print("🛡️ [SENTINELA] Iniciada — vigilância de reversão institucional", flush=True)
            while not self._stop.is_set():
                try:
                    if cycle_fn:
                        cycle_fn()
                    else:
                        self.run_once()
                except Exception as err:
                    print(f"⚠️ [SENTINELA] ciclo: {err}", flush=True)
                self._stop.wait(POLL_SECS)
            print("🛡️ [SENTINELA] Encerrada", flush=True)

        self._thread = threading.Thread(target=_run, daemon=True, name='SentinelaPosicaoAtiva')
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def run_once(
        self,
        *,
        get_open_positions: Callable[[], list] | None = None,
        fetch_ohlcv: Callable[[str, str], Any] | None = None,
        close_position: Callable[[str, str], bool] | None = None,
        on_debate: Callable[[str, dict], None] | None = None,
        record_exit: Callable[[str, str, str], None] | None = None,
    ) -> list:
        """
        Avalia posições. Dependências injetadas pelo main_web (broker/DB).
        Retorna lista de ações tomadas.
        """
        actions = []
        if not get_open_positions:
            return actions
        positions = get_open_positions() or []
        for pos in positions:
            symbol = pos.get('symbol') or pos.get('raw_symbol') or pos.get('pair')
            side = pos.get('side') or 'buy'
            if not symbol:
                continue
            try:
                df = fetch_ohlcv(symbol, TF) if fetch_ohlcv else None
                if df is None or len(df) < 25:
                    continue

                # Só reage a novo fechamento de vela (evita spam)
                last_ts = str(df.iloc[-1].get('ts') if hasattr(df.iloc[-1], 'get') else df.iloc[-1]['ts'])
                key = f"{symbol}|{side}"
                with self._lock:
                    if self._last_candle_key.get(key) == last_ts:
                        continue
                    # Marca após processar

                from src.engine.indicators import IndicatorEngine
                try:
                    signals = IndicatorEngine(df).get_signals()
                except Exception:
                    signals = {}

                candle = detect_institutional_reversal_candle(df, side)
                if not candle.get('triggered'):
                    with self._lock:
                        self._last_candle_key[key] = last_ts
                    continue

                print(
                    f"🚨 [SENTINELA] {symbol} {side.upper()}: {candle.get('reason')}",
                    flush=True,
                )
                debate = emergency_ai_debate(symbol, side, candle, signals)
                if on_debate:
                    try:
                        on_debate(symbol, debate)
                    except Exception:
                        pass

                print(f"   🗳️ [SENTINELA] {debate.get('summary')}", flush=True)
                for v in debate.get('votes') or []:
                    print(
                        f"      • {v.get('label')}: {v.get('action')} — {v.get('motivo')}",
                        flush=True,
                    )

                with self._lock:
                    self._last_candle_key[key] = last_ts

                if not debate.get('should_exit'):
                    continue

                closed = False
                if close_position:
                    closed = bool(close_position(symbol, side))
                note = 'Saída de Emergência por Inversão de Tendência'
                if closed:
                    print(f"   ✅ [SENTINELA] {symbol} fechada a mercado — {note}", flush=True)
                    if record_exit:
                        try:
                            record_exit(symbol, side, note)
                        except Exception as rec_err:
                            print(f"   ⚠️ [SENTINELA] registro DB: {rec_err}", flush=True)
                    actions.append({'symbol': symbol, 'side': side, 'closed': True, 'note': note, 'debate': debate})
                else:
                    print(f"   ❌ [SENTINELA] Falha ao fechar {symbol}", flush=True)
                    actions.append({'symbol': symbol, 'side': side, 'closed': False, 'debate': debate})
            except Exception as pos_err:
                print(f"⚠️ [SENTINELA] {symbol}: {pos_err}", flush=True)
        return actions


_SENTINEL: SentinelaPosicaoAtiva | None = None
_SENTINEL_LOCK = threading.Lock()


def get_position_sentinel() -> SentinelaPosicaoAtiva:
    global _SENTINEL
    if _SENTINEL is not None:
        return _SENTINEL
    with _SENTINEL_LOCK:
        if _SENTINEL is None:
            _SENTINEL = SentinelaPosicaoAtiva()
        return _SENTINEL
