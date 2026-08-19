# -*- coding: utf-8 -*-
"""
Gestão dinâmica de posições — Trend Following (Motor Sniper).

Regra de ouro (saída):
  • Segue a tendência. Recuo pequeno NÃO fecha.
  • Sai a mercado SÓ com vela FORTE + volume CONTRÁRIO (5m fechada).
  • Em +100% ROI: não realiza — trava piso e deixa correr (trailing).
  • Acima de 100%: proteção sobe com o pico (nunca abaixo do piso).

SL duro de perda (−50% ROI) continua na Bybit.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

ENABLED = str(os.getenv('ENABLE_TREND_POSITION_MANAGER', 'true')).strip().lower() in {
    '1', 'true', 'yes', 'on',
}
POLL_SECS = float(os.getenv('TREND_POS_POLL_SECS', '8'))
# BE só entra junto do trail (+100%) — recuo pequeno não vai a entrada
BE_ROI_PCT = float(os.getenv('BREAKEVEN_ROI_PCT', '100'))
BE_PRICE_PCT = float(os.getenv('BREAKEVEN_PRICE_PCT', '5.0'))
BE_FEE_BUFFER_PCT = float(os.getenv('BREAKEVEN_FEE_BUFFER_PCT', '0.12'))
TRAIL_ROI_PCT = float(os.getenv('TREND_TRAIL_ROI_PCT', '100'))
TRAIL_MIN_PCT = float(os.getenv('TREND_TRAIL_DIST_MIN_PCT', '2.0'))
TRAIL_MAX_PCT = float(os.getenv('TREND_TRAIL_DIST_MAX_PCT', '3.0'))
LOCK_ROI_PCT = float(os.getenv('TREND_LOCK_ROI_PCT', '80'))
EMA_FAST = int(os.getenv('TREND_TRAIL_EMA', '8'))
EMA_SLOW = int(os.getenv('TREND_EXIT_EMA', '20'))
VOL_EXIT_RATIO = float(os.getenv('TREND_EXIT_VOL_RATIO', '2.2'))
STRONG_EXIT_BODY_PCT = float(os.getenv('TREND_EXIT_BODY_PCT', '55'))
ENABLE_FIB_PARTIAL_TP = str(os.getenv('ENABLE_FIB_PARTIAL_TP', 'true')).strip().lower() in {
    '1', 'true', 'yes', 'on',
}
FIB_PARTIAL_FRACTION = float(os.getenv('FIB_PARTIAL_FRACTION', '0.5'))
MAX_HOLD_SECS = float(os.getenv('MAX_HOLD_SECS', str(4 * 3600)))
STAGNATION_ROI_ABS = float(os.getenv('STAGNATION_ROI_ABS', '0'))
EXTREME_IDLE_SECS = float(os.getenv('STAGNATION_NO_EXTREME_SECS', str(4 * 3600)))


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _is_long(side: str) -> bool:
    return str(side or '').strip().lower() in ('buy', 'long', 'comprar')


def _ema_series(closes, period: int):
    try:
        import pandas as pd
        s = closes if hasattr(closes, 'astype') else pd.Series(closes)
        return s.astype(float).ewm(span=int(period), adjust=False).mean()
    except Exception:
        return None


def _ema_last(df, period: int) -> float:
    if df is None or len(df) < max(period + 2, 5) or 'close' not in df.columns:
        return 0.0
    series = _ema_series(df['close'], period)
    if series is None or len(series) == 0:
        return 0.0
    return _f(series.iloc[-1])


def _atr_pct(df, period: int = 14) -> float:
    """ATR normalizado em % do close (para calibrar distância do trailing)."""
    if df is None or len(df) < period + 2:
        return 0.0
    try:
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        close = df['close'].astype(float)
        prev = close.shift(1)
        tr = (high - low).to_frame('hl')
        tr['hc'] = (high - prev).abs()
        tr['lc'] = (low - prev).abs()
        true_range = tr.max(axis=1)
        atr = float(true_range.tail(period).mean() or 0)
        last = float(close.iloc[-1] or 0)
        if last <= 0:
            return 0.0
        return (atr / last) * 100.0
    except Exception:
        return 0.0


def _vol_ratio(df) -> float:
    if df is None or 'vol' not in getattr(df, 'columns', []):
        return 1.0
    try:
        last = _f(df['vol'].iloc[-1])
        ma = _f(df['vol'].astype(float).iloc[:-1].tail(20).mean())
        if ma <= 0:
            return 1.0
        return last / ma
    except Exception:
        return 1.0


def price_move_pct(entry: float, mark: float, side: str) -> float:
    entry = _f(entry)
    mark = _f(mark)
    if entry <= 0 or mark <= 0:
        return 0.0
    if _is_long(side):
        return ((mark - entry) / entry) * 100.0
    return ((entry - mark) / entry) * 100.0


def compute_breakeven_sl(entry: float, side: str, fee_buffer_pct: float | None = None) -> float:
    """SL = entrada ± buffer de taxas (break-even positivo)."""
    entry = _f(entry)
    if entry <= 0:
        return 0.0
    buf = abs(_f(fee_buffer_pct, BE_FEE_BUFFER_PCT)) / 100.0
    if _is_long(side):
        return entry * (1.0 + buf)
    return entry * (1.0 - buf)


def _closed_ohlcv(df):
    """Descarta a vela em formação (última barra) — só barra fechada."""
    if df is None or len(df) < 3:
        return None
    try:
        return df.iloc[:-1]
    except Exception:
        return df


def compute_lock_sl_price(entry: float, side: str, lock_roi_pct: float | None = None, leverage: float = 20.0) -> float:
    """Piso de proteção: SL que trava lock_roi_pct de ROI (@leverage)."""
    try:
        from src.risk.profit_shield import compute_protected_sl_price
        return float(compute_protected_sl_price(
            entry, side, leverage=leverage,
            lock_roi_pct=lock_roi_pct if lock_roi_pct is not None else LOCK_ROI_PCT,
        ) or 0.0)
    except Exception:
        entry_v = _f(entry)
        lev = max(_f(leverage, 20.0), 1.0)
        lock = abs(_f(lock_roi_pct, LOCK_ROI_PCT))
        if entry_v <= 0:
            return 0.0
        move = (lock / 100.0) / lev
        if _is_long(side):
            return entry_v * (1.0 + move)
        return entry_v * (1.0 - move)


def compute_trail_distance_pct(df_fast=None, df_slow=None) -> float:
    """Distância trailing entre min/max %, calibrada pelo ATR."""
    atr = _atr_pct(df_fast if df_fast is not None else df_slow)
    if atr <= 0:
        return (TRAIL_MIN_PCT + TRAIL_MAX_PCT) / 2.0
    # ATR típico scalping ~0.3–1.5% → mapeia para [min, max]
    dist = max(TRAIL_MIN_PCT, min(TRAIL_MAX_PCT, atr * 0.85))
    return dist


def compute_trailing_sl(
    *,
    side: str,
    peak: float,
    mark: float,
    df_fast=None,
    df_slow=None,
) -> float:
    """
    SL trailing por distância do pico (2–3% de preço), sem abraçar EMA8.
    O piso de +80% ROI é aplicado em decide_trend_action.
    """
    peak = _f(peak) or _f(mark)
    if peak <= 0:
        return 0.0
    dist = compute_trail_distance_pct(df_fast, df_slow) / 100.0
    if _is_long(side):
        return peak * (1.0 - dist)
    return peak * (1.0 + dist)


def detect_early_reversal(df, side: str) -> dict[str, Any]:
    """
    Sai SOMENTE com vela 5m FECHADA forte + volume contrário.

    Não fecha em recuo pequeno, EMA20 sozinha ou vela fraca.
    """
    out = {'triggered': False, 'reasons': []}
    work = _closed_ohlcv(df)
    if work is None or len(work) < 8 or 'close' not in getattr(work, 'columns', []):
        return out
    last = work.iloc[-1]
    close = _f(last['close'])
    open_ = _f(last['open'])
    high = _f(last['high'])
    low = _f(last['low'])
    rng = max(high - low, 1e-9)
    body = abs(close - open_) / rng * 100.0
    close_pos = (close - low) / rng
    vol_r = _vol_ratio(work)
    if close <= 0:
        return out

    if _is_long(side):
        strong = close < open_ and body >= STRONG_EXIT_BODY_PCT and close_pos <= 0.35
        if strong and vol_r >= VOL_EXIT_RATIO:
            out['triggered'] = True
            out['reasons'] = [
                f'vela forte de BAIXA (corpo {body:.0f}%, close no fundo) vol×{vol_r:.1f}'
            ]
    else:
        strong = close > open_ and body >= STRONG_EXIT_BODY_PCT and close_pos >= 0.65
        if strong and vol_r >= VOL_EXIT_RATIO:
            out['triggered'] = True
            out['reasons'] = [
                f'vela forte de ALTA (corpo {body:.0f}%, close no topo) vol×{vol_r:.1f}'
            ]
    return out


def detect_engulfing_reversal(df_fast, df_slow, side: str) -> dict[str, Any]:
    """
    Sentinela: engolfo 5m FECHADO contra a posição + vela forte + volume.
    Ignora 1m (ruído). tipo: SAIDA_REVERSAO_TENDENCIA
    """
    out = {'triggered': False, 'reasons': [], 'tipo': 'SAIDA_REVERSAO_TENDENCIA'}
    try:
        from src.engine.candle_patterns import (
            detect_bearish_engulfing,
            detect_bullish_engulfing,
        )
    except Exception:
        return out

    work = _closed_ohlcv(df_slow if df_slow is not None else df_fast)
    if work is None or len(work) < 4:
        return out

    long = _is_long(side)
    vol_r = _vol_ratio(work)
    last = work.iloc[-1]
    close = _f(last['close'])
    open_ = _f(last['open'])
    high = _f(last['high'])
    low = _f(last['low'])
    rng = max(high - low, 1e-9)
    body = abs(close - open_) / rng * 100.0
    strong_body = body >= STRONG_EXIT_BODY_PCT
    if vol_r < VOL_EXIT_RATIO or not strong_body:
        return out

    try:
        if long and detect_bearish_engulfing(work):
            out['triggered'] = True
            out['reasons'] = [f'engolfo de baixa 5m corpo={body:.0f}% vol×{vol_r:.1f}']
        if (not long) and detect_bullish_engulfing(work):
            out['triggered'] = True
            out['reasons'] = [f'engolfo de alta 5m corpo={body:.0f}% vol×{vol_r:.1f}']
    except Exception:
        return out
    return out


def decide_trend_action(
    *,
    side: str,
    roi_pct: float,
    entry_price: float,
    mark_price: float,
    opened_at: float | None = None,
    peak_price: float | None = None,
    last_extreme_at: float | None = None,
    breakeven_armed: bool = False,
    trailing_armed: bool = False,
    partial_tp_done: bool = False,
    df_fast=None,
    df_slow=None,
    now: float | None = None,
) -> dict[str, Any]:
    """
    Orquestra decisão viva.

    action:
      HOLD | ARM_BREAKEVEN | EXTEND_TRAILING | EARLY_EXIT | STAGNATION_TIMEOUT
    """
    now = float(now if now is not None else time.time())
    roi = _f(roi_pct)
    entry = _f(entry_price)
    mark = _f(mark_price)
    move = price_move_pct(entry, mark, side)
    is_long = _is_long(side)

    peak = _f(peak_price) or mark or entry
    if is_long:
        new_peak = max(peak, mark)
    else:
        new_peak = min(peak, mark) if peak > 0 else mark

    extreme_updated = abs(new_peak - peak) > (entry * 1e-8) if entry > 0 else (new_peak != peak)
    extreme_ts = now if (extreme_updated or not last_extreme_at) else float(last_extreme_at or now)
    open_ts = float(opened_at or now)
    age = now - open_ts
    idle = now - float(last_extreme_at or open_ts)

    result = {
        'action': 'HOLD',
        'motivo': '',
        'tipo_execucao': '',
        'new_peak': new_peak,
        'last_extreme_at': extreme_ts,
        'sl_price': 0.0,
        'breakeven_armed': bool(breakeven_armed),
        'trailing_armed': bool(trailing_armed),
        'partial_tp_done': bool(partial_tp_done),
        'roi_pct': roi,
        'price_move_pct': move,
    }

    # ── 1) Única saída discricionária: vela forte + volume contra (5m) ─
    engolfo = detect_engulfing_reversal(df_fast, df_slow, side)
    if engolfo.get('triggered'):
        result['action'] = 'EARLY_EXIT'
        result['tipo_execucao'] = 'SAIDA_REVERSAO_TENDENCIA'
        result['motivo'] = (
            'SAIDA_REVERSAO_TENDENCIA: ' + ' | '.join(engolfo.get('reasons') or [])
        )
        return result

    # ── 1b) TP parcial Fib 100% (realiza metade, resto corre até 161.8 / reversão)
    df_struct = df_slow if df_slow is not None and len(df_slow) >= 10 else df_fast
    if ENABLE_FIB_PARTIAL_TP and not partial_tp_done and 20 <= roi < TRAIL_ROI_PCT and df_struct is not None:
        try:
            from src.engine.fibonacci_exponencial import exponential_fib_levels, fib_targets_for_side
            targets = fib_targets_for_side(exponential_fib_levels(df_struct), side)
            tp1 = _f(targets.get('tp1'))
            min_ext = entry * 0.025  # ignora “100%” que ainda é ruído de consolidação
            hit = (
                is_long and tp1 >= entry + min_ext and mark >= tp1
            ) or (
                (not is_long) and 0 < tp1 <= entry - min_ext and mark <= tp1
            )
            if hit:
                result['action'] = 'PARTIAL_TP'
                result['tipo_execucao'] = 'FIB_TP1_100'
                result['partial_tp_done'] = True
                result['tp1_price'] = tp1
                result['motivo'] = (
                    f'TP parcial Fib 100% @ {tp1:.6g} — realiza {FIB_PARTIAL_FRACTION*100:.0f}%, '
                    f'resto corre até Fib 161.8% / reversão 5m'
                )
                return result
        except Exception:
            pass

    df_struct = df_slow if df_slow is not None and len(df_slow) >= 10 else df_fast
    early = detect_early_reversal(df_struct, side)
    if early.get('triggered'):
        result['action'] = 'EARLY_EXIT'
        result['tipo_execucao'] = 'SAIDA_REVERSAO_TENDENCIA'
        result['motivo'] = (
            'SAIDA_REVERSAO_TENDENCIA: ' + ' | '.join(early.get('reasons') or [])
        )
        return result

    # Analista Pessoal NÃO fecha recuo — só confirma a mesma vela forte.
    # (refine_exit agora exige vela forte+volume; se não houver, ignora)

    # ── 2) Time-stop: só trade morto (ROI<=0) por horas, sem trail ─────
    stagnant_pnl = roi <= 0
    if age >= MAX_HOLD_SECS and idle >= EXTREME_IDLE_SECS and stagnant_pnl and not trailing_armed:
        result['action'] = 'STAGNATION_TIMEOUT'
        result['tipo_execucao'] = 'STAGNATION_TIMEOUT'
        result['motivo'] = (
            f'STAGNATION_TIMEOUT: {age/60:.0f}min aberta, '
            f'{idle/60:.0f}min sem novo extremo, ROI={roi:.1f}%'
        )
        return result

    # ── 3) Trailing Turtle (LL20 long / HH10 short) + piso +80% — deixa o lucro fluir
    if roi >= TRAIL_ROI_PCT or trailing_armed:
        lock_sl = compute_lock_sl_price(entry, side, LOCK_ROI_PCT)
        turtle_sl = 0.0
        turtle_rule = ''
        try:
            from src.engine.turtle_donchian import turtle_exit_stop
            td = turtle_exit_stop(df_struct if df_struct is not None else df_slow, side)
            turtle_sl = _f(td.get('sl_price'))
            turtle_rule = td.get('rule') or 'Turtle'
        except Exception:
            turtle_sl = 0.0

        if is_long:
            parts = [x for x in (lock_sl, turtle_sl) if x > 0]
            sl = max(parts) if parts else compute_trailing_sl(
                side=side, peak=new_peak, mark=mark, df_fast=df_fast, df_slow=df_slow,
            )
        else:
            parts = [x for x in (lock_sl, turtle_sl) if x > 0]
            sl = min(parts) if parts else compute_trailing_sl(
                side=side, peak=new_peak, mark=mark, df_fast=df_fast, df_slow=df_slow,
            )

        hit = (is_long and mark <= sl) or ((not is_long) and mark >= sl)
        if hit and trailing_armed:
            result['action'] = 'EARLY_EXIT'
            result['tipo_execucao'] = 'TRAILING_HIT'
            result['sl_price'] = sl
            result['trailing_armed'] = True
            result['breakeven_armed'] = True
            result['motivo'] = f'Trailing hit SL={sl:.6g} peak={new_peak:.6g} (piso +{LOCK_ROI_PCT:.0f}% ROI)'
            return result

        result['action'] = 'EXTEND_TRAILING'
        result['tipo_execucao'] = 'TRAILING_PROFIT'
        result['sl_price'] = sl
        result['trailing_armed'] = True
        result['breakeven_armed'] = True
        result['motivo'] = (
            f'Trailing Turtle {turtle_rule or "Donchian"} ROI={roi:.0f}% '
            f'peak={new_peak:.6g} SL={sl:.6g} (piso +{LOCK_ROI_PCT:.0f}% ROI — sem scalp 2-3%)'
        )
        return result

    result['motivo'] = 'Posição viva — segue tendência (recuo pequeno = HOLD)'
    return result


class TrendStateRegistry:
    def __init__(self) -> None:
        self._states: dict[tuple[int, str], dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(client_id: int, symbol: str) -> tuple[int, str]:
        sym = str(symbol or '').upper().replace('/', '').replace(':', '')
        return (int(client_id or 0), sym)

    def get(self, client_id: int, symbol: str) -> dict:
        with self._lock:
            st = self._states.get(self._key(client_id, symbol))
            return dict(st) if st else {}

    def touch_open(self, client_id: int, symbol: str, mark: float, now: float | None = None) -> dict:
        now = float(now if now is not None else time.time())
        with self._lock:
            k = self._key(client_id, symbol)
            st = self._states.get(k)
            if not st:
                st = {
                    'opened_at': now,
                    'peak': float(mark or 0),
                    'last_extreme_at': now,
                    'breakeven_armed': False,
                    'trailing_armed': False,
                    'partial_tp_done': False,
                    'sl': 0.0,
                }
                self._states[k] = st
            return dict(st)

    def update(self, client_id: int, symbol: str, **kwargs) -> None:
        with self._lock:
            k = self._key(client_id, symbol)
            st = self._states.get(k) or {
                'opened_at': time.time(),
                'peak': 0.0,
                'last_extreme_at': time.time(),
                'breakeven_armed': False,
                'trailing_armed': False,
                'partial_tp_done': False,
                'sl': 0.0,
            }
            st.update(kwargs)
            self._states[k] = st

    def clear(self, client_id: int, symbol: str) -> None:
        with self._lock:
            self._states.pop(self._key(client_id, symbol), None)


_REG = TrendStateRegistry()


def get_trend_registry() -> TrendStateRegistry:
    return _REG


class TrendPositionManager:
    """Loop assíncrono (thread) de acompanhamento de tendência."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, cycle_fn: Callable[[], None]) -> None:
        if not ENABLED:
            print('⏸️ [TREND MGR] Desativado (ENABLE_TREND_POSITION_MANAGER=false)', flush=True)
            return
        if self._thread and self._thread.is_alive():
            return

        def _run():
            print(
                f'🫀 [TREND MGR] Ativo — segue tendência | trail @{TRAIL_ROI_PCT:.0f}% ROI '
                f'(piso +{LOCK_ROI_PCT:.0f}%) | saída só vela forte+vol×{VOL_EXIT_RATIO:.1f} '
                f'| MaxHold {MAX_HOLD_SECS/60:.0f}min · poll {POLL_SECS:.0f}s',
                flush=True,
            )
            while not self._stop.is_set():
                try:
                    cycle_fn()
                except Exception as err:
                    print(f'⚠️ [TREND MGR] ciclo: {err}', flush=True)
                self._stop.wait(POLL_SECS)

        self._thread = threading.Thread(target=_run, daemon=True, name='TrendPositionManager')
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


_MGR: TrendPositionManager | None = None
_MGR_LOCK = threading.Lock()


def get_trend_position_manager() -> TrendPositionManager:
    global _MGR
    if _MGR is not None:
        return _MGR
    with _MGR_LOCK:
        if _MGR is None:
            _MGR = TrendPositionManager()
        return _MGR
