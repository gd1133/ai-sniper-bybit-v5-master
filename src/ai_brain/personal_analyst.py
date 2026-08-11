# -*- coding: utf-8 -*-
"""
Analista Pessoal (Cérebro 3+) — refinador assertivo de entrada/saída estilo DyTrade.

Não substitui Hard Gates, Anti-Chase, nem Thresholds de env.
Atua como camada soft/assertiva:
  • ENTRADA: pode ABORTAR (WAIT) ou dar boost/penalidade na probabilidade
  • SAÍDA: pode acelerar EARLY_EXIT (nunca afrouxa SL / Profit Shield)

Fail-open: se o módulo falhar, o fluxo atual segue intacto.
"""

from __future__ import annotations

import os
from typing import Any


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


ENABLED = _env_bool('ENABLE_PERSONAL_ANALYST', True)
ENTRY_MIN_SCORE = _env_float('ANALYST_ENTRY_MIN_SCORE', 45.0)
BOOST_CAP = _env_float('ANALYST_PROB_BOOST_CAP', 8.0)
PENALTY_CAP = _env_float('ANALYST_PROB_PENALTY_CAP', 12.0)
EXIT_GIVEBACK_PCT = _env_float('ANALYST_EXIT_GIVEBACK_PCT', 35.0)  # % do pico de ROI
EXIT_MIN_PEAK_ROI = _env_float('ANALYST_EXIT_MIN_PEAK_ROI', 28.0)
EXIT_MOMENTUM_FADE_ROI = _env_float('ANALYST_EXIT_MOMENTUM_FADE_ROI', 18.0)


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _is_long(side: str) -> bool:
    return str(side or '').strip().lower() in {'buy', 'long', 'comprar'}


def _ema_series(closes, period: int):
    try:
        import pandas as pd
        s = pd.Series(closes, dtype='float64')
        return s.ewm(span=period, adjust=False).mean()
    except Exception:
        return None


def _atr_pct(df, period: int = 14) -> float:
    try:
        if df is None or len(df) < period + 2:
            return 0.0
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        close = df['close'].astype(float)
        prev = close.shift(1)
        tr = (high - low).combine((high - prev).abs(), max).combine((low - prev).abs(), max)
        atr = float(tr.tail(period).mean())
        last = float(close.iloc[-1])
        return (atr / last) * 100.0 if last > 0 else 0.0
    except Exception:
        return 0.0


