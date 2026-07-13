import sqlite3
from typing import Optional

from src.ai_brain.learning import TradeLearner
from src.ai_brain.local_ml_engine import LocalMLEngine

# Relatório padrão quando Cérebro 1/2 falham por limite/API
AI_UNAVAILABLE_REPORT = "Dados indisponíveis devido a limites de API da IA"


class DataAnalystAgent:
    """
    Agente analista de dados local.
    Substitui a camada tática cloud por heurística determinística.
    """

    def get_signal(self, tech_data, symbol):
        score = 0
        reasons = []

        trend = tech_data.get('trend', 'NEUTRO')
        st_signal = tech_data.get('supertrend_signal', 0)

        if trend == 'ALTA' and st_signal == 1:
            score += 30
            reasons.append('SuperTrend alinhado com SMA 200 (Alta)')
        elif trend == 'BAIXA' and st_signal == -1:
            score += 30
            reasons.append('SuperTrend alinhado com SMA 200 (Baixa)')

        body_ratio = float(tech_data.get('candle_body_ratio', 0) or 0)
        range_expansion = float(tech_data.get('range_expansion', 0) or 0)
        if body_ratio > 60:
            score += 15
            reasons.append(f'Corpo do candle forte ({body_ratio:.1f}%)')
        if range_expansion > 1.2:
            score += 10
            reasons.append(f'Expansão de range detectada ({range_expansion:.1f}x ATR)')

        volume_ratio = float(tech_data.get('volume_ratio', 0) or 0)
        if volume_ratio > 1.5:
            score += 20
            reasons.append(f'Volume institucional detectado ({volume_ratio:.1f}x média)')

        rsi = float(tech_data.get('rsi', 50) or 50)
        if trend == 'ALTA' and 50 < rsi < 75:
            score += 15
            reasons.append(f'RSI em zona de aceleração ({rsi:.1f})')
        elif trend == 'BAIXA' and 25 < rsi < 50:
            score += 15
            reasons.append(f'RSI em zona de aceleração ({rsi:.1f})')
        elif rsi > 80 or rsi < 20:
            score -= 40
            reasons.append('RSI em exaustão extrema - risco de reversão')

        action = 'WAIT'
        trend = tech_data.get('trend', 'NEUTRO')
        st = int(tech_data.get('supertrend_signal', 0) or 0)
        if score >= 60 and trend == 'ALTA' and st == 1:
            action = 'BUY'
        elif score >= 60 and trend == 'BAIXA' and st == -1:
            action = 'SELL'

        return min(100, score), action, ' | '.join(reasons)


class IntelligenceAgent:
    """Agente de inteligência de mercado — regime, baleias, notícias e timing."""

    def get_signal(self, tech_data, symbol, intelligence_context=None):
        ctx = intelligence_context or {}
        score = float(ctx.get('intelligence_score', 50) or 50)
        reasons = [str(ctx.get('summary', 'Sem dados de inteligência'))]

        # Em modo autônomo do Cérebro 3, não trava por veto soft de IA cloud
        if (
            not ctx.get('allow_entry', True)
            and not ctx.get('ai_assistants_unavailable')
            and not ctx.get('autonomous_mode')
        ):
            return 0, 'WAIT', ' | '.join(ctx.get('veto_reasons', ['Entrada bloqueada pela IA']))

        if ctx.get('whale_aligned'):
            score = min(100.0, score + 10)
            reasons.append('Baleias alinhadas com a tendência')

        if ctx.get('is_trending'):
            score = min(100.0, score + 8)
            reasons.append('Moeda em destaque global')

        timing = float(ctx.get('timing_score', 50) or 50)
        if timing >= 80:
            score = min(100.0, score + 10)
            reasons.append(f'Timing institucional favorável ({timing:.0f}/100)')

        trend = tech_data.get('trend', 'NEUTRO')
        st = int(tech_data.get('supertrend_signal', 0) or 0)
        action = 'WAIT'
        # Baleias alinhadas aumentam o score acima; não são mais requisito duro de ação
        if score >= 50 and trend == 'ALTA' and st == 1:
            action = 'BUY'
        elif score >= 50 and trend == 'BAIXA' and st == -1:
            action = 'SELL'

        return max(0, min(100, score)), action, ' | '.join(reasons)


