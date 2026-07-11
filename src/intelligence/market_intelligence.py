"""
Orquestrador de inteligência de mercado.

Integra: regime (lateral vs tendência), baleias, notícias/sentimento e timing.
"""

from __future__ import annotations

import os
from typing import Any

from src.intelligence.news_analyzer import analyze_news_sentiment
from src.intelligence.regime_detector import detect_market_regime
from src.intelligence.whale_detector import analyze_whale_activity


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


class MarketIntelligence:
    """
    Camada de IA institucional do robô.

    Objetivos:
    - Ficar FORA do mercado lateral
    - Seguir fluxo de grandes players (baleias)
    - Considerar notícias e sentimento global
    - Escolher o melhor timing de entrada
    """

    def evaluate(
        self,
        symbol: str,
        df,
        signals: dict,
        ticker: dict | None = None,
    ) -> dict[str, Any]:
        if not _env_bool('ENABLE_MARKET_INTELLIGENCE', True):
            return self._passthrough(signals)

        regime = detect_market_regime(df, signals)
        whale = analyze_whale_activity(signals, ticker, df)
        news = analyze_news_sentiment(symbol, signals, regime, whale)

        block_lateral = _env_bool('BLOCK_LATERAL_MARKETS', True)
        veto_reasons = []

        if block_lateral and regime.get('is_lateral'):
            veto_reasons.append(
                f"Mercado LATERAL (ADX={regime.get('adx')}, Choppiness={regime.get('choppiness')})"
            )

        if news.get('block_trade'):
            veto_reasons.append(f"Notícias/sentimento bloqueiam: {news.get('reason', '')[:120]}")

        whale_score = float(whale.get('whale_score', 0) or 0)
        volume_ratio = float(signals.get('volume_ratio', 0) or 0)
        # Modo agressivo: desalinhamento de baleias PENALIZA o score (não veta duro).
        # Continua favorecendo fluxo alinhado, mas não trava o radar de tendências.
        whale_penalty = 0.0
        if not whale.get('whale_aligned'):
            whale_penalty = 12.0
        elif whale_score < 20 and volume_ratio < 1.15:
            whale_penalty = 8.0

        trend = str(signals.get('trend', 'NEUTRO')).upper()
        body_ratio = float(signals.get('candle_body_ratio', 0) or 0)
        recent_ret = float(signals.get('recent_return_pct', 0) or 0)
        # Só bloqueia velas CONTRÁRIAS muito fortes (evita matar pullbacks normais)
        if trend == 'ALTA' and recent_ret < -0.8 and body_ratio >= 60:
            veto_reasons.append('Vela de venda forte contra tendência de alta')
        if trend == 'BAIXA' and recent_ret > 0.8 and body_ratio >= 60:
            veto_reasons.append('Vela de compra forte contra tendência de baixa')

        # Timing: prefere entrada perto da golden zone (fib 0.618)
        fib_dist = float(signals.get('fib_distance_pct', 100) or 100)
        timing_score = 50.0
        if fib_dist <= 1.5:
            timing_score = 95.0
        elif fib_dist <= 3.0:
            timing_score = 75.0
        elif fib_dist <= 5.0:
            timing_score = 55.0
        else:
            timing_score = 30.0

        if whale.get('whale_aligned'):
            timing_score = min(100.0, timing_score + 15)

        # Score composto de inteligência
        intelligence_score = (
            (100 - float(regime.get('lateral_score', 50) or 50)) * 0.30 +
            float(whale.get('whale_score', 0) or 0) * 0.35 +
            float(news.get('sentiment_score', 50) or 50) * 0.20 +
            timing_score * 0.15
        ) - whale_penalty

        allow_entry = len(veto_reasons) == 0 and intelligence_score >= 50

        return {
            'intelligence_score': round(intelligence_score, 2),
            'timing_score': round(timing_score, 2),
            'allow_entry': allow_entry,
            'veto_reasons': veto_reasons,
            'market_regime': regime.get('market_regime'),
            'regime_label': regime.get('regime_label'),
            'is_lateral': regime.get('is_lateral'),
            'adx': regime.get('adx'),
            'choppiness': regime.get('choppiness'),
            'whale_score': whale.get('whale_score'),
            'whale_aligned': whale.get('whale_aligned'),
            'whale_reasons': whale.get('reasons', []),
            'sentiment_score': news.get('sentiment_score'),
            'global_trend': news.get('global_trend'),
            'investor_mood': news.get('investor_mood'),
            'news_risk': news.get('news_risk'),
            'is_trending': news.get('is_trending'),
            'news_reason': news.get('reason'),
            'ai_source': news.get('source'),
            'summary': self._build_summary(regime, whale, news, timing_score, allow_entry),
        }

    def _passthrough(self, signals: dict) -> dict:
        return {
            'intelligence_score': 70.0,
            'timing_score': 70.0,
            'allow_entry': True,
            'veto_reasons': [],
            'market_regime': 'TREND',
            'is_lateral': False,
            'summary': 'Inteligência de mercado desativada',
        }

    def _build_summary(self, regime, whale, news, timing_score, allow_entry) -> str:
        parts = [
            str(regime.get('regime_label', '')),
            f"Baleias: {whale.get('whale_score', 0)}/100",
            f"Sentimento: {news.get('global_trend', 'NEUTRAL')} ({news.get('investor_mood', '')})",
            f"Timing: {timing_score:.0f}/100",
        ]
        if not allow_entry:
            parts.append('ENTRADA BLOQUEADA')
        return ' | '.join(p for p in parts if p)


_market_intelligence: MarketIntelligence | None = None


def get_market_intelligence() -> MarketIntelligence:
    global _market_intelligence
    if _market_intelligence is None:
        _market_intelligence = MarketIntelligence()
    return _market_intelligence
