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
from src.intelligence.order_flow_analyzer import analyze_order_book_flow
from src.intelligence.gemini_macro_analyzer import analyze_gemini_macro_news
from src.ai_brain.cerebro3_soberano import market_condition_from_signals


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
        order_book: dict | None = None,
    ) -> dict[str, Any]:
        # ADX/BB são blindagem estrutural obrigatória, mesmo se a camada de IA
        # complementar estiver desativada.
        regime = detect_market_regime(df, signals)
        if not _env_bool('ENABLE_MARKET_INTELLIGENCE', True):
            return self._passthrough(signals, regime)

        whale = analyze_whale_activity(signals, ticker, df)
        # Notícias legado (assistente) — desligado por padrão via ENABLE_NEWS_AI
        news = analyze_news_sentiment(symbol, signals, regime, whale)

        # Incremental: Groq fluxo (order book) + Gemini macro (manchetes)
        flow = analyze_order_book_flow(symbol, order_book=order_book, signals=signals)
        headlines = list(news.get('headlines') or [])
        gemini_macro = analyze_gemini_macro_news(
            symbol,
            headlines=headlines,
            news_blob=str(news.get('reason') or ''),
            signals={**signals, 'market_regime': regime.get('market_regime')},
        )
        condicao = market_condition_from_signals(signals, regime)

        # Estrutura: amplitude, ADX e expansão das Bandas são travas absolutas.
        # BLOCK_LATERAL_MARKETS controla apenas critérios complementares (chop/range).
        amplitude_lateral = bool(
            regime.get('amplitude_lateral')
            or signals.get('is_lateral_amplitude')
            or signals.get('is_accumulation')
        )
        adx_blocked = float(regime.get('adx', 0) or 0) < 23
        bb_blocked = not bool(regime.get('bollinger_expanding', False))
        block_lateral = _env_bool('BLOCK_LATERAL_MARKETS', True)  # default ON — anti-acumulação
        hard_veto_reasons = []
        soft_veto_reasons = []
        ai_assistants_unavailable = False
        cloud_news_degraded = bool(
            news.get('cloud_ai_degraded')
            or news.get('ai_unavailable')
            or str(news.get('ai_status', '')).lower() in ('degradado', 'disabled')
            or str(news.get('source', '')).lower() == 'disabled'
        )

        if adx_blocked:
            hard_veto_reasons.append(
                f"SEM TENDÊNCIA: ADX(14)={regime.get('adx', 0)} < 23 — sinal forçado a NEUTRO"
            )
        if bb_blocked:
            hard_veto_reasons.append(
                f"SEM EXPANSÃO: BB Width={regime.get('bollinger_bandwidth', 0)} <= "
                f"média(50)={regime.get('bollinger_bandwidth_mean_50', 0)} — sinal forçado a NEUTRO"
            )
        if amplitude_lateral:
            hard_veto_reasons.append(
                f"ACUMULAÇÃO/LATERAL por amplitude "
                f"({regime.get('amplitude_pct', signals.get('amplitude_pct', 0))}% "
                f"< limite) — sinais ignorados (NEUTRO)"
            )
        elif block_lateral and regime.get('is_lateral') and not (adx_blocked or bb_blocked):
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

        # Soft alerta Gemini (hard-veto só se ALLOW_NEWS_HARD_VETO e filtro True)
        if gemini_macro.get('filtro_noticia_travar_bot'):
            soft_veto_reasons.append(
                f"Gemini macro: risco sistêmico — {gemini_macro.get('narrativa_dominante', '')}"
            )
            if _env_bool('ALLOW_NEWS_HARD_VETO', False):
                hard_veto_reasons.append(
                    f"GEMINI HARD VETO: {gemini_macro.get('narrativa_dominante', 'notícia crítica')}"
                )
            else:
                soft_ai_veto_only = True
        elif gemini_macro.get('filtro_noticia_travar_bot_sugerido'):
            soft_veto_reasons.append(
                f"Gemini alerta (soft): {gemini_macro.get('narrativa_dominante', '')}"
            )
            soft_ai_veto_only = True

        # Assertivo: libera com score baixo; Cérebro 3 soberano
        allow_entry = len(hard_veto_reasons) == 0 and intelligence_score >= 32
        autonomous_mode = True

        # Sentimento derivado do Gemini macro (não zera o contrato legado)
        sent_macro = float(gemini_macro.get('score_sentimento_noticias', 0) or 0)
        sentiment_score = 50.0 + (sent_macro * 50.0)
        if sent_macro > 0.25:
            global_trend = 'BULLISH'
        elif sent_macro < -0.25:
            global_trend = 'BEARISH'
        else:
            global_trend = str(news.get('global_trend') or 'NEUTRAL').upper()

        return {
            'intelligence_score': round(intelligence_score, 2),
            'timing_score': round(timing_score, 2),
            'allow_entry': allow_entry,
            'veto_reasons': veto_reasons + soft_veto_reasons,
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
            'sentiment_score': round(sentiment_score, 2),
            'global_trend': global_trend,
            'investor_mood': news.get('investor_mood', 'NEUTRAL'),
            'news_risk': (
                'HIGH' if gemini_macro.get('impacto_volatilidade') == 'ALTO'
                else news.get('news_risk', 'LOW')
            ),
            'is_trending': bool(news.get('is_trending')),
            'news_reason': news.get('reason'),
            'ai_source': news.get('source'),
            'ai_status': news.get('ai_status', 'disabled'),
            'news': news,
            'news_block_trade': False,
            'headlines': headlines,
            'web_news_bias': news.get('web_news_bias', 'NEUTRAL'),
            # Incremental Smart Money assistants
            'order_flow': flow,
            'groq_flow': flow,
            'gemini_macro': gemini_macro,
            'condicao_mercado': condicao,
            'summary': self._build_summary(regime, whale, news, timing_score, allow_entry, flow, gemini_macro),
        }

    def _passthrough(self, signals: dict, regime: dict) -> dict:
        amplitude_blocked = bool(
            regime.get('amplitude_lateral')
            or signals.get('is_lateral_amplitude')
            or signals.get('is_accumulation')
        )
        adx_blocked = float(regime.get('adx', 0) or 0) < 23
        bb_blocked = not bool(regime.get('bollinger_expanding', False))
        structure_blocked = amplitude_blocked or adx_blocked or bb_blocked
        reasons = []
        if adx_blocked:
            reasons.append(f"ADX(14)={regime.get('adx', 0)} < 23")
        if bb_blocked:
            reasons.append("BB Width sem expansão acima da média(50)")
        if amplitude_blocked:
            reasons.append("amplitude em acumulação")
        return {
            'intelligence_score': 70.0,
            'timing_score': 70.0,
            'allow_entry': not structure_blocked,
            'veto_reasons': reasons,
            'hard_veto_reasons': reasons,
            'soft_veto_reasons': [],
            'soft_ai_veto_only': False,
            'ai_assistants_unavailable': False,
            'autonomous_mode': False,
            'market_regime': regime.get('market_regime'),
            'is_lateral': regime.get('is_lateral'),
            'adx': regime.get('adx'),
            'bollinger_bandwidth': regime.get('bollinger_bandwidth'),
            'bollinger_bandwidth_mean_50': regime.get('bollinger_bandwidth_mean_50'),
            'bollinger_expanding': regime.get('bollinger_expanding'),
            'summary': (
                'Inteligência complementar desativada; entrada bloqueada pela estrutura'
                if structure_blocked
                else 'Inteligência complementar desativada; estrutura liberada'
            ),
        }

    def _build_summary(self, regime, whale, news, timing_score, allow_entry, flow=None, gemini_macro=None) -> str:
        flow = flow or {}
        gemini_macro = gemini_macro or {}
        parts = [
            str(regime.get('regime_label', '')),
            f"Baleias: {whale.get('whale_score', 0)}/100",
            f"Fluxo Groq: {float(flow.get('score_fluxo', 0) or 0):+.2f}",
            f"Gemini: {gemini_macro.get('narrativa_dominante') or news.get('global_trend', 'NEUTRAL')}",
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
