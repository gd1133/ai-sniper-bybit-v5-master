import sqlite3
from src.ai_brain.learning import TradeLearner


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

        if not ctx.get('allow_entry', True):
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


class GroqValidator:
    """
    Mantém o nome para compatibilidade com o restante do sistema.
    A implementação é 100% local e não depende de Groq/Gemini.
    """

    def __init__(self, api_key_gemini=None, api_key_groq=None):
        self.analyst = DataAnalystAgent()
        self.intelligence = IntelligenceAgent()
        self.learner = LearningAgent()
        self.memory = TradeLearner()

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
            }

        if intelligence_context and not intelligence_context.get('allow_entry', True):
            vetos = intelligence_context.get('veto_reasons', [])
            return {
                'probabilidade': 0,
                'decisao': 'WAIT',
                'motivo': f"IA institucional bloqueou: {' | '.join(vetos)}",
                'intelligence': intelligence_context,
            }

        score_local = self.local_signal(tech_data)
        score_analyst, action_analyst, motivo_analyst = self.analyst.get_signal(tech_data, symbol)
        score_intel, action_intel, motivo_intel = self.intelligence.get_signal(
            tech_data, symbol, intelligence_context,
        )
        score_learner, action_learner, motivo_learner = self.learner.get_signal(tech_data, symbol)

        probability = (
            (score_local * 0.20) +
            (score_analyst * 0.30) +
            (score_intel * 0.30) +
            (score_learner * 0.20)
        )

        final_action = 'WAIT'
        trend = tech_data.get('trend', 'NEUTRO')
        st = int(tech_data.get('supertrend_signal', 0) or 0)
        actions = [action_analyst, action_intel, action_learner]
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

        result = {
            'probabilidade': probability,
            'decisao': final_action,
            'motivo': (
                f'Analista: {motivo_analyst} | '
                f'IA Mercado: {motivo_intel} | '
                f'Aprendizado: {motivo_learner}'
            ),
            'brains': {
                'local': 'online',
                'analyst': 'online',
                'intelligence': 'online',
                'learner': 'online',
            },
        }
        if intelligence_context:
            result['intelligence'] = intelligence_context
        return result
