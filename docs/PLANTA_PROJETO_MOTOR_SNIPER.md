# Planta do projeto — Motor Sniper (Bybit V5)

Documento mestre para análise: o que o robô é, o que já foi construído, como opera hoje e o que falta melhorar.

**Versão operacional:** Motor Sniper V60.7+ (código em evolução contínua)  
**Exchange:** Bybit USDT Perpetual (linear), API V5, **conta real (mainnet)**  
**Ponto de entrada produção:** `wsgi.py` → `main_web.py` (Gunicorn, 1 worker)  
**Deploy:** Render (`render.yaml` + `Procfile`)  
**Data desta planta:** agosto 2026

---

## 1. Escopo do produto

O sistema é um **robô de futuros** que:

1. Varre as moedas de maior volume na Bybit (não só BTC).
2. Só entra com **confluência** (estrutura + volume institucional + lado vs VWAP + Cérebro 3).
3. **Evita mercado lateral** (ADX baixo, amplitude de acumulação, score de chop).
4. Abre ordem a mercado **por investidor** cadastrado (multi-cliente, 5% da banca, 20x isolada).
5. Coloca **Stop Loss −50% ROI** e **Take Profit +100% ROI** na posição (linhas no gráfico da Bybit).
6. Se o preço virar contra com **vela 5m forte + volume**, sai; se o trade for a favor, **sobe o SL (defesa)** sem apagar o TP.

Fora de escopo (não é o produto atual):

- Paper trading / testnet como modo principal (há flags, mas a operação-alvo é real).
- Grid, DCA, martingale.
- Gestão de portfólio spot.
- App mobile nativo.

---

## 2. Tecnologias (stack)

| Camada | Tecnologia | Onde |
|--------|------------|------|
| Backend web | Python 3, Flask, Flask-CORS, Gunicorn | `main_web.py`, `wsgi.py` |
| Frontend dashboard | React 18, Vite, Tailwind, Lucide, Recharts | `main.jsx` → build estático |
| Broker | **pybit 5.x** (Bybit V5 oficial) + **CCXT** fallback | `src/broker/bybit_client.py` |
| Dados OHLCV | CCXT `fetch_ohlcv` (15m radar, 1m/5m gestão) | radar + Trend Manager |
| Indicadores | pandas | `src/engine/indicators.py` |
| Banco | SQLite `./data/database.db` | `src/database/manager.py` |
| IA fluxo | Groq (order book / score_fluxo) | `src/intelligence/order_flow_analyzer.py` |
| IA macro | Gemini (notícias / sentimento) — **assistente, não bloqueia** | `src/intelligence/gemini_macro_analyzer.py` |
| Cérebro 3 | Motor local (regras + ML leve) | `src/ai_brain/local_ml_engine.py` |
| Aprendizado | Pesos evolutivos + Feedback Loop P&L Bybit | `adaptive_weights.py`, `src/learning/feedback_loop.py` |
| Hospedagem | Render (web service, 1 worker / 4 threads) | `Procfile`, `render.yaml` |

Dependências principais: `ccxt`, `pybit`, `pandas`, `flask`, `gunicorn`, `groq`, `python-dotenv`.

---

## 3. Arquitetura — do boot ao fechamento

```
wsgi.py
  └─ start_runtime_services()
        ├─ preload módulos (evita import circular)
        ├─ sniper_worker_loop          ← RADAR de entradas (15m)
        ├─ TrendPositionManager (~8s)  ← gestão viva / defesa / reversão
        ├─ monitor financeiro (~5s)    ← ROI 100/50, Profit Shield
        └─ sync dashboard / saldos Bybit

Flask
  ├─ GET  /api/status
  ├─ GET  /api/investidores
  ├─ POST /api/vincular_cliente
  ├─ DELETE /api/cliente/<id>
  └─ dashboard React (build Vite)
```

### 3.1 Pipeline de ENTRADA (uma moeda do radar)

Ordem obrigatória (fail-closed: qualquer corte aborta):

