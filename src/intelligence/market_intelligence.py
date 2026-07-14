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
        # Notícias desligadas por padrão — sem HTTP/Groq no caminho crítico de entrada
        news = analyze_news_sentiment(symbol, signals, regime, whale)

        # Lateral: só bloqueia se explicitamente ligado (default OFF = mais assertivo)
        block_lateral = _env_bool('BLOCK_LATERAL_MARKETS', False)
        hard_veto_reasons = []
        soft_veto_reasons = []
        ai_assistants_unavailable = False
        cloud_news_degraded = bool(
            news.get('cloud_ai_degraded')
            or news.get('ai_unavailable')
            or str(news.get('ai_status', '')).lower() in ('degradado', 'disabled')
            or str(news.get('source', '')).lower() == 'disabled'
        )

        if block_lateral and regime.get('is_lateral'):
            hard_veto_reasons.append(
                f"Mercado LATERAL (ADX={regime.get('adx')}, Choppiness={regime.get('choppiness')})"
            )

        whale_score = float(whale.get('whale_score', 0) or 0)
        volume_ratio = float(signals.get('volume_ratio', 0) or 0)
        # Assertivo: penalidade leve de baleias (não mata oportunidade)
        whale_penalty = 0.0
        if not whale.get('whale_aligned'):
            whale_penalty = 4.0
        elif whale_score < 20 and volume_ratio < 1.15:
            whale_penalty = 2.0

        # Velas contrárias: NÃO hard-veto no modo assertivo (só penalizam score via timing)
        veto_reasons = list(hard_veto_reasons)

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

        # Bônus incremental: pivô + vela forte (leitura de gráfico)
        chart_score = float(signals.get('chart_entry_score', 0) or 0)
        if chart_score >= 40:
            timing_score = min(100.0, timing_score + min(20.0, chart_score * 0.25))
        if signals.get('strong_bullish_candle') or signals.get('strong_bearish_candle'):
            timing_score = min(100.0, timing_score + 8)
        if signals.get('bounce_from_pivot_low') or signals.get('rejection_from_pivot_high'):
            timing_score = min(100.0, timing_score + 10)

        # Score SEM peso de notícias — só técnica (regime + baleias + timing)
        intelligence_score = (
            (100 - float(regime.get('lateral_score', 50) or 50)) * 0.35 +
            float(whale.get('whale_score', 0) or 0) * 0.40 +
            timing_score * 0.25
        ) - whale_penalty

        if whale.get('whale_aligned'):
            intelligence_score = min(100.0, intelligence_score + 8)

        soft_ai_veto_only = False

        # Assertivo: libera com score baixo; notícias nunca travam; Cérebro 3 soberano
        allow_entry = len(hard_veto_reasons) == 0 and intelligence_score >= 32
        autonomous_mode = True

        return {
            'intelligence_score': round(intelligence_score, 2),
            'timing_score': round(timing_score, 2),
            'allow_entry': allow_entry,
            'veto_reasons': veto_reasons,
            'hard_veto_reasons': hard_veto_reasons,
            'soft_veto_reasons': soft_veto_reasons,
            'soft_ai_veto_only': soft_ai_veto_only,
            'ai_assistants_unavailable': ai_assistants_unavailable,
            'cloud_news_degraded': cloud_news_degraded,
            'autonomous_mode': autonomous_mode or ai_assistants_unavailable,
            'market_regime': regime.get('market_regime'),
            'regime_label': regime.get('regime_label'),
            'is_lateral': regime.get('is_lateral'),
            'adx': regime.get('adx'),
            'choppiness': regime.get('choppiness'),
            'whale_score': whale.get('whale_score'),
            'whale_aligned': whale.get('whale_aligned'),
            'whale_reasons': whale.get('reasons', []),
            'sentiment_score': 50.0,
            'global_trend': 'NEUTRAL',
            'investor_mood': 'NEUTRAL',
            'news_risk': 'LOW',
            'is_trending': False,
            'news_reason': news.get('reason'),
            'ai_source': news.get('source'),
            'ai_status': news.get('ai_status', 'disabled'),
            'news': news,
            # Assistente nunca bloqueia — Cérebro 3 é soberano
            'news_block_trade': False,
            'headlines': [],
            'web_news_bias': 'NEUTRAL',
            'summary': self._build_summary(regime, whale, news, timing_score, allow_entry),
        }

    def _passthrough(self, signals: dict) -> dict:
        return {
            'intelligence_score': 70.0,
            'timing_score': 70.0,
            'allow_entry': True,
            'veto_reasons': [],
            'hard_veto_reasons': [],
            'soft_veto_reasons': [],
            'soft_ai_veto_only': False,
            'ai_assistants_unavailable': False,
            'autonomous_mode': False,
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
