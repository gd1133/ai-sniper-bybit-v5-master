# -*- coding: utf-8 -*-
"""
Filtro de direção e anatomia da vela (anti-compra em queda).

Regras absolutas:
  1) COMPRA_INSTITUCIONAL → vela VERDE (Close > Open)
     VENDA_INSTITUCIONAL  → vela VERMELHA (Close < Open)
  2) Pressão de sombra (fechamento nos 35% extremos da amplitude):
     COMPRA: Close >= High - (Spread * 0.35)
     VENDA:  Close <= Low  + (Spread * 0.35)
  3) Anti-faca caindo: se as 2 velas anteriores forem vermelhas com
     spread acima da média → bloqueia COMPRA imediata.
"""

from __future__ import annotations

import os
from typing import Any

INSTITUTIONAL_BUY = 'COMPRA_INSTITUCIONAL'
INSTITUTIONAL_SELL = 'VENDA_INSTITUCIONAL'
NEUTRO = 'NEUTRO'

# Fração da amplitude onde o close deve estar (35% superiores / inferiores)
CLOSE_ZONE_FRAC = float(os.getenv('CANDLE_CLOSE_ZONE_FRAC', '0.35'))
# Lookback para média de spread no falling-knife
SPREAD_MA_PERIOD = max(5, int(os.getenv('FALLING_KNIFE_SPREAD_MA', '20')))


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _normalize_signal(sinal: str | None) -> str:
    return str(sinal or NEUTRO).strip().upper()


def candle_color(open_p: float, close: float) -> str:
    """GREEN | RED | DOJI."""
    if close > open_p:
        return 'GREEN'
    if close < open_p:
        return 'RED'
    return 'DOJI'


def close_in_buy_zone(open_p: float, high: float, low: float, close: float, zone: float = CLOSE_ZONE_FRAC) -> bool:
    """Close nos 35% superiores da amplitude: Close >= High - (Spread * zone)."""
    spread = high - low
    if spread <= 0:
        return False
    return close >= (high - (spread * zone))


def close_in_sell_zone(open_p: float, high: float, low: float, close: float, zone: float = CLOSE_ZONE_FRAC) -> bool:
    """Close nos 35% inferiores da amplitude: Close <= Low + (Spread * zone)."""
    spread = high - low
    if spread <= 0:
        return False
    return close <= (low + (spread * zone))


def detect_falling_knife(
    opens,
    highs,
    lows,
    closes,
    *,
    ma_period: int = SPREAD_MA_PERIOD,
) -> dict[str, Any]:
    """
    Últimas 2 velas *anteriores* (índices -3 e -2) vermelhas com spread > MA.

    Arrays devem incluir a vela atual como último elemento.
    """
    result = {
        'falling_knife': False,
        'prior_red_count': 0,
        'prior_wide_spread_count': 0,
        'spread_ma': 0.0,
        'reason': '',
    }
    n = len(closes) if closes is not None else 0
    if n < 3:
        result['reason'] = 'histórico insuficiente para falling-knife'
        return result

    try:
        spreads = [max(_f(highs[i]) - _f(lows[i]), 0.0) for i in range(n)]
    except Exception:
        result['reason'] = 'OHLC inválido'
        return result

    lookback = min(ma_period, n)
    window = spreads[-lookback:]
    spread_ma = sum(window) / lookback if lookback else 0.0
    result['spread_ma'] = round(spread_ma, 8)
    if spread_ma <= 0:
        result['reason'] = 'spread médio inválido'
        return result

    # Duas velas anteriores à atual
    prior_idxs = (n - 3, n - 2)
    red_count = 0
    wide_count = 0
    for i in prior_idxs:
        o, c = _f(opens[i]), _f(closes[i])
        if c < o:
            red_count += 1
        if spreads[i] > spread_ma:
            wide_count += 1

    result['prior_red_count'] = red_count
    result['prior_wide_spread_count'] = wide_count

    if red_count >= 2 and wide_count >= 2:
        result['falling_knife'] = True
        result['reason'] = (
            f'2 velas anteriores vermelhas com spread > MA({lookback})={spread_ma:.6f} '
            f'(panic sell / faca caindo)'
        )
    else:
        result['reason'] = 'ok'
    return result


