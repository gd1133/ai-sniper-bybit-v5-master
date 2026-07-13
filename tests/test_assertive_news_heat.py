"""Testes: heat de velas, lateral rigoroso e TP 100% margem."""

from __future__ import annotations

from src.engine.market_heat import compute_candle_heat
from src.risk.position_sizing import calculate_tp_sl_prices, evaluate_position_exit
from src.ai_brain.local_ml_engine import LocalMLEngine


def test_heat_blocks_lateral():
    heat = compute_candle_heat({'trend': 'NEUTRO', 'is_lateral': True})
    assert heat['entry_heat_ok'] is False
    assert heat['heat_score'] <= 20


def test_heat_hot_on_trend_candle():
    heat = compute_candle_heat({
        'trend': 'ALTA',
        'is_lateral': False,
        'candle_body_ratio': 70,
        'range_expansion': 1.5,
        'volume_ratio': 2.0,
        'chart_entry_score': 50,
        'adx': 28,
        'strong_bullish_candle': True,
        'bounce_from_pivot_low': True,
        'heat_bias': 'BULL',
    })
    assert heat['heat_bias'] == 'BULL'
    assert heat['heat_score'] >= 55
    assert heat['entry_heat_ok'] is True


def test_tp_is_100pct_of_margin_roi():
    # Margem $5 → TP quando PnL >= +$5 (+100%)
    reason, roi = evaluate_position_exit(5.0, 5.0)
    assert reason == 'TAKE_PROFIT'
    reason2, _ = evaluate_position_exit(2.0, 5.0)
    assert reason2 is None
    reason3, _ = evaluate_position_exit(-2.5, 5.0)
    assert reason3 == 'STOP_LOSS'


def test_tp_sl_prices_scale_with_leverage():
    # 20x → TP move 5% preço (100/20), SL 2.5%
    tp, sl = calculate_tp_sl_prices(100.0, 'BUY', 20)
    assert abs(tp - 105.0) < 1e-6
    assert abs(sl - 97.5) < 1e-6


def test_cerebro3_blocks_lateral():
    ml = LocalMLEngine()
    ok, reason, conf = ml.evaluate_entry_conditions('BTCUSDT', {
        'trend': 'NEUTRO',
        'is_lateral': True,
        'supertrend_signal': 1,
        'rsi': 50,
    })
    assert ok is False
    assert 'LATERAL' in reason.upper() or 'direção' in reason.lower()
