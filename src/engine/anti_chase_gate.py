# -*- coding: utf-8 -*-
"""
Anti-Chase Gate — bloqueia entradas no topo/fundo esticados.

Filtros obrigatórios ANTES da ordem a mercado:
  1) RSI sobrecompra/sobrevenda (1m + 5m)
  2) Extensão vs EMA20 / VWAP (>1.2%)
  3) Gatilho de pivô: preço na zona da EMA8/EMA20 (pullback), não no ápice

Códigos de rejeição:
  REJECTED: OVERBOUGHT_RSI
  REJECTED: OVERSOLD_RSI
  REJECTED: PRICE_TOO_EXTENDED
  REJECTED: WAIT_PULLBACK_EMA
"""

from __future__ import annotations

import os
from typing import Any

ENABLED = str(os.getenv('ENABLE_ANTI_CHASE_GATE', 'true')).strip().lower() in {
    '1', 'true', 'yes', 'on',
}

RSI_PERIOD = int(os.getenv('ANTI_CHASE_RSI_PERIOD', '14'))
RSI_5M_LONG_MAX = float(os.getenv('ANTI_CHASE_RSI_5M_LONG_MAX', '68'))
RSI_1M_LONG_MAX = float(os.getenv('ANTI_CHASE_RSI_1M_LONG_MAX', '75'))
RSI_5M_SHORT_MIN = float(os.getenv('ANTI_CHASE_RSI_5M_SHORT_MIN', '32'))
RSI_1M_SHORT_MIN = float(os.getenv('ANTI_CHASE_RSI_1M_SHORT_MIN', '25'))
MAX_EXTENSION_PCT = float(os.getenv('ANTI_CHASE_MAX_EXTENSION_PCT', '3.5'))
ATR_EXTENSION_MULT = float(os.getenv('ANTI_CHASE_ATR_MULT', '2.0'))
C3_SOFT_CONFIDENCE_PCT = float(os.getenv('C3_SOFT_FILTER_MIN_CONF', '36'))
PULLBACK_TOL_PCT = float(os.getenv('ANTI_CHASE_PULLBACK_TOL_PCT', '0.90'))
EMA_FAST = int(os.getenv('ANTI_CHASE_EMA_FAST', '8'))
EMA_SLOW = int(os.getenv('ANTI_CHASE_EMA_SLOW', '20'))


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _is_long(side: str) -> bool:
    return str(side or '').strip().lower() in ('buy', 'long', 'comprar')


def _ema_last(closes, period: int) -> float:
    try:
        import pandas as pd
        s = closes if hasattr(closes, 'astype') else pd.Series(list(closes))
        return float(s.astype(float).ewm(span=int(period), adjust=False).mean().iloc[-1])
    except Exception:
        return 0.0


def compute_rsi(closes, period: int = 14) -> float:
    """RSI clássico (média de ganhos/perdas)."""
    try:
        import pandas as pd
        s = closes if hasattr(closes, 'astype') else pd.Series(list(closes))
        s = s.astype(float)
        if len(s) < period + 2:
            return 50.0
        delta = s.diff()
        gain = delta.clip(lower=0.0)
        loss = (-delta.clip(upper=0.0))
        avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-12)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return float(rsi.iloc[-1])
    except Exception:
        return 50.0


def extension_pct(price: float, ref: float) -> float:
    price = _f(price)
    ref = _f(ref)
    if price <= 0 or ref <= 0:
        return 0.0
    return abs(price - ref) / ref * 100.0


def _near_level(price: float, level: float, tol_pct: float) -> bool:
    if price <= 0 or level <= 0:
        return False
    return extension_pct(price, level) <= abs(tol_pct)


