"""
Leitura avançada de velas — confirmação institucional antes da entrada.

Bloqueia entradas contra o fluxo visível (ex.: vender em vela verde forte).
"""

from __future__ import annotations

from typing import Tuple

import pandas as pd


def _body_pct(row) -> float:
    rng = max(float(row['high'] - row['low']), 1e-9)
    return abs(float(row['close'] - row['open'])) / rng * 100.0


def is_bullish_candle(row) -> bool:
    return float(row['close']) > float(row['open'])


def is_bearish_candle(row) -> bool:
    return float(row['close']) < float(row['open'])


def _momentum_bars(df: pd.DataFrame, n: int = 3) -> Tuple[int, int]:
    """Conta velas de alta/baixa nas últimas n barras fechadas."""
    if len(df) < n + 1:
        return 0, 0
    window = df.iloc[-(n + 1):-1] if len(df) > n else df.iloc[-n:]
    bulls = sum(1 for _, r in window.iterrows() if is_bullish_candle(r))
    bears = sum(1 for _, r in window.iterrows() if is_bearish_candle(r))
    return bulls, bears


def detect_bullish_engulfing(df: pd.DataFrame) -> bool:
    if len(df) < 3:
        return False
    prev, curr = df.iloc[-2], df.iloc[-1]
    if not is_bearish_candle(prev) or not is_bullish_candle(curr):
        return False
    return float(curr['close']) > float(prev['open']) and float(curr['open']) <= float(prev['close'])


def detect_bearish_engulfing(df: pd.DataFrame) -> bool:
    if len(df) < 3:
        return False
    prev, curr = df.iloc[-2], df.iloc[-1]
    if not is_bullish_candle(prev) or not is_bearish_candle(curr):
        return False
    return float(curr['close']) < float(prev['open']) and float(curr['open']) >= float(prev['close'])


def detect_strong_up_candle(row, atr: float = 0.0, volume_ratio: float = 1.0) -> bool:
    """Vela forte de subida — delega para chart_structure."""
    try:
        from src.engine.chart_structure import detect_strong_bullish_candle
        return detect_strong_bullish_candle(row, atr=atr, volume_ratio=volume_ratio)
    except Exception:
        return is_bullish_candle(row) and _body_pct(row) >= 55


def detect_strong_down_candle(row, atr: float = 0.0, volume_ratio: float = 1.0) -> bool:
    """Vela forte de descida — delega para chart_structure."""
    try:
        from src.engine.chart_structure import detect_strong_bearish_candle
        return detect_strong_bearish_candle(row, atr=atr, volume_ratio=volume_ratio)
    except Exception:
        return is_bearish_candle(row) and _body_pct(row) >= 55


def institutional_candle_confirmation(
    side: str,
    df: pd.DataFrame,
    signals: dict | None = None,
) -> Tuple[bool, list[str]]:
    """
    Confirma que velas, momentum e fluxo institucional concordam com o lado da entrada.
    INCREMENTO: se houver vela forte + pivô na direção, acelera a confirmação.
  """
    signals = signals or {}
    side_norm = str(side or '').strip().lower()
    reasons: list[str] = []

    if df is None or len(df) < 5:
        return False, ['Histórico insuficiente para leitura de velas']

    last = df.iloc[-1]
    prev = df.iloc[-2]
    trend = str(signals.get('trend', 'NEUTRO')).upper()
    st = int(signals.get('supertrend_signal', 0) or 0)
    money_flow = str(signals.get('money_flow_side', 'WAIT')).upper()
    recent_ret = float(signals.get('recent_return_pct', 0) or 0)
    body_last = _body_pct(last)
    bulls, bears = _momentum_bars(df, 3)
    atr = float(signals.get('atr', 0) or 0)
    vol_ratio = float(signals.get('volume_ratio', 1) or 1)

    if side_norm in ('buy', 'long', 'comprar'):
        if trend == 'BAIXA':
            return False, ['BLOQUEIO: tendência macro BAIXA — não comprar contra tendência']
        if st == -1:
            return False, ['BLOQUEIO: SuperTrend ainda em BAIXA']
        # NUNCA comprar com vela vermelha (qualquer corpo)
        if is_bearish_candle(last):
            return False, [f'BLOQUEIO: NUNCA comprar com vela VERMELHA (corpo={body_last:.0f}%)']
        if detect_bearish_engulfing(df):
            return False, ['BLOQUEIO: padrão Engulfing de baixa na vela atual']
        if bears >= 2 and bulls == 0:
            return False, ['BLOQUEIO: 3 velas seguidas de pressão vendedora']
        if recent_ret < -0.35:
            return False, [f'BLOQUEIO: momentum recente negativo ({recent_ret:.2f}%)']
        if money_flow == 'SELL':
            return False, ['BLOQUEIO: fluxo institucional apontando VENDA']
        # Confirmação premium: vela forte de subida + pivô/estrutura
        if detect_strong_up_candle(last, atr, vol_ratio) or detect_strong_up_candle(prev, atr, vol_ratio):
            if signals.get('bounce_from_pivot_low') or signals.get('near_pivot_support') or signals.get('structure_bias') == 'ALTA':
                reasons.append('Vela FORTE de SUBIDA + pivô/estrutura — confirmação acelerada')
                return True, reasons
        if not is_bullish_candle(last):
            return False, ['Aguardando vela VERDE de confirmação de compra']
        reasons.append('Velas e momentum confirmam COMPRA institucional')
        return True, reasons

    if side_norm in ('sell', 'short', 'vender'):
        if trend == 'ALTA':
            return False, ['BLOQUEIO: tendência macro ALTA — não vender contra tendência']
        if st == 1:
            return False, ['BLOQUEIO: SuperTrend ainda em ALTA']
        # NUNCA vender com vela verde (qualquer corpo)
        if is_bullish_candle(last):
            return False, [f'BLOQUEIO: NUNCA vender com vela VERDE (corpo={body_last:.0f}%)']
        if detect_bullish_engulfing(df):
            return False, ['BLOQUEIO: padrão Engulfing de alta na vela atual']
        if bulls >= 2 and bears == 0:
            return False, ['BLOQUEIO: 3 velas seguidas de pressão compradora']
        if recent_ret > 0.35:
            return False, [f'BLOQUEIO: momentum recente positivo ({recent_ret:.2f}%)']
        if money_flow == 'BUY':
            return False, ['BLOQUEIO: fluxo institucional apontando COMPRA']
        if detect_strong_down_candle(last, atr, vol_ratio) or detect_strong_down_candle(prev, atr, vol_ratio):
            if signals.get('rejection_from_pivot_high') or signals.get('near_pivot_resistance') or signals.get('structure_bias') == 'BAIXA':
                reasons.append('Vela FORTE de DESCIDA + pivô/estrutura — confirmação acelerada')
                return True, reasons
        if not is_bearish_candle(last):
            return False, ['Aguardando vela VERMELHA de confirmação de venda']
        reasons.append('Velas e momentum confirmam VENDA institucional')
        return True, reasons

    return False, [f'Side inválido: {side}']
