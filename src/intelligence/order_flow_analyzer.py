# -*- coding: utf-8 -*-
"""
Subsistema de análise de fluxo (Order Book + agressões).

Prioridade:
1) Abacus Agent (quando habilitado)
2) Fallback local por order book
3) Fallback técnico por sinais

Falha de IA nunca interrompe execução quando hard-gates já aprovaram.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from src.intelligence.abacus_agent_client import abacus_agent_chat

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 45.0
_FLOW_DEGRADED_LOGGED_UNTIL = 0.0

FLOW_SYSTEM_PROMPT = """Você é o subsistema de análise de fluxo ultra-rápido do Motor Sniper.
Analise o Order Book (Livro de Ordens) e agressões recentes.
Retorne EXCLUSIVAMENTE JSON válido com:
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
        'ai_flow_degraded': False,
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
            'ai_flow_degraded': True,
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
        'ai_flow_degraded': True,
    }


def _technical_flow_from_signals(signals: dict | None) -> dict[str, Any]:
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
        'ai_flow_degraded': True,
    }


def _parse_flow_json(text: str, source: str = 'abacus_flow') -> dict | None:
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
            'ai_flow_degraded': False,
        }
    except (TypeError, ValueError):
        return None


def _call_abacus_flow(symbol: str, user_payload: str) -> dict | None:
    prompt = (
        f'{FLOW_SYSTEM_PROMPT}\n\n'
        f'Símbolo: {symbol}\n'
        f'{user_payload}\n\n'
        'Retorne apenas o JSON solicitado.'
    )
    try:
        text = abacus_agent_chat(prompt, purpose='order_flow')
        if not text:
            return None
        parsed = _parse_flow_json(text, source='abacus_flow')
        if parsed:
            parsed['reason'] = 'abacus_agent order-flow JSON'
            return parsed
    except Exception as exc:
        print(f'⚠️ [FLOW] Abacus Agent indisponível: {exc}', flush=True)
    return None


def _log_flow_degraded_once(message: str) -> None:
    global _FLOW_DEGRADED_LOGGED_UNTIL
    now = time.time()
    if now < _FLOW_DEGRADED_LOGGED_UNTIL:
        return
    print(message, flush=True)
    _FLOW_DEGRADED_LOGGED_UNTIL = now + 300.0


def analyze_order_book_flow(
    symbol: str,
    order_book: dict | None = None,
    signals: dict | None = None,
    aggressions_summary: str = '',
    df=None,
    hard_gates_approved: bool = False,
) -> dict[str, Any]:
    """
    Analisa fluxo via Abacus Agent com fallback local/técnico.
    """

    def _finish(payload: dict) -> dict:
        out = enrich_flow_with_liquidity(payload, df=df, signals=signals)
        # Alias de compatibilidade com partes legadas do projeto
        out['groq_degraded'] = bool(out.get('ai_flow_degraded', False))
        return out

    cache_key = f"{symbol}:{bool(order_book)}"
    now = time.time()
    if cache_key in _CACHE and (now - _CACHE[cache_key][0]) < _CACHE_TTL:
        cached = dict(_CACHE[cache_key][1])
        cached['from_cache'] = True
        return _finish(cached)

    local = _local_flow_from_book(order_book, signals)

    if not hard_gates_approved:
        local['reason'] = 'hard-gates pendentes — fluxo local'
        _CACHE[cache_key] = (now, local)
        return _finish(local)

    parsed = None
    if _env_bool('ABACUS_AGENT_ENABLED', True):
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
        parsed = _call_abacus_flow(symbol, user_payload)

    if parsed:
        parsed['score_fluxo'] = round(
            0.75 * float(parsed['score_fluxo']) + 0.25 * float(local.get('score_fluxo', 0)),
            4,
        )
        parsed['reason'] = f"{parsed.get('reason', 'abacus_agent')} + blend local"
        _CACHE[cache_key] = (now, parsed)
        return _finish(parsed)

    fallback = local if order_book else _technical_flow_from_signals(signals)
    _log_flow_degraded_once(
        f'⚠️ [FLOW] Abacus indisponível → fallback {fallback.get("source")} '
        f'score={fallback.get("score_fluxo"):+.2f} (execução continua)'
    )
    _CACHE[cache_key] = (now, fallback)
    return _finish(fallback)


def identify_liquidity_zones(df):
    from src.engine.liquidity_smc import identify_liquidity_zones as _zones
    return _zones(df)


def detect_liquidity_sweep(df, zones=None):
    from src.engine.liquidity_smc import detect_liquidity_sweep as _sweep
    return _sweep(df, zones)


def detect_fvg_magnets(df):
    from src.engine.liquidity_smc import detect_fair_value_gaps
    return detect_fair_value_gaps(df)


def enrich_flow_with_liquidity(flow: dict | None, df=None, signals: dict | None = None) -> dict[str, Any]:
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
    except Exception:
        pass
    return out