1. Top volume (`SCAN_TOP_COINS` = 40 no modo agressivo).
2. OHLCV 15m (≥ 200 velas).
3. Skip se **lateral** ou `trend == NEUTRO` (log `[LATERAL]`).
4. **Hard Gates Portas 1–5** (`hard_gates.py`) — se fechar, NEUTRO **antes** do Cérebro 3.
5. Score local mínimo.
6. Inteligência de mercado (ADX/regime/whales) — veto duro se lateral/ADX.
7. Cérebro 3 + validador: `prob ≥ THRESHOLD_ENTRADA` (42% agressivo / 50% conservador).
8. Lado = Smart Money (`COMPRA_INSTITUCIONAL` ↔ BUY, `VENDA_INSTITUCIONAL` ↔ SELL).
9. Analista Pessoal (pode abortar entrada fraca).
10. Filtro assimétrico (LONG menos rígido; SHORT em derretimento).
11. Timing + SuperTrend + anti-chase (não comprar no topo esticado).
12. Reserva de slot + 1 posição por par + `MAX_MOEDAS_ATIVAS` (5 agressivo).
13. Ordem market → `set_trading_stop` com **takeProfit + stopLoss** (strings, tickSize).

### 3.2 Pipeline de SAÍDA (posição aberta)

| Camada | O que faz |
|--------|-----------|
| Bybit TP | +100% ROI (~+5% preço @20x) — **realiza no gráfico** |
| Bybit SL | −50% ROI (~−2.5% preço @20x) — stop duro |
| Profit Shield | Em +100% ROI move SL para piso ~+80% (**defesa**), **não apaga o TP** |
| Trend Manager | Recuo pequeno = HOLD. Sai só com **vela 5m fechada forte + volume ≥ 2.2×** contra |
| Monitor financeiro | Se TP não estiver na corretora, fecha a mercado no alvo 100% |

---

## 4. Estratégias e regras (o que o robô “pensa”)

### 4.1 Portas institucionais (Cérebro 2 — short-circuit)

| Porta | Regra vigente | Papel |
|-------|----------------|-------|
| 1 ADX | ADX(14) ≥ **19** (`STRUCTURE_ADX_MIN`) | Exige tendência mínima |
| 1 BB | Expansão de Bandas **opcional** | Squeeze não é trava dura |
| 2 Amplitude | Range 20 velas ≥ **0.28%** | Anti-acumulação / lateral |
| 3 Volume | `vol > MA(20) + σ` adaptativo | Pegada de big player |
| 4 VWAP | Close do lado certo + spread ≥ **1.2×** média | Direção institucional |
| 5 Anatomia | Cor da vela + zona de close + anti-faca | Não comprar faca caindo |

**Porta 3 adaptativa (σ):**

- ADX médio das top 10 &lt; 25 → **1.0σ** (chop, mais sensível)
- ADX médio ≥ 25 → **1.25σ** (tendência)

### 4.2 Cinco estratégias com peso aprendido (Cérebro 3)

| # | Nome | Sinal | Peso base |
|---|------|-------|-----------|
| 1 | SMA 200 | Preço vs média longa | 22 |
| 2 | SuperTrend | Alinhado à tendência | 18 |
| 3 | Fibonacci 0.618 | Distância ≤ 1.5% | 13 |
| 4 | Volume | `volume_ratio` ≥ 1.3 | 10 |
| 5 | Pivô S/R | Bounce/rejeição | 12 |

Após ≥ 10 amostras, o peso sobe ou desce conforme win-rate real (Feedback Loop).

### 4.3 Filtros extras de entrada

- **Anti-chase:** não entra RSI esticado / preço longe da EMA/VWAP (extensão máx. 2.0%, pullback 0.9%).
- **Anti-lateral:** `BLOCK_LATERAL_MARKETS=true`.
- **Maturidade do par:** velas diárias mínimas (14 dias no modo moderado).
- **Cooldown 24h** após STOP LOSS no mesmo símbolo.
- **Notícias:** Groq/Gemini **não travam** entrada (`ALLOW_NEWS_HARD_VETO=false`).

### 4.4 Gestão de tendência (saída)

Construído para **não realizar cedo**:

- Não fecha em vela fraca, engolfo de 1m, BE em +12%, nem trail de 0.5% a partir de +25%.
- Fecha discricionário só com **reversão 5m forte + volume**.
- Alvo de lucro: **+100% ROI** na Bybit.
- Defesa: SL sobe para ~+80% ROI quando o trade está ganhando, se o preço virar contra.

---

## 5. Risco e tamanho de ordem

```
margem     = saldo_USDT × 5%     (3% se o último trade foi STOP)
quantidade = (margem × 20) / preço
```

- Alavancagem: **20x isolada** (`ALAVANCAGEM`).
- Se 5% for menor que o mínimo da Bybit → **aborta** (não aumenta o lote).
- Máximo simultâneo: **5** pares (agressivo) ou **1** (conservador).
- Uma posição por símbolo.

