"""
🧠 LOCAL ML ENGINE v61.0 - 3º CÉREBRO EXECUTOR PRINCIPAL
Decisões autônomas com aprendizado adaptativo baseado em SQLite.
Ativa quando APIs Groq/Gemini falham com status 429 ou timeout.
"""

import json
from datetime import datetime
from src.ai_brain.learning import TradeLearner
from src.ai_brain.adaptive_weights import AdaptiveStrategyWeights


class LocalMLEngine:
    """
    Máquina de aprendizado local que toma decisões de trading
    quando as APIs de nuvem (Groq/Gemini) falham.
    """
    
    def __init__(self, db_path=None):
        # Usa o mesmo banco do app quando db_path não é informado (consistência do aprendizado)
        if db_path is None:
            try:
                from src.database.manager import DB_PATH
                db_path = DB_PATH or "database.db"
            except Exception:
                db_path = "database.db"
        self.memory = TradeLearner(db_path)
        # 🧠 Pesos das 5 estratégias ajustados automaticamente por aprendizado
        self.weights = AdaptiveStrategyWeights(db_path)
        # Cauteloso: exige mais confluência para mirar win-rate alto (antes 52 assertivo)
        self.min_local_confidence = 62
        
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
    
    def _strategy_signals(self, tech_data):
        """
        Determina QUAIS das 5 estratégias estão ativas/alinhadas à direção do trade.
        Retorna dict {estrategia: bool} usado tanto na pontuação quanto no aprendizado.

        Estratégias: sma, supertrend, fibonacci, volume, support_resistance.
        """
        trend = str(tech_data.get('trend', '---')).upper()
        supertrend = tech_data.get('supertrend_signal', tech_data.get('supertrend', 0))
        fib_distance = float(tech_data.get('fib_distance_pct', 999) or 999)
        volume_ratio = float(tech_data.get('volume_ratio', 0) or 0)
        structure_bias = str(tech_data.get('structure_bias', 'NEUTRO')).upper()
        chart_score = float(tech_data.get('chart_entry_score', 0) or 0)

        # 1. SMA 200 — tendência macro definida (acima/abaixo da média)
        sma_ok = trend in ("ALTA", "BAIXA")

        # 2. SuperTrend (pivô) alinhado com a tendência
        st_ok = (trend == "ALTA" and supertrend == 1) or (trend == "BAIXA" and supertrend == -1)

        # 3. Fibonacci — dentro da Golden Zone (0.618)
        fib_ok = 0 < fib_distance <= 1.5

        # 4. Volume institucional
        vol_ok = volume_ratio >= 1.3

        # 5. Suporte/Resistência (pivôs de estrutura) alinhados à direção
        if trend == "ALTA":
            sr_ok = bool(
                tech_data.get('near_pivot_support')
                or tech_data.get('bounce_from_pivot_low')
                or structure_bias in ('ALTA', 'BULLISH', 'COMPRA')
            )
        elif trend == "BAIXA":
            sr_ok = bool(
                tech_data.get('near_pivot_resistance')
                or tech_data.get('rejection_from_pivot_high')
                or structure_bias in ('BAIXA', 'BEARISH', 'VENDA')
            )
        else:
            sr_ok = False
        if not sr_ok and chart_score >= 40:
            sr_ok = True

        return {
            'sma': bool(sma_ok),
            'supertrend': bool(st_ok),
            'fibonacci': bool(fib_ok),
            'volume': bool(vol_ok),
            'support_resistance': bool(sr_ok),
        }

    def _calculate_local_confidence(self, tech_data, intelligence_context=None):
        """
        Calcula confiança do 3º Cérebro com PESOS ADAPTATIVOS das 5 estratégias
        (SMA, SuperTrend, Fibonacci, Volume, Suporte/Resistência) + velas/heat + notícias.

        Os pesos das estratégias são ajustados automaticamente pelo aprendizado
        (AdaptiveStrategyWeights). Quanto mais uma estratégia acerta, mais peso ela ganha.
        """
        ctx = intelligence_context or {}
        trend = str(tech_data.get('trend', '---')).upper()
        score = 0.0

        # ── 5 ESTRATÉGIAS com pesos aprendidos ──
        signals = self._strategy_signals(tech_data)
        try:
            weights = self.weights.get_weights()
        except Exception:
            from src.ai_brain.adaptive_weights import BASE_WEIGHTS
            weights = dict(BASE_WEIGHTS)
        for name, active in signals.items():
            if active:
                score += float(weights.get(name, 0) or 0)

        # Rastreador Institucional (VWAP + big player + spread) — bônus incremental
        inst_sig = str(tech_data.get('sinal_institucional', 'NEUTRO') or 'NEUTRO').upper()
        if trend == 'ALTA' and inst_sig == 'COMPRA_INSTITUCIONAL':
            score += 15
        elif trend == 'BAIXA' and inst_sig == 'VENDA_INSTITUCIONAL':
            score += 15
        elif inst_sig in ('COMPRA_INSTITUCIONAL', 'VENDA_INSTITUCIONAL'):
            score += 6  # pegada detectada, direção parcialmente alinhada

        # Fair Value Gap alinhado — bônus SMC
        if trend == 'ALTA' and tech_data.get('fvg_bullish'):
            score += 8
        elif trend == 'BAIXA' and tech_data.get('fvg_bearish'):
            score += 8

        # Vela forte na direção — bônus de momento certo
        if trend == 'ALTA' and tech_data.get('strong_bullish_candle'):
            score += 10
        elif trend == 'BAIXA' and tech_data.get('strong_bearish_candle'):
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

        # Notícias web / sentimento - até 10 pontos (assistente, nunca bloqueia)
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

        tech_score = min(100, max(0, int(round(score))))

        # Blend incremental 70/20/10 (técnica + Groq fluxo + Gemini macro)
        try:
            from src.ai_brain.cerebro3_soberano import (
                get_cerebro3_soberano,
                market_condition_from_signals,
            )
            blend = get_cerebro3_soberano().calcular_probabilidade_sucesso(
                sinais_5_estrategias=signals,
                condicao_mercado=market_condition_from_signals(tech_data, ctx),
                dados_groq=ctx.get('groq_flow') or ctx.get('order_flow') or {},
                dados_gemini=ctx.get('gemini_macro') or {},
                tech_confidence_0_100=tech_score,
            )
            if blend.get('veto'):
                return 0
            return int(round(float(blend.get('probabilidade', tech_score))))
        except Exception:
            return tech_score
    
    def resolve_entry_direction(self, tech_data, intelligence_context=None):
        """
        Define direção (BUY/SELL/WAIT) — Cérebro 3 CAUTELOSO.
        Nunca BUY em vela vermelha / SELL em vela verde; nunca contra tendência.
        """
        ctx = intelligence_context or {}
        trend = str(tech_data.get('trend', '---')).upper()
        supertrend = tech_data.get('supertrend_signal', tech_data.get('supertrend', 1))
        rsi = float(tech_data.get('rsi', 50) or 50)
        heat_bias = str(tech_data.get('heat_bias', 'NEUTRAL')).upper()
        global_trend = str(ctx.get('global_trend', tech_data.get('global_trend', 'NEUTRAL'))).upper()
        strong_up = bool(tech_data.get('strong_bullish_candle'))
        strong_down = bool(tech_data.get('strong_bearish_candle'))
        # Cor da vela via candle_body + recent_return / heat (sem DF aqui)
        candle_bias = str(tech_data.get('heat_bias', 'NEUTRAL')).upper()
        body_ratio = float(tech_data.get('candle_body_ratio', 0) or 0)
        recent_ret = float(tech_data.get('recent_return_pct', 0) or 0)
        # Inferir cor aproximada: retorno recente + heat
        is_red_candle = recent_ret < 0 and candle_bias in ('BEAR', 'BEARISH')
        is_green_candle = recent_ret > 0 and candle_bias in ('BULL', 'BULLISH')
        if body_ratio >= 40:
            if recent_ret < -0.05:
                is_red_candle = True
                is_green_candle = False
            elif recent_ret > 0.05:
                is_green_candle = True
                is_red_candle = False

        if tech_data.get('is_lateral') or trend == 'NEUTRO':
            return "WAIT", "⚪ Mercado lateral — sem direção"

        # Lógica cautelosa: tendência + SuperTrend + COR da vela + força
        if trend == "ALTA" and supertrend == 1:
            if heat_bias == 'BEAR' or is_red_candle:
                return "WAIT", "🟡 NUNCA comprar com vela VERMELHA / heat bearish — aguarde verde forte"
            if global_trend == 'BEARISH':
                return "WAIT", "🟡 ALTA técnica mas notícias web bearish"
            if rsi >= 72 and not strong_up:
                return "WAIT", f"🟡 Armadilha de TOPO (RSI={rsi:.0f}) — aguarde vela FORTE verde"
            if rsi < 70 and (strong_up or is_green_candle or body_ratio < 40):
                return "BUY", (
                    f"🟢 ALTA cautelosa (ST={supertrend}, RSI={rsi:.0f}, "
                    f"VelaForte={strong_up}, Heat={tech_data.get('heat_score', 0)})"
                )
            if rsi < 70:
                return "WAIT", "🟡 ALTA mas sem vela VERDE de confirmação"
            return "WAIT", f"🟡 ALTA mas RSI exaurido ({rsi:.0f})"

        if trend == "BAIXA" and supertrend == -1:
            if heat_bias == 'BULL' or is_green_candle:
                return "WAIT", "🟡 NUNCA vender com vela VERDE / heat bullish — aguarde vermelha forte"
            if global_trend == 'BULLISH':
                return "WAIT", "🟡 BAIXA técnica mas notícias web bullish"
            # Armadilha de FUNDO: não vender no fundo sem vela FORTE vermelha
            if rsi <= 28 and not strong_down:
                return "WAIT", (
                    f"🟡 Armadilha de FUNDO (RSI={rsi:.0f}) — "
                    f"NÃO vender no fundo. Aguarde vela FORTE VERMELHA"
                )
            if rsi > 30 and strong_down:
                return "SELL", (
                    f"🔴 BAIXA cautelosa com vela FORTE VERMELHA "
                    f"(ST={supertrend}, RSI={rsi:.0f}, Heat={tech_data.get('heat_score', 0)})"
                )
            if rsi > 30 and is_red_candle:
                return "SELL", (
                    f"🔴 BAIXA + vela vermelha "
                    f"(ST={supertrend}, RSI={rsi:.0f})"
                )
            if rsi > 30:
                return "WAIT", "🟡 BAIXA mas sem vela VERMELHA FORTE — aguardando momento"
            return "WAIT", f"🟡 BAIXA mas RSI exaurido ({rsi:.0f})"

        return "WAIT", "⚪ Sem sinal claro nos indicadores"
    
    def record_local_decision(self, symbol, side, tech_data, entry_price, entry_qty, entry_margin):
        """
        Registra decisão local para aprendizado futuro.
        """
        strategy_signals = self._strategy_signals(tech_data)
        indicators_dict = {
            'trend': tech_data.get('trend', '---'),
            'sma_200': float(tech_data.get('sma_200', 0) or 0),
            'supertrend': int(tech_data.get('supertrend', 1)),
            'rsi': float(tech_data.get('rsi', 50) or 50),
            'fib_618': float(tech_data.get('fib_618', 0) or 0),
            'volume_ratio': float(tech_data.get('volume_ratio', 0) or 0),
            'strategy_signals': strategy_signals,
        }

        self.memory.record_local_entry(
            symbol=symbol,
            side=side,
            indicators_dict=indicators_dict,
            entry_price=entry_price,
            entry_qty=entry_qty,
            entry_margin=entry_margin
        )

        # Registra as estratégias ativas para o aprendizado de pesos no fechamento
        try:
            self.weights.log_entry(symbol, strategy_signals)
        except Exception as e:
            print(f"⚠️ [PESOS IA] log_entry falhou: {e}", flush=True)

        print(f"🧠 [3º CÉREBRO] Decisão registrada: {symbol} {side} @ {entry_price}")
    
    def close_local_trade(self, symbol, exit_price, pnl_pct):
        """Finaliza trade local e ajusta os pesos das estratégias pelo resultado."""
        self.memory.finalize_local_trade(
            symbol=symbol,
            exit_price=exit_price,
            pnl_pct=pnl_pct
        )
        try:
            self.weights.record_outcome(symbol, pnl_pct)
        except Exception as e:
            print(f"⚠️ [PESOS IA] record_outcome falhou: {e}", flush=True)

    def get_strategy_weights_report(self):
        """Relatório dos pesos aprendidos das 5 estratégias (para dashboard/API)."""
        try:
            return self.weights.get_report()
        except Exception as e:
            print(f"⚠️ [PESOS IA] get_report falhou: {e}", flush=True)
            return []
    
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