def evaluate_candle_anatomy(
    *,
    sinal_institucional: str,
    open_p: float,
    high: float,
    low: float,
    close: float,
    df=None,
    opens=None,
    highs=None,
    lows=None,
    closes=None,
) -> dict[str, Any]:
    """
    Avalia anatomia da vela atual vs sinal institucional.

    Fail-closed: qualquer falha → allowed=False e sinal efetivo NEUTRO.
    """
    sinal = _normalize_signal(sinal_institucional)
    o = _f(open_p)
    h = _f(high)
    l = _f(low)
    c = _f(close)
    spread = max(h - l, 0.0)
    color = candle_color(o, c)

    out: dict[str, Any] = {
        'allowed': False,
        'sinal_institucional': sinal,
        'candle_color': color,
        'candle_open': o,
        'candle_high': h,
        'candle_low': l,
        'candle_close': c,
        'candle_spread': spread,
        'close_zone_frac': CLOSE_ZONE_FRAC,
        'close_in_buy_zone': False,
        'close_in_sell_zone': False,
        'falling_knife': False,
        'abort_reason': '',
        'checks': {},
    }

    if sinal not in (INSTITUTIONAL_BUY, INSTITUTIONAL_SELL):
        out['abort_reason'] = f'sinal={sinal} (sem lado institucional)'
        return out

    if spread <= 0 or h < l:
        out['abort_reason'] = 'amplitude da vela inválida (High <= Low)'
        return out

    buy_zone = close_in_buy_zone(o, h, l, c)
    sell_zone = close_in_sell_zone(o, h, l, c)
    out['close_in_buy_zone'] = buy_zone
    out['close_in_sell_zone'] = sell_zone

    # --- Cor obrigatória ---
    if sinal == INSTITUTIONAL_BUY and color != 'GREEN':
        out['abort_reason'] = (
            f'PROIBIDO comprar em vela {color} (Close={c} <= Open={o}) — exige VERDE'
        )
        out['checks']['color'] = False
        return out
    if sinal == INSTITUTIONAL_SELL and color != 'RED':
        out['abort_reason'] = (
            f'PROIBIDO vender em vela {color} (Close={c} >= Open={o}) — exige VERMELHA'
        )
        out['checks']['color'] = False
        return out
    out['checks']['color'] = True

    # --- Pressão de sombra (35%) ---
    if sinal == INSTITUTIONAL_BUY and not buy_zone:
        threshold = h - (spread * CLOSE_ZONE_FRAC)
        out['abort_reason'] = (
            f'fechamento fora dos 35% superiores (Close={c:.8f} < {threshold:.8f})'
        )
        out['checks']['close_zone'] = False
        return out
    if sinal == INSTITUTIONAL_SELL and not sell_zone:
        threshold = l + (spread * CLOSE_ZONE_FRAC)
        out['abort_reason'] = (
            f'fechamento fora dos 35% inferiores (Close={c:.8f} > {threshold:.8f})'
        )
        out['checks']['close_zone'] = False
        return out
    out['checks']['close_zone'] = True

    # --- Falling knife (só bloqueia COMPRA) ---
    knife = {'falling_knife': False, 'reason': 'skipped'}
    try:
        if df is not None and hasattr(df, 'iloc') and len(df) >= 3:
            knife = detect_falling_knife(
                df['open'].tolist(),
                df['high'].tolist(),
                df['low'].tolist(),
                df['close'].tolist(),
            )
        elif opens is not None and closes is not None:
            knife = detect_falling_knife(opens, highs, lows, closes)
    except Exception as err:
        knife = {'falling_knife': True, 'reason': f'erro falling-knife (fail-closed): {err}'}

    out['falling_knife'] = bool(knife.get('falling_knife'))
    out['falling_knife_detail'] = knife
    if sinal == INSTITUTIONAL_BUY and out['falling_knife']:
        out['abort_reason'] = f"FALLING_KNIFE: {knife.get('reason')}"
        out['checks']['falling_knife'] = False
        return out
    out['checks']['falling_knife'] = True

    out['allowed'] = True
    out['abort_reason'] = ''
    return out


def analyze_from_dataframe(df, sinal_institucional: str) -> dict[str, Any]:
    """Atalho: avalia a última vela do DataFrame OHLC."""
    if df is None or len(df) < 1:
        return {
            'allowed': False,
            'sinal_institucional': _normalize_signal(sinal_institucional),
            'abort_reason': 'DataFrame OHLC vazio',
            'candle_color': 'DOJI',
            'falling_knife': False,
            'checks': {},
        }
    last = df.iloc[-1]
    return evaluate_candle_anatomy(
        sinal_institucional=sinal_institucional,
        open_p=_f(last.get('open') if hasattr(last, 'get') else last['open']),
        high=_f(last.get('high') if hasattr(last, 'get') else last['high']),
        low=_f(last.get('low') if hasattr(last, 'get') else last['low']),
        close=_f(last.get('close') if hasattr(last, 'get') else last['close']),
        df=df,
    )
