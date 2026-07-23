# -*- coding: utf-8 -*-
"""
Entrada Assimétrica do Motor Sniper — opinião quant + regras que já lucram.

Tese (o que costuma dar certo em crypto day-trade 15m @20x):
  SHORT em DERRETIMENTO  → agressivo: moeda caindo rápido com 1–2 vermelhas fortes
                           (panic sell / dump) tem edge maior que chase de topo.
  LONG no topo / fraco    → RÍGIDO: só com baleias alinhadas + vela VERDE forte.
                           Proibido comprar no meio de dump ou no topo frágil.

Regra operacional de SHORT (pedido do operador):
  - Máximo 2 velas vermelhas fortes no início da virada.
  - Entrada na metade da 2ª vela se a tendência já virou BAIXA.
  - Close nos 35% inferiores + volume acima da média.

Regra operacional de LONG:
  - Exige whale_aligned (ou whale_score alto) + strong_bullish_candle.
  - Bloqueia se houver pressão vermelha recente (falling knife / dump start).
"""

from __future__ import annotations

import os
from typing import Any

CLOSE_ZONE = float(os.getenv('CANDLE_CLOSE_ZONE_FRAC', '0.35'))
MELTDOWN_DROP_PCT = float(os.getenv('MELTDOWN_DROP_PCT', '1.2'))  # queda % em 2–3 velas
MELTDOWN_BODY_PCT = float(os.getenv('MELTDOWN_BODY_PCT', '55'))   # corpo mínimo da vermelha
WHALE_SCORE_MIN_LONG = float(os.getenv('WHALE_SCORE_MIN_LONG', '40'))
RIGID_LONG = str(os.getenv('RIGID_LONG_ENTRIES', 'true')).strip().lower() in {
    '1', 'true', 'yes', 'on',
}
AGGRESSIVE_MELTDOWN_SHORT = str(os.getenv('AGGRESSIVE_MELTDOWN_SHORT', 'true')).strip().lower() in {
    '1', 'true', 'yes', 'on',
}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _body_pct(open_p: float, high: float, low: float, close: float) -> float:
    spread = max(high - low, 1e-12)
    return abs(close - open_p) / spread * 100.0


def _is_red(open_p: float, close: float) -> bool:
    return close < open_p


def _is_green(open_p: float, close: float) -> bool:
    return close > open_p


def _close_in_lower_zone(high: float, low: float, close: float, zone: float = CLOSE_ZONE) -> bool:
    spread = high - low
    if spread <= 0:
        return False
    return close <= low + spread * zone


def _close_in_upper_zone(high: float, low: float, close: float, zone: float = CLOSE_ZONE) -> bool:
    spread = high - low
    if spread <= 0:
        return False
    return close >= high - spread * zone


