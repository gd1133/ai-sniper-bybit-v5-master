# -*- coding: utf-8 -*-
"""
Gestão Autônoma de Posição Viva — Motor Sniper.

1) Early Exit Guard: saída antecipada em CHoCH / engolfo / volume 2× / perda EMA8
2) Let Profits Run: após +100% ROI, se tendência FORTE → trailing 15% abaixo do peak
   (sem teto estático de TP); se exaustão → fecha a mercado.

Payloads de comando:
  ACTION: EMERGENCY_EXIT
  ACTION: EXTEND_TRAILING
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from src.engine.candle_patterns import (
    detect_bearish_engulfing,
    detect_bullish_engulfing,
    detect_strong_down_candle,
    detect_strong_up_candle,
    is_bearish_candle,
    is_bullish_candle,
)

ROI_EXPAND_PCT = float(os.getenv('LIVE_PROFIT_EXPAND_ROI', '100'))
TRAILING_PEAK_CALLBACK_PCT = float(os.getenv('TRAILING_PEAK_CALLBACK_PCT', '15'))  # % do preço
ADX_STRONG = float(os.getenv('LIVE_TREND_ADX_MIN', '30'))
RSI_BULL = float(os.getenv('LIVE_TREND_RSI_BULL', '60'))
RSI_BEAR = float(os.getenv('LIVE_TREND_RSI_BEAR', '40'))
VOL_RATIO_STRONG = float(os.getenv('LIVE_TREND_VOL_RATIO', '1.5'))
EMA_FAST = int(os.getenv('LIVE_EXIT_EMA_PERIOD', '8'))
POLL_SECS = float(os.getenv('LIVE_POSITION_POLL_SECS', '20'))
ENABLED = str(os.getenv('ENABLE_LIVE_POSITION_MANAGER', 'true')).strip().lower() in {
    '1', 'true', 'yes', 'on',
}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _side_long(side: str) -> bool:
    return str(side or '').strip().lower() in ('buy', 'long', 'comprar')


def _ema(series, period: int) -> float:
    try:
        return float(series.astype(float).ewm(span=period, adjust=False).mean().iloc[-1])
    except Exception:
        return 0.0


def detect_structure_break(df, side: str, signals: dict | None = None) -> dict[str, Any]:
    """
    Detecta reversão estrutural (CHoCH simplificado / engolfo / volume / EMA8).
    """
    signals = signals or {}
    out = {
        'broken': False,
        'reasons': [],
        'score': 0,
    }
    if df is None or len(df) < 12:
        return out

    last = df.iloc[-1]
    prev = df.iloc[-2]
    atr = _f(signals.get('atr'))
    vol_ratio = _f(signals.get('volume_ratio'), 1.0)
    if vol_ratio <= 0 and 'vol' in df.columns:
        vol_ma = float(df['vol'].astype(float).iloc[:-1].tail(20).mean() or 0)
        vol_ratio = (_f(last['vol']) / vol_ma) if vol_ma > 0 else 1.0

    ema8 = _ema(df['close'], EMA_FAST)
    close = _f(last['close'])
    score = 0
    reasons = []

    is_long = _side_long(side)

    if is_long:
        if detect_bearish_engulfing(df) or (
            is_bearish_candle(last) and _f(last['close']) < _f(prev['open'])
            and _f(last['open']) > _f(prev['close'])
        ):
            score += 35
            reasons.append('Engolfo de BAIXA')
        if detect_strong_down_candle(last, atr, vol_ratio):
            score += 25
            reasons.append('Vela VERMELHA FORTE')
        if vol_ratio >= 2.0 and is_bearish_candle(last):
            score += 25
            reasons.append(f'Volume de venda ×{vol_ratio:.1f} (≥2×)')
        if ema8 > 0 and close < ema8 and is_bearish_candle(last):
            score += 20
            reasons.append(f'Perda da EMA{EMA_FAST} ({close:.6f} < {ema8:.6f})')
        # CHoCH simplificado: rompe mínima das 3 velas anteriores
        prior_low = float(df['low'].iloc[-4:-1].min())
        if close < prior_low:
            score += 20
            reasons.append('CHoCH: rompeu suporte das 3 velas anteriores')
    else:
        if detect_bullish_engulfing(df) or (
            is_bullish_candle(last) and _f(last['close']) > _f(prev['open'])
            and _f(last['open']) < _f(prev['close'])
        ):
            score += 35
            reasons.append('Engolfo de ALTA')
        if detect_strong_up_candle(last, atr, vol_ratio):
            score += 25
            reasons.append('Vela VERDE FORTE')
        if vol_ratio >= 2.0 and is_bullish_candle(last):
            score += 25
            reasons.append(f'Volume de compra ×{vol_ratio:.1f} (≥2×)')
        if ema8 > 0 and close > ema8 and is_bullish_candle(last):
            score += 20
            reasons.append(f'Retomada da EMA{EMA_FAST}')
        prior_high = float(df['high'].iloc[-4:-1].max())
        if close > prior_high:
            score += 20
            reasons.append('CHoCH: rompeu resistência das 3 velas anteriores')

    out['score'] = score
    out['reasons'] = reasons
    out['broken'] = score >= 45  # pelo menos 2 sinais fortes
    return out


def assess_trend_momentum(signals: dict | None, side: str) -> dict[str, Any]:
    """Tendência FORTE para deixar lucro correr além de 100% ROI."""
    signals = signals or {}
    adx = _f(signals.get('adx'))
    rsi = _f(signals.get('rsi'), 50)
    vol_ratio = _f(signals.get('volume_ratio'), 1.0)
    trend = str(signals.get('trend') or '').upper()
    st = int(signals.get('supertrend_signal') or 0)
    is_long = _side_long(side)

    strong = False
    reasons = []
    if is_long:
        strong = (
            adx >= ADX_STRONG
            and rsi >= RSI_BULL
            and vol_ratio >= VOL_RATIO_STRONG
            and (trend == 'ALTA' or st == 1)
        )
        if adx >= ADX_STRONG:
            reasons.append(f'ADX={adx:.0f}≥{ADX_STRONG:.0f}')
        if rsi >= RSI_BULL:
            reasons.append(f'RSI={rsi:.0f}≥{RSI_BULL:.0f}')
        if vol_ratio >= VOL_RATIO_STRONG:
            reasons.append(f'vol×{vol_ratio:.1f}')
        if not strong:
            reasons.append('EXAUSTÃO DE COMPRA / momentum fraco')
    else:
        strong = (
            adx >= ADX_STRONG
            and rsi <= RSI_BEAR
            and vol_ratio >= VOL_RATIO_STRONG
            and (trend == 'BAIXA' or st == -1)
        )
        if adx >= ADX_STRONG:
            reasons.append(f'ADX={adx:.0f}')
        if rsi <= RSI_BEAR:
            reasons.append(f'RSI={rsi:.0f}≤{RSI_BEAR:.0f}')
        if vol_ratio >= VOL_RATIO_STRONG:
            reasons.append(f'vol×{vol_ratio:.1f}')
        if not strong:
            reasons.append('EXAUSTÃO DE VENDA / momentum fraco')

    return {
        'strong': strong,
        'exhausted': not strong,
        'reasons': reasons,
        'adx': adx,
        'rsi': rsi,
        'vol_ratio': vol_ratio,
    }


def compute_trailing_sl_from_peak(peak: float, side: str, callback_pct: float | None = None) -> float:
    """SL = peak ± callback% (LONG: abaixo; SHORT: acima)."""
    cb = abs(float(callback_pct if callback_pct is not None else TRAILING_PEAK_CALLBACK_PCT)) / 100.0
    peak = float(peak or 0)
    if peak <= 0:
        return 0.0
    if _side_long(side):
        return peak * (1.0 - cb)
    return peak * (1.0 + cb)


def decide_live_action(
    *,
    side: str,
    roi_pct: float,
    mark_price: float,
    entry_price: float,
    df_fast=None,
    df_slow=None,
    signals: dict | None = None,
    peak_price: float | None = None,
    trailing_armed: bool = False,
) -> dict[str, Any]:
    """
    Orquestra decisão viva.

    Returns action in:
      HOLD | EMERGENCY_EXIT | EXTEND_TRAILING | CLOSE_EXHAUSTION | TRAILING_HIT
    """
    signals = signals or {}
    result = {
        'action': 'HOLD',
        'payload': 'ACTION: HOLD',
        'motivo': '',
        'tipo_execucao': '',
        'new_peak': float(peak_price or mark_price or 0),
        'trailing_sl': 0.0,
        'structure': {},
        'momentum': {},
    }

    # Prefer 5m for structure, fallback 1m
    df_struct = df_slow if df_slow is not None and len(df_slow) >= 12 else df_fast
    structure = detect_structure_break(df_struct, side, signals)
    result['structure'] = structure

    # ── 1) Early exit por reversão ──────────────────────────────────────
    if structure.get('broken'):
        result['action'] = 'EMERGENCY_EXIT'
        result['payload'] = 'ACTION: EMERGENCY_EXIT'
        result['tipo_execucao'] = 'REVERSAL_EXIT'
        result['motivo'] = (
            'Saída antecipada por reversão: ' + ' | '.join(structure.get('reasons') or [])
        )
        return result

    # Trailing já armado: atualiza peak e verifica se preço bateu no trailing
    peak = float(peak_price or 0) or float(mark_price or 0)
    is_long = _side_long(side)
    if is_long:
        peak = max(peak, float(mark_price or 0))
    else:
        peak = min(peak, float(mark_price or 0)) if peak > 0 else float(mark_price or 0)
    result['new_peak'] = peak
    trailing_sl = compute_trailing_sl_from_peak(peak, side)
    result['trailing_sl'] = trailing_sl

    if trailing_armed and trailing_sl > 0:
        hit = (is_long and mark_price <= trailing_sl) or ((not is_long) and mark_price >= trailing_sl)
        if hit:
            result['action'] = 'EMERGENCY_EXIT'
            result['payload'] = 'ACTION: EMERGENCY_EXIT'
            result['tipo_execucao'] = 'TRAILING_PROFIT_EXPANSION'
            result['motivo'] = (
                f'Trailing stop atingido (peak={peak:.6f} SL={trailing_sl:.6f} '
                f'callback={TRAILING_PEAK_CALLBACK_PCT:.0f}%)'
            )
            return result
        # Continua estendendo
        result['action'] = 'EXTEND_TRAILING'
        result['payload'] = 'ACTION: EXTEND_TRAILING'
        result['tipo_execucao'] = 'TRAILING_PROFIT_EXPANSION'
        result['motivo'] = f'Tendência viva — sobe trailing (peak={peak:.6f})'
        return result

    # ── 2) Let profits run a partir de +100% ROI ────────────────────────
    if float(roi_pct or 0) >= ROI_EXPAND_PCT:
        momentum = assess_trend_momentum(signals, side)
        result['momentum'] = momentum
        if momentum.get('strong'):
            result['action'] = 'EXTEND_TRAILING'
            result['payload'] = 'ACTION: EXTEND_TRAILING'
            result['tipo_execucao'] = 'TRAILING_PROFIT_EXPANSION'
            result['motivo'] = (
                f'ROI {roi_pct:.0f}%≥{ROI_EXPAND_PCT:.0f}% + tendência FORTE — '
                f'remove TP e ativa trailing ({", ".join(momentum.get("reasons") or [])})'
            )
            return result
        result['action'] = 'CLOSE_EXHAUSTION'
        result['payload'] = 'ACTION: EMERGENCY_EXIT'
        result['tipo_execucao'] = 'TRAILING_PROFIT_EXPANSION'
        result['motivo'] = (
            f'ROI {roi_pct:.0f}% com exaustão — fecha a mercado e garante lucro no topo '
            f'({"; ".join(momentum.get("reasons") or [])})'
        )
        return result

    result['motivo'] = 'Posição viva — sem gatilho'
    return result


# ── Persistência de estado trailing (memória + SQLite best-effort) ─────
class TrailingStateRegistry:
    def __init__(self) -> None:
        self._states: dict[tuple[int, str], dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(client_id: int, symbol: str) -> tuple[int, str]:
        sym = str(symbol or '').upper().replace('/', '').replace(':', '')
        return (int(client_id or 0), sym)

    def get(self, client_id: int, symbol: str) -> dict:
        with self._lock:
            return dict(self._states.get(self._key(client_id, symbol)) or {})

    def set_trailing(self, client_id: int, symbol: str, peak: float, sl: float) -> None:
        with self._lock:
            self._states[self._key(client_id, symbol)] = {
                'armed': True,
                'peak': float(peak),
                'sl': float(sl),
                'updated_at': time.time(),
            }

    def clear(self, client_id: int, symbol: str) -> None:
        with self._lock:
            self._states.pop(self._key(client_id, symbol), None)


_TRAILING_REG = TrailingStateRegistry()


def get_trailing_registry() -> TrailingStateRegistry:
    return _TRAILING_REG


class LivePositionManager:
    """Loop: monitorar_posicoes_vivas()."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, cycle_fn: Callable[[], None]) -> None:
        if not ENABLED:
            print('⏸️ [GESTÃO VIVA] Desativada (ENABLE_LIVE_POSITION_MANAGER=false)', flush=True)
            return
        if self._thread and self._thread.is_alive():
            return

        def _run():
            print('🫀 [GESTÃO VIVA] Sentinela 24/7 — early exit + let profits run', flush=True)
            while not self._stop.is_set():
                try:
                    cycle_fn()
                except Exception as err:
                    print(f'⚠️ [GESTÃO VIVA] ciclo: {err}', flush=True)
                self._stop.wait(POLL_SECS)

        self._thread = threading.Thread(target=_run, daemon=True, name='LivePositionManager')
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


_LIVE_MGR: LivePositionManager | None = None
_LIVE_LOCK = threading.Lock()


def get_live_position_manager() -> LivePositionManager:
    global _LIVE_MGR
    if _LIVE_MGR is not None:
        return _LIVE_MGR
    with _LIVE_LOCK:
        if _LIVE_MGR is None:
            _LIVE_MGR = LivePositionManager()
        return _LIVE_MGR
