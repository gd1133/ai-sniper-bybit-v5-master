# -*- coding: utf-8 -*-
"""Saídas: HOLD em recuo; fecha só vela forte+volume; trail após 100%."""

import pandas as pd

from src.risk.trend_position_manager import (
    LOCK_ROI_PCT,
    TRAIL_ROI_PCT,
    compute_lock_sl_price,
    decide_trend_action,
    detect_early_reversal,
    detect_volume_flip_exit,
)


def _ohlcv(n=40, last_close=101.0, last_open=100.8, last_high=101.1, last_low=100.7, last_vol=100.0):
    rows = []
    for i in range(n - 1):
        px = 100.0 + i * 0.01
        rows.append({
            'open': px, 'high': px + 0.05, 'low': px - 0.05, 'close': px + 0.02, 'vol': 80.0,
        })
    rows.append({
        'open': last_open, 'high': last_high, 'low': last_low, 'close': last_close, 'vol': last_vol,
    })
    # barra em formação (será descartada pelo detector)
    rows.append({
        'open': last_close, 'high': last_close + 0.02, 'low': last_close - 0.4,
        'close': last_close - 0.3, 'vol': last_vol * 5,
    })
    return pd.DataFrame(rows)


def test_defaults_arm_trail_at_100():
    assert TRAIL_ROI_PCT >= 99.0
    assert LOCK_ROI_PCT >= 70.0


def test_small_red_candle_does_not_exit_long():
    df = _ohlcv(last_close=100.4, last_open=100.6, last_high=100.65, last_low=100.35, last_vol=90)
    early = detect_early_reversal(df, 'buy')
    assert early['triggered'] is False
    d = decide_trend_action(
        side='buy', roi_pct=22, entry_price=100.0, mark_price=101.1,
        df_slow=df, df_fast=df,
    )
    assert d['action'] == 'HOLD'


def test_strong_bearish_high_volume_exits_long():
    # corpo ~80%, close no fundo, vol alto vs MA
    df = _ohlcv(
        last_close=99.2, last_open=101.0, last_high=101.1, last_low=99.1, last_vol=400.0,
    )
    early = detect_early_reversal(df, 'buy')
    assert early['triggered'] is True
    d = decide_trend_action(
        side='buy', roi_pct=35, entry_price=100.0, mark_price=99.5,
        df_slow=df, df_fast=df,
    )
    assert d['action'] == 'EARLY_EXIT'
    assert 'SAIDA_REVERSAO' in d['tipo_execucao']


def test_at_100_roi_extends_trailing_does_not_close():
    df = _ohlcv()
    d = decide_trend_action(
        side='buy', roi_pct=105, entry_price=100.0, mark_price=105.2,
        peak_price=105.2, df_slow=df, df_fast=df,
    )
    assert d['action'] == 'EXTEND_TRAILING'
    assert d['trailing_armed'] is True
    lock = compute_lock_sl_price(100.0, 'buy', 80, leverage=20)
    assert abs(lock - 104.0) < 1e-6  # +4% preço @20x = +80% ROI
    assert d['sl_price'] >= lock - 1e-9


def test_stagnation_ignores_small_green_roi():
    d = decide_trend_action(
        side='buy', roi_pct=4.0, entry_price=100.0, mark_price=100.2,
        opened_at=0, last_extreme_at=0, now=10 * 3600,
    )
    assert d['action'] == 'HOLD'


def test_volume_flip_exits_short_when_green_volume():
    # Short em lucro: vela verde forte + volume = cobertura
    df = _ohlcv(
        last_close=101.8, last_open=99.5, last_high=101.9, last_low=99.4, last_vol=350.0,
    )
    flip = detect_volume_flip_exit(df, 'sell', roi_pct=40)
    assert flip['triggered'] is True
    d = decide_trend_action(
        side='sell', roi_pct=40, entry_price=102.0, mark_price=100.0,
        df_slow=df, df_fast=df,
    )
    assert d['action'] == 'EARLY_EXIT'
    assert d['tipo_execucao'] in ('SAIDA_VOLUME_CONTRA', 'SAIDA_REVERSAO_TENDENCIA')


def test_volume_flip_ignores_low_roi():
    df = _ohlcv(
        last_close=99.2, last_open=101.0, last_high=101.1, last_low=99.1, last_vol=400.0,
    )
    flip = detect_volume_flip_exit(df, 'buy', roi_pct=5)
    assert flip['triggered'] is False

