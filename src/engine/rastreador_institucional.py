# -*- coding: utf-8 -*-
"""
Rastreador de Pegadas Institucionais (Smart Money / Big Players)

Detecta entradas institucionais via:
  1. VWAP diário (linha de equilíbrio)
  2. Anomalia de volume (média 20 + 2.5× desvio padrão)
  3. Spread expressivo do candle (evita falsos rompimentos)

Integração incremental: não substitui SMA, SuperTrend, Fibonacci, Volume ou S/R.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


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


class RastreadorInstitucional:
    """
    Rastreador de Pegadas de Big Players (Smart Money).

    :param periodo_ma: Janela para médias de volume/spread (padrão: 20 candles).
    :param multiplicador_vol: Desvios padrão de volume para detectar big player.
    :param multiplicador_spread: Multiplicador do spread vs média recente.
    """

    def __init__(self, periodo_ma=20, multiplicador_vol=2.5, multiplicador_spread=1.5):
        self.periodo_ma = int(periodo_ma)
        self.multiplicador_vol = float(multiplicador_vol)
        self.multiplicador_spread = float(multiplicador_spread)

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
        Processa o histórico e marca cada candle com Sinal_Institucional.
        Retorna DataFrame enriquecido (compatível com análise offline/backtest).
        """
        df = _normalize_ohlcv(df)
        df = self.calcular_vwap(df)

        df['vol_ma'] = df['vol'].rolling(window=self.periodo_ma, min_periods=self.periodo_ma).mean()
        df['vol_std'] = df['vol'].rolling(window=self.periodo_ma, min_periods=self.periodo_ma).std()
        df['spread'] = df['high'] - df['low']
        df['spread_ma'] = df['spread'].rolling(window=self.periodo_ma, min_periods=self.periodo_ma).mean()

        vol_threshold = df['vol_ma'] + (self.multiplicador_vol * df['vol_std'].fillna(0))
        df['big_player_ativo'] = df['vol'] > vol_threshold

        df['sinal_institucional'] = 'NEUTRO'

        for i in range(self.periodo_ma, len(df)):
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

            if close > open_p and close > vwap and spread > (spread_ma * self.multiplicador_spread):
                df.iloc[i, df.columns.get_loc('sinal_institucional')] = 'COMPRA_INSTITUCIONAL'
            elif close < open_p and close < vwap and spread > (spread_ma * self.multiplicador_spread):
                df.iloc[i, df.columns.get_loc('sinal_institucional')] = 'VENDA_INSTITUCIONAL'

        return df

    def get_latest_signal(self, df: pd.DataFrame) -> dict:
        """
        Analisa o último candle e retorna dict pronto para merge em get_signals().
        Leve e rápido — uso no loop do radar em tempo real.
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
        }
        if df is None or len(df) < self.periodo_ma + 1:
            return neutral

        try:
            work = self.analisar_mercado(df)
            last = work.iloc[-1]
            sig = str(last.get('sinal_institucional', 'NEUTRO') or 'NEUTRO').upper()
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
            }
        except Exception:
            return neutral
