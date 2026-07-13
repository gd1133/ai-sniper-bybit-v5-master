"""
Confluência Absoluta (Modo Concordância Total) — Motor Sniper V60.7+

Mantém intacto o Triplo Cérebro (SMC, Volume Clímax, Saída Dinâmica).
Só autoriza entrada se TODOS os 5 filtros institucionais forem True.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from src.engine.smc_order_blocks import (
    detect_liquidity_sweep,
    filtro_estrutural_smc,
)
from src.intelligence.regime_detector import calculate_adx


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def absolute_confluence_enabled() -> bool:
    return _env_bool('ENABLE_ABSOLUTE_CONFLUENCE', True)


def _normalize_side(side: str) -> str:
    s = str(side or '').upper()
    if s in ('BUY', 'COMPRAR', 'LONG'):
        return 'BUY'
    if s in ('SELL', 'VENDER', 'SHORT'):
        return 'SELL'
    return s


def filtro_volume_fluxo(df, signals: dict | None = None, side: str = 'BUY') -> dict[str, Any]:
    """
    Filtro 2 — Cérebro 2 Volume Clímax / Liquidity Sweep.
    """
    signals = signals or {}
    side_n = _normalize_side(side)
    vol_ratio = float(signals.get('volume_ratio', 0) or 0)
    climax = vol_ratio >= 2.0
    if not climax and df is not None and len(df) >= 6:
        try:
            recent = float(df['vol'].iloc[-1])
            avg = float(df['vol'].iloc[-6:-1].mean())
            climax = avg > 0 and (recent / avg) >= 2.0
        except Exception:
            pass

    sweep = detect_liquidity_sweep(df)
    if side_n == 'BUY':
        sweep_ok = bool(sweep.get('bullish_sweep'))
    else:
        sweep_ok = bool(sweep.get('bearish_sweep'))

    # Whale / money flow alinhado reforça climax (Triplo Cérebro)
    money_flow = str(signals.get('money_flow_side', 'WAIT')).upper()
    flow_aligned = (
        (side_n == 'BUY' and money_flow == 'BUY')
        or (side_n == 'SELL' and money_flow == 'SELL')
    )
    institutional_vol = str(signals.get('volume_trend', '')).upper() == 'ALTO'

    ok = bool(climax or sweep_ok or (institutional_vol and flow_aligned and vol_ratio >= 1.5))
    detail = (
        f"climax={climax} vol×={vol_ratio:.2f} sweep={sweep_ok} "
        f"flow={money_flow} institucional={institutional_vol}"
    )
    return {
        'ok': ok,
        'detail': detail,
        'volume_climax': climax,
        'liquidity_sweep': sweep_ok,
        'sweep_info': sweep,
    }


def filtro_order_book_imbalance(
    order_book: dict | None,
    side: str,
    *,
    depth: int = 20,
    min_imbalance_ratio: float = 1.60,
) -> dict[str, Any]:
    """
    Filtro 3 — Desequilíbrio do livro (top N bids/asks).
    Long:  soma(bids) >= 1.60 × soma(asks)  (+60% compradores)
    Short: soma(asks) >= 1.60 × soma(bids)  (+60% vendedores)
    """
    side_n = _normalize_side(side)
    if not order_book:
        return {'ok': False, 'detail': 'order book indisponível', 'bid_vol': 0.0, 'ask_vol': 0.0, 'ratio': 0.0}

    bids = order_book.get('bids') or []
    asks = order_book.get('asks') or []

    def _sum_qty(levels, n):
        total = 0.0
        for level in levels[:n]:
            try:
                if isinstance(level, (list, tuple)) and len(level) >= 2:
                    total += float(level[1])
                elif isinstance(level, dict):
                    total += float(level.get('qty') or level.get('size') or 0)
            except (TypeError, ValueError):
                continue
        return total

    bid_vol = _sum_qty(bids, depth)
    ask_vol = _sum_qty(asks, depth)
    if bid_vol <= 0 or ask_vol <= 0:
        return {
            'ok': False,
            'detail': f'profundidade inválida bids={bid_vol:.4f} asks={ask_vol:.4f}',
            'bid_vol': bid_vol,
            'ask_vol': ask_vol,
            'ratio': 0.0,
        }

    if side_n == 'BUY':
        ratio = bid_vol / ask_vol
        ok = ratio >= min_imbalance_ratio
        detail = f'bids/asks={ratio:.2f} (exige ≥{min_imbalance_ratio:.2f})'
    else:
        ratio = ask_vol / bid_vol
        ok = ratio >= min_imbalance_ratio
        detail = f'asks/bids={ratio:.2f} (exige ≥{min_imbalance_ratio:.2f})'

    return {
        'ok': bool(ok),
        'detail': detail,
        'bid_vol': bid_vol,
        'ask_vol': ask_vol,
        'ratio': float(ratio),
    }


def filtro_adx_tendencia(df, min_adx: float = 22.0) -> dict[str, Any]:
    """Filtro 4 — ADX 15m > 22 (anti-lateralização)."""
    adx = float(calculate_adx(df) if df is not None else 0.0)
    ok = adx > float(min_adx)
    return {'ok': ok, 'detail': f'ADX={adx:.1f} (exige >{min_adx})', 'adx': adx}


def classify_news_sentiment(news: dict | None = None, intel_ctx: dict | None = None) -> str:
    """
    Classifica sentimento 24h em POSITIVO | NEUTRO | NEGATIVO.
    Aceita dict `news` aninhado ou campos flat do MarketIntelligence.
    """
    intel_ctx = intel_ctx or {}
    news = news or intel_ctx.get('news') or {}
    score = float(
        news.get('sentiment_score', intel_ctx.get('sentiment_score', 50)) or 50
    )
    trend = str(
        news.get('global_trend', intel_ctx.get('global_trend', 'NEUTRAL')) or 'NEUTRAL'
    ).upper()

    if trend in ('BEARISH', 'NEGATIVE', 'NEGATIVO') or score < 40:
        return 'NEGATIVO'
    if trend in ('BULLISH', 'POSITIVE', 'POSITIVO') or score > 60:
        return 'POSITIVO'
    return 'NEUTRO'


def filtro_noticias_sentimento(
    side: str,
    news: dict | None = None,
    intel_ctx: dict | None = None,
) -> dict[str, Any]:
    """
    Filtro 5 — Long só com sentimento Positivo ou Neutro (nunca Negativo).
    Short espelha: bloqueia sentimento Positivo forte (viés contrário).
    """
    intel_ctx = intel_ctx or {}
    side_n = _normalize_side(side)
    label = classify_news_sentiment(news, intel_ctx)
    if side_n == 'BUY':
        ok = label in ('POSITIVO', 'NEUTRO')
        detail = f'sentimento={label} (Long exige Positivo/Neutro)'
    else:
        ok = label in ('NEGATIVO', 'NEUTRO')
        detail = f'sentimento={label} (Short exige Negativo/Neutro)'

    nested = news or intel_ctx.get('news') or {}
    if nested.get('block_trade') or intel_ctx.get('news_block_trade'):
        ok = False
        detail += ' | block_trade ativo'

    return {'ok': bool(ok), 'detail': detail, 'sentiment_label': label}


def avaliar_confluencia_absoluta(
    *,
    side: str,
    df,
    signals: dict | None = None,
    intel_ctx: dict | None = None,
    order_book: dict | None = None,
    df_macro=None,
    fetch_order_book_fn: Callable[[], dict | None] | None = None,
    min_adx: float = 22.0,
    imbalance_ratio: float = 1.60,
) -> dict[str, Any]:
    """
    Checklist obrigatório de Concordância Total.

    filtros_aprovados = all([smc, volume, livro, tendencia, noticias])
    """
    signals = signals or {}
    intel_ctx = intel_ctx or {}
    side_n = _normalize_side(side)

    if fetch_order_book_fn is not None and order_book is None:
        try:
            order_book = fetch_order_book_fn()
        except Exception as exc:
            order_book = None
            print(f'⚠️ [CONFLUÊNCIA] fetch_order_book falhou: {exc}', flush=True)

    news = intel_ctx.get('news') if isinstance(intel_ctx.get('news'), dict) else {}

    smc = filtro_estrutural_smc(df, side_n, signals, df_macro=df_macro)
    volume = filtro_volume_fluxo(df, signals, side_n)
    livro = filtro_order_book_imbalance(order_book, side_n, min_imbalance_ratio=imbalance_ratio)
    tendencia = filtro_adx_tendencia(df, min_adx=min_adx)
    noticias = filtro_noticias_sentimento(side_n, news=news, intel_ctx=intel_ctx)

    filtro_smc = bool(smc['ok'])
    filtro_volume = bool(volume['ok'])
    filtro_livro = bool(livro['ok'])
    filtro_tendencia = bool(tendencia['ok'])
    filtro_noticias = bool(noticias['ok'])

    filtros = {
        'filtro_smc': filtro_smc,
        'filtro_volume': filtro_volume,
        'filtro_livro': filtro_livro,
        'filtro_tendencia': filtro_tendencia,
        'filtro_noticias': filtro_noticias,
    }
    detalhes = {
        'filtro_smc': smc['detail'],
        'filtro_volume': volume['detail'],
        'filtro_livro': livro['detail'],
        'filtro_tendencia': tendencia['detail'],
        'filtro_noticias': noticias['detail'],
    }

    filtros_aprovados = all([
        filtro_smc,
        filtro_volume,
        filtro_livro,
        filtro_tendencia,
        filtro_noticias,
    ])

    failed = [name for name, ok in filtros.items() if not ok]

    print('\n🎯 [CONFLUÊNCIA ABSOLUTA] Concordância Total:', flush=True)
    for name, ok in filtros.items():
        mark = '✅' if ok else '❌'
        print(f'   {mark} {name}: {detalhes[name]}', flush=True)

    if filtros_aprovados:
        print('✅ [SINAL APROVADO] Confluência Total — autorização de sniper liberada.', flush=True)
    else:
        print(
            '❌ [SINAL REJEITADO] Falha na Confluência Total. Fatores não se alinharam. '
            f'Falhas: {failed}',
            flush=True,
        )

    return {
        'aprovado': filtros_aprovados,
        'filtros': filtros,
        'detalhes': detalhes,
        'failed': failed,
        'side': side_n,
        'smc': smc,
        'volume': volume,
        'livro': livro,
        'tendencia': tendencia,
        'noticias': noticias,
    }
