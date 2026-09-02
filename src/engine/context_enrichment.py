# -*- coding: utf-8 -*-
"""
Enriquecimento contextual — Cérebros 1 e 2 como coletores (sem abort).

Substitui short-circuit das Portas 1–5 por métricas descritivas enviadas ao Cérebro 3.
Abort pré-C3 permitido apenas: OHLCV/API indisponível ou liquidez 24h abaixo do mínimo.
"""

from __future__ import annotations

import os
from typing import Any

from src.engine.structure_config import (
    DEFAULT_AMPLITUDE_PCT_MAX,
    STRUCTURE_ADX_MIN,
    STRUCTURE_REQUIRE_BB_EXPAND,
)


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


MIN_QUOTE_VOLUME_24H = _env_float('MIN_QUOTE_VOLUME_24H', 500_000.0)


def compute_volume_score(signals: dict | None) -> str:
    """
    Classifica pegada de volume (ex-Porta 3):
    Institucional | Normal | Baixo
    """
    signals = signals or {}
    vol_ratio = _f(signals.get('volume_ratio'), 1.0)
    if bool(signals.get('big_player_ativo')) or vol_ratio >= 1.5:
        return 'Institucional'
    if vol_ratio >= 1.0:
        return 'Normal'
    return 'Baixo'


def check_operational_abort(
    ticker: dict | None = None,
    df=None,
    *,
    api_error: str | None = None,
) -> dict[str, Any]:
    """Único abort permitido antes do Cérebro 3."""
    if api_error:
        return {'abort': True, 'reason': f'Erro API: {api_error}'}
    if df is None or not hasattr(df, '__len__') or len(df) < 50:
        return {'abort': True, 'reason': 'OHLCV insuficiente ou indisponível (API)'}
    quote_vol = _f((ticker or {}).get('quoteVolume') or (ticker or {}).get('baseVolume'))
    if quote_vol > 0 and quote_vol < MIN_QUOTE_VOLUME_24H:
        return {
            'abort': True,
            'reason': (
                f'Liquidez 24h insuficiente: {quote_vol:,.0f} USDT '
                f'< mínimo {MIN_QUOTE_VOLUME_24H:,.0f}'
            ),
        }
    return {'abort': False, 'reason': ''}


