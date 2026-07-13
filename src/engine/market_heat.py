"""
Heat estratégico de velas + fluxo — leitura avançada para o Cérebro 3.

Combina: corpo da vela, expansão de range, volume, pivôs e score estrutural
em um único ``heat_score`` (0–100) e ``heat_bias`` (BULL/BEAR/NEUTRAL).
"""

from __future__ import annotations

from typing import Any


def compute_candle_heat(signals: dict | None = None, df=None) -> dict[str, Any]:
    """
    Calcula heat de mercado a partir dos sinais já produzidos pelo IndicatorEngine.

    Não faz novas chamadas de API — reutiliza OHLCV/indicadores locais.
    """
    signals = signals or {}
    score = 50.0
    reasons: list[str] = []
    bias = 'NEUTRAL'

    trend = str(signals.get('trend', 'NEUTRO')).upper()
    body = float(signals.get('candle_body_ratio', 0) or 0)
    expansion = float(signals.get('range_expansion', 0) or 0)
    volume_ratio = float(signals.get('volume_ratio', 0) or 0)
    chart_score = float(signals.get('chart_entry_score', 0) or 0)
    adx = float(signals.get('adx', 0) or 0)
    strong_bull = bool(signals.get('strong_bullish_candle'))
    strong_bear = bool(signals.get('strong_bearish_candle'))
    bounce_low = bool(signals.get('bounce_from_pivot_low'))
    reject_high = bool(signals.get('rejection_from_pivot_high'))
    is_lateral = bool(signals.get('is_lateral'))

    if is_lateral or trend == 'NEUTRO':
        return {
            'heat_score': 15.0,
            'heat_bias': 'NEUTRAL',
            'heat_label': 'FRIO — mercado lateral / sem direção',
            'heat_reasons': ['Mercado lateral: heat desligado para entrada'],
            'entry_heat_ok': False,
        }

    # Corpo + expansão = "aquecimento" da vela
    if body >= 60:
        score += 12
        reasons.append(f'Corpo forte ({body:.0f}%)')
    if expansion >= 1.2:
        score += 10
        reasons.append(f'Expansão de range {expansion:.2f}× ATR')
    if volume_ratio >= 1.5:
        score += 12
        reasons.append(f'Volume institucional {volume_ratio:.2f}×')
    elif volume_ratio >= 1.2:
        score += 6
        reasons.append(f'Volume elevado {volume_ratio:.2f}×')

    if chart_score >= 40:
        score += min(18.0, chart_score * 0.25)
        reasons.append(f'Estrutura de gráfico {chart_score:.0f}/100')
    if adx >= 25:
        score += 10
        reasons.append(f'ADX direcional {adx:.0f}')
    elif adx >= 22:
        score += 5
        reasons.append(f'ADX em formação {adx:.0f}')

    if trend == 'ALTA':
        if strong_bull:
            score += 10
            reasons.append('Vela bullish institucional')
        if bounce_low:
            score += 8
            reasons.append('Repique em pivô de baixa')
        if strong_bear and body >= 55:
            score -= 20
            reasons.append('Vela bearish contra tendência de alta')
            bias = 'NEUTRAL'
        else:
            bias = 'BULL'
    elif trend == 'BAIXA':
        if strong_bear:
            score += 10
            reasons.append('Vela bearish institucional')
        if reject_high:
            score += 8
            reasons.append('Rejeição em pivô de alta')
        if strong_bull and body >= 55:
            score -= 20
            reasons.append('Vela bullish contra tendência de baixa')
            bias = 'NEUTRAL'
        else:
            bias = 'BEAR'

    # Delta de volume nas últimas barras (se df disponível)
    if df is not None and hasattr(df, '__len__') and len(df) >= 6 and 'vol' in getattr(df, 'columns', []):
        try:
            recent = float(df['vol'].iloc[-3:].sum())
            prev = float(df['vol'].iloc[-6:-3].sum()) or 1.0
            delta = recent / prev
            if delta >= 1.4:
                score += 8
                reasons.append(f'Heat de volume acelerando ({delta:.2f}×)')
            elif delta <= 0.7:
                score -= 8
                reasons.append(f'Volume esfriando ({delta:.2f}×)')
        except Exception:
            pass

    score = max(0.0, min(100.0, score))
    entry_heat_ok = score >= 55 and bias in ('BULL', 'BEAR') and not is_lateral

    if score >= 75:
        label = 'QUENTE — momentum alinhado à direção'
    elif score >= 55:
        label = 'MORNO — direção ok, aguardar confirmação de timing'
    else:
        label = 'FRIO — sem confluência de velas/fluxo'

    return {
        'heat_score': round(score, 2),
        'heat_bias': bias,
        'heat_label': label,
        'heat_reasons': reasons,
        'entry_heat_ok': entry_heat_ok,
    }
