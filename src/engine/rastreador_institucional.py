# -*- coding: utf-8 -*-
"""
Rastreador de Pegadas Institucionais (Smart Money / Big Players)

Detecta entradas institucionais via:
  1. Amplitude percentual (anti-acumulação / mercado lateral)
  2. VWAP diário (linha de equilíbrio)
  3. Anomalia de volume (média 20 + 2.5× desvio padrão)
  4. Spread expressivo do candle (evita falsos rompimentos)

Em acumulação (amplitude < limite), força Sinal = NEUTRO e ignora qualquer entrada.
"""

from __future__ import annotations

import os

import pandas as pd
import numpy as np


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == '':
        return default
    try:
        return float(str(raw).replace(',', '.'))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == '':
        return default
    try:
        return int(float(str(raw).replace(',', '.')))
    except (TypeError, ValueError):
        return default


# Amplitude dos últimos X candles: ((High.max - Low.min) / Low.min) * 100
DEFAULT_AMPLITUDE_PERIODS = 20
DEFAULT_AMPLITUDE_PCT_MAX = 0.35  # abaixo disso = acumulação / lateral


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Aceita colunas do robô (open/high/low/close/vol) ou formato clássico (Open/High/...)."""
    out = df.copy()
    mapping = {
        'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'vol',
        'volume': 'vol',
    }
    out = out.rename(columns={k: v for k, v in mapping.items() if k in out.columns})
    for col in ('open', 'high', 'low', 'close', 'vol'):
        if col not in out.columns:
            raise ValueError(f"DataFrame OHLCV incompleto: coluna '{col}' ausente")
    return out


def calculate_range_amplitude_pct(df: pd.DataFrame, periods: int = DEFAULT_AMPLITUDE_PERIODS) -> float:
    """
    Amplitude percentual dos últimos X períodos:
      ((High.max() - Low.min()) / Low.min()) * 100
    """
    if df is None or len(df) < 2:
        return 0.0
    n = max(2, int(periods or DEFAULT_AMPLITUDE_PERIODS))
    work = _normalize_ohlcv(df)
    window = work.iloc[-n:]
    low_min = float(window['low'].min())
    high_max = float(window['high'].max())
    if low_min <= 0:
        return 0.0
    return float(((high_max - low_min) / low_min) * 100.0)


def is_accumulation_range(
    df: pd.DataFrame,
    periods: int | None = None,
    max_amplitude_pct: float | None = None,
) -> tuple[bool, float]:
    """
    True se o mercado está em acumulação (variação abaixo do limite).
    Retorna (is_lateral_amplitude, amplitude_pct).
    """
    periods = periods if periods is not None else _env_int('LATERAL_AMPLITUDE_PERIODS', DEFAULT_AMPLITUDE_PERIODS)
    max_amp = (
        max_amplitude_pct
        if max_amplitude_pct is not None
        else _env_float('LATERAL_AMPLITUDE_PCT', DEFAULT_AMPLITUDE_PCT_MAX)
    )
    amp = calculate_range_amplitude_pct(df, periods)
    return bool(amp < float(max_amp)), float(amp)


class RastreadorInstitucional:
    """
    Rastreador de Pegadas de Big Players (Smart Money).

    :param periodo_ma: Janela para médias de volume/spread (padrão: 20 candles).
    :param multiplicador_vol: Desvios padrão de volume para detectar big player.
    :param multiplicador_spread: Multiplicador do tamanho do candle vs média recente.
    :param amplitude_periods: Janela da amplitude anti-lateral.
    :param amplitude_pct_max: Limite % — abaixo = força NEUTRO.
    """

    def __init__(
        self,
        periodo_ma=20,
        multiplicador_vol=2.5,
        multiplicador_spread=1.5,
        amplitude_periods=None,
        amplitude_pct_max=None,
    ):
        self.periodo_ma = int(periodo_ma)
        self.multiplicador_vol = float(multiplicador_vol)
        self.multiplicador_spread = float(multiplicador_spread)
        self.amplitude_periods = int(
            amplitude_periods
            if amplitude_periods is not None
            else _env_int('LATERAL_AMPLITUDE_PERIODS', DEFAULT_AMPLITUDE_PERIODS)
        )
        self.amplitude_pct_max = float(
            amplitude_pct_max
            if amplitude_pct_max is not None
            else _env_float('LATERAL_AMPLITUDE_PCT', DEFAULT_AMPLITUDE_PCT_MAX)
        )

    def calcular_vwap(self, df: pd.DataFrame) -> pd.DataFrame:
        """VWAP acumulado do dia (reinicia a cada nova data)."""
        df = df.copy()
        tp = (df['high'] + df['low'] + df['close']) / 3.0
        tp_v = tp * df['vol']

        if 'ts' in df.columns and len(df) > 0:
            ts = pd.to_datetime(df['ts'], unit='ms', errors='coerce')
            if ts.isna().all():
                ts = pd.to_datetime(df['ts'], errors='coerce')
            day_key = ts.dt.date
            cum_tp_v = tp_v.groupby(day_key).cumsum()
            cum_vol = df['vol'].groupby(day_key).cumsum()
        else:
            cum_tp_v = tp_v.cumsum()
            cum_vol = df['vol'].cumsum()

        df['vwap'] = cum_tp_v / (cum_vol + 1e-9)
        return df

    def analisar_mercado(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Processa o histórico e marca cada candle com sinal institucional.
        Em acumulação (amplitude baixa), força NEUTRO em todo o DataFrame.
        """
        df = _normalize_ohlcv(df)
        df = self.calcular_vwap(df)

        df['vol_ma'] = df['vol'].rolling(window=self.periodo_ma, min_periods=self.periodo_ma).mean()
        df['vol_std'] = df['vol'].rolling(window=self.periodo_ma, min_periods=self.periodo_ma).std()
        df['spread'] = df['high'] - df['low']
        df['spread_ma'] = df['spread'].rolling(window=self.periodo_ma, min_periods=self.periodo_ma).mean()

        # Amplitude rolling (anti-lateral por candle)
        roll_high = df['high'].rolling(window=self.amplitude_periods, min_periods=2).max()
        roll_low = df['low'].rolling(window=self.amplitude_periods, min_periods=2).min()
        df['amplitude_pct'] = ((roll_high - roll_low) / (roll_low + 1e-9)) * 100.0
        df['is_accumulation'] = df['amplitude_pct'] < self.amplitude_pct_max

        vol_threshold = df['vol_ma'] + (self.multiplicador_vol * df['vol_std'].fillna(0))
        df['big_player_ativo'] = df['vol'] > vol_threshold

        df['sinal_institucional'] = 'NEUTRO'

        # Snapshot global: se a janela atual está em acumulação, não dispara nenhum sinal
        is_acc_now, amp_now = is_accumulation_range(
            df, self.amplitude_periods, self.amplitude_pct_max,
        )
        if is_acc_now:
            df['amplitude_pct_atual'] = amp_now
            return df

        for i in range(self.periodo_ma, len(df)):
            # Por candle: ignora acumulação local
            if bool(df.iloc[i].get('is_accumulation', False)):
                continue
            if not bool(df.iloc[i]['big_player_ativo']):
                continue

            row = df.iloc[i]
            close = float(row['close'])
            open_p = float(row['open'])
            vwap = float(row['vwap'])
            spread = float(row['spread'])
            spread_ma = float(row['spread_ma']) if pd.notna(row['spread_ma']) else 0.0

            if spread_ma <= 0:
                continue
            # Spread real expressivo (evita falso rompimento)
            if spread <= (spread_ma * self.multiplicador_spread):
                continue

            # Sinal institucional: volume anômalo + VWAP + spread
            if close > open_p and close > vwap:
                df.iloc[i, df.columns.get_loc('sinal_institucional')] = 'COMPRA_INSTITUCIONAL'
            elif close < open_p and close < vwap:
                df.iloc[i, df.columns.get_loc('sinal_institucional')] = 'VENDA_INSTITUCIONAL'

        df['amplitude_pct_atual'] = amp_now
        return df

    def get_latest_signal(self, df: pd.DataFrame) -> dict:
        """
        Analisa o último candle e retorna dict pronto para merge em get_signals().
        Em acumulação → força NEUTRO (ignora qualquer sinal).
        """
        neutral = {
            'sinal_institucional': 'NEUTRO',
            'vwap': 0.0,
            'big_player_ativo': False,
            'institutional_spread': 0.0,
            'institutional_spread_ma': 0.0,
            'institutional_signal_low': 0.0,
            'institutional_signal_high': 0.0,
            'institutional_sl_price': 0.0,
            'amplitude_pct': 0.0,
            'is_accumulation': False,
            'is_lateral_amplitude': False,
        }
        if df is None or len(df) < self.periodo_ma + 1:
            return neutral

        try:
            is_acc, amp = is_accumulation_range(
                df, self.amplitude_periods, self.amplitude_pct_max,
            )
            if is_acc:
                return {
                    **neutral,
                    'amplitude_pct': round(amp, 4),
                    'is_accumulation': True,
                    'is_lateral_amplitude': True,
                    'sinal_institucional': 'NEUTRO',
                }

            work = self.analisar_mercado(df)
            last = work.iloc[-1]
            sig = str(last.get('sinal_institucional', 'NEUTRO') or 'NEUTRO').upper()
            # Dupla checagem: só dispara com big player + VWAP + spread (já no loop)
            if sig != 'NEUTRO' and not bool(last.get('big_player_ativo', False)):
                sig = 'NEUTRO'

            low = float(last['low'])
            high = float(last['high'])
            sl = low if sig == 'COMPRA_INSTITUCIONAL' else (high if sig == 'VENDA_INSTITUCIONAL' else 0.0)

            return {
                'sinal_institucional': sig,
                'vwap': round(float(last.get('vwap', 0) or 0), 8),
                'big_player_ativo': bool(last.get('big_player_ativo', False)),
                'institutional_spread': round(float(last.get('spread', 0) or 0), 8),
                'institutional_spread_ma': round(float(last.get('spread_ma', 0) or 0), 8),
                'institutional_signal_low': low,
                'institutional_signal_high': high,
                'institutional_sl_price': sl,
                'amplitude_pct': round(float(amp), 4),
                'is_accumulation': False,
                'is_lateral_amplitude': False,
            }
        except Exception:
            return neutral
