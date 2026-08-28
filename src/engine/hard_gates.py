# -*- coding: utf-8 -*-
"""
Motor Sniper — Portas de filtragem sequencial.

Modo consultivo (default): métricas descritivas → Cérebro 3 decide.
Modo legado (ADVISORY_GATES=false): short-circuit absoluto Portas 1–5.
"""

from __future__ import annotations

import os
from typing import Any

from src.engine.structure_config import (
    STRUCTURE_ADX_MIN,
    STRUCTURE_REQUIRE_BB_EXPAND,
    DEFAULT_AMPLITUDE_PCT_MAX,
)


def _advisory_mode() -> bool:
    return str(os.getenv('ADVISORY_GATES', 'true')).strip().lower() in {'1', 'true', 'yes', 'on'}


INSTITUTIONAL_BUY = 'COMPRA_INSTITUCIONAL'
INSTITUTIONAL_SELL = 'VENDA_INSTITUCIONAL'
NEUTRO = 'NEUTRO'


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def evaluate_hard_gates(signals: dict | None, df=None) -> dict[str, Any]:
    """
    Avalia portas. Modo consultivo (default): nunca bloqueia — só métricas.
    Modo legado: short-circuit na primeira porta fechada.
    """
    if _advisory_mode():
        from src.engine.context_enrichment import evaluate_gates_advisory
        return evaluate_gates_advisory(signals, df=df)

    return _evaluate_hard_gates_legacy(signals, df=df)


def _evaluate_hard_gates_legacy(signals: dict | None, df=None) -> dict[str, Any]:
    signals = signals or {}
    adx = _f(signals.get('adx'))
    bb_width = _f(signals.get('bollinger_bandwidth'))
    bb_mean = _f(signals.get('bollinger_bandwidth_mean_50'))
    amplitude = _f(signals.get('amplitude_pct'))
    sinal = str(signals.get('sinal_institucional', NEUTRO) or NEUTRO).upper()
    adx_min = float(STRUCTURE_ADX_MIN)
    amp_min = float(DEFAULT_AMPLITUDE_PCT_MAX)

    adx_ok = bool(signals.get('adx_gate_pass')) or adx >= adx_min
    bb_ok = True if not STRUCTURE_REQUIRE_BB_EXPAND else bool(signals.get('bollinger_expanding'))
    amp_ok = not bool(
        signals.get('is_accumulation')
        or signals.get('is_lateral_amplitude')
        or signals.get('amplitude_lateral')
    )
    # Se amplitude veio zerada sem flag, ainda exige >= limite quando disponível
    if amplitude > 0 and amplitude < amp_min:
        amp_ok = False

    volume_ok = bool(signals.get('big_player_ativo'))
    try:
        sigma = float(signals.get('porta3_vol_sigma') or 0) or None
    except (TypeError, ValueError):
        sigma = None
    if sigma is None:
        try:
            from src.engine.porta3_adaptive import resolve_porta3_sigma
            sigma = resolve_porta3_sigma()
        except Exception:
            sigma = 1.15
    side_ok = sinal in (INSTITUTIONAL_BUY, INSTITUTIONAL_SELL)

    # Porta 5 — anatomia da vela (cor + sombra + falling knife)
    anatomy = _evaluate_anatomy_gate(signals, sinal, df=df)
    anatomy_ok = bool(anatomy.get('allowed'))

    ports = {
        'porta1_adx': {
            'pass': adx_ok,
            'value': round(adx, 4),
            'rule': f'ADX(14) >= {adx_min:.0f}',
        },
        'porta1_bb_width': {
            'pass': bb_ok,
            'value': round(bb_width, 8),
            'mean_50': round(bb_mean, 8),
            'rule': (
                'BB Width atual > média(50)'
                if STRUCTURE_REQUIRE_BB_EXPAND
                else 'BB expandindo opcional (STRUCTURE_REQUIRE_BB_EXPAND=false)'
            ),
        },
        'porta2_amplitude': {
            'pass': amp_ok,
            'value': round(amplitude, 4),
            'rule': f'amplitude((Hmax-Lmin)/Lmin)*100 >= {amp_min}%',
        },
        'porta3_volume': {
            'pass': volume_ok,
            'sigma': round(float(sigma), 2),
            'rule': f'Volume > MA(20) + {float(sigma):.1f}σ (só após Portas 1–2; adaptativo)',
        },
        'porta4_vwap_lado': {
            'pass': side_ok,
            'sinal': sinal,
            'rule': 'COMPRA: alta+close>VWAP+spread | VENDA: baixa+close<VWAP+spread',
        },
        'porta5_anatomia_vela': {
            'pass': anatomy_ok,
            'candle_color': anatomy.get('candle_color'),
            'falling_knife': anatomy.get('falling_knife'),
            'is_doubt_candle': anatomy.get('is_doubt_candle'),
            'body_conviction': anatomy.get('body_conviction'),
            'amplitude_dominance': anatomy.get('amplitude_dominance'),
            'reason': anatomy.get('abort_reason') or anatomy.get('anatomy_log') or 'ok',
            'rule': (
                'Amplitude (dominância vs ATR) + corpo (convicção); '
                'bloqueia vela de DÚVIDA; COMPRA=verde zona topo; VENDA=vermelha zona fundo'
            ),
        },
    }

    # Short-circuit na primeira porta fechada (ordem obrigatória)
    if not adx_ok:
        return _blocked(ports, NEUTRO, f'Porta 1 fechada: ADX(14)={adx:.2f} < {adx_min:.0f}')
    if not bb_ok:
        return _blocked(
            ports,
            NEUTRO,
            f'Porta 1 fechada: BB Width={bb_width:.6f} <= média(50)={bb_mean:.6f}',
        )
    if not amp_ok:
        return _blocked(
            ports,
            NEUTRO,
            f'Porta 2 fechada: amplitude={amplitude:.3f}% < {amp_min}% (acumulação)',
        )
    if not volume_ok:
        return _blocked(
            ports,
            NEUTRO,
            f'Porta 3 fechada: sem volume institucional (μ+{float(sigma):.1f}σ)',
        )
    if not side_ok:
        return _blocked(ports, NEUTRO, f'Porta 4 fechada: sinal={sinal} (sem lado vs VWAP)')
    if not anatomy_ok:
        reason = anatomy.get('abort_reason') or 'anatomia da vela inválida'
        return _blocked(ports, NEUTRO, f'Porta 5 fechada: {reason}')

    # Liquidez: não ser a caça de stops (sweep BSL/SSL no sentido da entrada)
    if sinal == INSTITUTIONAL_BUY and signals.get('liquidity_block_long'):
        reason = signals.get('sweep_reason') or 'sweep BSL — não comprar o rompimento falso'
        return _blocked(ports, NEUTRO, f'Liquidez: {reason}')
    if sinal == INSTITUTIONAL_SELL and signals.get('liquidity_block_short'):
        reason = signals.get('sweep_reason') or 'sweep SSL — não vender o breakdown falso'
        return _blocked(ports, NEUTRO, f'Liquidez: {reason}')

    return {
        'allowed': True,
        'sinal_institucional': sinal,
        'abort_reason': '',
        'short_circuit': False,
        'ports': ports,
        'structure_filters_pass': True,
        'candle_anatomy': anatomy,
    }