def evaluate_pullback_pivot(
    *,
    side: str,
    df_1m,
    mark_price: float,
    tol_pct: float = PULLBACK_TOL_PCT,
) -> dict[str, Any]:
    """
    Autoriza só se o preço está na zona de valor (EMA8/EMA20) saindo de retração.
    """
    out = {
        'ok': False,
        'near_ema8': False,
        'near_ema20': False,
        'exiting_pullback': False,
        'ema8': 0.0,
        'ema20': 0.0,
        'reason': '',
    }
    if df_1m is None or len(df_1m) < max(EMA_SLOW + 3, 12) or 'close' not in df_1m.columns:
        out['reason'] = 'histórico 1m insuficiente para pullback EMA'
        return out

    last = df_1m.iloc[-1]
    prev = df_1m.iloc[-2]
    close = _f(mark_price) or _f(last['close'])
    low = _f(last['low'])
    high = _f(last['high'])
    open_ = _f(last['open'])
    ema8 = _ema_last(df_1m['close'], EMA_FAST)
    ema20 = _ema_last(df_1m['close'], EMA_SLOW)
    out['ema8'] = ema8
    out['ema20'] = ema20

    near8 = _near_level(close, ema8, tol_pct) or (low <= ema8 <= high)
    near20 = _near_level(close, ema20, tol_pct) or (low <= ema20 <= high)
    out['near_ema8'] = near8
    out['near_ema20'] = near20

    if not (near8 or near20):
        out['reason'] = (
            f'preço longe da zona EMA{EMA_FAST}/EMA{EMA_SLOW} '
            f'(close={close:.6g} ema8={ema8:.6g} ema20={ema20:.6g} tol={tol_pct:.2f}%)'
        )
        return out

    is_long = _is_long(side)
    prev_close = _f(prev['close'])
    prev_low = _f(prev['low'])
    prev_high = _f(prev['high'])

    if is_long:
        # Retração: veio de cima tocando EMA / ou low da atual/prev tocou EMA
        touched = (
            prev_low <= ema8 * (1 + tol_pct / 100.0)
            or low <= ema8 * (1 + tol_pct / 100.0)
            or prev_low <= ema20 * (1 + tol_pct / 100.0)
            or low <= ema20 * (1 + tol_pct / 100.0)
        )
        # Saindo da retração: candle verde ou close recuperando EMA8
        exiting = (close >= open_) or (close >= ema8 and prev_close < ema8)
        out['exiting_pullback'] = bool(touched and exiting)
        if not touched:
            out['reason'] = 'sem toque de pullback na EMA (LONG chase de topo)'
            return out
        if not exiting:
            out['reason'] = 'ainda em retração — aguardar rejeição/saída da EMA (LONG)'
            return out
    else:
        touched = (
            prev_high >= ema8 * (1 - tol_pct / 100.0)
            or high >= ema8 * (1 - tol_pct / 100.0)
            or prev_high >= ema20 * (1 - tol_pct / 100.0)
            or high >= ema20 * (1 - tol_pct / 100.0)
        )
        exiting = (close <= open_) or (close <= ema8 and prev_close > ema8)
        out['exiting_pullback'] = bool(touched and exiting)
        if not touched:
            out['reason'] = 'sem toque de pullback na EMA (SHORT chase de fundo)'
            return out
        if not exiting:
            out['reason'] = 'ainda em bounce — aguardar rejeição/saída da EMA (SHORT)'
            return out

    out['ok'] = True
    out['reason'] = (
        f'pullback OK na zona EMA{EMA_FAST}/EMA{EMA_SLOW} '
        f'(ema8={ema8:.6g} ema20={ema20:.6g})'
    )
    return out


