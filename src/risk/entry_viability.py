"""
Filtro de viabilidade de entrada vs Step Size / minOrderQty da Bybit.

Evita que bancas pequenas (ex.: $100) sejam forçadas a entrar com margem
acima da tolerância por causa do lote mínimo da corretora.

Regras:
  Target_Pct         = 5%   (margem alvo da banca)
  Max_Tolerance_Pct  = 7.5% (teto se arredondar para cima pelo Step Size)

  min_nominal  = min_order_qty × current_price
  min_margin   = min_nominal / leverage
  real_min_pct = (min_margin / bank_balance) × 100

  Se real_min_pct > Max_Tolerance_Pct → REJEITA
  Senão → calcula qty ideal ~5% e arredonda no step válido da Bybit
"""

from __future__ import annotations

import os
from decimal import Decimal, ROUND_DOWN, ROUND_UP, InvalidOperation
from typing import Any, Optional

from src.risk.position_sizing import DEFAULT_ENTRY_PCT, load_entry_pct

DEFAULT_MAX_TOLERANCE_PCT = 0.075  # 7.5%


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = str(raw).strip()
    if not raw:
        return default
    try:
        return float(raw.replace(',', '.'))
    except (TypeError, ValueError):
        return default


def load_target_pct() -> float:
    """Percentual alvo da banca (env RISK_PER_TRADE_PCT, padrão 5%)."""
    return load_entry_pct() or DEFAULT_ENTRY_PCT


def load_max_tolerance_pct() -> float:
    """
    Teto de tolerância ao arredondar pelo Step Size.
    Env: MAX_ENTRY_TOLERANCE_PCT (aceita 7.5 ou 0.075).
    """
    pct = _env_float('MAX_ENTRY_TOLERANCE_PCT', DEFAULT_MAX_TOLERANCE_PCT * 100)
    if pct > 1:
        return pct / 100.0
    return pct


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(float(value)))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal('0')


def quantize_qty_to_step(qty: float, step: float, *, round_up: bool = False) -> float:
    """Ajusta quantidade ao step size da Bybit (qtyStep / minOrderQty)."""
    qty_d = _to_decimal(qty)
    step_d = _to_decimal(step)
    if qty_d <= 0:
        return 0.0
    if step_d <= 0:
        return float(qty_d)

    units = qty_d / step_d
    if round_up:
        units = units.to_integral_value(rounding=ROUND_UP)
    else:
        units = units.to_integral_value(rounding=ROUND_DOWN)
        if units <= 0 and qty_d > 0:
            units = Decimal('1')
    return float(units * step_d)


def extract_bybit_lot_filters(market: Optional[dict] = None) -> dict:
    """
    Extrai minOrderQty / qtyStep dos limites CCXT + lotSizeFilter Bybit V5.
    """
    market = market or {}
    limits = market.get('limits') or {}
    amount_limits = limits.get('amount') or {}
    cost_limits = limits.get('cost') or {}

    min_amount = amount_limits.get('min')
    min_cost = cost_limits.get('min')

    info = market.get('info') or {}
    lot = info.get('lotSizeFilter') or {}
    qty_step = lot.get('qtyStep') or lot.get('basePrecision')
    min_order_qty = lot.get('minOrderQty') or min_amount

    try:
        min_order_qty = float(min_order_qty) if min_order_qty not in (None, '', 'None') else 0.001
    except (TypeError, ValueError):
        min_order_qty = 0.001
    if min_order_qty <= 0:
        min_order_qty = 0.001

    try:
        qty_step = float(qty_step) if qty_step not in (None, '', 'None') else min_order_qty
    except (TypeError, ValueError):
        qty_step = min_order_qty
    if qty_step <= 0:
        qty_step = min_order_qty

    try:
        min_cost = float(min_cost) if min_cost not in (None, '', 'None') else 0.0
    except (TypeError, ValueError):
        min_cost = 0.0

    precision = market.get('precision') or {}
    amount_precision = precision.get('amount')
    try:
        amount_precision = int(amount_precision) if amount_precision is not None else None
    except (TypeError, ValueError):
        amount_precision = None

    return {
        'min_order_qty': float(min_order_qty),
        'qty_step': float(qty_step),
        'min_cost': float(min_cost or 0.0),
        'amount_precision': amount_precision,
    }


