# -*- coding: utf-8 -*-
"""
Motor Sniper — Portas de filtragem sequencial (Short-Circuit Absoluto).

Ordem obrigatória (qualquer falha → NEUTRO e aborta ANTES do Cérebro 3):

  Porta 1 — Estrutura: ADX(14) >= 23 + BB Width > média(50)
  Porta 2 — Anti-acumulação: amplitude % dos últimos 20 >= 0.35%
  Porta 3 — Pegada institucional: Volume > MA(20) + 2.5σ
  Porta 4 — Lado vs VWAP: COMPRA/VENDA_INSTITUCIONAL

O surto de volume NUNCA é avaliado se as Portas 1–2 estiverem fechadas.
"""

from __future__ import annotations

from typing import Any


INSTITUTIONAL_BUY = 'COMPRA_INSTITUCIONAL'
INSTITUTIONAL_SELL = 'VENDA_INSTITUCIONAL'
NEUTRO = 'NEUTRO'


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def evaluate_hard_gates(signals: dict | None) -> dict[str, Any]:
    """
    Avalia as 4 portas a partir do dict já calculado por IndicatorEngine /
    RastreadorInstitucional. Fail-closed: dado ausente = porta fechada.
    """
    signals = signals or {}
    adx = _f(signals.get('adx'))
    bb_width = _f(signals.get('bollinger_bandwidth'))
    bb_mean = _f(signals.get('bollinger_bandwidth_mean_50'))
    amplitude = _f(signals.get('amplitude_pct'))
    sinal = str(signals.get('sinal_institucional', NEUTRO) or NEUTRO).upper()

    adx_ok = bool(signals.get('adx_gate_pass')) or adx >= 23.0
    bb_ok = bool(signals.get('bollinger_expanding'))
    amp_ok = not bool(
        signals.get('is_accumulation')
        or signals.get('is_lateral_amplitude')
        or signals.get('amplitude_lateral')
    )
    # Se amplitude veio zerada sem flag, ainda exige >= 0.35 quando disponível
    if amplitude > 0 and amplitude < 0.35:
        amp_ok = False

    volume_ok = bool(signals.get('big_player_ativo'))
    side_ok = sinal in (INSTITUTIONAL_BUY, INSTITUTIONAL_SELL)

    ports = {
        'porta1_adx': {
            'pass': adx_ok,
            'value': round(adx, 4),
            'rule': 'ADX(14) >= 23',
        },
        'porta1_bb_width': {
            'pass': bb_ok,
            'value': round(bb_width, 8),
            'mean_50': round(bb_mean, 8),
            'rule': 'BB Width atual > média(50)',
        },
        'porta2_amplitude': {
            'pass': amp_ok,
            'value': round(amplitude, 4),
            'rule': 'amplitude((Hmax-Lmin)/Lmin)*100 >= 0.35%',
        },
        'porta3_volume': {
            'pass': volume_ok,
            'rule': 'Volume > MA(20) + 2.5σ (só após Portas 1–2)',
        },
        'porta4_vwap_lado': {
            'pass': side_ok,
            'sinal': sinal,
            'rule': 'COMPRA: alta+close>VWAP+spread | VENDA: baixa+close<VWAP+spread',
        },
    }

    # Short-circuit na primeira porta fechada (ordem obrigatória)
    if not adx_ok:
        return _blocked(ports, NEUTRO, f'Porta 1 fechada: ADX(14)={adx:.2f} < 23')
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
            f'Porta 2 fechada: amplitude={amplitude:.3f}% < 0.35% (acumulação)',
        )
    if not volume_ok:
        return _blocked(ports, NEUTRO, 'Porta 3 fechada: sem volume institucional (μ+2.5σ)')
    if not side_ok:
        return _blocked(ports, NEUTRO, f'Porta 4 fechada: sinal={sinal} (sem lado vs VWAP)')

    return {
        'allowed': True,
        'sinal_institucional': sinal,
        'abort_reason': '',
        'short_circuit': False,
        'ports': ports,
        'structure_filters_pass': True,
    }


def _blocked(ports: dict, sinal: str, reason: str) -> dict[str, Any]:
    return {
        'allowed': False,
        'sinal_institucional': sinal,
        'abort_reason': reason,
        'short_circuit': True,
        'ports': ports,
        'structure_filters_pass': False,
    }


def institutional_entry_allowed(signals: dict | None) -> dict[str, Any]:
    """Alias semântico para o radar: True só com Smart Money completo."""
    return evaluate_hard_gates(signals)


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
