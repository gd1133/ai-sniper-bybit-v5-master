# -*- coding: utf-8 -*-
"""
Anti-armadilha de mercado (SMC) — bloqueia compra no topo / falso rompimento.

Regras:
  1) BLOQUEIO DE TOPO: preço a ≤0.5% do High_24h + pavio superior >40% da amplitude
     → "VARREDURA DE LIQUIDEZ / FALSO ROMPIMENTO"
  2) CONFIRMAÇÃO DE TENDÊNCIA (LONG): preço acima da EMA20 e VWAP + 2 velas verdes
     consecutivas com agressão compradora (volume acima da média).
"""

from __future__ import annotations

import os
from typing import Any

TOP_DISTANCE_PCT = float(os.getenv('ANTI_TRAP_TOP_DISTANCE_PCT', '0.5'))
UPPER_WICK_PCT = float(os.getenv('ANTI_TRAP_UPPER_WICK_PCT', '40'))
EMA_PERIOD = int(os.getenv('ANTI_TRAP_EMA_PERIOD', '20'))
BUY_VOLUME_RATIO = float(os.getenv('ANTI_TRAP_BUY_VOL_RATIO', '1.15'))


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _upper_wick_pct(open_p: float, high: float, low: float, close: float) -> float:
    spread = max(high - low, 1e-12)
    body_top = max(open_p, close)
    return max(0.0, (high - body_top) / spread * 100.0)


def _lower_wick_pct(open_p: float, high: float, low: float, close: float) -> float:
    spread = max(high - low, 1e-12)
    body_bot = min(open_p, close)
    return max(0.0, (body_bot - low) / spread * 100.0)


