# -*- coding: utf-8 -*-
"""Segundo Cérebro: Turtle HHLL, Fib exponencial, liquidez, anatomia, TP/SL dinâmico."""

import pandas as pd

from src.engine.candle_anatomy import evaluate_candle_anatomy, evaluate_ponto_continuo
from src.engine.fibonacci_exponencial import exponential_fib_levels, fib_targets_for_side
from src.engine.liquidity_smc import detect_liquidity_sweep, identify_liquidity_zones
from src.engine.turtle_donchian import detect_turtle_breakout, turtle_exit_stop
from src.risk.position_sizing import calculate_dynamic_tp_sl, calculate_tp_sl_prices, turtle_atr_stop
from src.risk.trend_position_manager import decide_trend_action, detect_early_reversal


def _trend_df(n=80, start=100.0, step=0.4):
    rows = []
    px = start
    for _ in range(n):
        rows.append({
            'open': px,
            'high': px + 0.6,
            'low': px - 0.15,
            'close': px + 0.45,
            'vol': 100.0,
        })
        px += step
    return pd.DataFrame(rows)


def test_turtle_breakout_buy_on_hh20():
    df = _trend_df()
    # força close acima do HH das 20 anteriores
    prior_hh = float(df['high'].iloc[-21:-1].max())
    last = df.iloc[-1].copy()
    last['high'] = prior_hh + 1.0
    last['close'] = prior_hh + 0.8
    df.iloc[-1] = last
    out = detect_turtle_breakout(df)
    assert out['turtle_breakout'] == 'BUY'
    assert out['hh_20'] > 0


def test_turtle_long_trail_is_ll20():
    df = _trend_df()
    sl = turtle_exit_stop(df, 'buy')
    assert sl['period'] == 20
    assert abs(sl['sl_price'] - float(df['low'].tail(20).min())) < 1e-9


def test_exponential_fib_extensions_ordered():
    df = _trend_df()
    lv = exponential_fib_levels(df)
    assert lv['exp_high'] > lv['exp_low']
    assert lv['fib_ext_1618_up'] > lv['fib_ext_100_up']
    t = fib_targets_for_side(lv, 'buy')
    assert t['tp2'] >= t['tp1']


def test_liquidity_sweep_bsl_invalidates_breakout():
    rows = []
    for i in range(30):
        px = 100 + i * 0.1
        rows.append({'open': px, 'high': px + 0.2, 'low': px - 0.2, 'close': px + 0.05, 'vol': 80})
    # equal highs ~103.2
    rows.append({'open': 103.0, 'high': 103.5, 'low': 102.8, 'close': 103.2, 'vol': 90})
    rows.append({'open': 103.1, 'high': 103.52, 'low': 102.9, 'close': 103.15, 'vol': 90})
    rows.append({'open': 103.2, 'high': 103.51, 'low': 102.85, 'close': 103.1, 'vol': 90})
    # sweep: wick above BSL, close back inside (long upper shadow)
    rows.append({'open': 103.2, 'high': 104.2, 'low': 102.9, 'close': 103.05, 'vol': 200})
    df = pd.DataFrame(rows)
    zones = identify_liquidity_zones(df)
    sweep = detect_liquidity_sweep(df, zones)
    assert sweep['sweep_bsl'] is True
    assert sweep['invalidate_breakout'] is True
    assert sweep['grab_reversal'] == 'SELL'


def test_doubt_candle_blocked():
    out = evaluate_candle_anatomy(
        sinal_institucional='COMPRA_INSTITUCIONAL',
        open_p=100.0,
        high=100.20,
        low=99.80,
        close=100.05,
        atr=1.0,
        fib_depth=0.8,
    )
    # corpo pequeno, sombras grandes, amplitude << ATR e correção profunda
    assert out['is_doubt_candle'] is True
    assert out['allowed'] is False
    assert 'DÚVIDA' in (out.get('abort_reason') or '')


def test_dynamic_sl_is_tighter_of_atr_and_roi():
    # ATR 1.0 → 2×ATR = 2 abaixo; ROI -50% @20x = 2.5 abaixo → SL Turtle 98
    sl = turtle_atr_stop(100.0, 'buy', atr=1.0, multiplier=2.0)
    assert abs(sl - 98.0) < 1e-9
    dyn = calculate_dynamic_tp_sl(100.0, 'buy', 20, {'atr_20': 1.0, 'fib_ext_1618_up': 108.0})
    roi_tp, roi_sl = calculate_tp_sl_prices(100.0, 'buy', 20)
    assert dyn['sl_price'] >= roi_sl - 1e-9
    assert dyn['sl_price'] >= sl - 1e-9
    assert dyn['tp_price'] >= roi_tp - 1e-9
    assert dyn['tp_price'] >= 108.0 - 1e-9


def test_small_red_still_does_not_exit_after_segundo_cerebro():
    rows = []
    for i in range(40):
        px = 100.0 + i * 0.01
        rows.append({'open': px, 'high': px + 0.05, 'low': px - 0.05, 'close': px + 0.02, 'vol': 80.0})
    rows.append({'open': 100.6, 'high': 100.65, 'low': 100.35, 'close': 100.4, 'vol': 90})
    rows.append({'open': 100.4, 'high': 100.42, 'low': 100.0, 'close': 100.1, 'vol': 90})
    df = pd.DataFrame(rows)
    early = detect_early_reversal(df, 'buy')
    assert early['triggered'] is False
    d = decide_trend_action(
        side='buy', roi_pct=22, entry_price=100.0, mark_price=101.1,
        df_slow=df, df_fast=df,
    )
    assert d['action'] == 'HOLD'


def test_ponto_continuo_requires_ema_and_force_candle():
    df = _trend_df(n=40)
    pc = evaluate_ponto_continuo(df, 'ALTA')
    assert 'ponto_continuo' in pc
    assert 'ponto_continuo_reason' in pc


def test_incremental_layer_does_not_require_replacing_classic_signals():
    from src.engine.triple_brain_layer import incremental_c1_bonus, incremental_c3_bonus
    base = {
        'trend': 'ALTA',
        'supertrend_signal': 1,
        'turtle_breakout': 'BUY',
        'turtle_reason': 'Turtle rompimento de ALTA',
        'ponto_continuo': True,
        'liquidity_ok': True,
        'candle_anatomy_ok': True,
        'anatomy_log': 'corpo=60%',
    }
    s1, r1 = incremental_c1_bonus(base)
    s3, r3 = incremental_c3_bonus(base)
    assert s1 > 0 and s3 > 0
    assert any('Turtle' in x or 'C1+' in x for x in r1)
    assert base['supertrend_signal'] == 1
    assert base['trend'] == 'ALTA'
