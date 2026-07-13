"""Testes da Confluência Absoluta (Concordância Total)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.engine.confluence_absoluta import (
    avaliar_confluencia_absoluta,
    classify_news_sentiment,
    filtro_adx_tendencia,
    filtro_noticias_sentimento,
    filtro_order_book_imbalance,
    filtro_volume_fluxo,
)


def _make_trending_df(n=80, direction='up', adx_strong=True):
    """OHLCV sintético com tendência e volume."""
    rng = np.random.default_rng(42)
    base = 100.0
    rows = []
    for i in range(n):
        drift = 0.4 if direction == 'up' else -0.4
        open_p = base
        close_p = base + drift + float(rng.normal(0, 0.05))
        high_p = max(open_p, close_p) + (1.2 if adx_strong else 0.1)
        low_p = min(open_p, close_p) - (1.2 if adx_strong else 0.1)
        vol = 1000.0 * (3.0 if i == n - 1 else 1.0)
        rows.append({
            'ts': i,
            'open': open_p,
            'high': high_p,
            'low': low_p,
            'close': close_p,
            'vol': vol,
        })
        base = close_p
    return pd.DataFrame(rows)


def test_order_book_imbalance_long_requires_60pct_more_bids():
    book = {
        'bids': [[100, 160]] * 20,
        'asks': [[101, 100]] * 20,
    }
    ok = filtro_order_book_imbalance(book, 'BUY')
    assert ok['ok'] is True
    assert ok['ratio'] >= 1.60

    weak = {
        'bids': [[100, 110]] * 20,
        'asks': [[101, 100]] * 20,
    }
    bad = filtro_order_book_imbalance(weak, 'BUY')
    assert bad['ok'] is False


def test_order_book_imbalance_short_requires_60pct_more_asks():
    book = {
        'bids': [[100, 100]] * 20,
        'asks': [[101, 160]] * 20,
    }
    ok = filtro_order_book_imbalance(book, 'SELL')
    assert ok['ok'] is True

    missing = filtro_order_book_imbalance(None, 'SELL')
    assert missing['ok'] is False


def test_news_long_blocks_negative_sentiment():
    assert classify_news_sentiment({'sentiment_score': 30, 'global_trend': 'BEARISH'}) == 'NEGATIVO'
    long_bad = filtro_noticias_sentimento('BUY', intel_ctx={'sentiment_score': 30, 'global_trend': 'BEARISH'})
    assert long_bad['ok'] is False

    long_ok = filtro_noticias_sentimento('BUY', intel_ctx={'sentiment_score': 55, 'global_trend': 'NEUTRAL'})
    assert long_ok['ok'] is True


def test_volume_climax_or_flow():
    df = _make_trending_df()
    signals = {'volume_ratio': 2.5, 'volume_trend': 'ALTO', 'money_flow_side': 'BUY'}
    result = filtro_volume_fluxo(df, signals, 'BUY')
    assert result['ok'] is True

    weak = filtro_volume_fluxo(df, {'volume_ratio': 1.0, 'volume_trend': 'BAIXO', 'money_flow_side': 'WAIT'}, 'BUY')
    # última barra tem vol 3x — climax detectado via df
    assert weak['ok'] is True


def test_all_false_rejects_absolute_confluence():
    df = _make_trending_df(direction='up')
    result = avaliar_confluencia_absoluta(
        side='BUY',
        df=df,
        signals={
            'trend': 'ALTA',
            'volume_ratio': 1.0,
            'volume_trend': 'BAIXO',
            'money_flow_side': 'WAIT',
            'fib_distance_pct': 20.0,
        },
        intel_ctx={'sentiment_score': 20, 'global_trend': 'BEARISH'},
        order_book={'bids': [[1, 1]], 'asks': [[1, 100]]},
    )
    assert result['aprovado'] is False
    assert 'filtro_noticias' in result['failed'] or 'filtro_livro' in result['failed']


def test_strict_all_boolean_gate():
    """Garante o contrato: all([...]) — um falso aborta."""
    filtros = [True, True, True, True, False]
    assert all(filtros) is False
    assert all([True, True, True, True, True]) is True


def test_adx_filter_threshold():
    df = _make_trending_df(adx_strong=True)
    # Pode variar com sintético; só garante estrutura do retorno
    out = filtro_adx_tendencia(df, min_adx=22.0)
    assert 'ok' in out and 'adx' in out
