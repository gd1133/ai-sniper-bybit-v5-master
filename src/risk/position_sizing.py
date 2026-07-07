"""
Gestão de tamanho de posição — percentual da banca (não mínimo da exchange).

Regra principal:
  margem = saldo × percentual_entrada
  qty    = (margem × alavancagem) / preço

Após STOP_LOSS o percentual pode ser reduzido (ex.: 3%).
"""

from __future__ import annotations

import math
import os
from typing import Tuple


DEFAULT_ENTRY_PCT = 0.05   # 5% da banca
DEFAULT_ENTRY_AFTER_STOP_PCT = 0.03  # 3% após stop loss
DEFAULT_TP_MARGIN_RATIO = 1.0   # +100% sobre a margem
DEFAULT_SL_MARGIN_RATIO = 0.5   # -50% sobre a margem


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


def load_entry_pct() -> float:
    """Percentual padrão de entrada (env RISK_PER_TRADE_PCT, default 5%)."""
    pct = _env_float('RISK_PER_TRADE_PCT', DEFAULT_ENTRY_PCT * 100)
    if pct > 1:
        return pct / 100.0
    return pct


def load_entry_after_stop_pct() -> float:
    """Percentual após stop loss (env ENTRY_AFTER_STOP_PCT, default 3%)."""
    pct = _env_float('ENTRY_AFTER_STOP_PCT', DEFAULT_ENTRY_AFTER_STOP_PCT * 100)
    if pct > 1:
        return pct / 100.0
    return pct


def format_entry_pct(pct: float | None = None) -> str:
    value = (pct if pct is not None else load_entry_pct()) * 100
    if math.isclose(value, round(value), rel_tol=0, abs_tol=1e-9):
        return f"{int(round(value))}%"
    return f"{value:.2f}%"


def calculate_order_margin(balance: float, after_stop: bool = False) -> float:
    """Calcula margem em USDT = percentual × saldo."""
    balance = float(balance or 0)
    if balance <= 0:
        return 0.0
    pct = load_entry_after_stop_pct() if after_stop else load_entry_pct()
    return round(balance * pct, 2)


def calculate_position_qty(
    balance: float,
    price: float,
    leverage: float,
    *,
    after_stop: bool = False,
) -> Tuple[float, float]:
    """
    Retorna (margem_usdt, quantidade).

    qty = (margem × alavancagem) / preço
    """
    price = float(price or 0)
    leverage = float(leverage or 1)
    if price <= 0 or leverage <= 0:
        return 0.0, 0.0

    margin = calculate_order_margin(balance, after_stop=after_stop)
    if margin <= 0:
        return 0.0, 0.0

    pct = load_entry_after_stop_pct() if after_stop else load_entry_pct()
    sizing = calcular_tamanho_posicao(balance, leverage, price, pct_banca=pct)
    return float(sizing['margem_inicial']), float(sizing['quantidade'])


def calculate_tp_sl_prices(
    entry_price: float,
    side: str,
    leverage: float,
    *,
    tp_margin_ratio: float = DEFAULT_TP_MARGIN_RATIO,
    sl_margin_ratio: float = DEFAULT_SL_MARGIN_RATIO,
) -> Tuple[float, float]:
    """
    Calcula preços de TP/SL com base na margem (não em % fixo de preço arbitrário).

    Com alavancagem L:
      movimento_preço_tp = tp_margin_ratio / L
      movimento_preço_sl = sl_margin_ratio / L

    Ex.: 20× → TP +5% preço (+100% margem), SL -2.5% preço (-50% margem).
    """
    entry = float(entry_price or 0)
    leverage = max(float(leverage or 1), 1.0)
    if entry <= 0:
        return 0.0, 0.0

    tp_move = tp_margin_ratio / leverage
    sl_move = sl_margin_ratio / leverage
    side_norm = str(side or '').strip().lower()

    if side_norm in ('buy', 'long', 'comprar'):
        return entry * (1 + tp_move), entry * (1 - sl_move)
    return entry * (1 - tp_move), entry * (1 + sl_move)


def financial_targets_from_margin(margin: float) -> Tuple[float, float]:
    """Retorna (alvo_lucro_usdt, alvo_perda_usdt) para monitor financeiro."""
    margin = max(float(margin or 0), 0.0)
    if margin <= 0:
        margin = calculate_order_margin(100.0)  # fallback ~$5 em banca $100
    return margin * DEFAULT_TP_MARGIN_RATIO, -margin * DEFAULT_SL_MARGIN_RATIO


def calcular_tamanho_posicao(
    saldo_banca: float,
    alavancagem: float,
    preco_entrada: float,
    *,
    pct_banca: float | None = None,
) -> dict:
    """
    Fórmula obrigatória para perpétuos Bybit:

      MI = Saldo × 5%
      Valor_Posição (USDT) = MI × L
      Qty = Valor_Posição / Preço

    A margem inicial NUNCA excede o percentual da banca (padrão 5%).
    Se a alavancagem mudar, apenas Qty muda — o capital em risco (MI) permanece fixo em %.
    """
    saldo = float(saldo_banca or 0)
    leverage = max(float(alavancagem or 1), 1.0)
    price = float(preco_entrada or 0)
    pct = float(pct_banca if pct_banca is not None else load_entry_pct())
    pct = min(pct, DEFAULT_ENTRY_PCT) if pct > DEFAULT_ENTRY_PCT else pct

    if saldo <= 0 or price <= 0:
        return {
            'margem_inicial': 0.0,
            'valor_posicao_usdt': 0.0,
            'quantidade': 0.0,
            'alavancagem': leverage,
            'preco_entrada': price,
            'pct_banca': pct,
            'saldo_referencia': saldo,
        }

    margem_inicial = saldo * pct
    valor_posicao = margem_inicial * leverage
    quantidade = valor_posicao / price

    return {
        'margem_inicial': round(margem_inicial, 8),
        'valor_posicao_usdt': round(valor_posicao, 8),
        'quantidade': quantidade,
        'alavancagem': leverage,
        'preco_entrada': price,
        'pct_banca': pct,
        'saldo_referencia': round(saldo, 8),
    }
