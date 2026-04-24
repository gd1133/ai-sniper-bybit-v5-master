import os
import json
import requests
import time
from groq import Groq
from src.ai_brain.learning import TradeLearner

class GroqValidator:
    """
    🧠 CÉREBRO TRIPLO v60.1 - GIVALDO SUPREME
    Lógica: Consenso Ponderado (Gemini 40% | Groq 35% | Local 25%)
    Rigor: 60% Mínimo para autorizar o Ponto Zero.
    """
    def __init__(self, api_key_gemini, api_key_groq):
        self.gemini_key = api_key_gemini
        self.groq_client = Groq(api_key=api_key_groq)
        self.memory = TradeLearner()
        self.model = "gemini-2.5-flash"
        self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.gemini_key}"
        self.global_cooldown_until = 0
        self.groq_cooldown_until = 0

    def _limpar_json(self, texto):
        """Limpa marcações de markdown e espaços para evitar erros de parsing."""
        if not texto: return "{}"
        limpo = texto.replace("```json", "").replace("```", "").strip()
        return limpo

    def _normalize_side(self, side):
        """Normaliza qualquer lado para BUY/SELL/WAIT."""
        value = str(side or "").strip().upper()
        map_side = {
            "BUY": "BUY",
            "COMPRAR": "BUY",
            "LONG": "BUY",
            "SELL": "SELL",
            "VENDER": "SELL",
            "SHORT": "SELL",
            "WAIT": "WAIT",
            "SCANNER": "WAIT",
            "ABORTAR": "WAIT",
        }
        return map_side.get(value, "WAIT")

    def _resolve_cloud_side(self, tactical_action, tactical_score, strategic_action, strategic_score):
        """Resolve o lado final somente com os lados explícitos vindos das IAs cloud."""
        buy_weight = 0.0
        sell_weight = 0.0

        if tactical_action == "BUY":
            buy_weight += tactical_score * 0.35
        elif tactical_action == "SELL":
            sell_weight += tactical_score * 0.35

        if strategic_action == "BUY":
            buy_weight += strategic_score * 0.40
        elif strategic_action == "SELL":
            sell_weight += strategic_score * 0.40

        if buy_weight == 0 and sell_weight == 0:
            return "WAIT"

        if buy_weight == sell_weight:
            return "WAIT"

        return "BUY" if buy_weight > sell_weight else "SELL"

    def local_signal(self, tech_data):
        """
        🟢 CÉREBRO 1: MOTOR MATEMÁTICO (LOCAL)
        Baseado em SMA 200, Fibonacci 0.618 e Volume.
        """
        score = 0
        trend = tech_data.get('trend', '---')
        
        # SMA 200 (Tendência Macro)
        if trend in ["ALTA", "BAIXA"]: score += 25
        
        # Fibonacci 0.618 (Golden Zone)
        fib = tech_data.get('fib_618', 0)
        price = tech_data.get('price', 0)
        if fib > 0 and price > 0:
            distancia = abs(price - fib) / price
            if distancia < 0.015: score += 35
            
        # Volume Institucional
        if float(tech_data.get('volume_ratio', 0) or 0) >= 1.5: score += 15
        
        # RSI (Filtro de Exaustão)
        rsi = tech_data.get('rsi', 50)
        if 20 < rsi < 80: score += 10
        
        return min(100, score)

    def get_tactical_signal(self, tech_data, symbol):
        """
        🟡 CÉREBRO 2: RADAR TÁTICO (GROQ)
        Focado em risco e velocidade do candle.
        Com retry logic e rate limit handling.
        """
        if time.time() < self.groq_cooldown_until:
            return 45, "WAIT"

        max_retries = 2
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                prompt = (f"Analise {symbol}: {tech_data}. JSON: {{\"score\": 0-100, \"action\": \"BUY|SELL|WAIT\"}}")
                
                res = self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    response_format={"type": "json_object"},
                    timeout=5
                )
                data = json.loads(res.choices[0].message.content)
                action = self._normalize_side(data.get('action', 'WAIT'))
                return int(data.get('score', 45)), action
            except Exception as e:
                error_str = str(e)
                if '429' in error_str or 'rate' in error_str.lower():
                    if attempt == 0:
                        wait_time = retry_delay
                        print(f"⏸️ [GROQ RATE LIMIT] Aguardando {wait_time}s antes de retry...")
                        time.sleep(wait_time)
                        continue

                    self.groq_cooldown_until = time.time() + 90
                    print("⚠️ [GROQ] Rate limit. Cooldown 90s")
                    return 45, 'WAIT'
                else:
                    # Outro erro - usar fallback
                    print(f"⚠️ [GROQ] Fallback (tentativa {attempt+1}/{max_retries})")
                    return 45, 'WAIT'
        
        return 45, 'WAIT'  # Fallback final

    def get_strategic_signal(self, tech_data, symbol):
        """
        🔵 CÉREBRO 3: ESTRATEGISTA CLOUD (GEMINI)
        Analisa contexto histórico e Smart Money.
        Com rate limit detection e cooldown automático.
        """
        if time.time() < self.global_cooldown_until:
            return 50, "⏸️ Gemini em cooldown..."

        try:
            history = self.memory.get_context()
            prompt = (
                f"Trader: {symbol} | Trend: {tech_data.get('trend')} | Data: {tech_data} | History: {history} | "
                f"JSON: {{\"probabilidade\": 0-100, \"lado\": \"BUY|SELL|WAIT\", \"motivo\": \"string\"}}"
            )
            
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(self.gemini_url, json=payload, timeout=5)
            
            if res.status_code == 200:
                try:
                    raw = self._limpar_json(res.json()['candidates'][0]['content']['parts'][0]['text'])
                    data = json.loads(raw)
                    lado = self._normalize_side(data.get('lado', data.get('action', 'WAIT')))
                    return int(data.get('probabilidade', 50)), data.get('motivo', '✅ Processado'), lado
                except Exception as parse_err:
                    return 50, f"Resposta inválida: {str(parse_err)[:20]}", "WAIT"
            elif res.status_code == 429:
                print(f"⚠️ [GEMINI] Rate limit 429. Cooldown 120s")
                self.global_cooldown_until = time.time() + 120
                return 50, "Rate limit", "WAIT"
            else:
                print(f"⚠️ [GEMINI] Status {res.status_code}")
                return 50, f"Erro {res.status_code}", "WAIT"
        except requests.Timeout:
            print(f"⏱️ [GEMINI] Timeout 5s")
            return 50, "Timeout", "WAIT"
        except Exception as e:
            print(f"⚠️ [GEMINI] {type(e).__name__}: {str(e)[:30]}")
            return 50, "Erro", "WAIT"

    def consensus_predict(self, tech_data, symbol, force_local_only=False):
        """
        ⚖️ O GRANDE TRIBUNAL: UNIFICAÇÃO DOS 3 CÉREBROS
        Aplica os pesos e decide se autoriza o Ponto Zero.
        
        force_local_only: Se True, usa APENAS o 3º Cérebro (Local Brain)
        """
        # 1. Executa as 3 camadas (ou apenas local se rate limit)
        local_score = self.local_signal(tech_data)
        trend = tech_data.get('trend', '---')
        fib_distance_pct = float(tech_data.get('fib_distance_pct', 999) or 999)
        volume_ratio = float(tech_data.get('volume_ratio', 0) or 0)
        rsi = float(tech_data.get('rsi', 50) or 50)
        local_checks = {
            "macro_trend": trend in ["ALTA", "BAIXA"],
            "fib_zone": fib_distance_pct <= 1.5,
            "institutional_volume": volume_ratio >= 1.5,
            "rsi_safe": 20 < rsi < 80,
        }
        
        if force_local_only:
            # 🧠 MODO FALLBACK: Apenas 3º Cérebro (Local)
            print(f"🧠 [3º CÉREBRO ONLY] Usando análise LOCAL para {symbol}")
            tactical_score = local_score  # Espelha o local
            strategic_score = local_score  # Espelha o local
            tactical_action = 'WAIT'
            strategic_action = 'WAIT'
            strategic_motivo = "🧠 3º Cérebro (Matemática Pura) ativado"
        else:
            # ⚙️ MODO NORMAL: Tenta usar Groq + Gemini
            tactical_score, tactical_action = self.get_tactical_signal(tech_data, symbol)
            strategic_score, strategic_motivo, strategic_action = self.get_strategic_signal(tech_data, symbol)
            
            # Se ambos falharem (rate limit), ativa fallback automático
            if tactical_score <= 45 and strategic_score <= 50:
                print(f"🚨 [AUTO-FALLBACK] Ambos APIs retornaram fallback. Ativando 3º Cérebro...")
                tactical_score = local_score
                strategic_score = local_score
                tactical_action = 'WAIT'
                strategic_action = 'WAIT'
                strategic_motivo = "Fallback automático: Usando 3º Cérebro (Local)"

        tactical_action = self._normalize_side(tactical_action)
        strategic_action = self._normalize_side(strategic_action)
        cloud_side = self._resolve_cloud_side(tactical_action, tactical_score, strategic_action, strategic_score)

        # 🛑 REGRA SOBERANA GIVALDO: Sem macro tendência válida, aborta.
        if local_score < 25:
            return {
                "probabilidade": 0, "decisao": "SCANNER", 
                "motivo": "Abortado: Sem confluência macro na SMA 200.",
                "brain_used": "LOCAL"
            }

        # 2. Cálculo Ponderado
        # Se apenas local, dá peso total ao local
        if force_local_only:
            final_prob = local_score
            pesos = "Local 100%"
        else:
            # Gemini 40%, Groq 35%, Local 25%
            final_prob = int((strategic_score * 0.40) + (tactical_score * 0.35) + (local_score * 0.25))
            pesos = f"Gemini 40% ({strategic_score}) | Groq 35% ({tactical_score}) | Local 25% ({local_score})"

        # 3. Decisão de Sentido baseada no lado explícito das IAs cloud
        decisao = "SCANNER"
        motivo_soberano = ""
        
        # Só autoriza se bater 60%
        if final_prob >= 60:
            if cloud_side == "BUY":
                decisao = "COMPRAR"
            elif cloud_side == "SELL":
                decisao = "VENDER"

            # 🛑 TRAVA SOBERANA: lado da IA não pode contrariar a SMA200.
            if (cloud_side == "BUY" and trend == "BAIXA") or (cloud_side == "SELL" and trend == "ALTA"):
                decisao = "ABORTAR"
                motivo_soberano = f"Trava Soberana: IA={cloud_side} conflita com tendência {trend}."
            elif cloud_side == "WAIT":
                decisao = "ABORTAR"
                motivo_soberano = "Trava Soberana: IAs cloud sem consenso de direção explícita."

        # 4. Formata Motivo Educativo
        motivo_consensuado = (f"Confluência de {final_prob}% detectada. "
                              f"Gemini: {strategic_score} | Groq: {tactical_score} | Local: {local_score}. "
                              f"Lados Cloud => Gemini: {strategic_action} | Groq: {tactical_action}. "
                              f"Veredito: {strategic_motivo}")

        if motivo_soberano:
            motivo_consensuado = f"{motivo_consensuado} | {motivo_soberano}"

        # Logging para o Telegram (Educational Purpose)
        if final_prob >= 60 and decisao in ["COMPRAR", "VENDER"]:
            print(f"✅ [CONSENSUS ALERT] {final_prob}% - {decisao}")
        
        return {
            "probabilidade": final_prob,
            "decisao": decisao,
            "motivo": motivo_consensuado,
            "brains": {"local": "online", "groq": "online", "gemini": "online"},
            "breakdown": {"local": local_score, "groq": tactical_score, "gemini": strategic_score},
            "tactical_action": tactical_action,
            "strategic_action": strategic_action,
            "cloud_side": cloud_side,
            "strategic_reason": strategic_motivo,
            "weights": {"local": 25, "groq": 35, "gemini": 40},
            "local_checks": local_checks,
        }