def _evaluate_anatomy_gate(signals: dict, sinal: str, df=None) -> dict[str, Any]:
    """Monta OHLC a partir de signals/df e avalia anatomia."""
    try:
        from src.engine.candle_anatomy import analyze_from_dataframe, evaluate_candle_anatomy
    except Exception as err:
        return {
            'allowed': False,
            'abort_reason': f'módulo candle_anatomy indisponível: {err}',
            'candle_color': 'DOJI',
            'falling_knife': False,
        }

    # Preferência: DataFrame completo (falling knife precisa de histórico)
    if df is not None and hasattr(df, 'iloc') and len(df) >= 1:
        return analyze_from_dataframe(df, sinal)

    # Fallback: OHLC embutido nos signals (+ arrays opcionais)
    open_p = _f(signals.get('candle_open', signals.get('open')))
    high = _f(signals.get('candle_high', signals.get('high')))
    low = _f(signals.get('candle_low', signals.get('low')))
    close = _f(signals.get('candle_close', signals.get('close', signals.get('price'))))
    return evaluate_candle_anatomy(
        sinal_institucional=sinal,
        open_p=open_p,
        high=high,
        low=low,
        close=close,
        opens=signals.get('candle_opens'),
        highs=signals.get('candle_highs'),
        lows=signals.get('candle_lows'),
        closes=signals.get('candle_closes'),
        atr=_f(signals.get('atr_20') or signals.get('atr')),
        fib_depth=_f(signals.get('fib_depth')),
    )


def _blocked(ports: dict, sinal: str, reason: str) -> dict[str, Any]:
    return {
        'allowed': False,
        'sinal_institucional': sinal,
        'abort_reason': reason,
        'short_circuit': True,
        'ports': ports,
        'structure_filters_pass': False,
    }


def institutional_entry_allowed(signals: dict | None, df=None) -> dict[str, Any]:
    """Alias semântico para o radar: True só com Smart Money completo."""
    return evaluate_hard_gates(signals, df=df)


def side_matches_institutional(side: str, sinal_institucional: str) -> bool:
    """BUY só com COMPRA_INSTITUCIONAL; SELL só com VENDA_INSTITUCIONAL."""
    side_n = str(side or '').strip().lower()
    sig = str(sinal_institucional or NEUTRO).upper()
    if side_n in ('buy', 'long', 'comprar'):
        return sig == INSTITUTIONAL_BUY
    if side_n in ('sell', 'short', 'vender'):
        return sig == INSTITUTIONAL_SELL
    return False


def is_neutro_signal(sinal: str | None) -> bool:
    sig = str(sinal or NEUTRO).strip().upper()
    return sig in (NEUTRO, '', 'NONE', 'NULL')
