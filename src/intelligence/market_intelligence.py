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
        hard_veto_reasons = []
        soft_veto_reasons = []
        ai_assistants_unavailable = False
        # Cloud news degradado NÃO derruba Cérebro 1/2/3 — só assistente informativo
        cloud_news_degraded = bool(
            news.get('cloud_ai_degraded')
            or news.get('ai_unavailable')
            or str(news.get('ai_status', '')).lower() == 'degradado'
        )
        if cloud_news_degraded:
            coin = str(symbol or '').replace('/USDT:USDT', '').replace('/USDT', '').replace(':USDT', '')
            print(
                f'⚠️ [ASSISTENTE IA] Notícias indisponíveis para {coin}. '
                f'Passando comando para análise técnica do Cérebro 3.',
                flush=True,
            )
            # #region agent log
            try:
                from src.debug_agent_log import agent_dbg
                agent_dbg('A', 'market_intelligence.py:evaluate', 'cloud_news_degraded_soft', {
                    'symbol': str(symbol)[:40],
                    'ai_assistants_unavailable': False,
                    'source': news.get('source'),
                    'ai_status': news.get('ai_status', 'degradado'),
                    'block_trade': False,
                })
            except Exception:
                pass
            # #endregion

        if block_lateral and regime.get('is_lateral'):
            hard_veto_reasons.append(
                f"Mercado LATERAL (ADX={regime.get('adx')}, Choppiness={regime.get('choppiness')})"
            )

        # Assistente de notícias: NUNCA adiciona veto soft / nunca bloqueia entrada.
        # (block_trade e cloud_news_degraded são apenas informativos.)

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
            hard_veto_reasons.append('Vela de venda forte contra tendência de alta')
        if trend == 'BAIXA' and recent_ret > 0.8 and body_ratio >= 60:
            hard_veto_reasons.append('Vela de compra forte contra tendência de baixa')

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

        # Score composto: com IA degradada/indisponível, sentimento neutro (50) para não penalizar
        news_score = 50.0 if cloud_news_degraded else float(news.get('sentiment_score', 50) or 50)
        intelligence_score = (
            (100 - float(regime.get('lateral_score', 50) or 50)) * 0.30 +
            float(whale.get('whale_score', 0) or 0) * 0.35 +
            news_score * 0.20 +
            timing_score * 0.15
        ) - whale_penalty

        # Seguir baleias: alinhado dá bônus extra (oportunidade assertiva ainda passa sem alinhamento total)
        if whale.get('whale_aligned'):
            intelligence_score = min(100.0, intelligence_score + 8)

        soft_ai_veto_only = False

        # Decisão soberana do Cérebro 3: notícias degradadas/neutras NÃO bloqueiam.
        # Só vetos duros (lateral / vela contrária) podem impedir allow_entry aqui.
        if cloud_news_degraded:
            allow_entry = len(hard_veto_reasons) == 0
            autonomous_mode = True  # Cérebro 3 assume análise técnica pura
        else:
            # Sem soft-veto de notícias — score composto + vetos duros
            allow_entry = len(hard_veto_reasons) == 0 and intelligence_score >= 48
            autonomous_mode = False

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
            'sentiment_score': 50.0 if cloud_news_degraded else news.get('sentiment_score'),
            'global_trend': 'NEUTRAL' if cloud_news_degraded else news.get('global_trend'),
            'investor_mood': news.get('investor_mood'),
            'news_risk': 'LOW' if cloud_news_degraded else news.get('news_risk'),
            'is_trending': news.get('is_trending'),
            'news_reason': news.get('reason'),
            'ai_source': news.get('source'),
            'ai_status': news.get('ai_status', 'degradado' if cloud_news_degraded else 'ok'),
            'news': news,
            # Assistente nunca bloqueia — Cérebro 3 é soberano
            'news_block_trade': False,
            'headlines': list(news.get('headlines') or []),
            'web_news_bias': 'NEUTRAL' if cloud_news_degraded else news.get('web_news_bias', 'NEUTRAL'),
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