def detect_meltdown(df, signals: dict | None = None) -> dict[str, Any]:
    """
    Detecta derretimento: 1–2 vermelhas fortes, queda rápida, pressão no fundo da vela.

    Entrada ideal SHORT: exatamente na 2ª vermelha (ou fim da 1ª se explosiva),
    tendência BAIXA, close na metade inferior.
    """
    signals = signals or {}
    out = {
        'meltdown': False,
        'second_red_entry': False,
        'red_streak': 0,
        'drop_pct': 0.0,
        'strength': 0.0,
        'reason': '',
        'prefer_short': False,
    }
    if df is None or len(df) < 4:
        out['reason'] = 'histórico insuficiente'
        return out

    last = df.iloc[-1]
    prev = df.iloc[-2]
    o0, h0, l0, c0 = _f(last['open']), _f(last['high']), _f(last['low']), _f(last['close'])
    o1, h1, l1, c1 = _f(prev['open']), _f(prev['high']), _f(prev['low']), _f(prev['close'])

    reds = 0
    for i in (-1, -2, -3):
        row = df.iloc[i]
        if _is_red(_f(row['open']), _f(row['close'])):
            reds += 1
        else:
            break
    out['red_streak'] = reds

    # Queda % dos últimos 2–3 fechamentos
    ref = _f(df['close'].iloc[-4]) if len(df) >= 4 else _f(df['close'].iloc[0])
    drop_pct = ((ref - c0) / ref * 100.0) if ref > 0 else 0.0
    out['drop_pct'] = round(drop_pct, 3)

    body0 = _body_pct(o0, h0, l0, c0)
    body1 = _body_pct(o1, h1, l1, c1)
    vol_ratio = _f(signals.get('volume_ratio'), 1.0)
    lower0 = _close_in_lower_zone(h0, l0, c0)
    lower1 = _close_in_lower_zone(h1, l1, c1)
    strong_bear = bool(signals.get('strong_bearish_candle')) or body0 >= MELTDOWN_BODY_PCT

    # Spreads acima da média recente
    spreads = (df['high'] - df['low']).astype(float)
    spread_ma = float(spreads.iloc[-20:].mean()) if len(spreads) >= 5 else float(spreads.mean())
    wide0 = (h0 - l0) > spread_ma * 1.15 if spread_ma > 0 else False
    wide1 = (h1 - l1) > spread_ma * 1.10 if spread_ma > 0 else False

    trend = str(signals.get('trend', '') or '').upper()
    st = int(signals.get('supertrend_signal', 0) or 0)

    # Caso A: exatamente 2 vermelhas — entrada na 2ª (regra do operador)
    second_red = (
        reds == 2
        and _is_red(o0, c0)
        and _is_red(o1, c1)
        and (body0 >= MELTDOWN_BODY_PCT * 0.85 or strong_bear)
        and (lower0 or lower1)
        and (wide0 or wide1 or vol_ratio >= 1.3)
        and drop_pct >= MELTDOWN_DROP_PCT * 0.7
    )

    # Caso B: 1 vermelha explosiva (derretimento vertical)
    single_blast = (
        reds >= 1
        and _is_red(o0, c0)
        and body0 >= MELTDOWN_BODY_PCT
        and lower0
        and (wide0 or vol_ratio >= 1.8)
        and drop_pct >= MELTDOWN_DROP_PCT
    )

    # Caso C: falling knife já detectado + tendência baixa
    knife = bool(signals.get('falling_knife'))
    knife_short = knife and trend == 'BAIXA' and _is_red(o0, c0)

    meltdown = bool(second_red or single_blast or knife_short)
    out['meltdown'] = meltdown
    out['second_red_entry'] = bool(second_red)
    out['prefer_short'] = meltdown and AGGRESSIVE_MELTDOWN_SHORT

    strength = 0.0
    if meltdown:
        strength = min(
            100.0,
            drop_pct * 12
            + body0 * 0.35
            + (20 if second_red else 0)
            + (15 if vol_ratio >= 1.5 else 0)
            + (10 if trend == 'BAIXA' else 0)
            + (10 if st == -1 else 0),
        )
    out['strength'] = round(strength, 1)

    if second_red:
        out['reason'] = (
            f'DERRETIMENTO: 2ª vela vermelha forte (corpo={body0:.0f}%) '
            f'queda={drop_pct:.2f}% — entrada SHORT na metade da 2ª'
        )
    elif single_blast:
        out['reason'] = (
            f'DERRETIMENTO vertical: vela vermelha explosiva (corpo={body0:.0f}%) '
            f'queda={drop_pct:.2f}% vol×{vol_ratio:.1f}'
        )
    elif knife_short:
        out['reason'] = 'Falling knife + tendência BAIXA — preferir SHORT'
    else:
        out['reason'] = 'sem derretimento claro'
    return out