def evaluate_anti_trap_smc(
    side: str,
    df,
    signals: dict | None = None,
) -> dict[str, Any]:
    """
    Fail-closed para LONG em armadilha de topo.
    SHORT: bloqueia fundo falso simétrico (pavio inferior longo perto do Low_24h).
    """
    signals = signals or {}
    side_n = str(side or '').strip().lower()
    out = {
        'allowed': True,
        'trap': False,
        'trap_type': '',
        'abort_reason': '',
        'checks': {},
        'high_24h': 0.0,
        'low_24h': 0.0,
        'upper_wick_pct': 0.0,
        'ema20': 0.0,
        'vwap': 0.0,
    }

    if df is None or len(df) < max(EMA_PERIOD + 2, 10):
        out['allowed'] = False
        out['abort_reason'] = 'histórico insuficiente para anti-armadilha SMC'
        return out

    # ~24h em 15m = 96 velas; High/Low prévios (exclui vela atual = varredura de liquidez)
    lookback = min(len(df) - 1, 96)
    if lookback < 10:
        out['allowed'] = False
        out['abort_reason'] = 'histórico insuficiente para anti-armadilha SMC'
        return out
    window = df.iloc[-(lookback + 1):-1]
    high_24h = float(window['high'].max())
    low_24h = float(window['low'].min())
    out['high_24h'] = high_24h
    out['low_24h'] = low_24h

    last = df.iloc[-1]
    o, h, l, c = _f(last['open']), _f(last['high']), _f(last['low']), _f(last['close'])
    upper_wick = _upper_wick_pct(o, h, l, c)
    lower_wick = _lower_wick_pct(o, h, l, c)
    out['upper_wick_pct'] = round(upper_wick, 1)
    out['checks']['lower_wick_pct'] = round(lower_wick, 1)

    ema20 = float(df['close'].astype(float).ewm(span=EMA_PERIOD, adjust=False).mean().iloc[-1])
    out['ema20'] = ema20
    vwap = _f(signals.get('vwap'))
    if vwap <= 0 and 'vwap' in df.columns:
        vwap = _f(df['vwap'].iloc[-1])
    out['vwap'] = vwap

    vol_ma = float(df['vol'].astype(float).tail(20).mean()) if 'vol' in df.columns else 0.0
    vol_now = _f(last['vol']) if 'vol' in last.index or hasattr(last, 'get') else 0.0
    try:
        vol_now = _f(last['vol'])
    except Exception:
        vol_now = 0.0
    vol_ratio = (vol_now / vol_ma) if vol_ma > 0 else _f(signals.get('volume_ratio'), 1.0)

    # Duas velas consecutivas de agressão
    prev = df.iloc[-2]
    o1, c1 = _f(prev['open']), _f(prev['close'])
    two_green = c > o and c1 > o1
    two_red = c < o and c1 < o1

    if side_n in ('buy', 'long', 'comprar'):
        dist_top_pct = ((high_24h - c) / high_24h * 100.0) if high_24h > 0 else 999.0
        near_top = dist_top_pct <= TOP_DISTANCE_PCT
        long_upper = upper_wick >= UPPER_WICK_PCT
        out['checks']['near_24h_high'] = near_top
        out['checks']['dist_top_pct'] = round(dist_top_pct, 3)
        out['checks']['long_upper_wick'] = long_upper

        if near_top and long_upper:
            out['allowed'] = False
            out['trap'] = True
            out['trap_type'] = 'BULL_TRAP'
            out['abort_reason'] = (
                f'VARREDURA DE LIQUIDEZ / FALSO ROMPIMENTO — '
                f'preço a {dist_top_pct:.2f}% do High_24h com pavio superior {upper_wick:.0f}%'
            )
            return out

        # Confirmação de tendência LONG
        above_ema = c > ema20
        above_vwap = (vwap <= 0) or (c > vwap)
        sustained_buy = two_green and vol_ratio >= BUY_VOLUME_RATIO
        out['checks']['above_ema20'] = above_ema
        out['checks']['above_vwap'] = above_vwap
        out['checks']['two_green_vol'] = sustained_buy

        if not above_ema:
            out['allowed'] = False
            out['abort_reason'] = f'LONG sem confirmação — close {c:.6f} abaixo EMA{EMA_PERIOD}={ema20:.6f}'
            return out
        if vwap > 0 and not above_vwap:
            out['allowed'] = False
            out['abort_reason'] = f'LONG sem confirmação — close abaixo da VWAP ({vwap:.6f})'
            return out
        if not sustained_buy:
            out['allowed'] = False
            out['abort_reason'] = (
                'LONG exige 2 velas verdes consecutivas com volume de agressão '
                f'(vol×{vol_ratio:.2f}, mín {BUY_VOLUME_RATIO:.2f})'
            )
            return out

        out['abort_reason'] = ''
        return out

    if side_n in ('sell', 'short', 'vender'):
        dist_bot_pct = ((c - low_24h) / low_24h * 100.0) if low_24h > 0 else 999.0
        near_bot = dist_bot_pct <= TOP_DISTANCE_PCT
        long_lower = lower_wick >= UPPER_WICK_PCT
        out['checks']['near_24h_low'] = near_bot
        out['checks']['dist_bot_pct'] = round(dist_bot_pct, 3)

        if near_bot and long_lower:
            out['allowed'] = False
            out['trap'] = True
            out['trap_type'] = 'BEAR_TRAP'
            out['abort_reason'] = (
                f'FALSO ROMPIMENTO DE FUNDO — preço a {dist_bot_pct:.2f}% do Low_24h '
                f'com pavio inferior {lower_wick:.0f}%'
            )
            return out

        # SHORT em tendência: abaixo EMA/VWAP (ou derretimento já liberado noutro módulo)
        if bool(signals.get('meltdown')) or bool(signals.get('second_red_entry')):
            out['checks']['meltdown_bypass'] = True
            return out

        below_ema = c < ema20
        below_vwap = (vwap <= 0) or (c < vwap)
        sustained_sell = two_red and vol_ratio >= BUY_VOLUME_RATIO
        out['checks']['below_ema20'] = below_ema
        out['checks']['below_vwap'] = below_vwap
        out['checks']['two_red_vol'] = sustained_sell

        if not below_ema:
            out['allowed'] = False
            out['abort_reason'] = f'SHORT sem confirmação — close acima EMA{EMA_PERIOD}'
            return out
        if vwap > 0 and not below_vwap:
            out['allowed'] = False
            out['abort_reason'] = 'SHORT sem confirmação — close acima da VWAP'
            return out
        if not sustained_sell:
            out['allowed'] = False
            out['abort_reason'] = 'SHORT exige 2 vermelhas consecutivas com volume de agressão'
            return out
        return out

    out['allowed'] = False
    out['abort_reason'] = f'side inválido: {side}'
    return out