def evaluate_entry_viability(
    *,
    bank_balance: float,
    current_price: float,
    leverage: float,
    min_order_qty: float,
    qty_step: Optional[float] = None,
    target_pct: Optional[float] = None,
    max_tolerance_pct: Optional[float] = None,
    symbol: str = '',
    min_cost: float = 0.0,
) -> dict:
    """
    Avalia se a entrada é viável para a banca e calcula qty final válida.

    Returns dict com campos aprovado/rejeitado, métricas e qty/margem finais.
    """
    balance = float(bank_balance or 0)
    price = float(current_price or 0)
    lev = max(float(leverage or 1), 1.0)
    min_qty = float(min_order_qty or 0)
    step = float(qty_step or min_qty or 0.001)
    target = float(target_pct if target_pct is not None else load_target_pct())
    max_tol = float(max_tolerance_pct if max_tolerance_pct is not None else load_max_tolerance_pct())
    if target > 1:
        target /= 100.0
    if max_tol > 1:
        max_tol /= 100.0
    # Tolerância nunca abaixo do alvo
    max_tol = max(max_tol, target)

    result = {
        'symbol': symbol,
        'aprovado': False,
        'decisao': 'REJEITADO',
        'bank_balance': round(balance, 4),
        'current_price': price,
        'leverage': lev,
        'min_order_qty': min_qty,
        'qty_step': step,
        'min_cost_exchange': float(min_cost or 0),
        'target_pct': target,
        'max_tolerance_pct': max_tol,
        'target_pct_display': round(target * 100, 4),
        'max_tolerance_pct_display': round(max_tol * 100, 4),
        'min_nominal': 0.0,
        'min_margin': 0.0,
        'real_min_pct': 0.0,
        'ideal_margin': 0.0,
        'ideal_qty': 0.0,
        'final_qty': 0.0,
        'final_notional': 0.0,
        'final_margin': 0.0,
        'final_pct': 0.0,
        'motivo': '',
    }

    if balance <= 0 or price <= 0 or min_qty <= 0:
        result['motivo'] = 'Dados inválidos (saldo, preço ou minOrderQty).'
        return result

    min_nominal = min_qty * price
    # Se a exchange exige nocional mínimo maior que o lote × preço, usa o maior
    if min_cost and min_cost > min_nominal:
        min_nominal = float(min_cost)
        # qty mínima implícita pelo nocional
        min_qty_for_cost = min_nominal / price
        if min_qty_for_cost > min_qty:
            min_qty = quantize_qty_to_step(min_qty_for_cost, step, round_up=True)
            min_nominal = min_qty * price

    min_margin = min_nominal / lev
    real_min_pct = (min_margin / balance) * 100.0

    result.update({
        'min_order_qty': min_qty,
        'min_nominal': round(min_nominal, 6),
        'min_margin': round(min_margin, 6),
        'real_min_pct': round(real_min_pct, 4),
    })

    # ── Regra de rejeição ────────────────────────────────────────────────────
    if real_min_pct > (max_tol * 100.0):
        result['motivo'] = (
            f"Moeda cara demais para a banca: margem mínima real {real_min_pct:.2f}% "
            f"excede a tolerância máxima de {max_tol * 100:.1f}% "
            f"(Step Size / minOrderQty Bybit = {min_qty})."
        )
        result['decisao'] = 'REJEITADO'
        result['aprovado'] = False
        return result

    # ── Arredondamento inteligente (~Target_Pct) ─────────────────────────────
    ideal_margin = balance * target
    ideal_qty = (ideal_margin * lev) / price

    # Se ideal < mínimo, sobe para o mínimo (ainda dentro da tolerância)
    if ideal_qty < min_qty:
        final_qty = quantize_qty_to_step(min_qty, step, round_up=True)
    else:
        final_qty = quantize_qty_to_step(ideal_qty, step, round_up=False)
        if final_qty < min_qty:
            final_qty = quantize_qty_to_step(min_qty, step, round_up=True)

    final_notional = final_qty * price
    final_margin = final_notional / lev
    final_pct = (final_margin / balance) * 100.0 if balance > 0 else 0.0

    # Revalida após arredondamento (step pode empurrar acima do teto)
    if final_pct > (max_tol * 100.0) + 1e-9:
        result.update({
            'ideal_margin': round(ideal_margin, 6),
            'ideal_qty': float(ideal_qty),
            'final_qty': float(final_qty),
            'final_notional': round(final_notional, 6),
            'final_margin': round(final_margin, 6),
            'final_pct': round(final_pct, 4),
            'aprovado': False,
            'decisao': 'REJEITADO',
            'motivo': (
                f"Após arredondamento pelo Step Size ({step}), a margem ficou em "
                f"{final_pct:.2f}% da banca — acima do teto {max_tol * 100:.1f}%."
            ),
        })
        return result

    result.update({
        'ideal_margin': round(ideal_margin, 6),
        'ideal_qty': float(ideal_qty),
        'final_qty': float(final_qty),
        'final_notional': round(final_notional, 6),
        'final_margin': round(final_margin, 6),
        'final_pct': round(final_pct, 4),
        'aprovado': True,
        'decisao': 'APROVADO',
        'motivo': (
            f"Entrada viável: margem ${final_margin:.4f} ≈ {final_pct:.2f}% da banca "
            f"(alvo {target * 100:.1f}%, teto {max_tol * 100:.1f}%)."
        ),
    })
    return result