class LearningAgent:
    """
    Agente de aprendizado local.
    Usa o histórico salvo no SQLite para penalizar ou reforçar ativos.
    """

    def __init__(self, db_path='database.db'):
        self.db_path = db_path

    def _get_history(self, symbol):
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT pnl_pct FROM neural_memory WHERE symbol = ? AND status = 'CLOSED' ORDER BY timestamp DESC LIMIT 5",
                (symbol,),
            )
            rows = cur.fetchall()
            conn.close()
            return [row[0] for row in rows]
        except Exception:
            return []

    def get_signal(self, tech_data, symbol):
        history = self._get_history(symbol)
        score = 70
        reasons = []

        if not history:
            reasons.append('Ativo novo - aguardar confirmação institucional')
            return 50, 'WAIT', reasons[0]

        wins = sum(1 for pnl in history if pnl > 0)
        losses = sum(1 for pnl in history if pnl < 0)
        total_pnl = sum(history)

        if total_pnl > 5:
            score += 20
            reasons.append(f'Histórico positivo (+{total_pnl:.1f}%)')
        elif total_pnl < -10:
            score -= 40
            reasons.append(f'Histórico negativo ({total_pnl:.1f}%)')

        if losses >= 3:
            score -= 30
            reasons.append('Sequência de derrotas')
        elif wins >= 3:
            score += 10
            reasons.append('Sequência de vitórias')

        action = 'WAIT'
        trend = tech_data.get('trend', 'NEUTRO')
        st = int(tech_data.get('supertrend_signal', 0) or 0)
        if score >= 60 and trend == 'ALTA' and st == 1:
            action = 'BUY'
        elif score >= 60 and trend == 'BAIXA' and st == -1:
            action = 'SELL'

        return max(0, min(100, score)), action, ' | '.join(reasons)


class Cerebro1TrendCandles:
    """Cérebro 1 — Assistente técnico de Tendência e Velas."""

    def __init__(self, analyst: DataAnalystAgent):
        self.analyst = analyst

    def generate_report(self, tech_data, symbol) -> dict:
        score, action, motivo = self.analyst.get_signal(tech_data, symbol)
        return {
            'brain': 1,
            'role': 'Tendência e Velas',
            'available': True,
            'score': float(score),
            'action': action,
            'report': motivo or 'Relatório técnico de tendência/velas',
        }


class Cerebro2BookVolume:
    """Cérebro 2 — Assistente técnico de Livro, Volume e Inteligência."""

    def __init__(self, intelligence: IntelligenceAgent):
        self.intelligence = intelligence

    def generate_report(self, tech_data, symbol, intelligence_context=None) -> dict:
        ctx = intelligence_context or {}
        # Se a camada cloud/news já sinalizou indisponibilidade, propaga relatório padrão
        if ctx.get('ai_assistants_unavailable'):
            return {
                'brain': 2,
                'role': 'Livro e Volume',
                'available': False,
                'score': 0.0,
                'action': 'WAIT',
                'report': AI_UNAVAILABLE_REPORT,
            }

        score, action, motivo = self.intelligence.get_signal(
            tech_data, symbol, intelligence_context,
        )
        # Reforça leitura de volume/livro local no relatório
        volume_ratio = float(tech_data.get('volume_ratio', 0) or 0)
        report = f"{motivo} | Volume×={volume_ratio:.2f}"
        return {
            'brain': 2,
            'role': 'Livro e Volume',
            'available': True,
            'score': float(score),
            'action': action,
            'report': report,
        }