def refine_entry(
    *,
    side: str,
    probabilidade: float,
    signals: dict | None,
    df=None,
    intelligence_context: dict | None = None,
    symbol: str = '',
) -> dict[str, Any]:
    """
    Analista assertivo de entrada (DyTrade-like).

    Returns:
      allowed: bool
      probabilidade: float (ajustada)
      abort_reason: str
      notes: list[str]
      score: float (0-100 qualidade analítica)
      boost: float
    """
    base = {
        'allowed': True,
        'probabilidade': _f(probabilidade),
        'abort_reason': '',
        'notes': [],
        'score': 50.0,
        'boost': 0.0,
        'enabled': ENABLED,
    }
    if not ENABLED:
        base['notes'] = ['Analista Pessoal desativado (ENABLE_PERSONAL_ANALYST=false)']
        return base

    try:
        signals = dict(signals or {})
        ctx = dict(intelligence_context or {})
        long = _is_long(side)
        score = 55.0
        notes: list[str] = []
        hard_blocks: list[str] = []

        trend = str(signals.get('trend') or 'NEUTRO').upper()
        inst = str(signals.get('sinal_institucional') or 'NEUTRO').upper()
        adx = _f(signals.get('adx'))
        vol_ratio = _f(signals.get('volume_ratio'), 1.0)
        rsi = _f(signals.get('rsi'), 50.0)
        price = _f(signals.get('price') or signals.get('close'))
        ema20 = _f(signals.get('ema20') or signals.get('sma_20'))
        vwap = _f(signals.get('vwap'))
        fib_dist = _f(signals.get('fib_distance_pct'), 99.0)
        money_flow = str(signals.get('money_flow_side') or '').upper()

        # ── 1) Alinhamento estrutura (EMA + tendência + Smart Money) ──
        if long and trend != 'ALTA':
            hard_blocks.append(f'tendência={trend} ≠ ALTA')
        if (not long) and trend != 'BAIXA':
            hard_blocks.append(f'tendência={trend} ≠ BAIXA')
        if long and inst not in ('COMPRA_INSTITUCIONAL', 'NEUTRO'):
            # NEUTRO já teria sido filtrado pelas portas; reforço se VENDA
            if 'VENDA' in inst:
                hard_blocks.append(f'Smart Money contra LONG ({inst})')
        if (not long) and 'COMPRA' in inst:
            hard_blocks.append(f'Smart Money contra SHORT ({inst})')

        # ── 2) Qualidade ADX / volume (tendência viva) ──
        from src.engine.structure_config import STRUCTURE_ADX_MIN
        adx_ok = float(STRUCTURE_ADX_MIN)
        if adx >= 28:
            score += 8
            notes.append(f'ADX forte {adx:.1f}')
        elif adx >= adx_ok:
            score += 3
            notes.append(f'ADX ok {adx:.1f}')
        else:
            score -= 10
            notes.append(f'ADX fraco {adx:.1f}')

        if vol_ratio >= 1.8:
            score += 10
            notes.append(f'volume institucional x{vol_ratio:.2f}')
        elif vol_ratio >= 1.3:
            score += 4
        elif vol_ratio < 0.85:
            score -= 8
            notes.append(f'volume seco x{vol_ratio:.2f}')

        # ── 3) Localização no candle / fibo (entrada perto do valor) ──
        if 0 < fib_dist <= 1.2:
            score += 7
            notes.append(f'perto Fib ({fib_dist:.2f}%)')
        elif fib_dist > 3.5:
            score -= 6
            notes.append(f'longe da Fib ({fib_dist:.2f}%)')

        # ── 4) RSI — evita extremos (complementa anti-chase) ──
        if long:
            if rsi >= 72:
                hard_blocks.append(f'RSI sobrecomprado {rsi:.1f}')
            elif rsi >= 65:
                score -= 6
                notes.append(f'RSI alto {rsi:.1f}')
            elif 45 <= rsi <= 62:
                score += 5
                notes.append(f'RSI saudável {rsi:.1f}')
        else:
            if rsi <= 28:
                hard_blocks.append(f'RSI sobrevendido {rsi:.1f}')
            elif rsi <= 35:
                score -= 6
                notes.append(f'RSI baixo {rsi:.1f}')
            elif 38 <= rsi <= 55:
                score += 5
                notes.append(f'RSI saudável {rsi:.1f}')

        # ── 5) Preço vs EMA20 / VWAP (lado a favor do fluxo) ──
        if price > 0 and ema20 > 0:
            ext_ema = ((price - ema20) / ema20) * 100.0
            if long and ext_ema > 1.4:
                hard_blocks.append(f'estirado +{ext_ema:.2f}% vs EMA20')
            elif long and -0.35 <= ext_ema <= 0.55:
                score += 6
                notes.append('pullback EMA20 ok')
            elif (not long) and ext_ema < -1.4:
                hard_blocks.append(f'estirado {ext_ema:.2f}% vs EMA20')
            elif (not long) and -0.55 <= ext_ema <= 0.35:
                score += 6
                notes.append('repique EMA20 ok')

        if price > 0 and vwap > 0:
            above = price >= vwap
            if long and above:
                score += 4
                notes.append('preço > VWAP')
            elif long and not above:
                score -= 5
                notes.append('preço < VWAP (LONG frágil)')
            elif (not long) and not above:
                score += 4
                notes.append('preço < VWAP')
            elif (not long) and above:
                score -= 5
                notes.append('preço > VWAP (SHORT frágil)')

        # ── 6) Fluxo de livro / baleias (intel) ──
        flow = str(ctx.get('order_flow_bias') or ctx.get('flow_bias') or '').upper()
        whale_ok = bool(ctx.get('whale_aligned'))
        if whale_ok:
            score += 6
            notes.append('baleias alinhadas')
        if (long and 'BUY' in flow) or ((not long) and 'SELL' in flow):
            score += 5
            notes.append(f'order-flow {flow or "align"}')
        elif flow and ((long and 'SELL' in flow) or ((not long) and 'BUY' in flow)):
            score -= 8
            notes.append(f'order-flow contrário ({flow})')

        if money_flow:
            if (long and money_flow in ('BUY', 'INFLOW', 'LONG')) or (
                (not long) and money_flow in ('SELL', 'OUTFLOW', 'SHORT')
            ):
                score += 4
                notes.append(f'money-flow {money_flow}')
            elif (long and money_flow in ('SELL', 'OUTFLOW')) or (
                (not long) and money_flow in ('BUY', 'INFLOW')
            ):
                score -= 5

        # ── 7) ATR — evita mercado morto / explosão já ocorrida ──
        atrp = _atr_pct(df, 14)
        if 0 < atrp < 0.12:
            score -= 8
            notes.append(f'ATR morto {atrp:.3f}%')
        elif 0.18 <= atrp <= 1.8:
            score += 3
        elif atrp > 3.5:
            score -= 4
            notes.append(f'ATR explosivo {atrp:.2f}%')

        # ── 8) Microestrutura EMA9/21 no df ──
        try:
            if df is not None and len(df) >= 30:
                closes = df['close'].astype(float).tolist()
                e9 = _ema_series(closes, 9)
                e21 = _ema_series(closes, 21)
                if e9 is not None and e21 is not None:
                    e9v, e21v = float(e9.iloc[-1]), float(e21.iloc[-1])
                    e9p, e21p = float(e9.iloc[-3]), float(e21.iloc[-3])
                    if long and e9v > e21v and e9v >= e9p:
                        score += 5
                        notes.append('EMA9>EMA21 acelerando')
                    elif long and e9v < e21v:
                        score -= 7
                        notes.append('EMA9<EMA21 (LONG frágil)')
                    elif (not long) and e9v < e21v and e9v <= e9p:
                        score += 5
                        notes.append('EMA9<EMA21 acelerando')
                    elif (not long) and e9v > e21v:
                        score -= 7
                        notes.append('EMA9>EMA21 (SHORT frágil)')
        except Exception:
            pass

        score = max(0.0, min(100.0, score))

        # Abortos hard do analista
        if hard_blocks:
            return {
                'allowed': False,
                'probabilidade': _f(probabilidade),
                'abort_reason': 'Analista Pessoal: ' + ' | '.join(hard_blocks[:3]),
                'notes': notes + hard_blocks,
                'score': score,
                'boost': 0.0,
                'enabled': True,
            }

        if score < ENTRY_MIN_SCORE:
            return {
                'allowed': False,
                'probabilidade': _f(probabilidade),
                'abort_reason': (
                    f'Analista Pessoal: score={score:.0f} < mínimo {ENTRY_MIN_SCORE:.0f} '
                    f'({"; ".join(notes[:3]) or "setup fraco"})'
                ),
                'notes': notes,
                'score': score,
                'boost': 0.0,
                'enabled': True,
            }

        # Ajuste fino de probabilidade (nunca derruba abaixo do veto já passado)
        delta = (score - 60.0) * 0.35
        delta = max(-PENALTY_CAP, min(BOOST_CAP, delta))
        new_prob = max(0.0, min(100.0, _f(probabilidade) + delta))
        if delta >= 1:
            notes.append(f'boost +{delta:.1f}pts → {new_prob:.1f}%')
        elif delta <= -1:
            notes.append(f'penalidade {delta:.1f}pts → {new_prob:.1f}%')

        return {
            'allowed': True,
            'probabilidade': round(new_prob, 2),
            'abort_reason': '',
            'notes': notes,
            'score': round(score, 2),
            'boost': round(delta, 2),
            'enabled': True,
            'symbol': symbol,
        }
    except Exception as err:
        return {
            'allowed': True,  # fail-open
            'probabilidade': _f(probabilidade),
            'abort_reason': '',
            'notes': [f'Analista fail-open: {err}'],
            'score': 50.0,
            'boost': 0.0,
            'enabled': ENABLED,
        }


