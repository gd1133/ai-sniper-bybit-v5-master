# -*- coding: utf-8 -*-
"""
Liquidez SMC — BSL / SSL, Liquidity Sweep (Grab) e Fair Value Gaps.

Smart Money caça stops acima de topos óbvios (triplos) e abaixo de fundos.
O robô NÃO deve ser essa liquidez: breakout com pavio longo + retorno = inválido.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


EQUAL_LEVEL_PCT = 0.15  # topos/fundos "iguais" (óbvios)
SWEEP_WICK_FRAC = 0.45  # pavio ≥ 45% da amplitude
FVG_LOOKBACK = 24


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _swing_indices(series: pd.Series, left: int = 2, right: int = 2, mode: str = 'high') -> list[int]:
    vals = series.astype(float).tolist()
    n = len(vals)
    out = []
    for i in range(left, n - right):
        window = vals[i - left: i + right + 1]
        pivot = vals[i]
        if mode == 'high' and pivot >= max(window) - 1e-12:
            out.append(i)
        elif mode == 'low' and pivot <= min(window) + 1e-12:
            out.append(i)
    return out


def identify_liquidity_zones(df: pd.DataFrame, lookback: int = 40) -> dict[str, Any]:
    """
    BSL = liquidez de compra acima de swing highs (stops de short / breakout buyers).
    SSL = liquidez de venda abaixo de swing lows (stops de long).
    """
    empty = {
        'bsl': 0.0,
        'ssl': 0.0,
        'equal_highs': False,
        'equal_lows': False,
        'triple_top': False,
        'triple_bottom': False,
        'swing_highs': [],
        'swing_lows': [],
        'reason': '',
    }
    if df is None or len(df) < 10:
        empty['reason'] = 'histórico insuficiente para zonas de liquidez'
        return empty

    work = df.tail(max(int(lookback), 12)).reset_index(drop=True)
    hi_idx = _swing_indices(work['high'], mode='high')
    lo_idx = _swing_indices(work['low'], mode='low')
    highs = [_f(work['high'].iloc[i]) for i in hi_idx[-6:]]
    lows = [_f(work['low'].iloc[i]) for i in lo_idx[-6:]]
    bsl = max(highs) if highs else _f(work['high'].max())
    ssl = min(lows) if lows else _f(work['low'].min())

    def _cluster(levels: list[float], pct: float) -> int:
        if len(levels) < 2:
            return 1
        last = levels[-1]
        if last <= 0:
            return 1
        return sum(1 for x in levels if abs(x - last) / last * 100.0 <= pct)

    eq_h = _cluster(highs, EQUAL_LEVEL_PCT) >= 2
    eq_l = _cluster(lows, EQUAL_LEVEL_PCT) >= 2
    triple_top = _cluster(highs, EQUAL_LEVEL_PCT) >= 3
    triple_bot = _cluster(lows, EQUAL_LEVEL_PCT) >= 3

    reason = f'BSL={bsl:.6g} SSL={ssl:.6g}'
    if triple_top:
        reason += ' | TOPO TRIPLO (caça de stops acima)'
    elif eq_h:
        reason += ' | equal highs (BSL óbvia)'
    if triple_bot:
        reason += ' | FUNDO TRIPLO (caça de stops abaixo)'
    elif eq_l:
        reason += ' | equal lows (SSL óbvia)'

    return {
        'bsl': bsl,
        'ssl': ssl,
        'equal_highs': eq_h,
        'equal_lows': eq_l,
        'triple_top': triple_top,
        'triple_bottom': triple_bot,
        'swing_highs': highs[-3:],
        'swing_lows': lows[-3:],
        'reason': reason,
    }


def detect_liquidity_sweep(df: pd.DataFrame, zones: dict | None = None) -> dict[str, Any]:
    """
    Liquidity Grab: rompe o nível com pavio longo e fecha de volta.

    BSL sweep → fake breakout de alta (não comprar o rompimento).
    SSL sweep → fake breakdown (não vender o rompimento).
    Após o grab, a reversão (lado oposto) é o setup.
    """
    out = {
        'sweep_bsl': False,
        'sweep_ssl': False,
        'invalidate_breakout': False,
        'grab_reversal': 'NONE',
        'sweep_reason': '',
    }
    if df is None or len(df) < 3:
        return out
    hist = df.iloc[:-1] if len(df) >= 4 else df
    hist_zones = identify_liquidity_zones(hist)
    merged = dict(hist_zones)
    if zones:
        for k in ('equal_highs', 'equal_lows', 'triple_top', 'triple_bottom', 'reason'):
            if zones.get(k):
                merged[k] = zones[k]
    # Níveis de caça vêm do histórico — a vela atual é o sweep, não o nível
    bsl = _f(hist_zones.get('bsl'))
    ssl = _f(hist_zones.get('ssl'))
    zones = merged
    last = df.iloc[-1]
    o = _f(last['open'])
    h = _f(last['high'])
    l = _f(last['low'])
    c = _f(last['close'])
    spread = max(h - l, 1e-12)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    bsl = _f(zones.get('bsl'))
    ssl = _f(zones.get('ssl'))

    if bsl > 0 and h > bsl and c < bsl and (upper_wick / spread) >= SWEEP_WICK_FRAC:
        out['sweep_bsl'] = True
        out['invalidate_breakout'] = True
        out['grab_reversal'] = 'SELL'
        out['sweep_reason'] = (
            f'LIQUIDITY SWEEP BSL: pavio acima de {bsl:.6g} '
            f'({upper_wick / spread * 100:.0f}% sombra) e close de volta — breakout inválido'
        )
        if zones.get('triple_top') or zones.get('equal_highs'):
            out['sweep_reason'] += ' (nível óbvio / topo triplo)'
    elif ssl > 0 and l < ssl and c > ssl and (lower_wick / spread) >= SWEEP_WICK_FRAC:
        out['sweep_ssl'] = True
        out['invalidate_breakout'] = True
        out['grab_reversal'] = 'BUY'
        out['sweep_reason'] = (
            f'LIQUIDITY SWEEP SSL: pavio abaixo de {ssl:.6g} '
            f'({lower_wick / spread * 100:.0f}% sombra) e close de volta — breakdown inválido'
        )
        if zones.get('triple_bottom') or zones.get('equal_lows'):
            out['sweep_reason'] += ' (nível óbvio / fundo triplo)'
    return out


def detect_fair_value_gaps(df: pd.DataFrame, lookback: int = FVG_LOOKBACK) -> dict[str, Any]:
    """FVGs recentes: zona ímã (preço tende a preencher o gap)."""
    empty = {
        'fvg_bullish': False,
        'fvg_bearish': False,
        'fvg_mid': 0.0,
        'fvg_magnet': False,
        'fvg_reason': '',
    }
    if df is None or len(df) < 3:
        return empty

    work = df.tail(max(int(lookback), 3)).reset_index(drop=True)
    last_bull = None
    last_bear = None
    for i in range(2, len(work)):
        c0 = work.iloc[i - 2]
        c2 = work.iloc[i]
        if _f(c2['low']) > _f(c0['high']):
            last_bull = (
                _f(c0['high']),
                _f(c2['low']),
                (_f(c0['high']) + _f(c2['low'])) / 2.0,
            )
        if _f(c2['high']) < _f(c0['low']):
            last_bear = (
                _f(c2['high']),
                _f(c0['low']),
                (_f(c2['high']) + _f(c0['low'])) / 2.0,
            )

    close = _f(work['close'].iloc[-1])
    if last_bull:
        lo, hi, mid = last_bull
        empty.update({
            'fvg_bullish': True,
            'fvg_mid': mid,
            'fvg_magnet': lo <= close <= hi * 1.002,
            'fvg_reason': f'FVG bullish ímã mid={mid:.6g}',
        })
    if last_bear:
        lo, hi, mid = last_bear
        empty.update({
            'fvg_bearish': True,
            'fvg_mid': mid if not last_bull else empty['fvg_mid'],
            'fvg_magnet': empty.get('fvg_magnet') or (lo * 0.998 <= close <= hi),
            'fvg_reason': (
                (empty.get('fvg_reason') + ' | ') if empty.get('fvg_reason') else ''
            ) + f'FVG bearish ímã mid={mid:.6g}',
        })
    if not empty.get('fvg_reason'):
        # 3 velas clássicas (compatível com cautious_entry_gate)
        c0 = work.iloc[-3]
        c2 = work.iloc[-1]
        bull = _f(c2['low']) > _f(c0['high'])
        bear = _f(c2['high']) < _f(c0['low'])
        empty['fvg_bullish'] = bull
        empty['fvg_bearish'] = bear
        if bull:
            empty['fvg_mid'] = (_f(c0['high']) + _f(c2['low'])) / 2.0
            empty['fvg_reason'] = 'FVG bullish 3 velas'
        elif bear:
            empty['fvg_mid'] = (_f(c0['low']) + _f(c2['high'])) / 2.0
            empty['fvg_reason'] = 'FVG bearish 3 velas'
    return empty


def analyze_smart_money_liquidity(df: pd.DataFrame, signals: dict | None = None) -> dict[str, Any]:
    """Pacote único para o radar / dashboard."""
    signals = signals or {}
    zones = identify_liquidity_zones(df)
    sweep = detect_liquidity_sweep(df, zones)
    fvg = detect_fair_value_gaps(df)
    trend = str(signals.get('trend') or '').upper()
    intended = str(signals.get('sinal_institucional') or '').upper()

    block_long = sweep['sweep_bsl'] and intended in ('COMPRA_INSTITUCIONAL',) or (
        sweep['sweep_bsl'] and trend == 'ALTA'
    )
    block_short = sweep['sweep_ssl'] and intended in ('VENDA_INSTITUCIONAL',) or (
        sweep['sweep_ssl'] and trend == 'BAIXA'
    )

    logs = [zones.get('reason') or '']
    if sweep.get('sweep_reason'):
        logs.append(sweep['sweep_reason'])
    if fvg.get('fvg_reason'):
        logs.append(fvg['fvg_reason'])

    return {
        **zones,
        **sweep,
        **fvg,
        'liquidity_block_long': bool(block_long),
        'liquidity_block_short': bool(block_short),
        'liquidity_ok': not (block_long or block_short),
        'liquidity_log': ' | '.join(x for x in logs if x),
    }