def evaluate_gates_advisory(signals: dict | None, df=None) -> dict[str, Any]:
    """
    Avalia Portas 1–5 como métricas descritivas — NUNCA bloqueia.
    Retorna sempre allowed=True para compatibilidade com código legado.
    """
    signals = signals or {}
    adx = _f(signals.get('adx'))
    bb_width = _f(signals.get('bollinger_bandwidth'))
    bb_mean = _f(signals.get('bollinger_bandwidth_mean_50'))
    amplitude = _f(signals.get('amplitude_pct'))
    sinal = str(signals.get('sinal_institucional', 'NEUTRO') or 'NEUTRO').upper()
    adx_min = float(STRUCTURE_ADX_MIN)
    amp_min = float(DEFAULT_AMPLITUDE_PCT_MAX)

    try:
        from src.engine.porta3_adaptive import resolve_porta3_sigma
        sigma = resolve_porta3_sigma(adx if adx > 0 else None)
    except Exception:
        sigma = 1.15

    volume_score = compute_volume_score(signals)
    is_lateral = bool(
        signals.get('is_lateral')
        or signals.get('is_accumulation')
        or signals.get('amplitude_lateral')
    )
    market_regime = 'LATERAL' if is_lateral or adx < 20 else (
        'TREND_UP' if str(signals.get('trend', '')).upper() == 'ALTA' else (
            'TREND_DOWN' if str(signals.get('trend', '')).upper() == 'BAIXA' else 'NEUTRO'
        )
    )

    anatomy = _evaluate_anatomy_advisory(signals, sinal, df=df)

    ports = {
        'porta1_adx': {
            'value': round(adx, 4),
            'pass': adx >= adx_min,
            'rule': f'ADX(14) >= {adx_min:.0f}',
            'structure_strength': 'FORTE' if adx >= 25 else ('MODERADA' if adx >= adx_min else 'FRACA'),
        },
        'porta1_bb_width': {
            'value': round(bb_width, 8),
            'mean_50': round(bb_mean, 8),
            'pass': bool(signals.get('bollinger_expanding')) if STRUCTURE_REQUIRE_BB_EXPAND else True,
            'expanding': bool(signals.get('bollinger_expanding')),
        },
        'porta2_amplitude': {
            'value': round(amplitude, 4),
            'pass': amplitude >= amp_min if amplitude > 0 else not is_lateral,
            'accumulation': bool(signals.get('is_accumulation')),
        },
        'porta3_volume': {
            'volume_score': volume_score,
            'volume_ratio': round(_f(signals.get('volume_ratio'), 1.0), 3),
            'sigma_threshold': round(float(sigma), 2),
            'big_player': bool(signals.get('big_player_ativo')),
            'pass': bool(signals.get('big_player_ativo')),
        },
        'porta4_vwap_lado': {
            'sinal': sinal,
            'pass': sinal in ('COMPRA_INSTITUCIONAL', 'VENDA_INSTITUCIONAL'),
        },
        'porta5_anatomia_vela': anatomy,
        'liquidity_sweep': {
            'block_long': bool(signals.get('liquidity_block_long')),
            'block_short': bool(signals.get('liquidity_block_short')),
            'reason': signals.get('sweep_reason') or '',
        },
    }

    advisory_notes = []
    if is_lateral:
        advisory_notes.append(
            f'Mercado lateral (ADX={adx:.1f}) — C3 pode avaliar RANGE_BOUNCE topo/fundo'
        )
    if volume_score == 'Baixo':
        advisory_notes.append('Volume abaixo do institucional — cautela em breakout')
    if sinal == 'NEUTRO':
        advisory_notes.append('Sem lado institucional VWAP — C3 define direção')

    return {
        'allowed': True,
        'advisory_only': True,
        'sinal_institucional': sinal,
        'volume_score': volume_score,
        'market_regime': market_regime,
        'is_lateral': is_lateral,
        'abort_reason': '',
        'short_circuit': False,
        'ports': ports,
        'advisory_notes': advisory_notes,
        'structure_filters_pass': ports['porta1_adx']['pass'] and ports['porta2_amplitude']['pass'],
        'candle_anatomy': anatomy,
    }