def refine_exit(
    *,
    side: str,
    roi_pct: float,
    peak_roi_pct: float | None = None,
    trailing_armed: bool = False,
    breakeven_armed: bool = False,
    df=None,
    signals: dict | None = None,
) -> dict[str, Any]:
    """
    Analista assertivo de saída.

    Pode sugerir EARLY_EXIT; nunca sugere afrouxar SL.
    """
    out = {
        'suggest_early_exit': False,
        'motivo': '',
        'enabled': ENABLED,
        'priority': 0,
    }
    if not ENABLED:
        return out

    try:
        roi = _f(roi_pct)
        peak = _f(peak_roi_pct if peak_roi_pct is not None else roi)
        if peak < roi:
            peak = roi
        long = _is_long(side)
        reasons: list[str] = []

        # 1) Give-back: deu lucro e devolveu parte relevante do pico
        if peak >= EXIT_MIN_PEAK_ROI and peak > 0:
            giveback = ((peak - roi) / peak) * 100.0
            if giveback >= EXIT_GIVEBACK_PCT and roi >= 10:
                reasons.append(
                    f'give-back {giveback:.0f}% do pico (pico ROI {peak:.0f}% → agora {roi:.0f}%)'
                )

        # 2) Momentum fade com lucro decente
        try:
            if df is not None and len(df) >= 25 and roi >= EXIT_MOMENTUM_FADE_ROI:
                closes = df['close'].astype(float).tolist()
                e8 = _ema_series(closes, 8)
                e20 = _ema_series(closes, 20)
                if e8 is not None and e20 is not None:
                    e8v, e20v = float(e8.iloc[-1]), float(e20.iloc[-1])
                    px = float(closes[-1])
                    if long and px < e8v and e8v < e20v:
                        reasons.append('momentum LONG quebrado (preço<EMA8<EMA20)')
                    if (not long) and px > e8v and e8v > e20v:
                        reasons.append('momentum SHORT quebrado (preço>EMA8>EMA20)')
        except Exception:
            pass

        # 3) Volume de distribuição contra a posição com lucro
        sig = signals or {}
        vol_ratio = _f(sig.get('volume_ratio'), 1.0)
        rsi = _f(sig.get('rsi'), 50.0)
        if roi >= EXIT_MOMENTUM_FADE_ROI and vol_ratio >= 1.6:
            if long and rsi >= 70:
                reasons.append(f'distribuição no topo (RSI {rsi:.0f}, vol x{vol_ratio:.1f})')
            if (not long) and rsi <= 30:
                reasons.append(f'captação no fundo (RSI {rsi:.0f}, vol x{vol_ratio:.1f})')

        # Com trailing armado, só sugere saída se give-back for evidente
        if trailing_armed and reasons:
            only_soft = all('give-back' not in r for r in reasons)
            if only_soft and roi >= 40:
                return out

        if reasons:
            out['suggest_early_exit'] = True
            out['motivo'] = 'Analista Pessoal: ' + ' | '.join(reasons[:3])
            out['priority'] = 2 if any('give-back' in r for r in reasons) else 1
            # Não força saída se ainda negativo (espera SL mecânico)
            if roi < 5 and not breakeven_armed:
                out['suggest_early_exit'] = False
                out['motivo'] = ''
        return out
    except Exception:
        return out
