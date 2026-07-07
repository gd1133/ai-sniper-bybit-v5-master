"""
Confirmação de timing de entrada — evita sinais falsos em repiques.

Short (tendência de baixa + correção para cima):
  - RSI subiu > 65 e cruzou de volta abaixo de 60
  - Preço fechou abaixo da EMA 9 OU cruzamento descendente EMA9/EMA21
  - Vela anterior de baixa (rejeição do topo)

Long (tendência de alta + correção para baixo) — espelhado:
  - RSI caiu < 35 e cruzou de volta acima de 40
  - Preço fechou acima da EMA 9 OU cruzamento ascendente EMA9/EMA21
  - Vela anterior de alta
"""

from __future__ import annotations

from typing import Tuple

import pandas as pd


RSI_SHORT_OVERBOUGHT = 65.0
RSI_SHORT_CROSS_LEVEL = 60.0
RSI_LONG_OVERSOLD = 35.0
RSI_LONG_CROSS_LEVEL = 40.0
REPIQUE_LOOKBACK = 12


def _ensure_ema_columns(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if 'ema_9' not in work.columns:
        work['ema_9'] = work['close'].ewm(span=9, adjust=False).mean()
    if 'ema_21' not in work.columns:
        work['ema_21'] = work['close'].ewm(span=21, adjust=False).mean()
    if 'rsi' not in work.columns:
        delta = work['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
        rs = gain / (loss + 1e-9)
        work['rsi'] = 100 - (100 / (1 + rs))
    return work


def _confirm_short_repique(df: pd.DataFrame) -> Tuple[bool, list[str]]:
    reasons = []
    if len(df) < REPIQUE_LOOKBACK + 2:
        return False, ['Histórico insuficiente para confirmar repique']

    work = _ensure_ema_columns(df)
    rsi = work['rsi']
    current_rsi = float(rsi.iloc[-1])
    prev_rsi = float(rsi.iloc[-2])
    recent_rsi = rsi.iloc[-REPIQUE_LOOKBACK:]

    had_overbought = bool((recent_rsi > RSI_SHORT_OVERBOUGHT).any())
    crossed_below_60 = prev_rsi >= RSI_SHORT_CROSS_LEVEL and current_rsi < RSI_SHORT_CROSS_LEVEL
    rsi_ok = had_overbought and crossed_below_60
    if rsi_ok:
        reasons.append(
            f'RSI repique confirmado (máx>{RSI_SHORT_OVERBOUGHT:.0f}, cruzou <{RSI_SHORT_CROSS_LEVEL:.0f})'
        )
    else:
        return False, [
            f'RSI aguardando: overbought={had_overbought}, cruzamento_abaixo_60={crossed_below_60} '
            f'(atual={current_rsi:.1f})'
        ]

    close = float(work['close'].iloc[-1])
    ema9 = float(work['ema_9'].iloc[-1])
    ema21 = float(work['ema_21'].iloc[-1])
    ema9_prev = float(work['ema_9'].iloc[-2])
    ema21_prev = float(work['ema_21'].iloc[-2])
    bearish_cross = ema9_prev >= ema21_prev and ema9 < ema21
    ema_ok = close < ema9 or bearish_cross
    if ema_ok:
        if bearish_cross:
            reasons.append('EMA9 cruzou abaixo da EMA21')
        else:
            reasons.append('Fechamento abaixo da EMA9 após repique')
    else:
        return False, [f'EMA: preço={close:.4f} ainda acima da EMA9={ema9:.4f}']

    prev = work.iloc[-2]
    bearish_candle = float(prev['close']) < float(prev['open'])
    if bearish_candle:
        reasons.append('Vela anterior de baixa (rejeição do topo)')
    else:
        return False, ['Vela anterior não confirma rejeição (não é vela de baixa)']

    return True, reasons


def _confirm_long_repique(df: pd.DataFrame) -> Tuple[bool, list[str]]:
    reasons = []
    if len(df) < REPIQUE_LOOKBACK + 2:
        return False, ['Histórico insuficiente para confirmar repique']

    work = _ensure_ema_columns(df)
    rsi = work['rsi']
    current_rsi = float(rsi.iloc[-1])
    prev_rsi = float(rsi.iloc[-2])
    recent_rsi = rsi.iloc[-REPIQUE_LOOKBACK:]

    had_oversold = bool((recent_rsi < RSI_LONG_OVERSOLD).any())
    crossed_above_40 = prev_rsi <= RSI_LONG_CROSS_LEVEL and current_rsi > RSI_LONG_CROSS_LEVEL
    rsi_ok = had_oversold and crossed_above_40
    if rsi_ok:
        reasons.append(
            f'RSI repique confirmado (mín<{RSI_LONG_OVERSOLD:.0f}, cruzou >{RSI_LONG_CROSS_LEVEL:.0f})'
        )
    else:
        return False, [
            f'RSI aguardando: oversold={had_oversold}, cruzamento_acima_40={crossed_above_40} '
            f'(atual={current_rsi:.1f})'
        ]

    close = float(work['close'].iloc[-1])
    ema9 = float(work['ema_9'].iloc[-1])
    ema21 = float(work['ema_21'].iloc[-1])
    ema9_prev = float(work['ema_9'].iloc[-2])
    ema21_prev = float(work['ema_21'].iloc[-2])
    bullish_cross = ema9_prev <= ema21_prev and ema9 > ema21
    ema_ok = close > ema9 or bullish_cross
    if ema_ok:
        if bullish_cross:
            reasons.append('EMA9 cruzou acima da EMA21')
        else:
            reasons.append('Fechamento acima da EMA9 após repique')
    else:
        return False, [f'EMA: preço={close:.4f} ainda abaixo da EMA9={ema9:.4f}']

    prev = work.iloc[-2]
    bullish_candle = float(prev['close']) > float(prev['open'])
    if bullish_candle:
        reasons.append('Vela anterior de alta (rejeição do fundo)')
    else:
        return False, ['Vela anterior não confirma rejeição (não é vela de alta)']

    return True, reasons


def confirmar_timing_entrada(side: str, df: pd.DataFrame, signals: dict | None = None) -> Tuple[bool, list[str]]:
    """
    Valida fim de repique antes de disparar ordem.
    Retorna (aprovado, motivos).
    """
    signals = signals or {}
    side_norm = str(side or '').strip().lower()
    trend = str(signals.get('trend', 'NEUTRO')).upper()

    if side_norm in ('sell', 'short', 'vender'):
        if trend != 'BAIXA':
            return True, ['Short em tendência não-baixista — filtro de repique não exigido']
        return _confirm_short_repique(df)

    if side_norm in ('buy', 'long', 'comprar'):
        if trend != 'ALTA':
            return True, ['Long em tendência não-altista — filtro de repique não exigido']
        return _confirm_long_repique(df)

    return False, [f'Side inválido: {side}']
