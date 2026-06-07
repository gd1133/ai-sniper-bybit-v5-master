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
        rsi = float(tech_data.get('rsi', 50) or 50)
        rsi_fast = float(tech_data.get('rsi_fast', 50) or 50)

        # CÉREBRO 1 - Filtro estrutural anti-armadilha
        near_resistance = bool(tech_data.get('near_resistance'))
        near_support = bool(tech_data.get('near_support'))
        block_long = bool(tech_data.get('block_long_trap'))
        block_short = bool(tech_data.get('block_short_trap'))

        macro_log = (
            f"[CÉREBRO 1] Tendência Macro identificada: {trend}. "
            f"Order Block Bull={bool(tech_data.get('bullish_order_block'))} | "
            f"Order Block Bear={bool(tech_data.get('bearish_order_block'))}."
        )
        reasons.append(macro_log)

        if trend == 'ALTA' and (near_resistance or block_long):
            return 0, 'WAIT', (
                f"{macro_log} Bloqueio Long: preço próximo da resistência/RSI esticado "
                f"(RSI={rsi:.1f}, RSI_fast={rsi_fast:.1f})."
            )
        if trend == 'BAIXA' and (near_support or block_short):
            return 0, 'WAIT', (
                f"{macro_log} Bloqueio Short: preço próximo do suporte/RSI esticado "
                f"(RSI={rsi:.1f}, RSI_fast={rsi_fast:.1f})."
            )

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

        bullish_sweep = bool(tech_data.get('bullish_liquidity_sweep'))
        bearish_sweep = bool(tech_data.get('bearish_liquidity_sweep'))
        volume_climax = bool(tech_data.get('volume_climax'))
        if (bullish_sweep and trend == 'ALTA') or (bearish_sweep and trend == 'BAIXA'):
            score += 20
            reasons.append('[CÉREBRO 2] Volume Clímax + sweep de liquidez validado')
        elif volume_climax:
            reasons.append('[CÉREBRO 2] Volume Clímax detectado, aguardando confirmação de rejeição')

        bullish_ob = bool(tech_data.get('bullish_order_block'))
        bearish_ob = bool(tech_data.get('bearish_order_block'))
        bullish_fvg = bool(tech_data.get('bullish_fvg'))
        bearish_fvg = bool(tech_data.get('bearish_fvg'))
        if trend == 'ALTA' and bullish_ob:
            score += 15
            reasons.append('Preço em Bullish Order Block (zona de desconto)')
        if trend == 'BAIXA' and bearish_ob:
            score += 15
            reasons.append('Preço em Bearish Order Block (zona premium)')
        if trend == 'ALTA' and bullish_fvg:
            score += 10
            reasons.append('Reteste em FVG bullish confirmado')
        if trend == 'BAIXA' and bearish_fvg:
            score += 10
            reasons.append('Reteste em FVG bearish confirmado')

        if trend == 'ALTA' and 45 < rsi < 70:
            score += 10
            reasons.append(f'RSI saudável para continuidade ({rsi:.1f})')
        elif trend == 'BAIXA' and 30 < rsi < 55:
            score += 10
            reasons.append(f'RSI saudável para continuidade ({rsi:.1f})')
        elif rsi > 80 or rsi < 20:
            score -= 40
            reasons.append('RSI em exaustão extrema - risco de reversão')

        action = 'WAIT'
        if score >= 60:
            action = 'BUY' if trend == 'ALTA' else 'SELL'

        return min(100, score), action, ' | '.join(reasons)


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
            reasons.append('Ativo novo - operar com cautela')
            return score, ('BUY' if tech_data.get('trend') == 'ALTA' else 'SELL'), reasons[0]

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
        if score >= 60:
            action = 'BUY' if tech_data.get('trend') == 'ALTA' else 'SELL'

        return max(0, min(100, score)), action, ' | '.join(reasons)


class GroqValidator:
    """
    Mantém o nome para compatibilidade com o restante do sistema.
    A implementação é 100% local e não depende de Groq/Gemini.
    """

    def __init__(self, api_key_gemini=None, api_key_groq=None):
        self.analyst = DataAnalystAgent()
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
        if trend == 'ALTA' and bool(tech_data.get('block_long_trap')):
            score = 0
        if trend == 'BAIXA' and bool(tech_data.get('block_short_trap')):
            score = 0
        return min(100, score)

    def consensus_predict(self, tech_data, symbol, force_local_only=True):
        trend = tech_data.get('trend', 'NEUTRO')
        if trend == 'NEUTRO':
            return {
                'probabilidade': 0,
                'decisao': 'WAIT',
                'motivo': 'Tendência neutra - bloqueio de scanner',
            }

        score_local = self.local_signal(tech_data)
        score_analyst, action_analyst, motivo_analyst = self.analyst.get_signal(tech_data, symbol)
        score_learner, action_learner, motivo_learner = self.learner.get_signal(tech_data, symbol)

        probability = (score_local * 0.25) + (score_analyst * 0.40) + (score_learner * 0.35)

        final_action = 'WAIT'
        if action_analyst == action_learner and probability >= 60:
            final_action = action_analyst
        elif probability >= 75:
            final_action = action_analyst

        brain_logs = {
            'brain1': (
                f"[CÉREBRO 1] Tendência={trend} | "
                f"OB(Bull/Bear)={bool(tech_data.get('bullish_order_block'))}/{bool(tech_data.get('bearish_order_block'))}"
            ),
            'brain2': (
                f"[CÉREBRO 2] VolumeRatio={float(tech_data.get('volume_ratio', 0) or 0):.2f} | "
                f"Sweep(Bull/Bear)={bool(tech_data.get('bullish_liquidity_sweep'))}/{bool(tech_data.get('bearish_liquidity_sweep'))}"
            ),
        }

        return {
            'probabilidade': probability,
            'decisao': final_action,
            'motivo': f'Analista: {motivo_analyst} | Aprendizado: {motivo_learner}',
            'brains': {'local': 'online', 'analyst': 'online', 'learner': 'online'},
            'brain_logs': brain_logs,
        }