class Cerebro3Sovereign:
    """
    Cérebro 3 — Tomador de decisão soberano.
    Usa matemática local da corretora + histórico de acertos/derrotas (local_ml_trades).
    """

    def __init__(self, learner: LearningAgent, local_ml: Optional[LocalMLEngine] = None):
        self.learner = learner
        self.local_ml = local_ml or LocalMLEngine()

    def decide(self, tech_data, symbol, report_c1: dict, report_c2: dict, intelligence_context=None) -> dict:
        ctx = intelligence_context or {}
        assistants_down = (
            (not report_c1.get('available', True))
            or (not report_c2.get('available', True))
            or AI_UNAVAILABLE_REPORT in str(report_c1.get('report', ''))
            or AI_UNAVAILABLE_REPORT in str(report_c2.get('report', ''))
        )

        learning_ctx = ''
        try:
            learning_ctx = self.local_ml.get_learning_context(symbol)
        except Exception:
            learning_ctx = 'Histórico local indisponível'

        score_learner, action_learner, motivo_learner = self.learner.get_signal(tech_data, symbol)

        # Injeta notícias/heat no tech_data para o Cérebro 3
        enriched = dict(tech_data or {})
        for key in ('sentiment_score', 'global_trend', 'news_risk', 'web_news_bias', 'is_trending'):
            if key in ctx and key not in enriched:
                enriched[key] = ctx.get(key)
        headlines = ctx.get('headlines') or (ctx.get('news') or {}).get('headlines') or []
        news_blurb = ''
        if headlines:
            titles = [str(h.get('title', ''))[:80] for h in headlines[:3] if isinstance(h, dict)]
            news_blurb = ' | Web: ' + ' // '.join(titles)

        if assistants_down:
            clean = (
                str(symbol or '')
                .replace('/USDT:USDT', '')
                .replace(':USDT', '')
                .replace('/USDT', '')
            )
            if clean.upper().endswith('USDT') and len(clean) > 4:
                clean = clean[:-4]
            clean = clean or symbol
            print(
                "⚠️ [MAESTRO] Cérebro 1/2 limitados por requisição. "
                "Ativando Modo Autônomo do Cérebro 3.",
                flush=True,
            )

            # Plano B: matemática + histórico + notícias web + heat de velas
            allowed, reason_entry, confidence = self.local_ml.evaluate_entry_conditions(
                symbol, enriched, intelligence_context=ctx,
            )
            direction, reason_dir = self.local_ml.resolve_entry_direction(enriched, intelligence_context=ctx)

            confidence = float(confidence)
            if 'positivo' in str(motivo_learner).lower() or 'vitórias' in str(motivo_learner).lower():
                confidence = min(100.0, confidence + 5)
            if 'negativo' in str(motivo_learner).lower() or 'derrotas' in str(motivo_learner).lower():
                confidence = max(0.0, confidence - 15)

            final_action = 'WAIT'
            if allowed and direction in ('BUY', 'SELL'):
                final_action = direction
            elif confidence >= 80 and direction in ('BUY', 'SELL'):
                final_action = direction

            print(
                f"🚀 [CÉREBRO 3] Decisão tomada de forma independente para o ativo [{clean}].",
                flush=True,
            )
            if headlines:
                print(f"   📰 [CÉREBRO 3] Notícias web analisadas: {len(headlines)} manchetes", flush=True)

            return {
                'autonomous': True,
                'probabilidade': confidence if final_action != 'WAIT' else max(confidence, float(score_learner)),
                'decisao': final_action,
                'motivo': (
                    f"Modo Autônomo Cérebro 3 | {reason_dir} | {reason_entry} | "
                    f"Aprendizado: {motivo_learner} | {learning_ctx}{news_blurb}"
                ),
                'score_learner': float(score_learner),
                'action_learner': action_learner,
                'motivo_learner': motivo_learner,
                'learning_context': learning_ctx,
            }

        # Modo normal: Cérebro 3 lidera com relatórios dos assistentes + histórico + news/heat
        local_score = 0
        trend = str(enriched.get('trend', 'NEUTRO')).upper()
        st = int(enriched.get('supertrend_signal', 0) or enriched.get('supertrend', 0) or 0)
        if trend in ('ALTA', 'BAIXA'):
            local_score += 25
        if float(enriched.get('fib_distance_pct', 100) or 100) < 1.5:
            local_score += 30
        if float(enriched.get('volume_ratio', 0) or 0) >= 1.5:
            local_score += 20
        heat = float(enriched.get('heat_score', 0) or 0)
        if heat >= 55:
            local_score += 15
        if str(ctx.get('global_trend', '')).upper() in ('BULLISH', 'BEARISH'):
            gt = str(ctx.get('global_trend')).upper()
            if (trend == 'ALTA' and gt == 'BULLISH') or (trend == 'BAIXA' and gt == 'BEARISH'):
                local_score += 10
            elif (trend == 'ALTA' and gt == 'BEARISH') or (trend == 'BAIXA' and gt == 'BULLISH'):
                local_score -= 15
        local_score = max(0, min(100, local_score))

        score_c1 = float(report_c1.get('score', 0) or 0)
        score_c2 = float(report_c2.get('score', 0) or 0)
        probability = (score_c1 * 0.28) + (score_c2 * 0.22) + (score_learner * 0.20) + (local_score * 0.30)

        actions = [
            report_c1.get('action', 'WAIT'),
            report_c2.get('action', 'WAIT'),
            action_learner,
        ]
        buy_votes = sum(1 for a in actions if a == 'BUY')
        sell_votes = sum(1 for a in actions if a == 'SELL')

        final_action = 'WAIT'
        if buy_votes >= 2 and probability >= 60 and trend == 'ALTA' and st == 1:
            final_action = 'BUY'
        elif sell_votes >= 2 and probability >= 60 and trend == 'BAIXA' and st == -1:
            final_action = 'SELL'
        elif probability >= 78 and trend == 'ALTA' and st == 1 and report_c1.get('action') == 'BUY':
            final_action = 'BUY'
        elif probability >= 78 and trend == 'BAIXA' and st == -1 and report_c1.get('action') == 'SELL':
            final_action = 'SELL'

        # Conflito notícias vs direção → não entra
        gt = str(ctx.get('global_trend', '')).upper()
        if final_action == 'BUY' and gt == 'BEARISH' and str(ctx.get('news_risk', '')).upper() == 'HIGH':
            final_action = 'WAIT'
        if final_action == 'SELL' and gt == 'BULLISH' and str(ctx.get('news_risk', '')).upper() == 'HIGH':
            final_action = 'WAIT'

        return {
            'autonomous': False,
            'probabilidade': probability,
            'decisao': final_action,
            'motivo': (
                f"C1: {str(report_c1.get('report', ''))[:80]} | "
                f"C2: {str(report_c2.get('report', ''))[:80]} | "
                f"C3 Aprendizado: {motivo_learner[:80]} | Heat={heat:.0f} | "
                f"News={gt or 'N/A'}{news_blurb[:120]}"
            ),
            'score_learner': float(score_learner),
            'action_learner': action_learner,
            'motivo_learner': motivo_learner,
            'learning_context': learning_ctx,
            'votes': {'buy': buy_votes, 'sell': sell_votes},
            'local_score': local_score,
        }


