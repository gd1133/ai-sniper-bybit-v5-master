import os
import json
import requests
import time
try:
    from groq import Groq
except Exception:
    Groq = None
from src.ai_brain.learning import TradeLearner

class GroqValidator:
    """
    🧠 CÉREBRO TRIPLO v60.1 - GIVALDO SUPREME
    Lógica: Consenso Ponderado (Gemini 40% | Groq 35% | Local 25%)
    Rigor: 60% Mínimo para autorizar o Ponto Zero.
    """
    # Modelos Gemini em ordem de preferência (fallback automático)
    GEMINI_MODELS = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    def __init__(self, api_key_gemini, api_key_groq):
        self.gemini_key = api_key_gemini or ""
        self.groq_client = None
        if not self.gemini_key:
            print("⚠️ [GEMINI] GEMINI_API_KEY não configurada – usando fallback local.")
        if Groq is not None and api_key_groq:
            try:
                self.groq_client = Groq(api_key=api_key_groq)
            except TypeError as e:
                # Erro comum de incompatibilidade entre groq/httpx (argumento proxies).
                print(f"⚠️ [GROQ INIT] Incompatibilidade de dependencias: {e}")
            except Exception as e:
                print(f"⚠️ [GROQ INIT] Falha ao inicializar cliente: {type(e).__name__}: {e}")
        else:
            print("⚠️ [GROQ INIT] SDK indisponivel ou chave ausente; usando fallback local.")
        self.memory = TradeLearner()
        self._gemini_model_index = 0   # índice atual no GEMINI_MODELS
        self.gemini_min_confidence = 60
        self.global_cooldown_until = 0
        self.groq_cooldown_until = 0
        # Throttle do log de AUTO-FALLBACK (evita spam nos logs)
        self._last_fallback_log = 0
        self._FALLBACK_LOG_INTERVAL = 60   # no mínimo 60s entre mensagens de fallback

    @property
    def model(self):
        return self.GEMINI_MODELS[self._gemini_model_index]

    @property
    def gemini_url(self):
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.gemini_key}"
        )

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

    def _resolve_local_fallback_side(self, tech_data):
        """
        Resolve o lado soberano do 3º cérebro quando as clouds falham.
        Usa a tendência macro como direção final por segurança.
        """
        trend = str(tech_data.get('trend', '---')).upper()
        if trend == "ALTA":
            return "BUY"
        if trend == "BAIXA":
            return "SELL"
        return "WAIT"

    def _normalize_gemini_score(self, score):
        """Gemini nunca trabalha abaixo do piso estratégico de 60%."""
        try:
            numeric = int(float(score))
        except Exception:
            numeric = self.gemini_min_confidence
        return max(self.gemini_min_confidence, min(100, numeric))

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
        Retorna (score, action, is_fallback).
        """
        if self.groq_client is None:
            return 45, "WAIT", True

        if time.time() < self.groq_cooldown_until:
            return 45, "WAIT", True

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
                return int(data.get('score', 45)), action, False
            except Exception as e:
                error_str = str(e)
                if '429' in error_str or 'rate' in error_str.lower():
                    if attempt == 0:
                        time.sleep(retry_delay)
                        continue
                    self.groq_cooldown_until = time.time() + 90
                    print("⚠️ [GROQ] Rate limit. Cooldown 90s")
                    return 45, 'WAIT', True
                else:
                    if attempt == 0:
                        continue
                    return 45, 'WAIT', True
        
        return 45, 'WAIT', True

    def get_strategic_signal(self, tech_data, symbol):
        """
        🔵 CÉREBRO 3: ESTRATEGISTA CLOUD (GEMINI)
        Analisa contexto histórico e Smart Money.
        Tenta os modelos em GEMINI_MODELS em cascata se o modelo atual não existe.
        """
        if not self.gemini_key:
            return self.gemini_min_confidence, "Sem chave Gemini", "WAIT", True

        if time.time() < self.global_cooldown_until:
            return self.gemini_min_confidence, "⏸️ Gemini em cooldown...", "WAIT", True

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
                    score = self._normalize_gemini_score(data.get('probabilidade', self.gemini_min_confidence))
                    return score, data.get('motivo', '✅ Processado'), lado, False
                except Exception as parse_err:
                    return self.gemini_min_confidence, f"Resposta inválida: {str(parse_err)[:20]}", "WAIT", True
            elif res.status_code == 429:
                print(f"⚠️ [GEMINI] Rate limit 429. Cooldown 120s")
                self.global_cooldown_until = time.time() + 120
                return self.gemini_min_confidence, "Rate limit", "WAIT", True
            elif res.status_code == 404:
                # Modelo não existe – tenta próximo na cadeia
                if self._gemini_model_index < len(self.GEMINI_MODELS) - 1:
                    self._gemini_model_index += 1
                    print(f"⚠️ [GEMINI] Modelo não encontrado. Tentando: {self.model}")
                    return self.get_strategic_signal(tech_data, symbol)
                print(f"⚠️ [GEMINI] Nenhum modelo disponível na cadeia.")
                return self.gemini_min_confidence, "Modelo indisponível", "WAIT", True
            else:
                return self.gemini_min_confidence, f"Erro {res.status_code}", "WAIT", True
        except requests.Timeout:
            return self.gemini_min_confidence, "Timeout", "WAIT", True
        except Exception as e:
            return self.gemini_min_confidence, "Erro", "WAIT", True

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
        
        fallback_local_active = False
        local_fallback_side = "WAIT"

        if force_local_only:
            # 🧠 MODO FALLBACK: Apenas 3º Cérebro (Local)
            print(f"🧠 [3º CÉREBRO ONLY] Usando análise LOCAL para {symbol}")
            tactical_score = local_score  # Espelha o local
            strategic_score = local_score  # Espelha o local
            tactical_action = 'WAIT'
            strategic_action = 'WAIT'
            strategic_motivo = "🧠 3º Cérebro (Matemática Pura) ativado"
            fallback_local_active = True
            local_fallback_side = self._resolve_local_fallback_side(tech_data)
        else:
            # ⚙️ MODO NORMAL: Tenta usar Groq + Gemini
            tactical_score, tactical_action, tactical_fallback = self.get_tactical_signal(tech_data, symbol)
            strategic_score, strategic_motivo, strategic_action, strategic_fallback = self.get_strategic_signal(tech_data, symbol)
            
            # Se ambos falharem, ativa fallback automático (log throttled)
            if tactical_fallback and strategic_fallback:
                now = time.time()
                if now - self._last_fallback_log >= self._FALLBACK_LOG_INTERVAL:
                    print(f"🚨 [AUTO-FALLBACK] APIs indisponíveis. 3º Cérebro ativado.")
                    self._last_fallback_log = now
                tactical_score = local_score
                strategic_score = local_score
                tactical_action = 'WAIT'
                strategic_action = 'WAIT'
                strategic_motivo = "Fallback automático: Usando 3º Cérebro (Local)"
                fallback_local_active = True
                local_fallback_side = self._resolve_local_fallback_side(tech_data)

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
        if fallback_local_active:
            final_prob = local_score
            pesos = "Local 100%"
        else:
            # Gemini 40%, Groq 35%, Local 25%
            final_prob = int((strategic_score * 0.40) + (tactical_score * 0.35) + (local_score * 0.25))
            pesos = f"Gemini 40% ({strategic_score}) | Groq 35% ({tactical_score}) | Local 25% ({local_score})"

        # 3. Decisão de Sentido baseada no lado explícito das IAs cloud
        decisao = "SCANNER"
        motivo_soberano = ""

        required_confidence = 80 if fallback_local_active else 60

        # Só autoriza se bater o mínimo exigido
        if final_prob >= required_confidence:
            decision_side = local_fallback_side if fallback_local_active else cloud_side

            if decision_side == "BUY":
                decisao = "COMPRAR"
            elif decision_side == "SELL":
                decisao = "VENDER"

            # 🛑 TRAVA SOBERANA: lado da decisão não pode contrariar a SMA200.
            if (decision_side == "BUY" and trend == "BAIXA") or (decision_side == "SELL" and trend == "ALTA"):
                decisao = "ABORTAR"
                motivo_soberano = f"Trava Soberana: lado={decision_side} conflita com tendência {trend}."
            elif decision_side == "WAIT":
                decisao = "ABORTAR"
                motivo_soberano = (
                    "Trava Soberana: 3º cérebro sem direção válida."
                    if fallback_local_active else
                    "Trava Soberana: IAs cloud sem consenso de direção explícita."
                )
        elif fallback_local_active:
            motivo_soberano = "Fallback local ativo, mas abaixo da confiança mínima de 80%."

        # 4. Formata Motivo Educativo
        motivo_consensuado = (f"Confluência de {final_prob}% detectada. "
                              f"Gemini: {strategic_score} | Groq: {tactical_score} | Local: {local_score}. "
                              f"Lados Cloud => Gemini: {strategic_action} | Groq: {tactical_action}. "
                              f"Veredito: {strategic_motivo}")

        if fallback_local_active:
            motivo_consensuado = (
                f"{motivo_consensuado} | Fallback soberano do 3º cérebro: "
                f"direção {local_fallback_side} com mínimo de 80%."
            )

        if motivo_soberano:
            motivo_consensuado = f"{motivo_consensuado} | {motivo_soberano}"

        # Logging para o Telegram (Educational Purpose)
        if final_prob >= required_confidence and decisao in ["COMPRAR", "VENDER"]:
            print(f"✅ [CONSENSUS ALERT] {final_prob}% - {decisao}")
        
        return {
            "probabilidade": final_prob,
            "decisao": decisao,
            "motivo": motivo_consensuado,
            "brains": {
                "local": "ONLY" if fallback_local_active else "online",
                "groq": "fallback" if fallback_local_active else "online",
                "gemini": "fallback" if fallback_local_active else "online"
            },
            "breakdown": {"local": local_score, "groq": tactical_score, "gemini": strategic_score},
            "tactical_action": tactical_action,
            "strategic_action": strategic_action,
            "cloud_side": cloud_side,
            "fallback_local_side": local_fallback_side,
            "fallback_local_active": fallback_local_active,
            "strategic_reason": strategic_motivo,
            "weights": {"local": 100, "groq": 0, "gemini": 0} if fallback_local_active else {"local": 25, "groq": 35, "gemini": 40},
            "required_confidence": required_confidence,
            "local_checks": local_checks,
        }
