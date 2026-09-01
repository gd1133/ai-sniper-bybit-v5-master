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


def _directional_bias(trend: str, short: str, st: int, rsi: float) -> str:
    """Bias direcional sem veto — macro, short, SuperTrend ou RSI."""
    if trend == 'ALTA':
        return 'BUY'
    if trend == 'BAIXA':
        return 'SELL'
    if short == 'ALTA' or st > 0:
        return 'BUY'
    if short == 'BAIXA' or st < 0:
        return 'SELL'
    if rsi <= 40:
        return 'BUY'
    if rsi >= 60:
        return 'SELL'
    return 'HOLD'


def _local_entry_decision(context: dict[str, Any]) -> dict[str, Any]:
    """
    Fallback matemático soberano.

    Com confluência gráfica: confiança dinâmica 50%–75% (nunca congelada sob o limiar).
    Sem confluência: HOLD com conf baixa (não opera).
    """
    c1 = context.get('cerebro1') or {}
    gates = context.get('gates_advisory') or {}
    snap = context.get('signals_snapshot') or {}
    c2 = context.get('cerebro2') or {}
    price = _f(context.get('price'))
    trend = str((c1.get('trend') or {}).get('macro', 'NEUTRO')).upper()
    short = str((c1.get('trend') or {}).get('short', 'NEUTRO')).upper()
    st = int((c1.get('trend') or {}).get('supertrend_signal', 0) or 0)
    rsi = _f((c1.get('momentum') or {}).get('rsi'), 50)
    adx = _f((c1.get('structure') or {}).get('adx'))
    vol_score = str(gates.get('volume_score') or snap.get('volume_score') or 'Normal')
    is_lateral = bool(gates.get('is_lateral') or (c1.get('structure') or {}).get('is_lateral'))
    atr = _f((c1.get('volatility_volume') or {}).get('atr'), price * 0.01)
    levels = c1.get('levels') or {}
    near_support = bool(levels.get('near_support') or snap.get('near_pivot_support'))
    near_resistance = bool(levels.get('near_resistance') or snap.get('near_pivot_resistance'))
    flow_bias = str(
        (c2.get('order_flow') or {}).get('bias')
        or snap.get('money_flow_side')
        or ''
    ).upper()

    action = 'HOLD'
    strat = 'TREND'
    confidence = 0.0
    rationale_extra = ''

    # ── Dump / derretimento → SHORT prioritário ──────────────────────────
    meltdown = bool(snap.get('meltdown') or snap.get('dump_lane') or snap.get('freefall'))
    melt_str = _f(snap.get('meltdown_strength'))
    if meltdown or melt_str >= 40:
        action, strat = 'SELL', 'BREAKOUT'
        confidence = 0.58 + min(0.12, melt_str / 500.0)
        if vol_score == 'Institucional':
            confidence += 0.06
        rationale_extra = f' dump/meltdown str={melt_str:.0f}'
    else:
        # Lateral / ADX fraco → RANGE; senão TREND (mesmo com macro NEUTRO)
        use_range = is_lateral or adx < 18
        bias = _directional_bias(trend, short, st, rsi)

        if use_range:
            strat = 'RANGE_BOUNCE'
            if rsi <= 32 or (rsi <= 40 and near_support):
                action = 'BUY'
                confidence = 0.55 + min(0.12, max(0.0, 40.0 - rsi) / 40.0 * 0.12)
                if near_support:
                    confidence += 0.06
            elif rsi >= 68 or (rsi >= 60 and near_resistance):
                action = 'SELL'
                confidence = 0.55 + min(0.12, max(0.0, rsi - 60.0) / 40.0 * 0.12)
                if near_resistance:
                    confidence += 0.06
            elif rsi <= 42 and bias == 'BUY':
                action, confidence = 'BUY', 0.52
            elif rsi >= 58 and bias == 'SELL':
                action, confidence = 'SELL', 0.52
            elif bias in ('BUY', 'SELL') and (adx >= 14 or vol_score in ('Normal', 'Institucional')):
                # Confluência leve: short/ST/fluxo — não fica preso em 35%
                action = bias
                confidence = 0.50 + (0.04 if vol_score == 'Institucional' else 0.02)
                if near_support and action == 'BUY':
                    confidence += 0.04
                if near_resistance and action == 'SELL':
                    confidence += 0.04
            if vol_score == 'Institucional' and action != 'HOLD':
                confidence += 0.04
        else:
            strat = 'TREND'
            ema_aligned_long = trend == 'ALTA' and st >= 0
            ema_aligned_short = trend == 'BAIXA' and st <= 0
            if adx >= 22 and ema_aligned_long and short in ('ALTA', 'NEUTRO'):
                action, confidence = 'BUY', 0.60
            elif adx >= 22 and ema_aligned_short and short in ('BAIXA', 'NEUTRO'):
                action, confidence = 'SELL', 0.60
            elif trend == 'ALTA' and short == 'ALTA':
                action, confidence = 'BUY', 0.58
            elif trend == 'BAIXA' and short == 'BAIXA':
                action, confidence = 'SELL', 0.58
            elif trend == 'ALTA' and rsi >= 48:
                action, confidence = 'BUY', 0.56
            elif trend == 'BAIXA' and rsi <= 52:
                action, confidence = 'SELL', 0.56
            elif bias == 'BUY' and (short == 'ALTA' or st > 0 or rsi >= 52):
                action, confidence = 'BUY', 0.54
            elif bias == 'SELL' and (short == 'BAIXA' or st < 0 or rsi <= 48):
                action, confidence = 'SELL', 0.54
            elif bias in ('BUY', 'SELL') and adx >= 20:
                # Macro NEUTRO mas ADX + short/ST/RSI — opera a favor do fluxo
                action, confidence = bias, 0.52
            elif rsi <= 35:
                action, confidence = 'BUY', 0.53
                strat = 'RANGE_BOUNCE'
            elif rsi >= 65:
                action, confidence = 'SELL', 0.53
                strat = 'RANGE_BOUNCE'
            if vol_score == 'Institucional' and action != 'HOLD':
                confidence += 0.04
            if adx >= 35 and action != 'HOLD':
                confidence += 0.05

        # Fluxo C2 / money flow reforça lado (nunca veta)
        if action != 'HOLD':
            if action == 'BUY' and flow_bias in ('BUY', 'LONG', 'COMPRA', 'BULLISH'):
                confidence += 0.03
            elif action == 'SELL' and flow_bias in ('SELL', 'SHORT', 'VENDA', 'BEARISH'):
                confidence += 0.03

    # Operável: sempre 50–75%. HOLD sem confluência: conf baixa explícita.
    if action in ('BUY', 'SELL'):
        confidence = max(0.50, min(0.75, confidence))
    else:
        confidence = min(0.34, max(0.0, confidence))

    sl_dist = max(atr * 1.5, price * 0.012)
    tp_dist = sl_dist * 2.2

    if action == 'BUY':
        sl, tp1, tp2 = price - sl_dist, price + tp_dist, price + tp_dist * 1.6
    elif action == 'SELL':
        sl, tp1, tp2 = price + sl_dist, price - tp_dist, price - tp_dist * 1.6
        if meltdown:
            vwap = _f(snap.get('vwap') or levels.get('vwap'))
            pivot_high = _f(levels.get('pivot_high') or price)
            sl = max(sl, vwap * 1.002 if vwap > 0 else 0, pivot_high * 1.001 if pivot_high > 0 else 0)
    else:
        sl = tp1 = tp2 = price

    return {
        'action': action,
        'confidence': round(confidence, 4),
        'strategy_type': strat,
        'entry_price': round(price, 8),
        'stop_loss': round(sl, 8),
        'take_profit_1': round(tp1, 8),
        'take_profit_2': round(tp2, 8),
        'invalidation_reason': '' if action != 'HOLD' else 'sem confluência gráfica mínima',
        'rationale': (
            f'Fallback local C3 | {strat} trend={trend} short={short} RSI={rsi:.0f} '
            f'ADX={adx:.0f} vol={vol_score} conf={confidence*100:.1f}%{rationale_extra}'
        ),
        'source': 'local_fallback',
    }