def evaluate_asymmetric_entry(
    side: str,
    df,
    signals: dict | None = None,
    intel_ctx: dict | None = None,
) -> dict[str, Any]:
    """
    Portão assimétrico pós-intel (tem baleias).

    BUY  → rígido (baleias + vela forte verde; anti-topo).
    SELL → favorece meltdown; exige vermelha com pressão.
    """
    signals = signals or {}
    intel = intel_ctx or {}
    side_n = str(side or '').strip().lower()
    melt = detect_meltdown(df, signals)

    result = {
        'allowed': False,
        'side': side_n,
        'meltdown': melt,
        'score_boost': 0.0,
        'abort_reason': '',
        'pleno_notes': [],
        'strategy': 'asymmetric_sniper',
    }

    whale_aligned = bool(intel.get('whale_aligned') or signals.get('whale_aligned'))
    whale_score = _f(intel.get('whale_score', signals.get('whale_score')), 0.0)
    strong_green = bool(signals.get('strong_bullish_candle'))
    strong_red = bool(signals.get('strong_bearish_candle'))
    trend = str(signals.get('trend', 'NEUTRO') or 'NEUTRO').upper()

    if df is None or len(df) < 3:
        result['abort_reason'] = 'OHLC insuficiente'
        return result

    last = df.iloc[-1]
    o, h, l, c = _f(last['open']), _f(last['high']), _f(last['low']), _f(last['close'])

    # ── SHORT ──────────────────────────────────────────────────────────
    if side_n in ('sell', 'short', 'vender'):
        if not _is_red(o, c):
            result['abort_reason'] = 'SHORT exige vela VERMELHA (proibido short em verde)'
            return result
        if not _close_in_lower_zone(h, l, c) and not melt['meltdown']:
            result['abort_reason'] = 'SHORT fraco — close fora dos 35% inferiores (sem derretimento)'
            return result

        # Meltdown: libera com força (tese principal de lucro)
        if melt['prefer_short']:
            result['allowed'] = True
            result['score_boost'] = 18.0 + min(12.0, melt['strength'] * 0.12)
            result['pleno_notes'] = [
                'Pleno SHORT: derretimento detectado — edge histórico favorável',
                melt['reason'],
                'Groq/Analista: priorizar venda em panic sell, não chase de alta',
            ]
            return result

        # SHORT normal: ainda exige pressão real
        if trend != 'BAIXA':
            result['abort_reason'] = f'SHORT sem meltdown exige tendência BAIXA (agora={trend})'
            return result
        if not (strong_red or melt['red_streak'] >= 2):
            result['abort_reason'] = 'SHORT sem vela forte vermelha / 2ª vermelha'
            return result

        result['allowed'] = True
        result['score_boost'] = 8.0 if strong_red else 5.0
        result['pleno_notes'] = [
            'Pleno SHORT: tendência BAIXA + pressão vermelha',
            'Entrada alinhada a Smart Money de venda',
        ]
        return result

    # ── LONG (RÍGIDO) ──────────────────────────────────────────────────
    if side_n in ('buy', 'long', 'comprar'):
        if not RIGID_LONG:
            result['allowed'] = True
            result['pleno_notes'] = ['LONG sem trava rígida (RIGID_LONG_ENTRIES=false)']
            return result

        if melt['meltdown'] or bool(signals.get('falling_knife')):
            result['abort_reason'] = (
                f'LONG bloqueado em derretimento/falling-knife — {melt.get("reason") or "faca caindo"}'
            )
            return result

        if not _is_green(o, c):
            result['abort_reason'] = 'LONG rígido: proibido comprar vela VERMELHA'
            return result
        if not _close_in_upper_zone(h, l, c):
            result['abort_reason'] = 'LONG rígido: close fora dos 35% superiores'
            return result

        # Baleias obrigatórias na subida
        whales_ok = whale_aligned or whale_score >= WHALE_SCORE_MIN_LONG
        if not whales_ok:
            result['abort_reason'] = (
                f'LONG rígido: exige BALEIAS (aligned={whale_aligned} score={whale_score:.0f} '
                f'< {WHALE_SCORE_MIN_LONG:.0f})'
            )
            return result

        if not strong_green:
            # Aceita corpo dominante alto como proxy
            body = _body_pct(o, h, l, c)
            if body < 60 or _f(signals.get('volume_ratio'), 1) < 1.4:
                result['abort_reason'] = (
                    'LONG rígido: exige vela VERDE FORTE (institucional) + volume'
                )
                return result

        # Anti-topo: RSI extremo sem engolfo/FVG já é tratado no cautious gate;
        # aqui só reforça se rejeição de pivô alto sem força.
        if signals.get('rejection_from_pivot_high') and not strong_green:
            result['abort_reason'] = 'LONG bloqueado: rejeição de topo sem vela forte'
            return result

        result['allowed'] = True
        result['score_boost'] = 10.0 if whale_aligned else 6.0
        result['pleno_notes'] = [
            'Pleno LONG RÍGIDO: baleias + vela verde forte — sem chase de topo',
            f'whale_score={whale_score:.0f} aligned={whale_aligned}',
        ]
        return result

    result['abort_reason'] = f'side inválido: {side}'
    return result


def pleno_study_notes(side: str, asym: dict, signals: dict | None = None) -> list[str]:
    """Notas para o Tribunal de IAs agir como um pleno de mesa."""
    signals = signals or {}
    notes = list(asym.get('pleno_notes') or [])
    melt = asym.get('meltdown') or {}
    side_n = str(side or '').lower()
    if side_n in ('sell', 'short', 'vender'):
        notes.append(
            'Opinião Quant: em dump rápido, short costuma pagar mais que long no fundo falso.'
        )
        if melt.get('second_red_entry'):
            notes.append('Setup clássico: entrada na 2ª vermelha após virada BAIXA.')
    else:
        notes.append(
            'Opinião Quant: long só com fluxo institucional (baleias) — topo frágil = armadilha.'
        )
        if signals.get('falling_knife'):
            notes.append('Tribunal: faca caindo — COMPRA vetada por unanimidade.')
    return notes
