"""Testes do filtro de viabilidade Target 5% / Max Tolerance 7.5%."""

from __future__ import annotations

from src.risk.entry_viability import (
    build_frontend_entry_card,
    evaluate_entry_viability,
    quantize_qty_to_step,
)


def test_reject_when_min_margin_exceeds_tolerance():
    # Banca $100, L=20×, min qty força margem alta
    # min_nominal = 1 * 200 = 200 → min_margin = 10 → 10% > 7.5%
    report = evaluate_entry_viability(
        bank_balance=100,
        current_price=200,
        leverage=20,
        min_order_qty=1,
        qty_step=1,
        target_pct=0.05,
        max_tolerance_pct=0.075,
        symbol='EXPENSIVE/USDT:USDT',
    )
    assert report['aprovado'] is False
    assert report['decisao'] == 'REJEITADO'
    assert report['real_min_pct'] > 7.5


def test_approve_near_five_percent():
    # Banca $100, L=20×, preço baixo → min margem pequena
    # alvo 5% = $5 margem → notional $100 → qty = 100/10 = 10
    report = evaluate_entry_viability(
        bank_balance=100,
        current_price=10,
        leverage=20,
        min_order_qty=0.1,
        qty_step=0.1,
        target_pct=0.05,
        max_tolerance_pct=0.075,
        symbol='ETH/USDT:USDT',
    )
    assert report['aprovado'] is True
    assert report['decisao'] == 'APROVADO'
    assert 4.5 <= report['final_pct'] <= 7.5
    assert report['final_qty'] > 0


def test_round_up_to_min_within_tolerance():
    # Ideal abaixo do mínimo, mas mínimo ainda <= 7.5%
    # min_margin = (0.01*50)/20 = 0.025 → 0.025% ok; sobe qty para min
    report = evaluate_entry_viability(
        bank_balance=1000,
        current_price=50,
        leverage=20,
        min_order_qty=0.01,
        qty_step=0.01,
        target_pct=0.05,
        max_tolerance_pct=0.075,
        symbol='ALT/USDT:USDT',
    )
    assert report['aprovado'] is True
    assert report['final_qty'] >= 0.01


def test_quantize_step():
    assert quantize_qty_to_step(1.234, 0.1, round_up=False) == 1.2
    assert quantize_qty_to_step(1.01, 0.1, round_up=True) == 1.1


def test_frontend_card_fields():
    report = evaluate_entry_viability(
        bank_balance=100,
        current_price=10,
        leverage=20,
        min_order_qty=0.1,
        qty_step=0.1,
        symbol='BTC/USDT:USDT',
    )
    card = build_frontend_entry_card(report)
    assert 'margem_proxima_entrada' in card
    assert 'pct_proxima_entrada' in card
    assert 'target_pct' in card
    assert card['target_pct'] == 5.0
