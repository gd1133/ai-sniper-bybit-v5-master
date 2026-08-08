# -*- coding: utf-8 -*-
"""
Gestão dinâmica de posições — Trend Following (Motor Sniper).

1) Breakeven relâmpago: ROI>=12% ou preço>=+0.8% → SL em entrada + taxas
2) Trailing dinâmico: ROI>=25% → SL acompanha EMA8/ATR (0.5–1.0% do peak)
3) Early exit: fecha a mercado se fechar além da EMA20 com volume contrário
4) Time-stop: >35 min sem novo extremo e PnL ~0/negativo → STAGNATION_TIMEOUT
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
BE_ROI_PCT = float(os.getenv('BREAKEVEN_ROI_PCT', '12'))
BE_PRICE_PCT = float(os.getenv('BREAKEVEN_PRICE_PCT', '0.8'))
BE_FEE_BUFFER_PCT = float(os.getenv('BREAKEVEN_FEE_BUFFER_PCT', '0.12'))  # entrada + taxas
TRAIL_ROI_PCT = float(os.getenv('TREND_TRAIL_ROI_PCT', '25'))
TRAIL_MIN_PCT = float(os.getenv('TREND_TRAIL_DIST_MIN_PCT', '0.5'))
TRAIL_MAX_PCT = float(os.getenv('TREND_TRAIL_DIST_MAX_PCT', '1.0'))
EMA_FAST = int(os.getenv('TREND_TRAIL_EMA', '8'))
EMA_SLOW = int(os.getenv('TREND_EXIT_EMA', '20'))
VOL_EXIT_RATIO = float(os.getenv('TREND_EXIT_VOL_RATIO', '1.5'))
MAX_HOLD_SECS = float(os.getenv('MAX_HOLD_SECS', str(35 * 60)))
STAGNATION_ROI_ABS = float(os.getenv('STAGNATION_ROI_ABS', '5'))  # |ROI| <= 5% ~ zerado
EXTREME_IDLE_SECS = float(os.getenv('STAGNATION_NO_EXTREME_SECS', str(35 * 60)))


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


def compute_trail_distance_pct(df_fast=None, df_slow=None) -> float:
    """Distância trailing entre 0.5% e 1.0%, calibrada pelo ATR."""
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
    SL trailing: mais apertado entre (peak ± dist%) e EMA8.
    LONG: SL abaixo; SHORT: SL acima.
    """
    peak = _f(peak) or _f(mark)
    if peak <= 0:
        return 0.0
    dist = compute_trail_distance_pct(df_fast, df_slow) / 100.0
    ema8 = _ema_last(df_fast if df_fast is not None and len(df_fast) >= EMA_FAST + 2 else df_slow, EMA_FAST)

    if _is_long(side):
        sl_peak = peak * (1.0 - dist)
        if ema8 > 0:
            # Trailing sob a EMA8 (sombra da tendência), sem ficar acima do peak-callback
            return max(sl_peak, min(ema8 * 0.998, peak * (1.0 - TRAIL_MIN_PCT / 100.0)))
        return sl_peak

    sl_peak = peak * (1.0 + dist)
    if ema8 > 0:
        return min(sl_peak, max(ema8 * 1.002, peak * (1.0 + TRAIL_MIN_PCT / 100.0)))
    return sl_peak