def build_cerebro1_payload(signals: dict | None, df=None, gates: dict | None = None) -> dict[str, Any]:
    """Cérebro 1 — métricas matemáticas puras (EMA/SMA/ADX/RSI/VWAP/ATR/S&R) → C3."""
    signals = signals or {}
    gates = gates or {}
    price = _f(signals.get('price') or signals.get('close'))
    ema8 = _f(signals.get('ema_8') or signals.get('ema_9'))
    ema20 = _f(signals.get('ema_20') or signals.get('ema_21'))
    sma200 = _f(signals.get('sma_200'))
    return {
        'brain': 1,
        'role': 'Técnico — Tendência e Estrutura (Python puro)',
        'available': True,
        'score': round(min(100.0, max(0.0, (
            (55 if str(signals.get('trend', '')).upper() in ('ALTA', 'BAIXA') else 30)
            + min(25.0, _f(signals.get('adx')) * 0.8)
            + (10 if _f(signals.get('volume_ratio'), 1) >= 1.3 else 0)
        ))), 1),
        'action': (
            'BUY' if str(signals.get('trend', '')).upper() == 'ALTA' and int(signals.get('supertrend_signal') or 0) == 1
            else (
                'SELL' if str(signals.get('trend', '')).upper() == 'BAIXA' and int(signals.get('supertrend_signal') or 0) == -1
                else 'WAIT'
            )
        ),
        'report': (
            f"EMA8={ema8:.4f} EMA20={ema20:.4f} SMA200={sma200:.4f} "
            f"ADX={_f(signals.get('adx')):.1f} RSI={_f(signals.get('rsi'), 50):.1f} "
            f"VWAP={_f(signals.get('vwap')):.4f} ATR={_f(signals.get('atr_20') or signals.get('atr')):.4f}"
        ),
        'trend': {
            'macro': str(signals.get('trend', 'NEUTRO')),
            'short': str(signals.get('short_trend', 'NEUTRO')),
            'supertrend_signal': int(signals.get('supertrend_signal', 0) or 0),
            'ema_alignment': 'BULL' if ema8 > ema20 > 0 else ('BEAR' if ema8 < ema20 else 'FLAT'),
        },
        'emas': {
            'ema_8': round(ema8, 6),
            'ema_20': round(ema20, 6),
            'sma_200': round(sma200, 6),
            'vwap': round(_f(signals.get('vwap')), 6),
        },
        'structure': {
            'adx': round(_f(signals.get('adx')), 2),
            'is_lateral': bool(gates.get('is_lateral') or signals.get('is_lateral')),
            'market_regime': gates.get('market_regime', 'NEUTRO'),
            'amplitude_pct': round(_f(signals.get('amplitude_pct')), 3),
            'bollinger_expanding': bool(signals.get('bollinger_expanding')),
            'choppiness': round(_f(signals.get('choppiness')), 2),
        },
        'momentum': {
            'rsi': round(_f(signals.get('rsi'), 50), 2),
            'macd_hist': round(_f(signals.get('macd_hist')), 6),
            'macd_trend': str(signals.get('macd_trend', 'NEUTRO')),
        },
        'volatility_volume': {
            'atr': round(_f(signals.get('atr_20') or signals.get('atr')), 6),
            'atr_pct': round(_f(signals.get('atr_pct')), 3),
            'volume_ratio': round(_f(signals.get('volume_ratio'), 1.0), 3),
            'volume_score': gates.get('volume_score') or compute_volume_score(signals),
        },
        'levels': {
            'price': price,
            'pivot_high': _f(signals.get('pivot_high')),
            'pivot_low': _f(signals.get('pivot_low')),
            'near_support': bool(signals.get('near_pivot_support')),
            'near_resistance': bool(signals.get('near_pivot_resistance')),
            'fib_distance_pct': round(_f(signals.get('fib_distance_pct'), 100), 2),
        },
        'candle': {
            'body_ratio': round(_f(signals.get('candle_body_ratio')), 2),
            'strong_bullish': bool(signals.get('strong_bullish_candle')),
            'strong_bearish': bool(signals.get('strong_bearish_candle')),
        },
    }


def build_cerebro2_payload(
    signals: dict | None,
    intel_ctx: dict | None = None,
    order_book: dict | None = None,
    ticker: dict | None = None,
) -> dict[str, Any]:
    """Cérebro 2 — fluxo/liquidez em Python puro (volume, book skew, long/short) → C3."""
    signals = signals or {}
    intel_ctx = intel_ctx or {}
    flow = intel_ctx.get('groq_flow') or intel_ctx.get('order_flow') or {}

    bids = list((order_book or {}).get('bids') or [])[:20]
    asks = list((order_book or {}).get('asks') or [])[:20]
    bid_sz = sum(_f(x[1]) for x in bids if len(x) >= 2)
    ask_sz = sum(_f(x[1]) for x in asks if len(x) >= 2)
    imb = (bid_sz - ask_sz) / (bid_sz + ask_sz + 1e-9)
    book_skew = bid_sz / (ask_sz + 1e-9)

    info = (ticker or {}).get('info') or {}
    funding = _f(info.get('fundingRate') or info.get('funding_rate') or (ticker or {}).get('fundingRate'))
    recent_ret = _f(signals.get('recent_return_pct'))
    vol_ratio = _f(signals.get('volume_ratio'), 1.0)

    ls_hint = 'NEUTRAL'
    if funding > 0.0003:
        ls_hint = 'LONG_CROWDED'
    elif funding < -0.0003:
        ls_hint = 'SHORT_CROWDED'
    if book_skew >= 1.6:
        ls_hint = 'BID_DOMINANT'
    elif book_skew <= (1 / 1.6):
        ls_hint = 'ASK_DOMINANT'

    return {
        'brain': 2,
        'role': 'Fluxo / Liquidez (Python puro)',
        'available': True,
        'score': round(min(100.0, max(0.0, 40 + abs(imb) * 40 + min(20.0, (vol_ratio - 1) * 20))), 1),
        'action': (
            'BUY' if imb > 0.15 and vol_ratio >= 1.2
            else ('SELL' if imb < -0.15 and vol_ratio >= 1.2 else 'WAIT')
        ),
        'report': (
            f"vol×={vol_ratio:.2f} skew={book_skew:.2f} imb={imb:.3f} "
            f"ret%={recent_ret:.2f} LS={ls_hint}"
        ),
        'order_book': {
            'imbalance': round(imb, 4),
            'book_skew': round(book_skew, 4),
            'bid_size_top20': round(bid_sz, 4),
            'ask_size_top20': round(ask_sz, 4),
            'score_fluxo': _f(flow.get('score_fluxo')),
            'forca_agressao': _f(flow.get('forca_agressao')),
            'source': flow.get('source', 'local_book'),
        },
        'volume_flow': {
            'volume_ratio': round(vol_ratio, 3),
            'recent_return_pct': round(recent_ret, 3),
            'money_flow_side': str(signals.get('money_flow_side', 'WAIT')),
        },
        'sentiment': {
            'global_trend': 'NEUTRAL',  # notícias desativadas — neutro técnico
            'sentiment_score': 50.0,
            'news_risk': 'LOW',
            'investor_mood': 'NEUTRAL',
        },
        'whales': {
            'whale_score': round(_f((intel_ctx.get('whale') or {}).get('whale_score') or intel_ctx.get('whale_score')), 1),
            'whale_aligned': bool(intel_ctx.get('whale_aligned')),
        },
        'derivatives': {
            'funding_rate': funding if funding else None,
            'open_interest': info.get('openInterest') or info.get('open_interest'),
            'long_short_hint': ls_hint,
        },
        'timing_score': round(_f(intel_ctx.get('timing_score'), 50), 1),
        'advisory_flags': list(intel_ctx.get('advisory_flags') or []),
    }


