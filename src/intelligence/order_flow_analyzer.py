# -*- coding: utf-8 -*-
"""
Subsistema Groq — análise de fluxo ultra-rápido (Order Book + agressões).

Incremental: não substitui whale_detector nem confluence_absoluta.
Retorna JSON estrito para o Cérebro 3 modular a probabilidade (peso ~20%).

Resiliência: Groq → Gemini (opcional) → order book local → sinais técnicos.
Falha de IA NUNCA aborta ordem se hard-gates (Portas 1–5) já aprovaram.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

from src.intelligence.groq_client import groq_chat_completion, log_groq_degraded

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 45.0  # fluxo muda rápido

GROQ_FLOW_SYSTEM = """Você é o subsistema de análise de fluxo ultra-rápido do Motor Sniper. Sua função é analisar o Order Book (Livro de Ordens) e as últimas agressões de mercado enviadas pelo usuário.
Identifique onde os investidores estão empurrando o preço através de ordens a mercado (agressão) ou defendendo posições (absorção).

Retorne EXCLUSIVAMENTE um objeto JSON válido, sem qualquer texto explicativo antes ou depois, com a seguinte estrutura:
{
  "score_fluxo": -1.0 a 1.0,
  "forca_agressao": 0 a 100,
  "zona_defesa_institucional": true/false,
  "alerta_liquidacao": true/false
}"""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _neutral_flow(reason: str = 'fluxo neutro') -> dict[str, Any]:
    return {
        'score_fluxo': 0.0,
        'forca_agressao': 0.0,
        'zona_defesa_institucional': False,
        'alerta_liquidacao': False,
        'source': 'neutral',
        'reason': reason,
        'available': False,
        'liquidity_ok': True,
        'groq_degraded': False,
    }


def _summarize_order_book(order_book: dict | None, limit: int = 10) -> str:
    if not order_book:
        return 'Order book indisponível.'
    bids = list(order_book.get('bids') or [])[:limit]
    asks = list(order_book.get('asks') or [])[:limit]

    def _sz(levels):
        total = 0.0
        lines = []
        for lv in levels:
            try:
                price = float(lv[0])
                qty = float(lv[1])
            except (TypeError, ValueError, IndexError):
                continue
            total += qty
            lines.append(f'{price:.6g}@{qty:.4g}')
        return total, lines

    bid_sz, bid_lines = _sz(bids)
    ask_sz, ask_lines = _sz(asks)
    imbalance = (bid_sz - ask_sz) / (bid_sz + ask_sz + 1e-9)
    return (
        f'Imbalance top{limit}: {imbalance:+.3f} (bids={bid_sz:.4g} asks={ask_sz:.4g})\n'
        f'Bids: {", ".join(bid_lines[:6]) or "-"}\n'
        f'Asks: {", ".join(ask_lines[:6]) or "-"}'
    )


def _local_flow_from_book(order_book: dict | None, signals: dict | None) -> dict[str, Any]:
    """Fallback matemático sem cloud — mantém o robô vivo."""
    signals = signals or {}
    if not order_book:
        vol_r = float(signals.get('volume_ratio', 1) or 1)
        score = 0.0
        if vol_r >= 1.5 and str(signals.get('trend', '')).upper() == 'ALTA':
            score = 0.25
        elif vol_r >= 1.5 and str(signals.get('trend', '')).upper() == 'BAIXA':
            score = -0.25
        return {
            **_neutral_flow('fallback local sem order book'),
            'score_fluxo': score,
            'forca_agressao': min(100.0, max(0.0, (vol_r - 1.0) * 40)),
            'source': 'local_volume',
            'available': True,
            'groq_degraded': True,
        }

    bids = list(order_book.get('bids') or [])[:15]
    asks = list(order_book.get('asks') or [])[:15]
    bid_sz = sum(float(x[1]) for x in bids if len(x) >= 2)
    ask_sz = sum(float(x[1]) for x in asks if len(x) >= 2)
    imb = (bid_sz - ask_sz) / (bid_sz + ask_sz + 1e-9)
    score = max(-1.0, min(1.0, imb * 1.5))
    force = min(100.0, abs(imb) * 120)
    defense = abs(imb) >= 0.35 and (bid_sz + ask_sz) > 0
    return {
        'score_fluxo': round(score, 4),
        'forca_agressao': round(force, 2),
        'zona_defesa_institucional': bool(defense),
        'alerta_liquidacao': bool(abs(imb) >= 0.55 and force >= 70),
        'source': 'local_order_book',
        'reason': f'imbalance local {imb:+.3f}',
        'available': True,
        'groq_degraded': True,
    }


def _technical_flow_from_signals(signals: dict | None) -> dict[str, Any]:
    """Fallback puro das Portas 1–5 / sinais técnicos quando cloud indisponível."""
    signals = signals or {}
    trend = str(signals.get('trend', 'NEUTRO')).upper()
    vol_r = float(signals.get('volume_ratio', 1) or 1)
    adx = float(signals.get('adx', 0) or 0)
    score = 0.0
    if trend == 'ALTA' and vol_r >= 1.2:
        score = 0.15 + min(0.35, (vol_r - 1.0) * 0.2)
    elif trend == 'BAIXA' and vol_r >= 1.2:
        score = -(0.15 + min(0.35, (vol_r - 1.0) * 0.2))
    force = min(100.0, max(0.0, vol_r * 25 + adx * 0.5))
    return {
        'score_fluxo': round(max(-1.0, min(1.0, score)), 4),
        'forca_agressao': round(force, 2),
        'zona_defesa_institucional': bool(signals.get('sinal_institucional')),
        'alerta_liquidacao': bool(signals.get('grab_reversal')),
        'source': 'technical_gates',
        'reason': f'fallback técnico trend={trend} vol×={vol_r:.2f} ADX={adx:.0f}',
        'available': True,
        'groq_degraded': True,
    }


def _parse_flow_json(text: str, source: str = 'groq') -> dict | None:
    text = (text or '').strip()
    text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(text)
    except Exception:
        m = re.search(r'\{.*\}', text, flags=re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    try:
        score = float(data.get('score_fluxo', 0) or 0)
        score = max(-1.0, min(1.0, score))
        force = float(data.get('forca_agressao', 0) or 0)
        force = max(0.0, min(100.0, force))
        return {
            'score_fluxo': score,
            'forca_agressao': force,
            'zona_defesa_institucional': bool(data.get('zona_defesa_institucional', False)),
            'alerta_liquidacao': bool(data.get('alerta_liquidacao', False)),
            'source': source,
            'reason': f'{source} order-flow JSON',
            'available': True,
            'groq_degraded': source != 'groq',
        }
    except (TypeError, ValueError):
        return None


def _gemini_flow_fallback(symbol: str, user_payload: str) -> dict | None:
    """Segundo tier cloud — Gemini analisa order book quando Groq falha."""
    if not _env_bool('ENABLE_GEMINI_FLOW_FALLBACK', True):
        return None
    gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not gemini_key:
        return None
    try:
        model = os.getenv('GEMINI_FLOW_MODEL', os.getenv('GEMINI_MACRO_MODEL', 'gemini-2.0-flash'))
        url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'{model}:generateContent?key={gemini_key}'
        )
        prompt = f'{GROQ_FLOW_SYSTEM}\n\nSímbolo: {symbol}\n{user_payload}'
        rsp = requests.post(
            url,
            json={
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 220},
            },
            timeout=12,
        )
        if rsp.status_code != 200:
            return None
        parts = (rsp.json().get('candidates') or [{}])[0].get('content', {}).get('parts') or []
        text = ' '.join(str(p.get('text', '')) for p in parts).strip()
        parsed = _parse_flow_json(text, source='gemini_flow')
        if parsed:
            parsed['groq_degraded'] = True
            parsed['reason'] = f'Gemini fallback (Groq indisponível) — {parsed.get("reason", "")}'
        return parsed
    except Exception as exc:
        print(f'⚠️ [GROQ FLOW] Gemini fallback indisponível: {exc}', flush=True)
        return None


def _call_groq_flow(symbol: str, user_payload: str) -> dict | None:
    result = groq_chat_completion(
        messages=[
            {'role': 'system', 'content': GROQ_FLOW_SYSTEM},
            {'role': 'user', 'content': user_payload},
        ],
        purpose='flow',
        temperature=0.1,
        max_tokens=220,
    )
    if result.get('ok'):
        parsed = _parse_flow_json(result.get('content') or '', source='groq')
        if parsed:
            parsed['groq_model'] = result.get('model')
            parsed['groq_degraded'] = False
            return parsed
        return None
    log_groq_degraded('GROQ FLOW', result, symbol=symbol)
    return None


def analyze_order_book_flow(
    symbol: str,
    order_book: dict | None = None,
    signals: dict | None = None,
    aggressions_summary: str = '',
    df=None,
    hard_gates_approved: bool = False,
) -> dict[str, Any]:
    """
    Analisa order book via Groq (JSON estrito) com fallback Gemini → local → técnico.
    Anexa BSL/SSL, sweep e FVG quando há OHLCV.
    Desligável: ENABLE_GROQ_FLOW_AI=false

    hard_gates_approved: quando True, falha de IA nunca retorna available=False.
    """
    def _finish(payload: dict) -> dict:
        out = enrich_flow_with_liquidity(payload, df=df, signals=signals)
        if hard_gates_approved and not out.get('available', True):
            tech = _technical_flow_from_signals(signals)
            out.update(tech)
            out['reason'] = f"hard-gates OK — {out.get('reason', tech.get('reason', ''))}"
        return out

    if not _env_bool('ENABLE_GROQ_FLOW_AI', True):
        local = _local_flow_from_book(order_book, signals)
        local['groq_degraded'] = True
        local['reason'] = 'ENABLE_GROQ_FLOW_AI=false — fluxo local'
        return _finish(local)

    cache_key = f"{symbol}:{bool(order_book)}"
    now = time.time()
    if cache_key in _CACHE and (now - _CACHE[cache_key][0]) < _CACHE_TTL:
        cached = dict(_CACHE[cache_key][1])
        cached['from_cache'] = True
        return _finish(cached)

    local = _local_flow_from_book(order_book, signals)
    groq_key = os.getenv('GROQ_API_KEY', '').strip()
    if not groq_key:
        print(
            f'⚠️ [GROQ FLOW] {symbol}: GROQ_API_KEY ausente → fallback local '
            f'(execução continua se hard-gates OK)',
            flush=True,
        )
        _CACHE[cache_key] = (now, local)
        return _finish(local)

    book_txt = _summarize_order_book(order_book)
    sig = signals or {}
    user_payload = (
        f'Símbolo: {symbol}\n'
        f'Tendência técnica: {sig.get("trend")}\n'
        f'Volume ratio: {sig.get("volume_ratio")}\n'
        f'Sinal institucional: {sig.get("sinal_institucional")}\n'
        f'{book_txt}\n'
        f'Agressões recentes: {aggressions_summary or "n/d"}'
    )

    parsed = _call_groq_flow(symbol, user_payload)
    if parsed:
        parsed['score_fluxo'] = round(
            0.75 * float(parsed['score_fluxo']) + 0.25 * float(local.get('score_fluxo', 0)),
            4,
        )
        _CACHE[cache_key] = (now, parsed)
        return _finish(parsed)

    # Groq falhou — tenta Gemini
    gemini_parsed = _gemini_flow_fallback(symbol, user_payload)
    if gemini_parsed:
        gemini_parsed['score_fluxo'] = round(
            0.70 * float(gemini_parsed['score_fluxo'])
            + 0.30 * float(local.get('score_fluxo', 0)),
            4,
        )
        print(
            f'⚠️ [GROQ FLOW] {symbol}: Groq indisponível — usando Gemini fallback '
            f'(execução continua se hard-gates OK)',
            flush=True,
        )
        _CACHE[cache_key] = (now, gemini_parsed)
        return _finish(gemini_parsed)

    # Fallback final: order book local ou sinais técnicos das portas
    fallback = local if order_book else _technical_flow_from_signals(signals)
    print(
        f'⚠️ [GROQ FLOW] {symbol}: cloud indisponível → '
        f"fallback {fallback.get('source')} score={fallback.get('score_fluxo'):+.2f} "
        f'(execução continua se hard-gates OK)',
        flush=True,
    )
    _CACHE[cache_key] = (now, fallback)
    return _finish(fallback)


def identify_liquidity_zones(df):
    """BSL acima de swing highs / SSL abaixo de swing lows."""
    from src.engine.liquidity_smc import identify_liquidity_zones as _zones
    return _zones(df)


def detect_liquidity_sweep(df, zones=None):
    """Pavio longo além do nível + retorno = grab (invalida breakout)."""
    from src.engine.liquidity_smc import detect_liquidity_sweep as _sweep
    return _sweep(df, zones)


def detect_fvg_magnets(df):
    """Fair Value Gaps como zonas ímã de retorno de preço."""
    from src.engine.liquidity_smc import detect_fair_value_gaps
    return detect_fair_value_gaps(df)


def enrich_flow_with_liquidity(flow: dict | None, df=None, signals: dict | None = None) -> dict[str, Any]:
    """Anexa zonas SMC ao JSON de fluxo (Groq ou local) para o dashboard."""
    out = dict(flow or _neutral_flow())
    if df is None:
        return out
    try:
        from src.engine.liquidity_smc import analyze_smart_money_liquidity
        liq = analyze_smart_money_liquidity(df, signals)
        out.update({
            'bsl': liq.get('bsl'),
            'ssl': liq.get('ssl'),
            'sweep_bsl': liq.get('sweep_bsl'),
            'sweep_ssl': liq.get('sweep_ssl'),
            'grab_reversal': liq.get('grab_reversal'),
            'fvg_bullish': liq.get('fvg_bullish'),
            'fvg_bearish': liq.get('fvg_bearish'),
            'fvg_magnet': liq.get('fvg_magnet'),
            'triple_top': liq.get('triple_top'),
            'liquidity_ok': liq.get('liquidity_ok', True),
            'liquidity_log': liq.get('liquidity_log') or '',
        })
        if liq.get('sweep_reason'):
            out['reason'] = liq['sweep_reason']
        if liq.get('sweep_bsl') or liq.get('sweep_ssl'):
            out['alerta_liquidacao'] = True
    except Exception as err:
        out['liquidity_log'] = f'liquidez indisponível: {err}'
    return out
