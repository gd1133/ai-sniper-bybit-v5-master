"""
Confirmação de timing de entrada — consultivo pós-C3.

Com POST_C3_GATES_ADVISORY=true (default), nunca bloqueia execução decidida
pelo C3 — apenas informa alinhamento de tendência/SuperTrend/repique e
sugere ajustes de gestão de risco.
"""

from __future__ import annotations

import os
from typing import Tuple

import pandas as pd

from src.engine.candle_patterns import institutional_candle_confirmation
from src.engine.cautious_entry_gate import cautious_entry_gate, enrich_signals_with_fvg


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


def _trend_must_align(side: str, signals: dict) -> Tuple[bool, list[str]]:
    """Contexto C1: tendência + SuperTrend (consultivo — não veta ordem no modo soberano)."""
    side_norm = str(side or '').strip().lower()
    trend = str(signals.get('trend', 'NEUTRO')).upper()
    st = int(signals.get('supertrend_signal', 0) or 0)

    if side_norm in ('buy', 'long', 'comprar'):
        if trend != 'ALTA':
            return False, [f'Tendência {trend} — COMPRA bloqueada (exige ALTA)']
        if st != 1:
            return False, ['SuperTrend não confirma ALTA']
        return True, ['Tendência ALTA + SuperTrend alinhados para COMPRA']

    if side_norm in ('sell', 'short', 'vender'):
        if trend != 'BAIXA':
            return False, [f'Tendência {trend} — VENDA bloqueada (exige BAIXA)']
        if st != -1:
            return False, ['SuperTrend não confirma BAIXA']
        return True, ['Tendência BAIXA + SuperTrend alinhados para VENDA']

    return False, [f'Side inválido: {side}']


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
    if not (had_overbought and crossed_below_60):
        return False, [
            f'RSI aguardando repique: overbought={had_overbought}, '
            f'cruzou_abaixo_60={crossed_below_60} (atual={current_rsi:.1f})'
        ]
    reasons.append(
        f'RSI repique (máx>{RSI_SHORT_OVERBOUGHT:.0f}, cruzou <{RSI_SHORT_CROSS_LEVEL:.0f})'
    )

    close = float(work['close'].iloc[-1])
    ema9 = float(work['ema_9'].iloc[-1])
    ema21 = float(work['ema_21'].iloc[-1])
    ema9_prev = float(work['ema_9'].iloc[-2])
    ema21_prev = float(work['ema_21'].iloc[-2])
    bearish_cross = ema9_prev >= ema21_prev and ema9 < ema21
    if not (close < ema9 or bearish_cross):
        return False, [f'Preço {close:.4f} ainda acima da EMA9={ema9:.4f}']
    reasons.append('EMA9 cruzou abaixo EMA21' if bearish_cross else 'Fechamento abaixo EMA9')

    prev = work.iloc[-2]
    if float(prev['close']) >= float(prev['open']):
        return False, ['Vela anterior não é de baixa (sem rejeição do topo)']
    reasons.append('Vela anterior de baixa — rejeição institucional')

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
    if not (had_oversold and crossed_above_40):
        return False, [
            f'RSI aguardando repique: oversold={had_oversold}, '
            f'cruzou_acima_40={crossed_above_40} (atual={current_rsi:.1f})'
        ]
    reasons.append(
        f'RSI repique (mín<{RSI_LONG_OVERSOLD:.0f}, cruzou >{RSI_LONG_CROSS_LEVEL:.0f})'
    )

    close = float(work['close'].iloc[-1])
    ema9 = float(work['ema_9'].iloc[-1])
    ema21 = float(work['ema_21'].iloc[-1])
    ema9_prev = float(work['ema_9'].iloc[-2])
    ema21_prev = float(work['ema_21'].iloc[-2])
    bullish_cross = ema9_prev <= ema21_prev and ema9 > ema21
    if not (close > ema9 or bullish_cross):
        return False, [f'Preço {close:.4f} ainda abaixo da EMA9={ema9:.4f}']
    reasons.append('EMA9 cruzou acima EMA21' if bullish_cross else 'Fechamento acima EMA9')

    prev = work.iloc[-2]
    if float(prev['close']) <= float(prev['open']):
        return False, ['Vela anterior não é de alta (sem rejeição do fundo)']
    reasons.append('Vela anterior de alta — rejeição institucional')

    return True, reasons


def _post_c3_advisory_only() -> bool:
    from src.engine.advisory_gates import post_c3_advisory_enabled
    return post_c3_advisory_enabled()


def confirmar_timing_entrada(
    side: str,
    df: pd.DataFrame,
    signals: dict | None = None,
    *,
    advisory_only: bool | None = None,
) -> Tuple[bool, list[str]]:
    """
    Validação de timing antes de disparar ordem.

    advisory_only=True (default via POST_C3_GATES_ADVISORY): 100% consultivo —
    nunca retorna False; C3 soberano decide execução.
    """
    if advisory_only is None:
        advisory_only = _post_c3_advisory_only()

    signals = enrich_signals_with_fvg(df, signals or {})
    side_norm = str(side or '').strip().lower()
    all_reasons: list[str] = []

    def _finalize(ok: bool, reasons: list[str]) -> Tuple[bool, list[str]]:
        if advisory_only and not ok:
            return True, [f'[consultivo] {r}' for r in reasons]
        return ok, reasons

    # ── 0) PORTÃO CAUTELOSO ──
    ok_gate, gate_reasons = cautious_entry_gate(side, df, signals)
    if not ok_gate:
        return _finalize(False, gate_reasons)
    all_reasons.extend(gate_reasons)

    # ── 1) Tendência + SuperTrend ──
    ok_trend, trend_reasons = _trend_must_align(side, signals)
    if not ok_trend:
        return _finalize(False, trend_reasons)
    all_reasons.extend(trend_reasons)

    # ── 2) Confirmações adicionais (não bypassam o portão) ──
    ok_candles, candle_reasons = institutional_candle_confirmation(side, df, signals)
    if ok_candles:
        all_reasons.extend(candle_reasons)

    try:
        from src.engine.chart_structure import assertive_structure_entry
        ok_assert, assert_reasons = assertive_structure_entry(side, df, signals)
    except Exception as exc:
        ok_assert, assert_reasons = False, [f'Estrutura indisponível: {exc}']

    if ok_assert:
        all_reasons.extend(assert_reasons)

    if side_norm in ('sell', 'short', 'vender'):
        ok_repique, repique_reasons = _confirm_short_repique(df)
    elif side_norm in ('buy', 'long', 'comprar'):
        ok_repique, repique_reasons = _confirm_long_repique(df)
    else:
        return _finalize(False, [f'Side inválido: {side}'])

    if ok_repique:
        all_reasons.extend(repique_reasons)
        all_reasons.append('✅ Timing completo (portão + tendência + repique)')
        return True, all_reasons

    # Portão cauteloso já passou — se tiver estrutura OU velas institucionais, libera
    if ok_candles or ok_assert:
        all_reasons.append('✅ Timing cauteloso OK (portão + tendência + confirmação de vela/estrutura)')
        return True, all_reasons

    # Portão passou sozinho (vela forte na direção) — ainda assim exige volume mínimo
    vol_ratio = float(signals.get('volume_ratio', 0) or 0)
    if vol_ratio >= 1.15:
        all_reasons.append(
            f'✅ Timing cauteloso OK (portão + tendência + volume×{vol_ratio:.2f})'
        )
        return True, all_reasons

    all_reasons.append(
        '⏳ Portão OK mas volume fraco — aguarde confirmação de fluxo'
    )
    return _finalize(False, all_reasons)