def c3_action_to_institutional(action_or_side: str) -> str:
    """Mapeia decisão soberana C3 → sinal estrutural para execução Bybit."""
    a = str(action_or_side or '').strip().upper()
    if a in ('BUY', 'COMPRAR', 'LONG'):
        return 'COMPRA_INSTITUCIONAL'
    if a in ('SELL', 'VENDER', 'SHORT'):
        return 'VENDA_INSTITUCIONAL'
    return 'NEUTRO'


def apply_dump_lane_override(
    res: dict[str, Any],
    signals: dict | None,
    prob: float,
) -> dict[str, Any]:
    """
    Inverte BUY → SELL quando dump/meltdown ativo.
    SL curto acima de VWAP/topo para SHORT.
    """
    signals = dict(signals or {})
    decisao = str(res.get('decisao', 'WAIT')).upper()
    side = 'sell' if decisao in ('SELL', 'VENDER') else (
        'buy' if decisao in ('BUY', 'COMPRAR') else 'wait'
    )

    meltdown = bool(
        signals.get('meltdown')
        or signals.get('dump_lane')
        or signals.get('freefall')
    )
    prefer_short = bool(signals.get('prefer_short')) or _f(signals.get('meltdown_strength')) >= 40
    if not meltdown and not prefer_short:
        return {'side': side, 'decisao': decisao, 'prob': prob, 'res': res, 'inverted': False}

    price = _f(signals.get('price') or res.get('entry_price'))
    vwap = _f(signals.get('vwap'))
    pivot_high = _f(signals.get('pivot_high') or signals.get('candle_high') or price)
    atr = _f(signals.get('atr_20') or signals.get('atr'), price * 0.01)

    if side == 'buy' or decisao in ('BUY', 'COMPRAR'):
        sl_short = price + max(atr * 1.2, price * 0.008)
        if vwap > price:
            sl_short = max(sl_short, vwap * 1.003)
        if pivot_high > price:
            sl_short = max(sl_short, pivot_high * 1.001)
        tp_dist = max(atr * 2.0, price * 0.015)
        new_dec = 'SELL'
        new_prob = max(prob, 55.0)
        c3 = dict(res.get('cerebro3_decision') or {})
        c3.update({
            'action': 'SELL',
            'decisao': 'SELL',
            'strategy_type': 'BREAKOUT',
            'confidence': new_prob / 100.0,
            'stop_loss': round(sl_short, 8),
            'take_profit_1': round(price - tp_dist, 8),
            'take_profit_2': round(price - tp_dist * 1.5, 8),
            'rationale': (
                f'DUMP-LANE: inversão BUY→SHORT | meltdown={meltdown} '
                f'str={_f(signals.get("meltdown_strength")):.0f}'
            ),
            'source': 'dump_lane_override',
        })
        new_res = dict(res)
        new_res.update({
            'decisao': new_dec,
            'probabilidade': new_prob,
            'motivo': c3['rationale'],
            'cerebro3_decision': c3,
            'strategy_type': 'BREAKOUT',
            'stop_loss': c3['stop_loss'],
        })
        return {
            'side': 'sell',
            'decisao': new_dec,
            'prob': new_prob,
            'res': new_res,
            'inverted': True,
        }

    return {'side': side, 'decisao': decisao, 'prob': prob, 'res': res, 'inverted': False}


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


