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
        self.min_local_confidence = 80  # 80% confiança necessária para 3º Cérebro
        
    def evaluate_entry_conditions(self, symbol, tech_data):
        """
        Avalia se entrada é permitida baseado em aprendizado local.
        
        Args:
            symbol: Par de trading (ex: ETHUSDT)
            tech_data: Dicionário com indicadores técnicos
        
        Returns:
            (should_enter: bool, reason: str, confidence: int)
        """
        # 1. Verificar bloqueio temporário por padrão de falha
        is_blocked, block_reason = self.memory.is_symbol_blocked(symbol)
        if is_blocked:
            return False, f"⛔ {block_reason}", 0
        
        # 2. Analisar padrões históricos
        should_block, failure_reason, consecutive_losses = self.memory.analyze_failure_patterns(symbol)
        if should_block:
            self.memory.block_symbol_temporarily(symbol, failure_reason, duration_seconds=1800)
            return False, f"⛔ Padrão detectado: {failure_reason}", 0
        
        # 3. Avaliar força do sinal técnico local
        confidence = self._calculate_local_confidence(tech_data)
        
        if confidence < self.min_local_confidence:
            return False, f"📊 Confiança insuficiente: {confidence}% (mín: {self.min_local_confidence}%)", confidence
        
        return True, f"✅ Entrada autorizada (Confiança: {confidence}%)", confidence
    
    def _calculate_local_confidence(self, tech_data):
        """
        Calcula confiança do 3º Cérebro baseado em indicadores técnicos locais.
        Usa SMA, Supertrend, RSI, Fib, Volume como fatores.
        """
        score = 0
        
        # SMA 200 (Tendência Macro) - 30 pontos
        trend = str(tech_data.get('trend', '---')).upper()
        if trend in ["ALTA", "BAIXA"]:
            score += 30
        
        # SuperTrend (Confirmação de tendência) - 25 pontos
        supertrend = tech_data.get('supertrend', 1)
        if (trend == "ALTA" and supertrend == 1) or (trend == "BAIXA" and supertrend == -1):
            score += 25
        
        # Fibonacci 0.618 (Golden Zone) - 20 pontos
        fib_distance = float(tech_data.get('fib_distance_pct', 999) or 999)
        if 0 < fib_distance <= 1.5:
            score += 20
        
        # Volume Institucional - 15 pontos
        volume_ratio = float(tech_data.get('volume_ratio', 0) or 0)
        if volume_ratio >= 1.5:
            score += 15
        
        # RSI (Filtro de Exaustão) - 10 pontos
        rsi = float(tech_data.get('rsi', 50) or 50)
        if 20 < rsi < 80:
            score += 10
        
        return min(100, score)
    
    def resolve_entry_direction(self, tech_data):
        """
        Define direção (BUY/SELL/WAIT) baseada em indicadores técnicos.
        
        Returns:
            (direction: str, reason: str)
        """
        trend = str(tech_data.get('trend', '---')).upper()
        supertrend = tech_data.get('supertrend', 1)
        rsi = float(tech_data.get('rsi', 50) or 50)
        
        # Lógica: Seguir tendência macro com confirmação de SuperTrend
        if trend == "ALTA" and supertrend == 1:
            if rsi < 70:  # Não exaurido em alta
                return "BUY", f"🟢 Sinal ALTA confirmado (Trend: {trend}, SuperTrend: {supertrend}, RSI: {rsi:.0f})"
            else:
                return "WAIT", f"🟡 ALTA mas RSI exaurido ({rsi:.0f})"
        
        if trend == "BAIXA" and supertrend == -1:
            if rsi > 30:  # Não exaurido em baixa
                return "SELL", f"🔴 Sinal BAIXA confirmado (Trend: {trend}, SuperTrend: {supertrend}, RSI: {rsi:.0f})"
            else:
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
