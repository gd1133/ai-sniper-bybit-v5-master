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

from src.intelligence.abacus_agent_client import (
    abacus_agent_chat,
    parse_abacus_agent_json_response,
)

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


class PositionGuard:
    """Escada de lucro + kill-switch técnico para gestão ciclo a ciclo."""

    def __init__(self) -> None:
        self.level1_trigger_pct = _f(os.getenv('POSITION_GUARD_LEVEL1_TRIGGER_PCT'), 1.8)
        self.level1_partial_fraction = max(
            0.1,
            min(0.9, _f(os.getenv('POSITION_GUARD_LEVEL1_PARTIAL_FRACTION'), 0.40)),
        )
        self.level2_trigger_pct = _f(os.getenv('POSITION_GUARD_LEVEL2_TRIGGER_PCT'), 3.5)
        self.trailing_atr_mult = max(0.5, _f(os.getenv('POSITION_GUARD_TRAIL_ATR_MULT'), 1.5))
        self.fee_buffer_pct = max(0.0, _f(os.getenv('POSITION_GUARD_FEE_BUFFER_PCT'), 0.12))

    @staticmethod
    def _is_long(side: str) -> bool:
        return str(side or '').strip().lower() in ('buy', 'long', 'comprar')

    @staticmethod
    def _closed_df(df):
        if df is None or len(df) < 3:
            return None
        try:
            return df.iloc[:-1]
        except Exception:
            return df

    @staticmethod
    def _ema_series(values, span: int):
        try:
            import pandas as pd
            series = values if hasattr(values, 'astype') else pd.Series(values)
            return series.astype(float).ewm(span=int(span), adjust=False).mean()
        except Exception:
            return None

    @staticmethod
    def _atr_last(df, period: int = 14) -> float:
        if df is None or len(df) < period + 1:
            return 0.0
        try:
            high = df['high'].astype(float)
            low = df['low'].astype(float)
            close = df['close'].astype(float)
            prev = close.shift(1)
            tr_hl = (high - low).abs()
            tr_hc = (high - prev).abs()
            tr_lc = (low - prev).abs()
            tr = tr_hl.combine(tr_hc, max).combine(tr_lc, max)
            return _f(tr.tail(period).mean())
        except Exception:
            return 0.0

    def _breakeven_sl(self, entry_price: float, side: str) -> float:
        entry = _f(entry_price)
        if entry <= 0:
            return 0.0
        buf = self.fee_buffer_pct / 100.0
        if self._is_long(side):
            return entry * (1.0 + buf)
        return entry * (1.0 - buf)

    def _kill_switch(self, side: str, df_5m) -> dict[str, Any]:
        out = {'triggered': False, 'reason': ''}
        work = self._closed_df(df_5m)
        if work is None or len(work) < 25 or 'close' not in work.columns:
            return out
        try:
            close = work['close'].astype(float)
            open_ = work['open'].astype(float)
            vol_col = 'volume' if 'volume' in work.columns else ('vol' if 'vol' in work.columns else None)
            if not vol_col:
                return out
            vol = work[vol_col].astype(float)
            ema20 = self._ema_series(close, 20)
            if ema20 is None or len(ema20) < 2:
                return out

            last_close = _f(close.iloc[-1])
            last_open = _f(open_.iloc[-1])
            last_ema20 = _f(ema20.iloc[-1])
            last_vol = _f(vol.iloc[-1])
            vol_avg = _f(vol.iloc[:-1].tail(20).mean(), 0.0)
            vol_ratio = (last_vol / vol_avg) if vol_avg > 0 else 1.0

            is_long = self._is_long(side)
            if is_long and last_close < last_ema20 and vol_ratio >= 1.1:
                out['triggered'] = True
                out['reason'] = (
                    f'KILL_SWITCH_LONG: close 5m abaixo EMA20 ({last_close:.6g}<{last_ema20:.6g}) '
                    f'com volume acima da média (x{vol_ratio:.2f})'
                )
                return out

            buyer_volume = (last_close > last_open) and vol_ratio >= 1.1
            if (not is_long) and last_close > last_ema20 and buyer_volume:
                out['triggered'] = True
                out['reason'] = (
                    f'KILL_SWITCH_SHORT: close 5m acima EMA20 ({last_close:.6g}>{last_ema20:.6g}) '
                    f'com volume comprador (x{vol_ratio:.2f})'
                )
                return out
        except Exception:
            return out
        return out

    def _level3_exhaustion_or_reversal(self, side: str, df_5m) -> dict[str, Any]:
        out = {'triggered': False, 'reason': ''}
        work = self._closed_df(df_5m)
        if work is None or len(work) < 30:
            return out
        try:
            close = work['close'].astype(float)
            ema8 = self._ema_series(close, 8)
            ema20 = self._ema_series(close, 20)
            vol_col = 'volume' if 'volume' in work.columns else ('vol' if 'vol' in work.columns else None)
            if ema8 is None or ema20 is None or vol_col is None or len(work) < 4:
                return out

            prev_ema8 = _f(ema8.iloc[-2])
            prev_ema20 = _f(ema20.iloc[-2])
            last_ema8 = _f(ema8.iloc[-1])
            last_ema20 = _f(ema20.iloc[-1])

            is_long = self._is_long(side)
            cross_reversal = (
                (is_long and prev_ema8 >= prev_ema20 and last_ema8 < last_ema20)
                or ((not is_long) and prev_ema8 <= prev_ema20 and last_ema8 > last_ema20)
            )

            v = work[vol_col].astype(float)
            v1, v2, v3 = _f(v.iloc[-3]), _f(v.iloc[-2]), _f(v.iloc[-1])
            volume_exhaustion = v1 > v2 > v3 > 0

            if cross_reversal:
                out['triggered'] = True
                out['reason'] = 'NIVEL3_REVERSAO_EMA: cruzamento reverso EMA8/EMA20 na vela 5m fechada'
                return out
            if volume_exhaustion:
                out['triggered'] = True
                out['reason'] = (
                    f'NIVEL3_EXAUSTAO_VOLUME: 3 velas com volume decrescente ({v1:.3g}>{v2:.3g}>{v3:.3g})'
                )
                return out
        except Exception:
            return out
        return out

    def evaluate_position_cycle(
        self,
        *,
        side: str,
        entry_price: float,
        mark_price: float,
        roi_pct: float,
        df_5m=None,
        level1_done: bool = False,
        level2_done: bool = False,
    ) -> dict[str, Any]:
        entry = _f(entry_price)
        mark = _f(mark_price)
        roi = _f(roi_pct)
        out = {
            'action': 'HOLD',
            'motivo': '',
            'tipo_execucao': '',
            'sl_price': 0.0,
            'partial_fraction': self.level1_partial_fraction,
            'level1_done': bool(level1_done),
            'level2_done': bool(level2_done),
        }
        if entry <= 0 or mark <= 0:
            return out

        kill = self._kill_switch(side, df_5m)
        if kill.get('triggered'):
            out.update({
                'action': 'EARLY_EXIT',
                'tipo_execucao': 'KILL_SWITCH_TECNICO',
                'motivo': str(kill.get('reason') or ''),
            })
            return out

        if (not level1_done) and roi >= self.level1_trigger_pct:
            out.update({
                'action': 'PARTIAL_TP',
                'tipo_execucao': 'PROFIT_LADDER_N1',
                'motivo': (
                    f'Nível 1 acionado (ROI={roi:.2f}% >= {self.level1_trigger_pct:.2f}%). '
                    f'Realiza {self.level1_partial_fraction*100:.0f}% e arma breakeven.'
                ),
                'sl_price': self._breakeven_sl(entry, side),
                'level1_done': True,
            })
            return out

        if roi >= self.level2_trigger_pct:
            work = self._closed_df(df_5m)
            if work is not None and len(work) >= 25:
                close = work['close'].astype(float)
                ema8_series = self._ema_series(close, 8)
                ema8 = _f(ema8_series.iloc[-1]) if ema8_series is not None and len(ema8_series) else 0.0
                atr = self._atr_last(work, period=14)
                is_long = self._is_long(side)
                atr_anchor = (mark - self.trailing_atr_mult * atr) if is_long else (mark + self.trailing_atr_mult * atr)
                candidates = [x for x in (ema8, atr_anchor) if _f(x) > 0]
                if candidates:
                    sl = max(candidates) if is_long else min(candidates)
                    out.update({
                        'action': 'EXTEND_TRAILING',
                        'tipo_execucao': 'PROFIT_LADDER_N2',
                        'motivo': (
                            f'Nível 2 acionado (ROI={roi:.2f}% >= {self.level2_trigger_pct:.2f}%). '
                            f'Trailing ancorado em EMA8/ATR({self.trailing_atr_mult:.2f}x).'
                        ),
                        'sl_price': sl,
                        'level2_done': True,
                    })
                    if level2_done:
                        lvl3 = self._level3_exhaustion_or_reversal(side, df_5m)
                        if lvl3.get('triggered'):
                            out.update({
                                'action': 'EARLY_EXIT',
                                'tipo_execucao': 'PROFIT_LADDER_N3',
                                'motivo': str(lvl3.get('reason') or 'Nível 3 acionado'),
                            })
                    return out

        if level2_done:
            lvl3 = self._level3_exhaustion_or_reversal(side, df_5m)
            if lvl3.get('triggered'):
                out.update({
                    'action': 'EARLY_EXIT',
                    'tipo_execucao': 'PROFIT_LADDER_N3',
                    'motivo': str(lvl3.get('reason') or 'Nível 3 acionado'),
                })
                return out

        return out