def _call_gemini_tribunal(messages: list[dict]) -> dict | None:
    """Fallback Gemini quando Groq falha ou está em rate limit."""
    if not _env_bool('ENABLE_GEMINI_C3_FALLBACK', True):
        return None
    from src.intelligence.gemini_client import gemini_generate_text

    system = next((m.get('content', '') for m in messages if m.get('role') == 'system'), '')
    user = next((m.get('content', '') for m in messages if m.get('role') == 'user'), '')
    result = gemini_generate_text(
        f'{system}\n\n{user}',
        purpose='tribunal',
        temperature=0.15,
        max_tokens=int(os.getenv('CEREBRO3_MAX_TOKENS', '320') or 320),
    )
    if not result.get('ok'):
        status = result.get('status_code') or 0
        if status:
            print(
                f'⚠️ [C3] Gemini fallback HTTP {status} — fallback técnico local',
                flush=True,
            )
        return None
    parsed = _parse_decision_json(result.get('text') or '')
    if parsed:
        print(f'⚠️ [C3] Groq indisponível → Gemini ({result.get("model")})', flush=True)
    return parsed


def _call_llm(messages: list[dict], purpose: str = 'tribunal') -> dict | None:
    if not _env_bool('ENABLE_CEREBRO3_LLM', True):
        return None
    try:
        from src.intelligence.groq_client import groq_chat_completion, log_groq_degraded
        result = groq_chat_completion(
            messages=messages,
            purpose=purpose,
            temperature=0.15,
            max_tokens=int(os.getenv('CEREBRO3_MAX_TOKENS', '320') or 320),
        )
        if result.get('ok'):
            parsed = _parse_decision_json(result.get('content') or '')
            if parsed:
                return parsed
        elif not result.get('cooldown'):
            log_groq_degraded('C3 TRIBUNAL', result)
    except Exception as exc:
        print(f'⚠️ [C3] Groq erro: {exc}', flush=True)
    return _call_gemini_tribunal(messages)