def evaluate_anti_chase_entry(
    *,
    side: str,
    mark_price: float,
    df_1m=None,
    df_5m=None,
    signals: dict | None = None,
    c3_confidence_pct: float | None = None,
) -> dict[str, Any]:
    """
    Avalia os 3 filtros. Fail-closed se dados essenciais faltarem (quando habilitado).

    Returns:
      allowed, code, abort_reason, details
    """
    signals = signals or {}
    result = {
        'allowed': True,
        'code': 'OK',
        'abort_reason': '',
        'details': {},
        'enabled': ENABLED,
    }
    if not ENABLED:
        result['code'] = 'DISABLED'
        return result

    mark = _f(mark_price) or _f(signals.get('price'))
    is_long = _is_long(side)
    c3_soft = c3_confidence_pct is not None and float(c3_confidence_pct) >= C3_SOFT_CONFIDENCE_PCT

    def _soft_allow(blocked: dict) -> dict:
        """C3 >= limiar operacional: não aborta — aperta gestão de risco."""
        if not c3_soft or blocked.get('allowed'):
            return blocked
        out = dict(blocked)
        out['allowed'] = True
        out['code'] = 'SOFT_PASS_C3'
        out['soft_override'] = True
        prev = out.get('abort_reason') or out.get('code') or ''
        out['abort_reason'] = (
            f'C3 conf={float(c3_confidence_pct):.1f}% — anti-chase soft (ajuste SL): {prev}'
        )
        atr_pct = _f(signals.get('atr_pct'))
        if atr_pct <= 0 and mark > 0:
            atr_abs = _f(signals.get('atr_20') or signals.get('atr'))
            if atr_abs > 0:
                atr_pct = (atr_abs / mark) * 100.0
        tighten = max(0.8, min(2.5, atr_pct * 0.5)) if atr_pct > 0 else 1.2
        out['sl_tighten_pct'] = round(tighten, 3)
        return out

    # ── RSI 1m / 5m ────────────────────────────────────────────────────
    rsi_1m = 50.0
    rsi_5m = 50.0
    if df_1m is not None and len(df_1m) >= RSI_PERIOD + 2 and 'close' in df_1m.columns:
        rsi_1m = compute_rsi(df_1m['close'], RSI_PERIOD)
    elif signals.get('rsi_1m') is not None:
        rsi_1m = _f(signals.get('rsi_1m'), 50.0)

    if df_5m is not None and len(df_5m) >= RSI_PERIOD + 2 and 'close' in df_5m.columns:
        rsi_5m = compute_rsi(df_5m['close'], RSI_PERIOD)
    elif signals.get('rsi_5m') is not None:
        rsi_5m = _f(signals.get('rsi_5m'), 50.0)
    else:
        # fallback: RSI do timeframe principal (15m) como proxy do 5m
        rsi_5m = _f(signals.get('rsi'), rsi_5m)

    result['details']['rsi_1m'] = round(rsi_1m, 2)
    result['details']['rsi_5m'] = round(rsi_5m, 2)

    if is_long:
        if rsi_5m > RSI_5M_LONG_MAX or rsi_1m > RSI_1M_LONG_MAX:
            return _soft_allow({
                'allowed': False,
                'code': 'REJECTED: OVERBOUGHT_RSI',
                'abort_reason': (
                    f'REJECTED: OVERBOUGHT_RSI — RSI5m={rsi_5m:.1f} '
                    f'(lim {RSI_5M_LONG_MAX:.0f}) RSI1m={rsi_1m:.1f} (lim {RSI_1M_LONG_MAX:.0f})'
                ),
                'details': dict(result['details']),
            })
    else:
        if rsi_5m < RSI_5M_SHORT_MIN or rsi_1m < RSI_1M_SHORT_MIN:
            return _soft_allow({
                'allowed': False,
                'code': 'REJECTED: OVERSOLD_RSI',
                'abort_reason': (
                    f'REJECTED: OVERSOLD_RSI — RSI5m={rsi_5m:.1f} '
                    f'(lim {RSI_5M_SHORT_MIN:.0f}) RSI1m={rsi_1m:.1f} (lim {RSI_1M_SHORT_MIN:.0f})'
                ),
                'details': dict(result['details']),
            })

    # ── Extensão EMA20 / VWAP ───────────────────────────────────────────
    ema20 = 0.0
    if df_5m is not None and len(df_5m) >= EMA_SLOW + 2 and 'close' in df_5m.columns:
        ema20 = _ema_last(df_5m['close'], EMA_SLOW)
    if ema20 <= 0 and df_1m is not None and len(df_1m) >= EMA_SLOW + 2:
        ema20 = _ema_last(df_1m['close'], EMA_SLOW)
    if ema20 <= 0:
        ema20 = _f(signals.get('ema_21')) or _f(signals.get('ema_20'))

    vwap = _f(signals.get('vwap'))
    dist_ema = extension_pct(mark, ema20) if ema20 > 0 else 0.0
    dist_vwap = extension_pct(mark, vwap) if vwap > 0 else 0.0
    # Usa o maior afastamento (mais conservador)
    dist = max(dist_ema, dist_vwap)
    result['details']['ema20'] = ema20
    result['details']['vwap'] = vwap
    result['details']['extension_pct'] = round(dist, 3)
    result['details']['extension_ema_pct'] = round(dist_ema, 3)
    result['details']['extension_vwap_pct'] = round(dist_vwap, 3)

    atr_pct = _f(signals.get('atr_pct'))
    if atr_pct <= 0 and mark > 0:
        atr_abs = _f(signals.get('atr_20') or signals.get('atr'))
        if atr_abs > 0:
            atr_pct = (atr_abs / mark) * 100.0
    max_ext = MAX_EXTENSION_PCT
    if atr_pct > 0:
        max_ext = max(MAX_EXTENSION_PCT, atr_pct * ATR_EXTENSION_MULT)
    result['details']['max_extension_pct'] = round(max_ext, 3)

    if ema20 > 0 and dist_ema > max_ext:
        blocked = {
            'allowed': False,
            'code': 'REJECTED: PRICE_TOO_EXTENDED',
            'abort_reason': (
                f'REJECTED: PRICE_TOO_EXTENDED — |preço-EMA20|/EMA20='
                f'{dist_ema:.2f}% > {max_ext:.1f}% (preço={mark:.6g} ema20={ema20:.6g})'
            ),
            'details': dict(result['details']),
        }
        soft = _soft_allow(blocked)
        if soft.get('allowed'):
            result.update(soft)
            return result
        result.update(blocked)
        return result
    if vwap > 0 and dist_vwap > max_ext:
        blocked = {
            'allowed': False,
            'code': 'REJECTED: PRICE_TOO_EXTENDED',
            'abort_reason': (
                f'REJECTED: PRICE_TOO_EXTENDED — |preço-VWAP|/VWAP='
                f'{dist_vwap:.2f}% > {max_ext:.1f}%'
            ),
            'details': dict(result['details']),
        }
        soft = _soft_allow(blocked)
        if soft.get('allowed'):
            result.update(soft)
            return result
        result.update(blocked)
        return result

    # ── Pullback EMA8/EMA20 (pivô) ─────────────────────────────────────
    pull = evaluate_pullback_pivot(side=side, df_1m=df_1m, mark_price=mark)
    result['details']['pullback'] = pull
    if not pull.get('ok'):
        blocked = {
            'allowed': False,
            'code': 'REJECTED: WAIT_PULLBACK_EMA',
            'abort_reason': (
                f"REJECTED: WAIT_PULLBACK_EMA — {pull.get('reason') or 'aguardar zona EMA'}"
            ),
            'details': dict(result['details']),
        }
        soft = _soft_allow(blocked)
        if soft.get('allowed'):
            result.update(soft)
            return result
        result.update(blocked)
        return result

    result['abort_reason'] = (
        f'Anti-chase OK — RSI5m={rsi_5m:.0f}/1m={rsi_1m:.0f} '
        f'ext={dist:.2f}% | {pull.get("reason")}'
    )
    return result
