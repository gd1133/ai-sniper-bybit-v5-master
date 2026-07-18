"""Detecção de regime de mercado — tendência vs lateral (range)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, adjust=False).mean()


def calculate_adx_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Série ADX com suavização de Wilder; dados insuficientes permanecem NaN."""
    if df is None or len(df) < period + 2:
        return pd.Series(np.nan, index=df.index if df is not None else None, dtype=float)

    high = pd.to_numeric(df['high'], errors='coerce')
    low = pd.to_numeric(df['low'], errors='coerce')
    close = pd.to_numeric(df['close'], errors='coerce')

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    atr = _wilder_smooth(tr, period)
    plus_di = 100 * _wilder_smooth(plus_dm, period) / atr.replace(0, np.nan)
    minus_di = 100 * _wilder_smooth(minus_dm, period) / atr.replace(0, np.nan)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
    adx = _wilder_smooth(dx, period)

    # ADX precisa de aproximadamente 2*period-1 candles para estabilizar.
    adx.iloc[: max(0, (period * 2) - 1)] = np.nan
    return adx


def calculate_adx(df: pd.DataFrame, period: int = 14) -> float:
    """ADX atual — força da tendência. Retorna 0 se não houver dados suficientes."""
    adx = calculate_adx_series(df, period)
    if adx.empty or pd.isna(adx.iloc[-1]):
        return 0.0
    return float(adx.iloc[-1])


def calculate_choppiness(df: pd.DataFrame, period: int = 14) -> float:
    """
    Choppiness Index — alto (> 61.8) indica mercado lateral/consolidação.
    Baixo (< 38.2) indica tendência direcional.
    """
    if df is None or len(df) < period + 1:
        return 50.0

    high = df['high'].iloc[-period:]
    low = df['low'].iloc[-period:]
    close = df['close']

    tr = pd.concat([
        high - low,
        (high - close.shift().iloc[-period:]).abs(),
        (low - close.shift().iloc[-period:]).abs(),
    ], axis=1).max(axis=1)
    atr_sum = tr.sum()
    range_high_low = high.max() - low.min()
    if range_high_low <= 0:
        return 50.0

    chop = 100 * np.log10(atr_sum / range_high_low) / np.log10(period)
    return float(max(0.0, min(100.0, chop)))


def calculate_bollinger_bandwidth_series(
    df: pd.DataFrame,
    period: int = 20,
    deviations: float = 2.0,
) -> pd.Series:
    """Série BB Width no formato (Upper - Lower) / Middle."""
    if df is None or len(df) < period:
        return pd.Series(np.nan, index=df.index if df is not None else None, dtype=float)
    close = pd.to_numeric(df['close'], errors='coerce')
    middle = close.rolling(period, min_periods=period).mean()
    std = close.rolling(period, min_periods=period).std()
    upper = middle + (deviations * std)
    lower = middle - (deviations * std)
    return (upper - lower) / middle.replace(0, np.nan)


def calculate_bollinger_bandwidth(
    df: pd.DataFrame,
    period: int = 20,
    average_period: int = 50,
) -> tuple[float, float, bool]:
    """
    Retorna (largura_atual, média_das_últimas_50_larguras, expansão).
    Falha fechada: sem 50 larguras válidas, expansão=False.
    """
    width = calculate_bollinger_bandwidth_series(df, period, 2.0)
    width_mean = width.rolling(average_period, min_periods=average_period).mean()
    if width.empty or pd.isna(width.iloc[-1]) or pd.isna(width_mean.iloc[-1]):
        return 0.0, 0.0, False
    current = float(width.iloc[-1])
    average = float(width_mean.iloc[-1])
    return current, average, bool(current > average)


def calculate_range_amplitude_pct(df: pd.DataFrame, period: int = 20) -> float:
    """
    Amplitude percentual dos últimos X períodos:
      ((High.max() - Low.min()) / Low.min()) * 100
    """
    try:
        from src.engine.rastreador_institucional import calculate_range_amplitude_pct as _amp
        return float(_amp(df, period))
    except Exception:
        if df is None or len(df) < 2:
            return 0.0
        window = df.iloc[-max(2, int(period)):]
        low_min = float(window['low'].min())
        high_max = float(window['high'].max())
        if low_min <= 0:
            return 0.0
        return float(((high_max - low_min) / low_min) * 100.0)


