# -*- coding: utf-8 -*-
"""
Cérebro 3 — Analista Sênior / Gestor de Risco (decisor principal).

Recebe payload JSON dos Cérebros 1 e 2 e retorna decisão estruturada.
Fallback local quando LLM indisponível (Groq rate limit / sem API key).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

CEREBRO3_SYSTEM_PROMPT = """Você é um Analista Quantitativo Sênior e Gestor de Risco do Motor Sniper.
Analise o contexto técnico + sentimento e decida a operação.

Capacidades:
- TREND: seguir tendência forte (ADX alto, volume institucional)
- RANGE_BOUNCE: mercado lateral — comprar fundo / vender topo (RSI extremo + pivôs)
- BREAKOUT: rompimento com volume e confirmação estrutural
- Scalp de reversão quando momentum diverge do preço

Regras:
- HOLD se confluência insuficiente ou risco assimétrico desfavorável
- stop_loss e take_profit devem ser preços numéricos coerentes com entry_price
- confidence 0.0–1.0 reflete convicção real (não infle artificialmente)
- Em mercado LATERAL, prefira RANGE_BOUNCE se RSI/topos/fundos alinhados

Retorne EXCLUSIVAMENTE JSON válido (sem markdown):
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": float,
  "strategy_type": "TREND" | "RANGE_BOUNCE" | "BREAKOUT",
  "entry_price": float,
  "stop_loss": float,
  "take_profit_1": float,
  "take_profit_2": float,
  "invalidation_reason": string,
  "rationale": string
}"""

CEREBRO3_EXIT_PROMPT = """Você monitora uma posição ABERTA e decide gestão ativa.
Opções na action:
- HOLD: manter até TP/SL
- CLOSE: encerrar a mercado antecipadamente
- TRAIL: apertar trailing stop (descreva em invalidation_reason)

