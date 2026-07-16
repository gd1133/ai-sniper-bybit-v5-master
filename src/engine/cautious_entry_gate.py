# -*- coding: utf-8 -*-
"""
Portão cauteloso do Cérebro 3 — anti-armadilha de mercado.

Regras de ouro (bloqueio DURO):
  1. NUNCA comprar com vela vermelha (close < open).
  2. NUNCA vender com vela verde (close > open).
  3. NUNCA operar contra a tendência macro.
  4. Venda no fundo: exige vela FORTE vermelha (não vender só porque caiu).
  5. Compra no fundo: só com vela FORTE verde + mudança de momentum (bounce).
  6. Sempre buscar o momento certo: cor da vela + força + engolfo/FVG.

Estratégias incrementais lucrativas (confirmação, não substituição):
  - Engolfo (bullish/bearish engulfing)
  - Fair Value Gap (FVG) alinhado à direção
  - Rejeição de pivô + vela forte
  - Momentum de 3 velas na direção
"""

from __future__ import annotations

from typing import Tuple

import pandas as pd

from src.engine.candle_patterns import (
    detect_bearish_engulfing,
    detect_bullish_engulfing,
    detect_strong_down_candle,
    detect_strong_up_candle,
    is_bearish_candle,
    is_bullish_candle,
    _body_pct,
    _momentum_bars,
)


def detect_fair_value_gap(df: pd.DataFrame) -> dict:
    """
    Fair Value Gap (FVG) nas 3 últimas velas fechadas:
      Bullish FVG: low[atual] > high[i-2]  (gap para cima)
      Bearish FVG: high[atual] < low[i-2]  (gap para baixo)
    """
    empty = {'fvg_bullish': False, 'fvg_bearish': False, 'fvg_mid': 0.0}
    if df is None or len(df) < 3:
        return empty
    c0 = df.iloc[-3]  # candle que abre o gap
    c2 = df.iloc[-1]  # candle atual
    bull = float(c2['low']) > float(c0['high'])
    bear = float(c2['high']) < float(c0['low'])
    mid = 0.0
    if bull:
        mid = (float(c0['high']) + float(c2['low'])) / 2.0
    elif bear:
        mid = (float(c0['low']) + float(c2['high'])) / 2.0
    return {'fvg_bullish': bull, 'fvg_bearish': bear, 'fvg_mid': mid}


def _near_bottom_trap(signals: dict, rsi: float) -> bool:
    """Possível armadilha de fundo: RSI oversold ou perto de pivô baixo."""
    if rsi <= 28:
        return True
    if signals.get('near_pivot_support') or signals.get('bounce_from_pivot_low'):
        return True
    return False


def _near_top_trap(signals: dict, rsi: float) -> bool:
    """Possível armadilha de topo: RSI overbought ou perto de pivô alto."""
    if rsi >= 72:
        return True
    if signals.get('near_pivot_resistance') or signals.get('rejection_from_pivot_high'):
        return True
    return False