def detect_market_regime(df: pd.DataFrame, signals: dict | None = None) -> dict:
    """
    Classifica o mercado em TREND ou RANGE (lateral).

    Bloqueia entradas quando:
    - Amplitude % dos últimos X períodos < LATERAL_AMPLITUDE_PCT (padrão 0.35%)
    - ADX(14) < 23 (trava absoluta)
    - BB Width atual <= média das últimas 50 larguras (sem expansão)
    - Preço preso na SMA200 (trend NEUTRO) com baixa expansão
    """
    import os
    signals = signals or {}
    adx = calculate_adx(df)
    choppiness = calculate_choppiness(df)
    bb_width, bb_width_mean, bb_expanding = calculate_bollinger_bandwidth(df)
    trend = str(signals.get('trend', 'NEUTRO')).upper()
    distance_sma = float(signals.get('distance_from_sma_pct', 0) or 0)
    range_expansion = float(signals.get('range_expansion', 0) or 0)

    # Amplitude anti-acumulação (configurável via env)
    try:
        amp_periods = int(float(os.getenv('LATERAL_AMPLITUDE_PERIODS', '20') or 20))
    except (TypeError, ValueError):
        amp_periods = 20
    try:
        amp_max = float(str(os.getenv('LATERAL_AMPLITUDE_PCT', '0.35') or '0.35').replace(',', '.'))
    except (TypeError, ValueError):
        amp_max = 0.35
    amplitude_pct = calculate_range_amplitude_pct(df, amp_periods)
    amplitude_lateral = amplitude_pct < amp_max

    lateral_score = 0.0
    if amplitude_lateral:
        lateral_score += 50  # peso alto: acumulação = bloqueio
    if adx < 23:
        lateral_score += 35
    if adx < 15:
        lateral_score += 15
    if choppiness > 55:
        lateral_score += 30
    if choppiness > 62:
        lateral_score += 10
    if trend == 'NEUTRO':
        lateral_score += 20
    if distance_sma < 1.0:
        lateral_score += 10
    if not bb_expanding:
        lateral_score += 15
    if range_expansion < 0.8:
        lateral_score += 10

    lateral_score = min(100.0, lateral_score)
    # Travas absolutas: amplitude, ADX e ausência de expansão das Bandas.
    structure_blocked = bool(adx < 23 or not bb_expanding)
    is_lateral = (
        bool(amplitude_lateral)
        or structure_blocked
        or lateral_score >= 45
    )

    if is_lateral:
        regime = 'RANGE'
        if adx < 23:
            regime_label = f'LATERAL/SEM TENDÊNCIA — ADX(14) {adx:.2f} < 23 — sinais ignorados'
        elif not bb_expanding:
            regime_label = (
                f'LATERAL/SEM EXPANSÃO — BB Width {bb_width:.6f} <= '
                f'média(50) {bb_width_mean:.6f} — sinais ignorados'
            )
        elif amplitude_lateral:
            regime_label = (
                f'LATERAL/ACUMULAÇÃO — amplitude {amplitude_pct:.3f}% < {amp_max}% '
                f'(últimos {amp_periods} períodos) — sinais ignorados'
            )
        else:
            regime_label = 'LATERAL — grandes players em consolidação, sem direção clara'
    elif trend == 'ALTA' and adx >= 23:
        regime = 'TREND_UP'
        regime_label = 'TENDÊNCIA DE ALTA — fluxo institucional comprador'
    elif trend == 'BAIXA' and adx >= 23:
        regime = 'TREND_DOWN'
        regime_label = 'TENDÊNCIA DE BAIXA — fluxo institucional vendedor'
    else:
        regime = 'TREND'
        regime_label = 'TENDÊNCIA EM FORMAÇÃO'

    return {
        'market_regime': regime,
        'regime_label': regime_label,
        'is_lateral': is_lateral,
        'lateral_score': round(lateral_score, 2),
        'adx': round(adx, 2),
        'adx_period': 14,
        'adx_gate_pass': bool(adx >= 23),
        'choppiness': round(choppiness, 2),
        'bollinger_bandwidth': round(bb_width, 8),
        'bollinger_bandwidth_mean_50': round(bb_width_mean, 8),
        'bollinger_expanding': bool(bb_expanding),
        'structure_filters_pass': bool(adx >= 23 and bb_expanding),
        'amplitude_pct': round(amplitude_pct, 4),
        'amplitude_lateral': bool(amplitude_lateral),
        'allow_entry': not is_lateral,
    }