def decide_entry(context: dict[str, Any]) -> dict[str, Any]:
    """Decisão principal de entrada — Cérebro 3."""
    price = _f(context.get('price'))

    from src.config.c3_mode import is_c3_solo_mode

    if is_c3_solo_mode():
        decision = _local_entry_decision(context)
        decision['source'] = 'c3_solo_local'
    else:
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
    intel = context.get('intel') or {}
    flow_ok = bool((intel.get('groq_flow') or intel.get('order_flow') or {}).get('available'))
    autonomous = bool(
        intel.get('force_assistants_unavailable')
        or (
            intel.get('autonomous_mode')
            and intel.get('ai_assistants_unavailable')
            and not flow_ok
        )
    )

    agents = [
        {
            'id': 'gemini',
            'label': 'Gemini Macro',
            'score': float((intel.get('gemini_macro') or {}).get('score_sentimento_noticias', 0) or 0) * 50 + 50,
            'action': 'WAIT',
            'motivo': str((intel.get('gemini_macro') or {}).get('motivo', 'contexto macro')),
        },
        {
            'id': 'groq',
            'label': 'Groq Tático',
            'score': float((intel.get('groq_flow') or {}).get('forca_agressao', 0) or 0),
            'action': 'WAIT',
            'motivo': str((intel.get('groq_flow') or {}).get('reason', 'fluxo de ordens')),
        },
        {
            'id': 'analyst',
            'label': 'Analista de Dados',
            'score': float(report_c1.get('score', 0) or 0),
            'action': report_c1.get('action', 'WAIT'),
            'motivo': str(report_c1.get('report', ''))[:200],
        },
        {
            'id': 'learner',
            'label': 'Aprendizado Neural',
            'score': float(decision.get('confidence', 0) or 0) * 100,
            'action': action if action in ('BUY', 'SELL') else 'WAIT',
            'motivo': str(decision.get('rationale') or decision.get('motivo', ''))[:200],
        },
    ]

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
        'autonomous_mode': autonomous,
        'agents': agents,
        'cerebro_reports': {
            'cerebro1': report_c1,
            'cerebro2': report_c2,
            'cerebro3': decision,
        },
        'brains': {
            'cerebro1': 'collector',
            'cerebro2': 'collector',
            'cerebro3': 'autonomous' if autonomous else 'leader',
        },
        'intelligence': intel,
    }
