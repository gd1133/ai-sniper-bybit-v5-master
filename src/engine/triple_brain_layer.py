# -*- coding: utf-8 -*-
"""
Camada incremental do Triplo Cérebro (Turtle / Fib exponencial / liquidez / anatomia).

NÃO substitui Cérebro 1, 2 ou 3. Só acrescenta bônus/razões em cima do que já existe:
  C1 — SMA 200, SuperTrend, corpo, RSI
  C2 — volume institucional, VWAP, order book, baleias
  C3 — 5 estratégias + Groq/Gemini + aprendizado
"""

from __future__ import annotations

from typing import Any


def _trend(tech: dict) -> str:
    return str((tech or {}).get('trend') or '').upper()


def incremental_c1_bonus(tech_data: dict | None) -> tuple[int, list[str]]:
    """Cérebro 1 (tendência/velas): Turtle + Ponto Contínuo + anatomia — só bônus."""
    tech = tech_data or {}
    trend = _trend(tech)
    score = 0
    reasons: list[str] = []

    turtle = str(tech.get('turtle_breakout') or 'NONE').upper()
    if trend == 'ALTA' and turtle == 'BUY':
        score += 8
        reasons.append(tech.get('turtle_reason') or 'Turtle HH20/55 alinhado (C1+)')
    elif trend == 'BAIXA' and turtle == 'SELL':
        score += 8
        reasons.append(tech.get('turtle_reason') or 'Turtle LL20/55 alinhado (C1+)')

    if tech.get('ponto_continuo'):
        score += 6
        reasons.append(tech.get('ponto_continuo_reason') or 'Ponto Contínuo EMA21 (C1+)')

    if tech.get('anatomy_log') and tech.get('candle_anatomy_ok'):
        reasons.append(f"Anatomia ok: {tech.get('anatomy_log')} (C1+)")

    return score, reasons


def incremental_c2_bonus(tech_data: dict | None) -> tuple[int, list[str]]:
    """Cérebro 2 (livro/volume/fluxo): liquidez SMC + FVG — só bônus, sem apagar VWAP."""
    tech = tech_data or {}
    trend = _trend(tech)
    score = 0
    reasons: list[str] = []

    if tech.get('liquidity_log'):
        reasons.append(str(tech.get('liquidity_log')))

    if tech.get('liquidity_ok', True) and not tech.get('liquidity_blocked'):
        if trend == 'ALTA' and tech.get('grab_reversal') == 'BUY':
            score += 8
            reasons.append(tech.get('sweep_reason') or 'Liquidity grab SSL → reversão alta (C2+)')
        elif trend == 'BAIXA' and tech.get('grab_reversal') == 'SELL':
            score += 8
            reasons.append(tech.get('sweep_reason') or 'Liquidity grab BSL → reversão baixa (C2+)')
        elif tech.get('fvg_magnet') or (
            (trend == 'ALTA' and tech.get('fvg_bullish'))
            or (trend == 'BAIXA' and tech.get('fvg_bearish'))
        ):
            score += 5
            reasons.append(tech.get('fvg_reason') or 'FVG ímã alinhado (C2+)')

    if tech.get('sweep_bsl') and trend == 'ALTA':
        reasons.append('C2+ aviso: sweep BSL — não ser liquidez do topo')
    if tech.get('sweep_ssl') and trend == 'BAIXA':
        reasons.append('C2+ aviso: sweep SSL — não ser liquidez do fundo')

    return score, reasons


def incremental_c3_bonus(tech_data: dict | None) -> tuple[int, list[str]]:
    """Cérebro 3: confluência extra das novas estratégias — não troca as 5 clássicas."""
    tech = tech_data or {}
    trend = _trend(tech)
    score = 0
    reasons: list[str] = []
    turtle = str(tech.get('turtle_breakout') or 'NONE').upper()
    aligned = (
        (trend == 'ALTA' and turtle == 'BUY')
        or (trend == 'BAIXA' and turtle == 'SELL')
    )
    if aligned:
        score += 6
        reasons.append('C3+ Turtle na direção')
    if tech.get('ponto_continuo'):
        score += 6
        reasons.append('C3+ Ponto Contínuo')
    if tech.get('liquidity_ok', True) and not tech.get('liquidity_blocked'):
        score += 4
        reasons.append('C3+ liquidez limpa (sem sweep contra)')
    return score, reasons


def summarize_incremental(tech_data: dict | None) -> dict[str, Any]:
    """Snapshot para dashboard /api/status — camada extra, não um 4º cérebro."""
    tech = tech_data or {}
    return {
        'camada': 'incremental_triplo_cerebro',
        'nao_substitui': ['sma200', 'supertrend', 'portas_1_5', 'vwap', 'groq', 'gemini'],
        'turtle': tech.get('turtle_reason') or tech.get('turtle_breakout'),
        'liquidity': tech.get('liquidity_log') or tech.get('sweep_reason') or '',
        'anatomy': tech.get('anatomy_log') or tech.get('candle_anatomy_reason') or '',
        'ponto_continuo': tech.get('ponto_continuo_reason') or '',
        'fib_depth': tech.get('fib_depth'),
        'atr_20': tech.get('atr_20'),
        'grab_reversal': tech.get('grab_reversal'),
    }