def cautious_entry_gate(
    side: str,
    df: pd.DataFrame,
    signals: dict | None = None,
) -> Tuple[bool, list[str]]:
    """
    Portão cauteloso obrigatório antes de qualquer entrada.
    Retorna (ok, reasons). Se ok=False, a entrada DEVE ser abortada.
    """
    signals = signals or {}
    side_norm = str(side or '').strip().lower()
    reasons: list[str] = []

    if df is None or len(df) < 5:
        return False, ['⛔ Histórico insuficiente para portão cauteloso']

    last = df.iloc[-1]
    prev = df.iloc[-2]
    trend = str(signals.get('trend', 'NEUTRO')).upper()
    st = int(signals.get('supertrend_signal', 0) or signals.get('supertrend', 0) or 0)
    atr = float(signals.get('atr', 0) or 0)
    vol_ratio = float(signals.get('volume_ratio', 1) or 1)
    rsi = float(signals.get('rsi', 50) or 50)
    body_last = _body_pct(last)
    bulls, bears = _momentum_bars(df, 3)
    fvg = detect_fair_value_gap(df)
    strong_up = detect_strong_up_candle(last, atr, vol_ratio) or detect_strong_up_candle(prev, atr, vol_ratio)
    strong_down = detect_strong_down_candle(last, atr, vol_ratio) or detect_strong_down_candle(prev, atr, vol_ratio)
    engulf_up = detect_bullish_engulfing(df)
    engulf_down = detect_bearish_engulfing(df)

    # ── COMPRA ──────────────────────────────────────────────────────────
    if side_norm in ('buy', 'long', 'comprar'):
        # 1) Tendência
        if trend != 'ALTA':
            return False, [f'⛔ COMPRA bloqueada — tendência={trend} (exige ALTA)']
        if st != 1:
            return False, ['⛔ COMPRA bloqueada — SuperTrend não confirma ALTA']

        # 2) NUNCA comprar com vela vermelha
        if is_bearish_candle(last):
            return False, [
                f'⛔ NUNCA comprar com vela VERMELHA (corpo={body_last:.0f}%) — '
                f'aguarde vela VERDE forte'
            ]

        # 3) Armadilha de topo: não comprar no topo sem confirmação extra
        if _near_top_trap(signals, rsi) and not (strong_up and (engulf_up or fvg['fvg_bullish'])):
            return False, [
                f'⛔ Armadilha de TOPO (RSI={rsi:.0f}) — '
                f'exige vela FORTE verde + engolfo/FVG'
            ]

        # 4) Compra no fundo: só com vela FORTE verde (mudança de tendência)
        if _near_bottom_trap(signals, rsi):
            if not strong_up:
                return False, [
                    '⛔ Compra no FUNDO — aguarde vela FORTE VERDE '
                    '(confirmação de mudança de momentum)'
                ]
            reasons.append('✅ Compra no fundo com vela FORTE VERDE (bounce)')
        else:
            # Em tendência normal: exige vela verde + (forte OU engolfo OU FVG OU momentum)
            if not is_bullish_candle(last):
                return False, ['⛔ Aguardando vela VERDE de confirmação']
            if not (strong_up or engulf_up or fvg['fvg_bullish'] or bulls >= 2):
                return False, [
                    '⛔ Momento ainda fraco — aguarde vela FORTE / engolfo / FVG / 2+ verdes'
                ]

        if strong_up:
            reasons.append('Vela FORTE VERDE confirmada')
        if engulf_up:
            reasons.append('Engolfo de ALTA detectado')
        if fvg['fvg_bullish']:
            reasons.append('Fair Value Gap bullish alinhado')
        if bulls >= 2:
            reasons.append(f'Momentum: {bulls} velas verdes recentes')
        reasons.append('✅ Portão cauteloso COMPRA OK')
        return True, reasons

    # ── VENDA ───────────────────────────────────────────────────────────
    if side_norm in ('sell', 'short', 'vender'):
        if trend != 'BAIXA':
            return False, [f'⛔ VENDA bloqueada — tendência={trend} (exige BAIXA)']
        if st != -1:
            return False, ['⛔ VENDA bloqueada — SuperTrend não confirma BAIXA']

        # NUNCA vender com vela verde
        if is_bullish_candle(last):
            return False, [
                f'⛔ NUNCA vender com vela VERDE (corpo={body_last:.0f}%) — '
                f'aguarde vela VERMELHA forte'
            ]

        # Armadilha de fundo: NÃO vender no fundo sem vela FORTE vermelha
        if _near_bottom_trap(signals, rsi):
            if not strong_down:
                return False, [
                    f'⛔ Armadilha de FUNDO (RSI={rsi:.0f}/pivô) — '
                    f'NÃO vender no fundo. Aguarde vela FORTE VERMELHA'
                ]
            if not (engulf_down or fvg['fvg_bearish'] or bears >= 2):
                return False, [
                    '⛔ Fundo com pressão ainda fraca — aguarde engolfo/FVG/2+ vermelhas'
                ]
            reasons.append('✅ Venda após fundo só com vela FORTE VERMELHA + confirmação')
        else:
            if not is_bearish_candle(last):
                return False, ['⛔ Aguardando vela VERMELHA de confirmação']
            # Exige força real — não vender em vela vermelha fraca/doji
            if not (strong_down or engulf_down or fvg['fvg_bearish'] or bears >= 2):
                return False, [
                    '⛔ Momento ainda fraco para venda — '
                    'aguarde vela FORTE VERMELHA / engolfo / FVG'
                ]

        # Armadilha de topo já passou — venda em topo é OK se vela forte vermelha
        if _near_top_trap(signals, rsi) and strong_down:
            reasons.append('Rejeição de topo + vela FORTE VERMELHA')

        if strong_down:
            reasons.append('Vela FORTE VERMELHA confirmada')
        if engulf_down:
            reasons.append('Engolfo de BAIXA detectado')
        if fvg['fvg_bearish']:
            reasons.append('Fair Value Gap bearish alinhado')
        if bears >= 2:
            reasons.append(f'Momentum: {bears} velas vermelhas recentes')
        reasons.append('✅ Portão cauteloso VENDA OK')
        return True, reasons

    return False, [f'Side inválido: {side}']


def enrich_signals_with_fvg(df: pd.DataFrame, signals: dict) -> dict:
    """Injeta flags FVG no dict de sinais (incremental)."""
    out = dict(signals or {})
    try:
        fvg = detect_fair_value_gap(df)
        out.update(fvg)
    except Exception:
        out.setdefault('fvg_bullish', False)
        out.setdefault('fvg_bearish', False)
        out.setdefault('fvg_mid', 0.0)
    return out
