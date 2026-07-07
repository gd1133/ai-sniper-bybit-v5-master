"""Detecção de atividade de baleias e grandes players."""

from __future__ import annotations

from datetime import datetime, timezone


# Horários UTC com maior participação institucional (NYSE + Londres overlap)
_INSTITUTIONAL_HOURS_UTC = {(13, 14, 15, 16, 7, 8, 9, 10)}


def _session_score() -> tuple[float, str]:
    """Bônus quando grandes mercados estão abertos."""
    hour = datetime.now(timezone.utc).hour
    if hour in _INSTITUTIONAL_HOURS_UTC:
        return 25.0, 'Sessão institucional ativa (NY/Londres)'
    if hour in (0, 1, 2, 3):
        return 5.0, 'Sessão asiática — volume institucional reduzido'
    return 12.0, 'Sessão intermediária'


def analyze_whale_activity(signals: dict, ticker: dict | None = None, df=None) -> dict:
    """
    Pontua atividade de grandes players com base em:
    - Volume relativo (volume_ratio)
    - Pressão direcional (money_flow_side)
    - Corpo do candle e expansão de range
    - Liquidez do par (quote volume 24h)
    - Horário institucional
    """
    ticker = ticker or {}
    volume_ratio = float(signals.get('volume_ratio', 0) or 0)
    body_ratio = float(signals.get('candle_body_ratio', 0) or 0)
    range_expansion = float(signals.get('range_expansion', 0) or 0)
    money_flow = str(signals.get('money_flow_side', 'WAIT')).upper()
    trend = str(signals.get('trend', 'NEUTRO')).upper()
    quote_volume_m = float(ticker.get('quoteVolume', 0) or 0) / 1_000_000

    score = 0.0
    reasons = []

    if volume_ratio >= 2.0:
        score += 30
        reasons.append(f'Volume explosivo {volume_ratio:.1f}x — possível acumulação institucional')
    elif volume_ratio >= 1.5:
        score += 20
        reasons.append(f'Volume acima da média ({volume_ratio:.1f}x)')
    elif volume_ratio >= 1.2:
        score += 10
        reasons.append(f'Volume moderado ({volume_ratio:.1f}x)')

    if body_ratio >= 65 and range_expansion >= 1.2:
        score += 20
        reasons.append('Candle de convicção — grandes players empurrando preço')
    elif body_ratio >= 50:
        score += 10
        reasons.append('Corpo de candle forte')

    if money_flow in ('BUY', 'SELL'):
        score += 20
        reasons.append(f'Fluxo de dinheiro alinhado: {money_flow}')
        if trend == 'ALTA' and money_flow == 'BUY':
            score += 10
            reasons.append('Baleias comprando em tendência de alta')
        elif trend == 'BAIXA' and money_flow == 'SELL':
            score += 10
            reasons.append('Baleias vendendo em tendência de baixa')

    if quote_volume_m >= 100:
        score += 15
        reasons.append(f'Alta liquidez 24h (${quote_volume_m:.0f}M)')
    elif quote_volume_m >= 20:
        score += 8
        reasons.append(f'Boa liquidez (${quote_volume_m:.0f}M)')

    session_bonus, session_note = _session_score()
    score += session_bonus
    reasons.append(session_note)

    # Detecta spike de volume nas últimas barras
    if df is not None and len(df) >= 5:
        try:
            recent_vol = float(df['vol'].iloc[-1])
            avg_vol = float(df['vol'].iloc[-6:-1].mean())
            if avg_vol > 0 and recent_vol / avg_vol >= 2.5:
                score += 15
                reasons.append('Spike de volume na última barra — entrada de grande player')
        except Exception:
            pass

    whale_aligned = (
        (trend == 'ALTA' and money_flow == 'BUY') or
        (trend == 'BAIXA' and money_flow == 'SELL')
    )

    return {
        'whale_score': round(min(100.0, score), 2),
        'whale_aligned': whale_aligned,
        'institutional_pressure': round(max(0.0, volume_ratio - 1.0) * 35.0, 2),
        'money_flow_side': money_flow,
        'session_note': session_note,
        'reasons': reasons,
    }
