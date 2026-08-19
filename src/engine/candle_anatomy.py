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
CLOSE_ZONE_FRAC = float(os.getenv('CANDLE_CLOSE_ZONE_FRAC', '0.45'))
# Lookback para média de spread no falling-knife
SPREAD_MA_PERIOD = max(5, int(os.getenv('FALLING_KNIFE_SPREAD_MA', '20')))
# Porta 5 — dúvida: corpo baixo + sombras altas + amplitude fraca vs ATR
DOUBT_BODY_MAX = float(os.getenv('CANDLE_DOUBT_BODY_MAX', '0.35'))
DOUBT_WICK_MIN = float(os.getenv('CANDLE_DOUBT_WICK_MIN', '0.55'))
DOUBT_ATR_FRAC = float(os.getenv('CANDLE_DOUBT_ATR_FRAC', '0.70'))
PONTO_CONTINUO_EMA_PCT = float(os.getenv('PONTO_CONTINUO_EMA_PCT', '0.45'))


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
    atr: float = 0.0,
    fib_depth: float = 0.0,
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
        'body_conviction': 0.0,
        'amplitude_dominance': 0.0,
        'is_doubt_candle': False,
        'anatomy_log': '',
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

    body = abs(c - o)
    body_frac = body / spread if spread > 0 else 0.0
    wick_frac = max(0.0, 1.0 - body_frac)
    atr_v = _f(atr)
    if atr_v <= 0 and df is not None and 'atr_20' in getattr(df, 'columns', []):
        atr_v = _f(df['atr_20'].iloc[-1])
    if atr_v <= 0 and df is not None and 'atr' in getattr(df, 'columns', []):
        atr_v = _f(df['atr'].iloc[-1])
    dominance = (spread / atr_v) if atr_v > 0 else 1.0
    out['body_conviction'] = round(body_frac, 4)
    out['amplitude_dominance'] = round(dominance, 4)

    # Correção profunda no Fibonacci exige vela mais larga (menos ambiguidade)
    min_dom = DOUBT_ATR_FRAC
    depth = _f(fib_depth)
    if depth >= 0.75:
        min_dom = max(min_dom, 1.00)
    elif depth >= 0.50:
        min_dom = max(min_dom, 0.80)

    is_doubt = body_frac < DOUBT_BODY_MAX and wick_frac >= DOUBT_WICK_MIN and dominance < min_dom
    out['is_doubt_candle'] = bool(is_doubt)
    out['anatomy_log'] = (
        f'corpo={body_frac * 100:.0f}% sombras={wick_frac * 100:.0f}% '
        f'amp={dominance:.2f}×ATR fib_depth={depth:.2f}'
    )
    if is_doubt:
        out['abort_reason'] = (
            f'DÚVIDA: {out["anatomy_log"]} — bloqueia entrada mesmo com setup técnico'
        )
        out['checks']['doubt'] = False
        return out
    out['checks']['doubt'] = True

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
    atr_v = 0.0
    if 'atr_20' in df.columns:
        atr_v = _f(last['atr_20'])
    elif 'atr' in df.columns:
        atr_v = _f(last['atr'])
    fib_depth = 0.0
    if 'exp_high' in df.columns and 'exp_low' in df.columns:
        eh = _f(last['exp_high'])
        el = _f(last['exp_low'])
        rng = max(eh - el, 0.0)
        close = _f(last['close'])
        if rng > 0:
            fib_depth = max(0.0, min(1.0, (eh - close) / rng))
    return evaluate_candle_anatomy(
        sinal_institucional=sinal_institucional,
        open_p=_f(last.get('open') if hasattr(last, 'get') else last['open']),
        high=_f(last.get('high') if hasattr(last, 'get') else last['high']),
        low=_f(last.get('low') if hasattr(last, 'get') else last['low']),
        close=_f(last.get('close') if hasattr(last, 'get') else last['close']),
        df=df,
        atr=atr_v,
        fib_depth=fib_depth,
    )


def evaluate_ponto_continuo(df, trend: str | None = None) -> dict[str, Any]:
    """
    Ponto Contínuo: preço na EMA 21 inclinada + vela de força a favor da tendência.
    Confirmação de entrada (não substitui as Portas 1–5).
    """
    out = {
        'ponto_continuo': False,
        'ema21_slope': 0.0,
        'ponto_continuo_reason': '',
    }
    if df is None or len(df) < 8 or 'close' not in getattr(df, 'columns', []):
        out['ponto_continuo_reason'] = 'histórico insuficiente para Ponto Contínuo'
        return out

    close = df['close'].astype(float)
    ema21 = close.ewm(span=21, adjust=False).mean() if 'ema_21' not in df.columns else df['ema_21'].astype(float)
    last_c = _f(close.iloc[-1])
    last_e = _f(ema21.iloc[-1])
    prev_e = _f(ema21.iloc[-4] if len(ema21) >= 4 else ema21.iloc[0])
    slope = last_e - prev_e
    out['ema21_slope'] = round(slope, 8)
    dist_pct = abs(last_c - last_e) / last_e * 100.0 if last_e else 999.0
    last = df.iloc[-1]
    o = _f(last['open'])
    h = _f(last['high'])
    l = _f(last['low'])
    c = _f(last['close'])
    spread = max(h - l, 1e-12)
    body_frac = abs(c - o) / spread
    close_pos = (c - l) / spread
    trend_u = str(trend or '').upper()
    near = dist_pct <= PONTO_CONTINUO_EMA_PCT
    force_up = c > o and body_frac >= 0.55 and close_pos >= 0.60 and slope > 0
    force_dn = c < o and body_frac >= 0.55 and close_pos <= 0.40 and slope < 0

    if trend_u == 'ALTA' and near and force_up:
        out['ponto_continuo'] = True
        out['ponto_continuo_reason'] = (
            f'Ponto Contínuo LONG: EMA21 inclinada↑ dist={dist_pct:.2f}% corpo={body_frac*100:.0f}%'
        )
    elif trend_u == 'BAIXA' and near and force_dn:
        out['ponto_continuo'] = True
        out['ponto_continuo_reason'] = (
            f'Ponto Contínuo SHORT: EMA21 inclinada↓ dist={dist_pct:.2f}% corpo={body_frac*100:.0f}%'
        )
    else:
        out['ponto_continuo_reason'] = (
            f'sem Ponto Contínuo (dist EMA21={dist_pct:.2f}% slope={slope:.6g} corpo={body_frac*100:.0f}%)'
        )
    return out
