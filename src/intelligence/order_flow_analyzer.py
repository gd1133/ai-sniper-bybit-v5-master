# -*- coding: utf-8 -*-
"""
Subsistema Groq — análise de fluxo ultra-rápido (Order Book + agressões).

Incremental: não substitui whale_detector nem confluence_absoluta.
Retorna JSON estrito para o Cérebro 3 modular a probabilidade (peso ~20%).
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

try:
    from groq import Groq
except Exception:
    Groq = None

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
    }


def _parse_flow_json(text: str) -> dict | None:
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
            'source': 'groq',
            'reason': 'Groq order-flow JSON',
            'available': True,
        }
    except (TypeError, ValueError):
        return None


def analyze_order_book_flow(
    symbol: str,
    order_book: dict | None = None,
    signals: dict | None = None,
    aggressions_summary: str = '',
) -> dict[str, Any]:
    """
    Analisa order book via Groq (JSON estrito) com fallback local.
    Desligável: ENABLE_GROQ_FLOW_AI=false
    """
    if not _env_bool('ENABLE_GROQ_FLOW_AI', True):
        return _local_flow_from_book(order_book, signals)

    cache_key = f"{symbol}:{bool(order_book)}"
    now = time.time()
    if cache_key in _CACHE and (now - _CACHE[cache_key][0]) < _CACHE_TTL:
        return _CACHE[cache_key][1]

    local = _local_flow_from_book(order_book, signals)
    groq_key = os.getenv('GROQ_API_KEY', '').strip()
    if not groq_key or Groq is None:
        _CACHE[cache_key] = (now, local)
        return local

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
    try:
        client = Groq(api_key=groq_key)
        rsp = client.chat.completions.create(
            model=os.getenv('GROQ_FLOW_MODEL', 'llama-3.3-70b-versatile'),
            messages=[
                {'role': 'system', 'content': GROQ_FLOW_SYSTEM},
                {'role': 'user', 'content': user_payload},
            ],
            temperature=0.1,
            max_tokens=220,
        )
        parsed = _parse_flow_json((rsp.choices[0].message.content or ''))
        if parsed:
            # Mistura leve com local para estabilidade
            parsed['score_fluxo'] = round(
                0.75 * float(parsed['score_fluxo']) + 0.25 * float(local.get('score_fluxo', 0)),
                4,
            )
            _CACHE[cache_key] = (now, parsed)
            return parsed
    except Exception as exc:
        print(f'⚠️ [GROQ FLOW] indisponível: {exc}', flush=True)

    _CACHE[cache_key] = (now, local)
    return local