def evaluate_position_guard(
    *,
    side: str,
    entry_price: float,
    mark_price: float,
    roi_pct: float,
    df_5m=None,
    level1_done: bool = False,
    level2_done: bool = False,
) -> dict[str, Any]:
    """Wrapper estável para uso no monitor de posições do runtime."""
    guard = PositionGuard()
    return guard.evaluate_position_cycle(
        side=side,
        entry_price=entry_price,
        mark_price=mark_price,
        roi_pct=roi_pct,
        df_5m=df_5m,
        level1_done=level1_done,
        level2_done=level2_done,
    )


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
        'source': str(raw.get('source') or 'llm'),
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


def _messages_to_abacus_text(messages: list[dict]) -> str:
    parts: list[str] = []
    for msg in messages or []:
        role = str(msg.get('role') or 'user').upper()
        content = str(msg.get('content') or '').strip()
        if content:
            parts.append(f'{role}:\n{content}')
    return '\n\n'.join(parts)


def _call_abacus_tribunal(messages: list[dict], purpose: str = 'tribunal') -> dict | None:
    prompt = _messages_to_abacus_text(messages)
    if not prompt:
        return None
    try:
        text = abacus_agent_chat(prompt, purpose=f'c3_{purpose}')
        if not text:
            return None
        parsed = parse_abacus_agent_json_response(text)
        if not parsed:
            parsed = _parse_decision_json(text)
        if parsed:
            parsed['source'] = 'abacus_agent'
            return parsed
    except Exception as exc:
        print(f'⚠️ [C3] Abacus Agent indisponível: {exc}', flush=True)
    return None