@20x, em linguagem de preço:

| ROI margem | Movimento de preço |
|------------|--------------------|
| +100% TP | +5.0% |
| +80% piso | +4.0% |
| −50% SL | −2.5% |

---

## 6. Multi-cliente e dashboard

- Tabela SQLite `clientes_sniper` (não `clientes`).
- Cada cliente: API key/secret Bybit, saldo vivo, posições.
- Vincular: salva primeiro, valida Bybit com timeout (não trava o POST).
- Excluir: `DELETE /api/cliente/<id>` + commit SQLite; frontend envia DELETE de verdade (lixeira).
- Dashboard React consome `/api/status` (saldos reais, posições, tribunal, Porta 3, pesos IA).

---

## 7. Linha do tempo — o que colocamos e acrescentamos

Ordem cronológica recente (o que mudou a planta operacional). Números de PR no GitHub `gd1133/ai-sniper-bybit-v5-master`.

| PR / branch | O que entrou | Por quê |
|-------------|--------------|---------|
| #193–194 | Maturidade 30D/14D + cooldown 24h pós-SL + anatomia da vela | Não operar par morto; não reentrar no mesmo stop |
| #195 | Feedback Loop P&L Bybit + pesos evolutivos | O robô aprende com win/loss real |
| #196 | SHORT em derretimento + LONG mais seletivo | Assimetría de mercado |
| #198 | Trend Position Manager (BE/trail/early) | Gestão viva (depois afrouxada — saía cedo) |
| #199 | Anti-chase | Não perseguir topo/fundo |
| #202–204 | Vincular cliente sem hang + saldo JSON | Dashboard e cadastro estáveis no Render |
| #205–208 | DELETE investidor + Porta 3 σ adaptativo | Lixeira falhava; volume 1.8σ matava chop |
| #206–207 | Analista Pessoal + tribunal SQLite + sentinela | Transparência + saída de reversão |
| #209 | Modo **moderado** de entrada (ADX 19, σ 1.0/1.25) | 2 dias sem ordem — funil rígido demais |
| #210 | Seguir tendência; sair só vela forte+volume | Saídas de scalp comiam o lucro |
| `feat/bybit-tp-visible` | **TP visível** na Bybit (`takeProfit` string + tickSize + logs) | SL ia, TP não aparecia no gráfico |

Camadas de produto que já existiam na base V60.x:

- Triplo Cérebro, radar top volume, 5% banca, TP/SL 100/50, dashboard React, SQLite, Groq/Gemini assistentes, confluência institucional/VWAP.

---

## 8. Estado atual — parâmetros que importam

| Parâmetro | Valor atual | Efeito |
|-----------|-------------|--------|
| `THRESHOLD_ENTRADA` | 42 / 50 | Barra do Cérebro 3 |
| `STRUCTURE_ADX_MIN` | 19 | Tendência mínima |
| `PORTA3_VOL_SIGMA` / `_CHOP` | 1.25 / 1.0 | Volume institucional |
| `ATTACH_EXCHANGE_TP` | **true** | Linha de TP no gráfico |
| `TREND_TRAIL_ROI_PCT` | 100 | Defesa/trail só no alvo |
| `PROFIT_SHIELD_TRIGGER/LOCK` | 100 / 80 | Piso de lucro |
| `TREND_EXIT_VOL_RATIO` | 2.2 | Volume da vela de saída |
| `BLOCK_LATERAL_MARKETS` | true | Sem range morto |
| `ALAVANCAGEM` | 20 | Conversão ROI ↔ preço |
| `RISK_PER_TRADE_PCT` | 5 | Tamanho da ordem |

**Atenção Render:** variáveis do painel **sobrescrevem** o código. Se `ATTACH_EXCHANGE_TP=false` estiver no Environment, o TP some de novo.

---

## 9. Arquivos-chave (mapa mental)

```
main_web.py                         orquestrador (radar, APIs, monitor, execução)
src/broker/bybit_client.py          ordens V5, TP/SL, posições
src/broker/tpsl_format.py           tickSize + validação LONG/SHORT
src/engine/hard_gates.py            Portas 1–5
src/engine/rastreador_institucional.py  VWAP / volume / spread
src/engine/porta3_adaptive.py       σ de volume pelo ADX médio
src/engine/anti_chase_gate.py       anti-topo
src/risk/trend_position_manager.py  HOLD vs reversão 5m
src/risk/profit_shield.py           defesa de lucro
src/risk/position_sizing.py         5% / TP-SL preços
src/ai_brain/local_ml_engine.py     Cérebro 3
src/ai_brain/personal_analyst.py    refinador entrada/saída
src/learning/feedback_loop.py       P&L → pesos
src/database/manager.py             SQLite clientes/trades
main.jsx                            dashboard
```