Retorne EXCLUSIVAMENTE JSON:
{
  "action": "HOLD" | "CLOSE" | "TRAIL",
  "confidence": float,
  "strategy_type": "TREND" | "RANGE_BOUNCE" | "BREAKOUT",
  "entry_price": float,
  "stop_loss": float,
  "take_profit_1": float,
  "take_profit_2": float,
  "invalidation_reason": string,
  "rationale": string
}"""


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _parse_decision_json(text: str) -> dict | None:
    text = (text or '').strip()
    text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    m = re.search(r'\{.*\}', text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _normalize_decision(raw: dict | None, price: float, *, exit_mode: bool = False) -> dict[str, Any]:
    raw = raw or {}
    action = str(raw.get('action', 'HOLD')).upper()
    if exit_mode:
        if action not in ('HOLD', 'CLOSE', 'TRAIL'):
            action = 'HOLD'
    elif action not in ('BUY', 'SELL', 'HOLD'):
        action = 'HOLD'

    try:
        confidence = max(0.0, min(1.0, float(raw.get('confidence', 0) or 0)))
    except (TypeError, ValueError):
        confidence = 0.0

    entry = _f(raw.get('entry_price'), price)
    if entry <= 0:
        entry = price

    strat = str(raw.get('strategy_type', 'TREND')).upper()
    if strat not in ('TREND', 'RANGE_BOUNCE', 'BREAKOUT'):
        strat = 'TREND'

    return {
        'action': action,
        'confidence': round(confidence, 4),
        'strategy_type': strat,
        'entry_price': round(entry, 8),
        'stop_loss': round(_f(raw.get('stop_loss')), 8),
        'take_profit_1': round(_f(raw.get('take_profit_1')), 8),
        'take_profit_2': round(_f(raw.get('take_profit_2')), 8),
        'invalidation_reason': str(raw.get('invalidation_reason') or ''),
        'rationale': str(raw.get('rationale') or ''),
        'source': 'llm',
    }


def _local_entry_decision(context: dict[str, Any]) -> dict[str, Any]:
    """Fallback matemático quando LLM indisponível."""
    c1 = context.get('cerebro1') or {}
    gates = context.get('gates_advisory') or {}
    price = _f(context.get('price'))
    trend = str((c1.get('trend') or {}).get('macro', 'NEUTRO')).upper()
    short = str((c1.get('trend') or {}).get('short', 'NEUTRO')).upper()
    rsi = _f((c1.get('momentum') or {}).get('rsi'), 50)
    adx = _f((c1.get('structure') or {}).get('adx'))
    vol_score = gates.get('volume_score', 'Normal')
    is_lateral = bool(gates.get('is_lateral'))
    atr = _f((c1.get('volatility_volume') or {}).get('atr'), price * 0.01)

    action = 'HOLD'
    strat = 'TREND'
    confidence = 0.35

    if is_lateral or adx < 20:
        strat = 'RANGE_BOUNCE'
        if rsi <= 32 and (c1.get('levels') or {}).get('near_support'):
            action, confidence = 'BUY', 0.52
        elif rsi >= 68 and (c1.get('levels') or {}).get('near_resistance'):
            action, confidence = 'SELL', 0.52
    elif trend == 'ALTA' and short == 'ALTA' and vol_score in ('Normal', 'Institucional'):
        action, confidence, strat = 'BUY', 0.58, 'TREND'
    elif trend == 'BAIXA' and short == 'BAIXA' and vol_score in ('Normal', 'Institucional'):
        action, confidence, strat = 'SELL', 0.58, 'TREND'
    elif vol_score == 'Institucional' and adx >= 22:
        if trend == 'ALTA':
            action, confidence, strat = 'BUY', 0.50, 'BREAKOUT'
        elif trend == 'BAIXA':
            action, confidence, strat = 'SELL', 0.50, 'BREAKOUT'

    sl_dist = max(atr * 1.5, price * 0.012)
    tp_dist = sl_dist * 2.2

    if action == 'BUY':
        sl, tp1, tp2 = price - sl_dist, price + tp_dist, price + tp_dist * 1.6
    elif action == 'SELL':
        sl, tp1, tp2 = price + sl_dist, price - tp_dist, price - tp_dist * 1.6
    else:
        sl = tp1 = tp2 = price

    return {
        'action': action,
        'confidence': confidence,
        'strategy_type': strat,
        'entry_price': round(price, 8),
        'stop_loss': round(sl, 8),
        'take_profit_1': round(tp1, 8),
        'take_profit_2': round(tp2, 8),
        'invalidation_reason': '',
        'rationale': (
            f'Fallback local C3 | {strat} trend={trend} RSI={rsi:.0f} '
            f'ADX={adx:.0f} vol={vol_score}'
        ),
        'source': 'local_fallback',
    }


def _local_exit_decision(context: dict[str, Any], position: dict) -> dict[str, Any]:
    roi = _f(position.get('roi_pct'))
    side = str(position.get('side', 'buy')).lower()
    is_long = side in ('buy', 'long')

    c1 = context.get('cerebro1') or {}
    rsi = _f((c1.get('momentum') or {}).get('rsi'), 50)
    trend = str((c1.get('trend') or {}).get('macro', 'NEUTRO')).upper()

    action = 'HOLD'
    if is_long and roi >= 15 and (rsi >= 75 or trend == 'BAIXA'):
        action = 'CLOSE'
    elif not is_long and roi >= 15 and (rsi <= 25 or trend == 'ALTA'):
        action = 'CLOSE'
    elif roi >= 80:
        action = 'TRAIL'

    return {
        'action': action,
        'confidence': 0.55 if action != 'HOLD' else 0.4,
        'strategy_type': 'TREND',
        'entry_price': _f(position.get('entry_price')),
        'stop_loss': _f(position.get('sl_price')),
        'take_profit_1': 0.0,
        'take_profit_2': 0.0,
        'invalidation_reason': f'ROI={roi:.1f}%',
        'rationale': f'Fallback local saída | RSI={rsi:.0f} trend={trend}',
        'source': 'local_fallback',
    }


def _call_llm(messages: list[dict], purpose: str = 'tribunal') -> dict | None:
    if not _env_bool('ENABLE_CEREBRO3_LLM', True):
        return None
    try:
        from src.intelligence.groq_client import groq_chat_completion
        result = groq_chat_completion(
            messages=messages,
            purpose=purpose,
            temperature=0.15,
            max_tokens=int(os.getenv('CEREBRO3_MAX_TOKENS', '320') or 320),
        )
        if result.get('ok'):
            return _parse_decision_json(result.get('content') or '')
    except Exception:
        pass
    return None


def decide_entry(context: dict[str, Any]) -> dict[str, Any]:
    """Decisão principal de entrada — Cérebro 3."""
    price = _f(context.get('price'))
    payload_txt = json.dumps(context, ensure_ascii=False, default=str)[:6000]
    user_msg = f'Contexto de mercado:\n{payload_txt}\n\nDecida BUY/SELL/HOLD com gestão de risco.'

    raw = _call_llm([
        {'role': 'system', 'content': CEREBRO3_SYSTEM_PROMPT},
        {'role': 'user', 'content': user_msg},
    ], purpose='tribunal')

    if raw:
        decision = _normalize_decision(raw, price, exit_mode=False)
    else:
        decision = _local_entry_decision(context)

    decision['probabilidade'] = round(decision['confidence'] * 100, 2)
    if decision['action'] == 'BUY':
        decision['decisao'] = 'BUY'
    elif decision['action'] == 'SELL':
        decision['decisao'] = 'SELL'
    else:
        decision['decisao'] = 'WAIT'
    return decision


def evaluate_exit(context: dict[str, Any], position: dict) -> dict[str, Any]:
    """Avaliação ativa de posição aberta."""
    position = position or {}
    payload = {
        'context': context,
        'position': {
            'side': position.get('side'),
            'entry_price': position.get('entry_price'),
            'mark_price': position.get('mark_price'),
            'roi_pct': position.get('roi_pct'),
            'age_secs': position.get('age_secs'),
            'trailing_armed': position.get('trailing_armed'),
        },
    }
    user_msg = json.dumps(payload, ensure_ascii=False, default=str)[:5000]

    raw = _call_llm([
        {'role': 'system', 'content': CEREBRO3_EXIT_PROMPT},
        {'role': 'user', 'content': user_msg},
    ], purpose='tribunal')

    price = _f(position.get('mark_price') or context.get('price'))
    if raw:
        return _normalize_decision(raw, price, exit_mode=True)
    return _local_exit_decision(context, position)


def decision_to_consensus(decision: dict, context: dict, report_c1: dict, report_c2: dict) -> dict:
    """Adapta decisão C3 para formato legado do radar."""
    action = str(decision.get('decisao') or decision.get('action', 'WAIT')).upper()
    prob = float(decision.get('probabilidade') or decision.get('confidence', 0) * 100)

    return {
        'probabilidade': prob,
        'decisao': 'BUY' if action in ('BUY', 'COMPRAR') else (
            'SELL' if action in ('SELL', 'VENDER') else 'WAIT'
        ),
        'motivo': decision.get('rationale') or decision.get('motivo', ''),
        'cerebro3_decision': decision,
        'strategy_type': decision.get('strategy_type'),
        'entry_price': decision.get('entry_price'),
        'stop_loss': decision.get('stop_loss'),
        'take_profit_1': decision.get('take_profit_1'),
        'take_profit_2': decision.get('take_profit_2'),
        'autonomous_mode': decision.get('source') == 'local_fallback',
        'agents': [],
        'cerebro_reports': {
            'cerebro1': report_c1,
            'cerebro2': report_c2,
            'cerebro3': decision,
        },
        'brains': {
            'cerebro1': 'collector',
            'cerebro2': 'collector',
            'cerebro3': 'leader',
        },
        'intelligence': context.get('intel') or {},
    }