def _unavailable_report(brain: int, role: str) -> dict:
    return {
        'brain': brain,
        'role': role,
        'available': False,
        'score': 0.0,
        'action': 'WAIT',
        'report': AI_UNAVAILABLE_REPORT,
    }


class GroqValidator:
    """
    Mantém o nome para compatibilidade com o restante do sistema.
    Hierarquia resiliente:
      - Cérebro 1/2: assistentes técnicos isolados (try/except)
      - Cérebro 3: tomador soberano (LocalML + histórico wins/losses)
    """

    def __init__(self, api_key_gemini=None, api_key_groq=None):
        self.analyst = DataAnalystAgent()
        self.intelligence = IntelligenceAgent()
        self.learner = LearningAgent()
        self.memory = TradeLearner()
        self.local_ml = LocalMLEngine()
        self.cerebro1 = Cerebro1TrendCandles(self.analyst)
        self.cerebro2 = Cerebro2BookVolume(self.intelligence)
        self.cerebro3 = Cerebro3Sovereign(self.learner, self.local_ml)

    def local_signal(self, tech_data):
        score = 0
        trend = tech_data.get('trend', '---')
        if trend in ['ALTA', 'BAIXA']:
            score += 30
        if float(tech_data.get('fib_distance_pct', 100) or 100) < 1.5:
            score += 40
        if float(tech_data.get('volume_ratio', 0) or 0) >= 1.5:
            score += 30
        return min(100, score)

    def consensus_predict(self, tech_data, symbol, force_local_only=True, intelligence_context=None):
        trend = tech_data.get('trend', 'NEUTRO')
        if trend == 'NEUTRO':
            return {
                'probabilidade': 0,
                'decisao': 'WAIT',
                'motivo': 'Tendência neutra - bloqueio de scanner',
                'agents': [],
            }

        ctx = dict(intelligence_context or {})
        assistants_unavailable = bool(ctx.get('ai_assistants_unavailable') or ctx.get('autonomous_mode'))

        # Vetos duros (ex.: mercado lateral) ainda bloqueiam.
        # Vetos soft / API indisponível NÃO travam — Cérebro 3 assume.
        if ctx and not ctx.get('allow_entry', True) and not assistants_unavailable:
            hard = ctx.get('hard_veto_reasons') or ctx.get('veto_reasons', [])
            soft_only = bool(ctx.get('soft_ai_veto_only'))
            if hard and not soft_only:
                return {
                    'probabilidade': 0,
                    'decisao': 'WAIT',
                    'motivo': f"IA institucional bloqueou: {' | '.join(hard)}",
                    'intelligence': ctx,
                    'agents': [],
                }
            # Soft veto → ativa autonomia do Cérebro 3
            ctx['ai_assistants_unavailable'] = True
            assistants_unavailable = True

        # ── Cérebro 1 (Tendência e Velas) — isolado ──────────────────────────
        try:
            if assistants_unavailable and ctx.get('force_assistants_unavailable'):
                report_c1 = _unavailable_report(1, 'Tendência e Velas')
            else:
                report_c1 = self.cerebro1.generate_report(tech_data, symbol)
        except Exception:
            report_c1 = _unavailable_report(1, 'Tendência e Velas')

        # ── Cérebro 2 (Livro e Volume / IA cloud) — isolado ──────────────────
        try:
            report_c2 = self.cerebro2.generate_report(tech_data, symbol, ctx)
        except Exception:
            report_c2 = _unavailable_report(2, 'Livro e Volume')

        # ── Cérebro 3 soberano ───────────────────────────────────────────────
        decision = self.cerebro3.decide(
            tech_data, symbol, report_c1, report_c2, intelligence_context=ctx,
        )

        score_local = self.local_signal(tech_data)
        score_analyst = float(report_c1.get('score', 0) or 0)
        action_analyst = report_c1.get('action', 'WAIT')
        motivo_analyst = str(report_c1.get('report', ''))

        score_intel = float(report_c2.get('score', 0) or 0)
        action_intel = report_c2.get('action', 'WAIT')
        motivo_intel = str(report_c2.get('report', ''))

        score_learner = float(decision.get('score_learner', 50) or 50)
        action_learner = decision.get('action_learner', 'WAIT')
        motivo_learner = str(decision.get('motivo_learner', ''))

        # Personas cloud preservadas para UI/Tribunal (não remove lógica atual)
        score_gemini = min(100.0, (score_intel * 0.65) + (score_local * 0.35)) if report_c2.get('available') else 0.0
        score_groq = (
            min(100.0, (score_analyst * 0.55) + (float(tech_data.get('volume_ratio', 1) or 1) * 12) + (score_local * 0.2))
            if report_c1.get('available') else 0.0
        )

        if report_c2.get('available'):
            action_gemini = action_intel if action_intel != 'WAIT' else (
                'BUY' if trend == 'ALTA' and score_gemini >= 55 else (
                    'SELL' if trend == 'BAIXA' and score_gemini >= 55 else 'WAIT'
                )
            )
            motivo_gemini = (
                f"{motivo_intel} | Macro local={score_local:.0f} | "
                f"Sentimento={ctx.get('global_trend', 'NEUTRAL')}"
            )
        else:
            action_gemini = 'WAIT'
            motivo_gemini = AI_UNAVAILABLE_REPORT
            score_gemini = 0.0

        if report_c1.get('available'):
            action_groq = action_analyst if action_analyst != 'WAIT' else (
                'BUY' if trend == 'ALTA' and score_groq >= 55 else (
                    'SELL' if trend == 'BAIXA' and score_groq >= 55 else 'WAIT'
                )
            )
            motivo_groq = (
                f"{motivo_analyst} | Timing tático score={score_groq:.0f} | "
                f"Volume×={float(tech_data.get('volume_ratio', 0) or 0):.2f}"
            )
        else:
            action_groq = 'WAIT'
            motivo_groq = AI_UNAVAILABLE_REPORT
            score_groq = 0.0

        autonomous = bool(decision.get('autonomous'))
        if autonomous:
            probability = float(decision.get('probabilidade', 0) or 0)
            final_action = decision.get('decisao', 'WAIT')
            buy_votes = 1 if final_action == 'BUY' else 0
            sell_votes = 1 if final_action == 'SELL' else 0
        else:
            # Consenso ponderado original (preservado) quando assistentes online
            probability = (
                (score_gemini * 0.25) +
                (score_groq * 0.25) +
                (score_analyst * 0.30) +
                (score_learner * 0.20)
            )
            final_action = 'WAIT'
            st = int(tech_data.get('supertrend_signal', 0) or 0)
            actions = [action_gemini, action_groq, action_analyst, action_learner]
            buy_votes = sum(1 for a in actions if a == 'BUY')
            sell_votes = sum(1 for a in actions if a == 'SELL')

            if buy_votes >= 2 and probability >= 60 and trend == 'ALTA' and st == 1:
                final_action = 'BUY'
            elif sell_votes >= 2 and probability >= 60 and trend == 'BAIXA' and st == -1:
                final_action = 'SELL'
            elif probability >= 78 and trend == 'ALTA' and st == 1 and action_analyst == 'BUY':
                final_action = 'BUY'
            elif probability >= 78 and trend == 'BAIXA' and st == -1 and action_analyst == 'SELL':
                final_action = 'SELL'

            # Cérebro 3 lidera: se o soberano divergiu com confiança alta, respeita
            sovereign_action = decision.get('decisao', 'WAIT')
            if sovereign_action in ('BUY', 'SELL') and float(decision.get('probabilidade', 0) or 0) >= 70:
                final_action = sovereign_action
                probability = max(probability, float(decision.get('probabilidade', 0) or 0))

        agents = [
            {
                'id': 'gemini',
                'label': 'Gemini Estratégico',
                'score': round(float(score_gemini), 1),
                'action': action_gemini,
                'motivo': motivo_gemini,
                'provider': 'local+intel' if report_c2.get('available') else 'unavailable',
                'weight': 25,
            },
            {
                'id': 'groq',
                'label': 'Groq Tático',
                'score': round(float(score_groq), 1),
                'action': action_groq,
                'motivo': motivo_groq,
                'provider': 'local+analyst' if report_c1.get('available') else 'unavailable',
                'weight': 25,
            },
            {
                'id': 'analyst',
                'label': 'Analista de Dados',
                'score': round(float(score_analyst), 1),
                'action': action_analyst,
                'motivo': motivo_analyst,
                'provider': 'local',
                'weight': 30,
            },
            {
                'id': 'learner',
                'label': 'Aprendizado Neural',
                'score': round(float(score_learner), 1),
                'action': action_learner,
                'motivo': motivo_learner,
                'provider': 'neural_memory',
                'weight': 20,
                'learning_notes': motivo_learner,
            },
        ]

        result = {
            'probabilidade': probability,
            'decisao': final_action,
            'motivo': (
                decision.get('motivo')
                if autonomous
                else (
                    f'Gemini: {motivo_gemini[:80]} | '
                    f'Groq: {motivo_groq[:80]} | '
                    f'Analista: {motivo_analyst[:80]} | '
                    f'Aprendizado: {motivo_learner[:80]}'
                )
            ),
            'agents': agents,
            'brains': {
                'gemini': 'online' if report_c2.get('available') else 'unavailable',
                'groq': 'online' if report_c1.get('available') else 'unavailable',
                'analyst': 'online' if report_c1.get('available') else 'unavailable',
                'learner': 'online',
                'local': 'autonomous' if autonomous else 'online',
                'intelligence': 'online' if report_c2.get('available') else 'unavailable',
                'cerebro1': 'online' if report_c1.get('available') else 'unavailable',
                'cerebro2': 'online' if report_c2.get('available') else 'unavailable',
                'cerebro3': 'autonomous' if autonomous else 'leader',
            },
            'votes': {'buy': buy_votes, 'sell': sell_votes},
            'autonomous_mode': autonomous,
            'cerebro_reports': {
                'cerebro1': report_c1,
                'cerebro2': report_c2,
                'cerebro3': {
                    'autonomous': autonomous,
                    'learning_context': decision.get('learning_context', ''),
                },
            },
        }
        if ctx:
            result['intelligence'] = ctx
        return result
