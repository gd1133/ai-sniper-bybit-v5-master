"""
🧠 LOCAL ML ENGINE v61.0 - 3º CÉREBRO EXECUTOR PRINCIPAL
Decisões autônomas com aprendizado adaptativo baseado em SQLite.
Ativa quando APIs Groq/Gemini falham com status 429 ou timeout.
"""

import json
from datetime import datetime
from src.ai_brain.learning import TradeLearner


class LocalMLEngine:
    """
    Máquina de aprendizado local que toma decisões de trading
    quando as APIs de nuvem (Groq/Gemini) falham.
    """
    
    def __init__(self, db_path="database.db"):
        self.memory = TradeLearner(db_path)
        self.min_local_confidence = 52  # assertivo — antes 80%
        
    def evaluate_entry_conditions(self, symbol, tech_data, intelligence_context=None):
        """
        Avalia se entrada é permitida baseado em aprendizado local + notícias + heat.
        """
        ctx = intelligence_context or {}

        # 0. Mercado lateral / sem direção — nunca entra
        if tech_data.get('is_lateral') or str(tech_data.get('trend', '')).upper() == 'NEUTRO':
            return False, "⛔ Mercado LATERAL / sem direção clara — Cérebro 3 aborta", 0

        # 1. Verificar bloqueio temporário por padrão de falha
        is_blocked, block_reason = self.memory.is_symbol_blocked(symbol)
        if is_blocked:
            return False, f"⛔ {block_reason}", 0
        
        # 2. Analisar padrões históricos
        should_block, failure_reason, consecutive_losses = self.memory.analyze_failure_patterns(symbol)
        if should_block:
            self.memory.block_symbol_temporarily(symbol, failure_reason, duration_seconds=1800)
            return False, f"⛔ Padrão detectado: {failure_reason}", 0

        # 2b. Notícias web vs direção técnica
        news_risk = str(ctx.get('news_risk') or tech_data.get('news_risk') or 'LOW').upper()
        global_trend = str(ctx.get('global_trend') or tech_data.get('global_trend') or 'NEUTRAL').upper()
        trend = str(tech_data.get('trend', '')).upper()
        if news_risk == 'HIGH' and (
            (trend == 'ALTA' and global_trend == 'BEARISH')
            or (trend == 'BAIXA' and global_trend == 'BULLISH')
        ):
            return False, f"⛔ Notícias web conflitam com a direção ({global_trend})", 0
        
        # 3. Avaliar força do sinal técnico local (+ heat + chart)
        confidence = self._calculate_local_confidence(tech_data, intelligence_context=ctx)
        
        if confidence < self.min_local_confidence:
            return False, f"📊 Confiança insuficiente: {confidence}% (mín: {self.min_local_confidence}%)", confidence
        
        return True, f"✅ Entrada autorizada (Confiança: {confidence}%)", confidence
    
    def _calculate_local_confidence(self, tech_data, intelligence_context=None):
        """
        Calcula confiança do 3º Cérebro: técnica + velas/heat + notícias.
        """
        ctx = intelligence_context or {}
        score = 0
        
        # SMA 200 (Tendência Macro) - 25 pontos
        trend = str(tech_data.get('trend', '---')).upper()
        if trend in ["ALTA", "BAIXA"]:
            score += 25
        
        # SuperTrend (Confirmação de tendência) - 20 pontos
        supertrend = tech_data.get('supertrend_signal', tech_data.get('supertrend', 1))
        if (trend == "ALTA" and supertrend == 1) or (trend == "BAIXA" and supertrend == -1):
            score += 20
        
        # Fibonacci 0.618 (Golden Zone) - 15 pontos
        fib_distance = float(tech_data.get('fib_distance_pct', 999) or 999)
        if 0 < fib_distance <= 1.5:
            score += 15
        
        # Volume Institucional - 10 pontos
        volume_ratio = float(tech_data.get('volume_ratio', 0) or 0)
        if volume_ratio >= 1.5:
            score += 10
        
        # RSI (Filtro de Exaustão) - 8 pontos
        rsi = float(tech_data.get('rsi', 50) or 50)
        if 20 < rsi < 80:
            score += 8

        # Heat / leitura avançada de velas - até 12 pontos
        heat = float(tech_data.get('heat_score', 0) or 0)
        if heat >= 75:
            score += 12
        elif heat >= 55:
            score += 8
        chart_score = float(tech_data.get('chart_entry_score', 0) or 0)
        if chart_score >= 40:
            score += 5

        # Notícias web / sentimento - até 10 pontos
        sentiment = float(ctx.get('sentiment_score', tech_data.get('sentiment_score', 50)) or 50)
        global_trend = str(ctx.get('global_trend', tech_data.get('global_trend', 'NEUTRAL'))).upper()
        if trend == 'ALTA' and global_trend == 'BULLISH':
            score += 10
        elif trend == 'BAIXA' and global_trend == 'BEARISH':
            score += 10
        elif sentiment >= 65 and trend in ('ALTA', 'BAIXA'):
            score += 5
        elif global_trend in ('BULLISH', 'BEARISH') and (
            (trend == 'ALTA' and global_trend == 'BEARISH')
            or (trend == 'BAIXA' and global_trend == 'BULLISH')
        ):
            score -= 15
        
        return min(100, max(0, score))
    
    def resolve_entry_direction(self, tech_data, intelligence_context=None):
        """
        Define direção (BUY/SELL/WAIT) baseada em indicadores + heat + notícias.
        """
        ctx = intelligence_context or {}
        trend = str(tech_data.get('trend', '---')).upper()
        supertrend = tech_data.get('supertrend_signal', tech_data.get('supertrend', 1))
        rsi = float(tech_data.get('rsi', 50) or 50)
        heat_bias = str(tech_data.get('heat_bias', 'NEUTRAL')).upper()
        global_trend = str(ctx.get('global_trend', tech_data.get('global_trend', 'NEUTRAL'))).upper()

        if tech_data.get('is_lateral') or trend == 'NEUTRO':
            return "WAIT", "⚪ Mercado lateral — sem direção"

        # Lógica: Seguir tendência macro com confirmação de SuperTrend
        if trend == "ALTA" and supertrend == 1:
            if heat_bias == 'BEAR':
                return "WAIT", "🟡 ALTA técnica mas heat de velas bearish"
            if global_trend == 'BEARISH':
                return "WAIT", "🟡 ALTA técnica mas notícias web bearish"
            if rsi < 70:
                return "BUY", (
                    f"🟢 ALTA confirmada (ST={supertrend}, RSI={rsi:.0f}, "
                    f"Heat={tech_data.get('heat_score', 0)}, News={global_trend})"
                )
            return "WAIT", f"🟡 ALTA mas RSI exaurido ({rsi:.0f})"
        
        if trend == "BAIXA" and supertrend == -1:
            if heat_bias == 'BULL':
                return "WAIT", "🟡 BAIXA técnica mas heat de velas bullish"
            if global_trend == 'BULLISH':
                return "WAIT", "🟡 BAIXA técnica mas notícias web bullish"
            if rsi > 30:
                return "SELL", (
                    f"🔴 BAIXA confirmada (ST={supertrend}, RSI={rsi:.0f}, "
                    f"Heat={tech_data.get('heat_score', 0)}, News={global_trend})"
                )
            return "WAIT", f"🟡 BAIXA mas RSI exaurido ({rsi:.0f})"
        
        return "WAIT", "⚪ Sem sinal claro nos indicadores"
    
    def record_local_decision(self, symbol, side, tech_data, entry_price, entry_qty, entry_margin):
        """
        Registra decisão local para aprendizado futuro.
        """
        indicators_dict = {
            'trend': tech_data.get('trend', '---'),
            'sma_200': float(tech_data.get('sma_200', 0) or 0),
            'supertrend': int(tech_data.get('supertrend', 1)),
            'rsi': float(tech_data.get('rsi', 50) or 50),
            'fib_618': float(tech_data.get('fib_618', 0) or 0),
            'volume_ratio': float(tech_data.get('volume_ratio', 0) or 0),
        }
        
        self.memory.record_local_entry(
            symbol=symbol,
            side=side,
            indicators_dict=indicators_dict,
            entry_price=entry_price,
            entry_qty=entry_qty,
            entry_margin=entry_margin
        )
        
        print(f"🧠 [3º CÉREBRO] Decisão registrada: {symbol} {side} @ {entry_price}")
    
    def close_local_trade(self, symbol, exit_price, pnl_pct):
        """Finaliza trade local com resultado para aprendizado."""
        self.memory.finalize_local_trade(
            symbol=symbol,
            exit_price=exit_price,
            pnl_pct=pnl_pct
        )
    
    def get_learning_context(self, symbol):
        """Retorna contexto de aprendizado para o símbolo."""
        trades = self.memory.get_last_50_trades(symbol)
        
        if not trades:
            return "Novo símbolo: sem histórico"
        
        recent = trades[:5]
        context = f"Últimos 5 trades de {symbol}: "
        
        for trade in recent:
            try:
                pnl = float(trade.get('pnl_pct', 0) or 0)
                result = "✅ LUCRO" if pnl > 0 else "❌ PERDA"
                indicators = json.loads(trade.get('entry_indicators', '{}'))
                sma = indicators.get('sma_200', 0)
                context += f"[{result} {pnl:.2f}% | SMA: {sma:.2f}] "
            except:
                continue
        
        return context
    
    def get_performance_stats(self, symbol=None):
        """Retorna estatísticas de performance do 3º Cérebro."""
        return self.memory.get_local_ml_stats(symbol)
    
    def get_blocked_symbols(self):
        """Retorna lista de símbolos atualmente bloqueados."""
        conn = self.memory._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT symbol, block_until, reason FROM symbol_blocks
                WHERE block_until > datetime('now')
            ''')
            return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            print(f"❌ Erro ao buscar símbolos bloqueados: {e}")
            return []
        finally:
            conn.close()