def detect_early_reversal(df, side: str) -> dict[str, Any]:
    """Fecha se candle fecha além da EMA20 com volume contrário em expansão."""
    out = {'triggered': False, 'reasons': []}
    if df is None or len(df) < EMA_SLOW + 3 or 'close' not in df.columns:
        return out
    last = df.iloc[-1]
    close = _f(last['close'])
    open_ = _f(last['open'])
    ema20 = _ema_last(df, EMA_SLOW)
    vol_r = _vol_ratio(df)
    if ema20 <= 0 or close <= 0:
        return out

    reasons = []
    if _is_long(side):
        if close < ema20 and open_ >= ema20 * 0.999:
            reasons.append(f'fechou abaixo EMA{EMA_SLOW}')
        elif close < ema20:
            reasons.append(f'preço < EMA{EMA_SLOW}')
        if vol_r >= VOL_EXIT_RATIO and close < open_:
            reasons.append(f'volume vendedor ×{vol_r:.1f}')
        # Exige preço abaixo da EMA20 + (volume ou candle bearish)
        if close < ema20 and (vol_r >= VOL_EXIT_RATIO or close < open_):
            out['triggered'] = True
            out['reasons'] = reasons or [f'reversão vs EMA{EMA_SLOW}']
    else:
        if close > ema20:
            reasons.append(f'fechou acima EMA{EMA_SLOW}')
        if vol_r >= VOL_EXIT_RATIO and close > open_:
            reasons.append(f'volume comprador ×{vol_r:.1f}')
        if close > ema20 and (vol_r >= VOL_EXIT_RATIO or close > open_):
            out['triggered'] = True
            out['reasons'] = reasons or [f'reversão vs EMA{EMA_SLOW}']
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
        'roi_pct': roi,
        'price_move_pct': move,
    }

    # ── 3) Early exit (prioridade sobre trailing se estrutura quebrou) ──
    df_struct = df_slow if df_slow is not None and len(df_slow) >= EMA_SLOW + 3 else df_fast
    early = detect_early_reversal(df_struct, side)
    # Em lucro mínimo ou prejuízo: early exit corta o mal pela raiz
    if early.get('triggered') and roi < TRAIL_ROI_PCT:
        # Se already strongly profitable with trailing, prefer let trailing work
        # unless deep structure break (always honor early if ROI < trail threshold
        # OR if not trailing yet)
        if not trailing_armed or roi < 40:
            result['action'] = 'EARLY_EXIT'
            result['tipo_execucao'] = 'REVERSAL_EXIT'
            result['motivo'] = 'Saída antecipada: ' + ' | '.join(early.get('reasons') or [])
            return result

    # Early exit even com trailing se reversão forte + ROI recuando
    if early.get('triggered') and trailing_armed and roi < (TRAIL_ROI_PCT * 0.7):
        result['action'] = 'EARLY_EXIT'
        result['tipo_execucao'] = 'REVERSAL_EXIT'
        result['motivo'] = 'Reversão com trailing fraco: ' + ' | '.join(early.get('reasons') or [])
        return result

    # ── 3b) Analista Pessoal — give-back / momentum fade (nunca afrouxa SL) ──
    try:
        from src.ai_brain.personal_analyst import refine_exit
        # peak_roi aproximado pelo extremo de preço vs entrada
        peak_roi_est = roi
        if entry > 0 and new_peak > 0:
            if is_long:
                peak_move = ((new_peak - entry) / entry) * 100.0
            else:
                peak_move = ((entry - new_peak) / entry) * 100.0
            # ROI margem ~ move% * leverage; usamos ratio relativo se leverage desconhecido
            # Conservador: escala peak pelo mesmo fator roi/move quando move>0
            move_now = abs(move) if abs(move) > 1e-9 else 0.0
            if move_now > 0 and roi != 0:
                peak_roi_est = max(roi, abs(roi) * (abs(peak_move) / move_now))
            else:
                peak_roi_est = max(roi, abs(peak_move) * 10.0)  # ~10x implícito se sem leverage

        analyst_exit = refine_exit(
            side=side,
            roi_pct=roi,
            peak_roi_pct=peak_roi_est,
            trailing_armed=trailing_armed,
            breakeven_armed=breakeven_armed,
            df=df_struct,
        )
        if analyst_exit.get('suggest_early_exit'):
            result['action'] = 'EARLY_EXIT'
            result['tipo_execucao'] = 'ANALYST_EXIT'
            result['motivo'] = str(analyst_exit.get('motivo') or 'Analista Pessoal: saída assertiva')
            return result
    except Exception:
        pass

    # ── 4) Time-stop / estagnação ──────────────────────────────────────
    stagnant_pnl = roi <= 0 or abs(roi) <= STAGNATION_ROI_ABS
    if age >= MAX_HOLD_SECS and idle >= EXTREME_IDLE_SECS and stagnant_pnl and not trailing_armed:
        result['action'] = 'STAGNATION_TIMEOUT'
        result['tipo_execucao'] = 'STAGNATION_TIMEOUT'
        result['motivo'] = (
            f'STAGNATION_TIMEOUT: {age/60:.0f}min aberta, '
            f'{idle/60:.0f}min sem novo extremo, ROI={roi:.1f}%'
        )
        return result

    # ── 2) Trailing dinâmico (ROI >= 25%) ───────────────────────────────
    if roi >= TRAIL_ROI_PCT or trailing_armed:
        sl = compute_trailing_sl(
            side=side, peak=new_peak, mark=mark, df_fast=df_fast, df_slow=df_slow,
        )
        # Nunca piorar o SL abaixo do breakeven positivo
        be_sl = compute_breakeven_sl(entry, side)
        if is_long and be_sl > 0:
            sl = max(sl, be_sl)
        elif (not is_long) and be_sl > 0:
            sl = min(sl, be_sl) if sl > 0 else be_sl

        # Se preço já cruzou o trailing SL → fecha
        hit = (is_long and mark <= sl) or ((not is_long) and mark >= sl)
        if hit and trailing_armed:
            result['action'] = 'EARLY_EXIT'
            result['tipo_execucao'] = 'TRAILING_HIT'
            result['sl_price'] = sl
            result['trailing_armed'] = True
            result['breakeven_armed'] = True
            result['motivo'] = f'Trailing hit SL={sl:.6g} peak={new_peak:.6g}'
            return result

        result['action'] = 'EXTEND_TRAILING'
        result['tipo_execucao'] = 'TRAILING_PROFIT'
        result['sl_price'] = sl
        result['trailing_armed'] = True
        result['breakeven_armed'] = True
        result['motivo'] = (
            f'Trailing vivo ROI={roi:.0f}% peak={new_peak:.6g} SL={sl:.6g} '
            f'(dist~{compute_trail_distance_pct(df_fast, df_slow):.2f}%)'
        )
        return result

    # ── 1) Breakeven relâmpago ─────────────────────────────────────────
    if (not breakeven_armed) and (roi >= BE_ROI_PCT or move >= BE_PRICE_PCT):
        sl = compute_breakeven_sl(entry, side)
        result['action'] = 'ARM_BREAKEVEN'
        result['tipo_execucao'] = 'BREAKEVEN'
        result['sl_price'] = sl
        result['breakeven_armed'] = True
        result['motivo'] = (
            f'Breakeven ROI={roi:.1f}% / preço={move:.2f}% → SL={sl:.6g} '
            f'(entrada+taxas {BE_FEE_BUFFER_PCT}%)'
        )
        return result

    result['motivo'] = 'Posição viva — aguardando gatilho'
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
                f'🫀 [TREND MGR] Ativo — BE@{BE_ROI_PCT:.0f}%ROI / Trailing@{TRAIL_ROI_PCT:.0f}% / '
                f'Early EMA{EMA_SLOW} / MaxHold {MAX_HOLD_SECS/60:.0f}min · poll {POLL_SECS:.0f}s',
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