def merge_context_for_cerebro3(
    symbol: str,
    signals: dict,
    gates: dict,
    c1: dict,
    c2: dict,
    intel_ctx: dict | None = None,
) -> dict[str, Any]:
    """Payload unificado entregue ao Cérebro 3 decisor."""
    price = _f(signals.get('price') or signals.get('close'))
    return {
        'symbol': symbol,
        'price': price,
        'gates_advisory': gates,
        'cerebro1': c1,
        'cerebro2': c2,
        'intel': intel_ctx or {},
        'signals_snapshot': {
            'trend': signals.get('trend'),
            'short_trend': signals.get('short_trend'),
            'sinal_institucional': signals.get('sinal_institucional'),
            'volume_score': gates.get('volume_score'),
            'is_lateral': gates.get('is_lateral'),
            'turtle_breakout': signals.get('turtle_breakout'),
            'meltdown': signals.get('meltdown'),
            'dump_lane': signals.get('dump_lane'),
            'freefall': signals.get('freefall'),
            'meltdown_strength': signals.get('meltdown_strength'),
            'prefer_short': signals.get('prefer_short'),
            'vwap': signals.get('vwap'),
        },
    }


def _evaluate_anatomy_advisory(signals: dict, sinal: str, df=None) -> dict[str, Any]:
    try:
        from src.engine.candle_anatomy import analyze_from_dataframe, evaluate_candle_anatomy
    except Exception as err:
        return {'allowed': True, 'advisory': True, 'error': str(err)}

    if df is not None and hasattr(df, 'iloc') and len(df) >= 1:
        result = analyze_from_dataframe(df, sinal)
    else:
        result = evaluate_candle_anatomy(
            sinal_institucional=sinal,
            open_p=_f(signals.get('candle_open', signals.get('open'))),
            high=_f(signals.get('candle_high', signals.get('high'))),
            low=_f(signals.get('candle_low', signals.get('low'))),
            close=_f(signals.get('candle_close', signals.get('close', signals.get('price')))),
            opens=signals.get('candle_opens'),
            highs=signals.get('candle_highs'),
            lows=signals.get('candle_lows'),
            closes=signals.get('candle_closes'),
            atr=_f(signals.get('atr_20') or signals.get('atr')),
            fib_depth=_f(signals.get('fib_depth')),
        )
    result['advisory'] = True
    result['quality'] = 'FORTE' if result.get('allowed') else 'FRACA'
    return result