def _call_llm(messages: list[dict], purpose: str = 'tribunal') -> dict | None:
    """Camada LLM do C3: somente Abacus Agent (sem Groq/Gemini)."""
    if not _env_bool('ENABLE_CEREBRO3_LLM', True):
        return None
    return _call_abacus_tribunal(messages, purpose=purpose)


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
    intel = context.get('intel') or {}
    flow_ok = bool((intel.get('flow_ai') or intel.get('order_flow') or {}).get('available'))
    autonomous = bool(
        intel.get('force_assistants_unavailable')
        or (
            intel.get('autonomous_mode')
            and intel.get('ai_assistants_unavailable')
            and not flow_ok
        )
    )

    macro_ctx = intel.get('macro_ai') or {}
    flow_ctx = intel.get('flow_ai') or intel.get('order_flow') or {}

    agents = [
        {
            'id': 'macro',
            'label': 'Macro IA',
            'score': float(macro_ctx.get('score_sentimento_noticias', 0) or 0) * 50 + 50,
            'action': 'WAIT',
            'motivo': str(macro_ctx.get('motivo') or macro_ctx.get('narrativa_dominante') or 'contexto macro'),
        },
        {
            'id': 'flow',
            'label': 'Fluxo IA',
            'score': float(flow_ctx.get('forca_agressao', 0) or 0),
            'action': 'WAIT',
            'motivo': str(flow_ctx.get('reason', 'fluxo de ordens')),
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