---

## 10. O que precisa melhorar (prioridade)

### P0 — operação / dinheiro

1. **Confirmar no Render** `ATTACH_EXCHANGE_TP=true` e validar 1 ordem com TP+SL no gráfico.
2. **Um único modo de posição (hedge vs one-way):** o código tenta `positionIdx` 1/2 e retry 0; contas one-way ainda podem falhar TP em silêncio — logar `positionIdx` real da conta.
3. **Auditoria de P&L:** confrontar `unrealisedPnl` Bybit × ROI calculado × trades SQLite (há aliases de saldo, mas o fechamento ainda pode dessincronizar).

### P1 — qualidade das entradas

4. **Métricas de bloqueio:** contar por ciclo quantas moedas morreram em LATERAL / Porta 3 / anti-chase / threshold (hoje parte do skip é silenciosa demais).
5. **Timeframe:** radar em 15m + saída em 5m é coerente; avaliar 5m também na Porta 3 para não entrar “atrasado” no impulso.
6. **BB expandindo:** está opcional (mais entradas). Se voltar muito lateral, religar `STRUCTURE_REQUIRE_BB_EXPAND=true` só em chop.

### P1 — qualidade das saídas

7. **Não competir TP da Bybit com software:** se o TP está no gráfico, o monitor não deve “inventar” outro critério de +100%. Já melhorado; falta teste em conta real.
8. **Partial TP:** hoje é Full close. Escada 50% no TP + resto trailing seria o próximo nível institucional.
9. **ATR real no trail** em vez de 2–3% fixo de preço (alts vs BTC).

### P2 — robustez / produto

10. **SQLite no Render** some se o disco não for persistente — backup ou Postgres.
11. **Documentação duplicada** (`DOCUMENTACAO.md`, `docs/LOGICA_*`, vários `CORRECAO_*.md`) — esta planta deve ser a fonte da verdade.
12. **Testes de integração Bybit** (sandbox) para `set_trading_stop` — unitários não pegam rejeição de tick/idx.
13. **Observabilidade:** um único log estruturado `[ENTRADA]` / `[SAIDA]` / `[TP/SL]` com symbol, ROI, retCode.

### P2 — IA

14. Groq 429: já há cooldown; garantir que **nunca** derruba Cérebro 1/2 (já é a regra).
15. Tribunal/analista: úteis no dashboard; não devem fechar trade em pullback (já desarmado).

---

## 11. Como analisar um ciclo (checklist)

Entrada boa:

- [ ] Log `[HARD-GATE] … portas 1–5 liberadas`
- [ ] Não é `[LATERAL]`
- [ ] Porta 3 com σ atual (`[PORTA3]`)
- [ ] `set_trading_stop` com `takeProfit=...` e `retCode=0`
- [ ] Gráfico Bybit: duas linhas (TP e SL)

Saída boa:

- [ ] TP Bybit no +100% **ou** `SAIDA_REVERSAO_TENDENCIA` com vela 5m forte + vol
- [ ] SL subiu (defesa) se estava em lucro e virou contra
- [ ] Não saiu em recuo de 0.5–1% no meio do caminho

---

## 12. Documentos relacionados

| Arquivo | Uso |
|---------|-----|
| **Este arquivo** `docs/PLANTA_PROJETO_MOTOR_SNIPER.md` | Planta mestre (ler primeiro) |
| `DOCUMENTACAO.md` | Detalhe técnico histórico (algumas tabelas podem estar defasadas) |
| `docs/LOGICA_ROBO_COMPLETA.md` | Sizing 5% e monitores |
| `.env.example` | Lista viva de env |
| `README.md` | Quick start e flags real vs testnet |

---

## 13. Resumo em uma frase

O Motor Sniper é um **sniper institucional em 15m** na Bybit real: entra só com volume/tendência (não lateral), arrisca 5% da banca a 20x, mira **+100% na margem** com TP visível, defende o lucro subindo o SL, e só abandona a tendência se uma **vela forte com volume** virar contra.