def print_entry_viability_log(report: dict) -> None:
    """Bloco visual no console com o cálculo matemático completo."""
    bal = float(report.get('bank_balance') or 0)
    price = float(report.get('current_price') or 0)
    min_qty = float(report.get('min_order_qty') or 0)
    min_nom = float(report.get('min_nominal') or 0)
    lev = float(report.get('leverage') or 1)
    min_m = float(report.get('min_margin') or 0)
    real_pct = float(report.get('real_min_pct') or 0)
    target = float(report.get('target_pct_display') or 5)
    max_tol = float(report.get('max_tolerance_pct_display') or 7.5)
    decisao = str(report.get('decisao') or '---')
    symbol = str(report.get('symbol') or '---')
    aprovado = bool(report.get('aprovado'))

    lines = [
        "",
        "╔══════════════════════════════════════════════════════════════╗",
        "║           📐 VIABILIDADE DE ENTRADA × BANCA                  ║",
        "╚══════════════════════════════════════════════════════════════╝",
        f"  Ativo              : {symbol}",
        f"  Saldo Atual        : ${bal:.4f} USDT",
        f"  Preço de Mercado   : ${price:.8f}",
        f"  Contrato Mínimo    : {min_qty} (minOrderQty / Step Size)",
        f"  Valor Nominal Mín. : ${min_nom:.6f} USDT",
        f"  Alavancagem        : {lev:.0f}×",
        f"  Margem Exigida Mín.: ${min_m:.6f} USDT  ({real_pct:.2f}% da banca)",
        f"  Alvo (Target)      : {target:.1f}%  |  Teto (Max Tolerance): {max_tol:.1f}%",
    ]
    if aprovado:
        lines.extend([
            f"  Margem Final       : ${float(report.get('final_margin') or 0):.4f} USDT",
            f"  Qty Final          : {float(report.get('final_qty') or 0)}",
            f"  % Real da Banca    : {float(report.get('final_pct') or 0):.2f}%",
            f"  Decisão Final     : ✅ APROVADO",
        ])
    else:
        lines.append(f"  Decisão Final     : ❌ REJEITADO")
        lines.append(f"  Motivo             : {report.get('motivo', '')}")
        lines.append(
            "  → Moeda incompatível com o tamanho da banca "
            "(regras de Step Size / minOrderQty da Bybit)."
        )
    lines.append("════════════════════════════════════════════════════════════════")
    print("\n".join(lines), flush=True)


def build_frontend_entry_card(report: dict) -> dict:
    """Payload enxuto para card do dashboard (próxima entrada ~5%)."""
    return {
        'symbol': report.get('symbol') or '---',
        'saldo_atual': round(float(report.get('bank_balance') or 0), 2),
        'preco_mercado': float(report.get('current_price') or 0),
        'contrato_minimo': float(report.get('min_order_qty') or 0),
        'valor_nominal_min': round(float(report.get('min_nominal') or 0), 4),
        'alavancagem': float(report.get('leverage') or 1),
        'margem_minima': round(float(report.get('min_margin') or 0), 4),
        'impacto_min_pct': round(float(report.get('real_min_pct') or 0), 2),
        'target_pct': round(float(report.get('target_pct_display') or 5), 2),
        'max_tolerance_pct': round(float(report.get('max_tolerance_pct_display') or 7.5), 2),
        'margem_proxima_entrada': round(float(report.get('final_margin') or report.get('ideal_margin') or 0), 4),
        'pct_proxima_entrada': round(
            float(report.get('final_pct') or report.get('target_pct_display') or 5),
            2,
        ),
        'qty_proxima_entrada': float(report.get('final_qty') or 0),
        'decisao': report.get('decisao') or '---',
        'aprovado': bool(report.get('aprovado')),
        'motivo': report.get('motivo') or '',
    }
