"""
Leitura estrutural de gráfico — pivôs, velas fortes e tendência de preço.

Camada INCREMENTAL: não substitui SMC/Fibonacci/SuperTrend existentes.
Usada para entradas assertivas quando o repique clássico ainda não disparou,
sem operar contra tendência nem contra fluxo de baleias oposto.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


PIVOT_LEFT = 2
PIVOT_RIGHT = 2
STRONG_BODY_PCT = 55.0
STRONG_RANGE_ATR = 1.0
NEAR_PIVOT_ATR = 0.85


def _atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    if 'atr' in df.columns:
        return df['atr']
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


def find_pivot_highs(df: pd.DataFrame, left: int = PIVOT_LEFT, right: int = PIVOT_RIGHT) -> list[dict]:
    """Pivôs de topo (fractal): high maior que vizinhos left/right."""
    pivots = []
    n = len(df)
    if n < left + right + 1:
        return pivots
    highs = df['high'].values
    for i in range(left, n - right):
        if all(highs[i] >= highs[i - j] for j in range(1, left + 1)) and all(
            highs[i] > highs[i + j] for j in range(1, right + 1)
        ):
            pivots.append({'index': i, 'price': float(highs[i]), 'kind': 'high'})
    return pivots


def find_pivot_lows(df: pd.DataFrame, left: int = PIVOT_LEFT, right: int = PIVOT_RIGHT) -> list[dict]:
    """Pivôs de fundo (fractal): low menor que vizinhos left/right."""
    pivots = []
    n = len(df)
    if n < left + right + 1:
        return pivots
    lows = df['low'].values
    for i in range(left, n - right):
        if all(lows[i] <= lows[i - j] for j in range(1, left + 1)) and all(
            lows[i] < lows[i + j] for j in range(1, right + 1)
        ):
            pivots.append({'index': i, 'price': float(lows[i]), 'kind': 'low'})
    return pivots


def detect_strong_bullish_candle(row, atr: float = 0.0, volume_ratio: float = 1.0) -> bool:
    """Vela forte de SUBIDA: corpo grande, fecha no terço superior, range expandido."""
    o, h, l, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
    if c <= o:
        return False
    rng = max(h - l, 1e-9)
    body = c - o
    body_pct = body / rng * 100.0
    close_pos = (c - l) / rng
    range_ok = atr <= 0 or rng >= (atr * STRONG_RANGE_ATR * 0.85)
    vol_ok = volume_ratio >= 1.1
    return body_pct >= STRONG_BODY_PCT and close_pos >= 0.65 and range_ok and vol_ok


def detect_strong_bearish_candle(row, atr: float = 0.0, volume_ratio: float = 1.0) -> bool:
    """Vela forte de DESCIDA: corpo grande, fecha no terço inferior, range expandido."""
    o, h, l, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
    if c >= o:
        return False
    rng = max(h - l, 1e-9)
    body = o - c
    body_pct = body / rng * 100.0
    close_pos = (c - l) / rng
    range_ok = atr <= 0 or rng >= (atr * STRONG_RANGE_ATR * 0.85)
    vol_ok = volume_ratio >= 1.1
    return body_pct >= STRONG_BODY_PCT and close_pos <= 0.35 and range_ok and vol_ok


def _structure_bias(pivot_highs: list[dict], pivot_lows: list[dict]) -> str:
    """HH/HL = ALTA | LH/LL = BAIXA | senão NEUTRO."""
    if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
        hh = pivot_highs[-1]['price'] > pivot_highs[-2]['price']
        hl = pivot_lows[-1]['price'] > pivot_lows[-2]['price']
        lh = pivot_highs[-1]['price'] < pivot_highs[-2]['price']
        ll = pivot_lows[-1]['price'] < pivot_lows[-2]['price']
        if hh and hl:
            return 'ALTA'
        if lh and ll:
            return 'BAIXA'
    return 'NEUTRO'


def analyze_chart_structure(df: pd.DataFrame, signals: dict | None = None) -> dict[str, Any]:
    """
    Consolida pivôs, velas fortes e proximidade de suporte/resistência.
    """
    signals = signals or {}
    empty = {
        'pivot_high': 0.0,
        'pivot_low': 0.0,
        'near_pivot_support': False,
        'near_pivot_resistance': False,
        'bounce_from_pivot_low': False,
        'rejection_from_pivot_high': False,
        'strong_bullish_candle': False,
        'strong_bearish_candle': False,
        'structure_bias': 'NEUTRO',
        'chart_entry_score': 0.0,
        'chart_reasons': [],
    }
    if df is None or len(df) < 30:
        return empty

    atr_s = _atr_series(df)
    atr = float(atr_s.iloc[-1] or 0)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last['close'])
    vol_ratio = float(signals.get('volume_ratio') or last.get('volume_ratio') or 1.0)

    # Pivôs confirmados (precisa de `right` barras à direita → ignora as últimas RIGHT)
    confirmed = df.iloc[: max(0, len(df) - PIVOT_RIGHT)] if len(df) > PIVOT_RIGHT else df
    highs = find_pivot_highs(confirmed)
    lows = find_pivot_lows(confirmed)
    last_high = highs[-1]['price'] if highs else float(df['high'].iloc[-20:].max())
    last_low = lows[-1]['price'] if lows else float(df['low'].iloc[-20:].min())

    near_support = atr > 0 and abs(price - last_low) <= atr * NEAR_PIVOT_ATR
    near_resist = atr > 0 and abs(price - last_high) <= atr * NEAR_PIVOT_ATR

    # Bounce: toque no pivô baixo + vela de alta forte (atual ou anterior)
    touched_low = float(last['low']) <= last_low + (atr * 0.35) or float(prev['low']) <= last_low + (atr * 0.35)
    touched_high = float(last['high']) >= last_high - (atr * 0.35) or float(prev['high']) >= last_high - (atr * 0.35)

    strong_up = detect_strong_bullish_candle(last, atr, vol_ratio) or detect_strong_bullish_candle(prev, atr, vol_ratio)
    strong_down = detect_strong_bearish_candle(last, atr, vol_ratio) or detect_strong_bearish_candle(prev, atr, vol_ratio)

    bounce_low = bool(touched_low and strong_up)
    reject_high = bool(touched_high and strong_down)
    structure = _structure_bias(highs, lows)

    reasons = []
    score = 0.0
    if near_support:
        score += 18
        reasons.append(f'Perto do pivô de suporte ({last_low:.4f})')
    if near_resist:
        score += 18
        reasons.append(f'Perto do pivô de resistência ({last_high:.4f})')
    if bounce_low:
        score += 28
        reasons.append('Bounce no pivô baixo + vela forte de SUBIDA')
    if reject_high:
        score += 28
        reasons.append('Rejeição no pivô alto + vela forte de DESCIDA')
    if strong_up:
        score += 20
        reasons.append('Vela forte de SUBIDA detectada')
    if strong_down:
        score += 20
        reasons.append('Vela forte de DESCIDA detectada')
    if structure == 'ALTA':
        score += 12
        reasons.append('Estrutura HH/HL (tendência de alta)')
    elif structure == 'BAIXA':
        score += 12
        reasons.append('Estrutura LH/LL (tendência de baixa)')

    # MACD histograma simples (já calculado no df se existir)
    if 'macd_hist' in df.columns:
        hist = float(df['macd_hist'].iloc[-1] or 0)
        hist_prev = float(df['macd_hist'].iloc[-2] or 0)
        if hist > 0 and hist > hist_prev:
            score += 8
            reasons.append('MACD histograma acelerando alta')
        elif hist < 0 and hist < hist_prev:
            score += 8
            reasons.append('MACD histograma acelerando baixa')

    return {
        'pivot_high': float(last_high),
        'pivot_low': float(last_low),
        'near_pivot_support': bool(near_support),
        'near_pivot_resistance': bool(near_resist),
        'bounce_from_pivot_low': bool(bounce_low),
        'rejection_from_pivot_high': bool(reject_high),
        'strong_bullish_candle': bool(strong_up),
        'strong_bearish_candle': bool(strong_down),
        'structure_bias': structure,
        'chart_entry_score': round(min(100.0, score), 2),
        'chart_reasons': reasons,
    }


def assertive_structure_entry(
    side: str,
    df: pd.DataFrame,
    signals: dict | None = None,
) -> tuple[bool, list[str]]:
    """
    Caminho ASSERTIVO de entrada (complementar ao repique clássico).

    Exige:
      - tendência + SuperTrend alinhados (já validados pelo caller)
      - vela forte na direção
      - pivô (bounce/rejeição) OU estrutura HH/HL / LH/LL
      - fluxo de baleias NÃO oposto (WAIT ou alinhado OK)
    """
    signals = signals or {}
    side_norm = str(side or '').strip().lower()
    chart = analyze_chart_structure(df, signals)
    money_flow = str(signals.get('money_flow_side', 'WAIT')).upper()
    whale_aligned = bool(signals.get('whale_aligned', False))
    reasons = list(chart.get('chart_reasons') or [])

    # Nunca entrar contra baleias
    if side_norm in ('buy', 'long', 'comprar') and money_flow == 'SELL':
        return False, ['Assertivo: baleias em VENDA — não compra']
    if side_norm in ('sell', 'short', 'vender') and money_flow == 'BUY':
        return False, ['Assertivo: baleias em COMPRA — não vende']

    if side_norm in ('buy', 'long', 'comprar'):
        if not chart.get('strong_bullish_candle'):
            return False, ['Assertivo: falta vela forte de SUBIDA']
        # Não compra se a última estrutura também marca vela forte de descida dominante
        if chart.get('strong_bearish_candle') and not chart.get('bounce_from_pivot_low'):
            return False, ['Assertivo: vela forte de DESCIDA conflita com COMPRA']
        structure_ok = (
            chart.get('bounce_from_pivot_low')
            or chart.get('near_pivot_support')
            or chart.get('structure_bias') == 'ALTA'
        )
        if not structure_ok:
            return False, ['Assertivo: sem pivô/estrutura de alta']
        if whale_aligned or money_flow in ('BUY', 'WAIT'):
            reasons.append('Entrada ASSERTIVA long: pivô + vela forte (baleias ok)')
            return True, reasons
        return False, ['Assertivo: fluxo incompatível com COMPRA']

    if side_norm in ('sell', 'short', 'vender'):
        if not chart.get('strong_bearish_candle'):
            return False, ['Assertivo: falta vela forte de DESCIDA']
        # Bloqueia short se há vela forte de SUBIDA (caso BLUR nos logs)
        if chart.get('strong_bullish_candle'):
            return False, ['Assertivo: vela forte de SUBIDA conflita com VENDA — aguardar']
        structure_ok = (
            chart.get('rejection_from_pivot_high')
            or chart.get('near_pivot_resistance')
            or chart.get('structure_bias') == 'BAIXA'
        )
        if not structure_ok:
            return False, ['Assertivo: sem pivô/estrutura de baixa']
        if whale_aligned or money_flow in ('SELL', 'WAIT'):
            reasons.append('Entrada ASSERTIVA short: pivô + vela forte (baleias ok)')
            return True, reasons
        return False, ['Assertivo: fluxo incompatível com VENDA']

    return False, [f'Side inválido: {side}']
