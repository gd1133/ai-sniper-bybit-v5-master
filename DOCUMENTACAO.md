# Documentação Técnica: Motor Sniper V60.7 🚀

Sistema de trading automatizado de alta frequência integrado à **API Bybit V5**, operando
**100% em conta real (mainnet)**. Este documento descreve a arquitetura, todas as estratégias,
a lógica de decisão, o gerenciamento de risco e as proteções anti-falha do robô.

> **Regra de ouro:** a IA de notícias é apenas *assistente*. A palavra final é sempre do
> **Cérebro 3** (decisão soberana com indicadores locais). Nenhuma indisponibilidade de IA
> externa pode travar uma entrada.

---

## 1. Visão Geral da Arquitetura

```
                         ┌──────────────────────────────┐
   Bybit V5 (mainnet) ── │  RADAR (sniper_worker_loop)  │  varre top volume a cada ciclo
                         └───────────────┬──────────────┘
                                         │ para cada moeda
                    ┌────────────────────▼─────────────────────┐
                    │  PIPELINE DE DECISÃO (Triplo Cérebro)     │
                    │  1. Estrutura/SMC  2. Volume & Fluxo      │
                    │  3. Decisão Soberana (ML local)           │
                    └────────────────────┬─────────────────────┘
                                         │ sinal aprovado (prob ≥ THRESHOLD)
                    ┌────────────────────▼─────────────────────┐
                    │  RESERVA DE SLOT (anti-overtrading lock)  │
                    └────────────────────┬─────────────────────┘
                                         │
                    ┌────────────────────▼─────────────────────┐
                    │  EXECUÇÃO POR CLIENTE (background thread)  │
                    │  • margem ISOLADA 20x                      │
                    │  • checa posição aberta (has_open_position)│
                    │  • lote = 3% da banca × 20x / preço       │
                    │  • ordem a mercado + TP/SL inline         │
                    └───────────────────────────────────────────┘
```

Componentes principais (arquivos):

| Camada | Arquivo | Responsabilidade |
|---|---|---|
| Web / API / Radar | `main_web.py` | Servidor Flask, dashboard, loop do radar, orquestração de ordens por cliente |
| CLI / execução single | `main.py` | Execução direta (linha de comando) e helpers de posição |
| Broker | `src/broker/bybit_client.py` | Chamadas à Bybit V5 (CCXT + pybit): saldo, ordens, margem, TP/SL, posições |
| Cálculo de ordem | `src/broker/order_calculator.py` | Precisão/step size, arredondamento de lote |
| Risco | `src/risk/position_sizing.py` | Fórmula de lote (3%), preços de TP/SL, ROI |
| Risco | `src/risk/entry_viability.py` | Viabilidade da entrada (notional mínimo etc.) |
| Cérebro 1/2 | `src/engine/confluence_absoluta.py` | Confluência institucional (volume, order book, ADX) |
| Timing | `src/engine/entry_timing.py` | Confirmação de timing (tendência, pullback, momentum) |
| Institucional | `src/engine/rastreador_institucional.py` | Portas 1–4: ADX+BB+amplitude+volume μ+2.5σ+VWAP → COMPRA/VENDA_INSTITUCIONAL |
| Hard Gates | `src/engine/hard_gates.py` | Short-circuit absoluto: qualquer porta fechada = NEUTRO e aborta ANTES do Cérebro 3 |
| Indicadores | `src/engine/indicators.py` | Cálculo de indicadores técnicos |
| Cérebro 3 | `src/ai_brain/local_ml_engine.py` | Motor de ML local (decisão soberana / contingência) |
| Aprendizado | `src/ai_brain/adaptive_weights.py` | Pesos das 5 estratégias auto-ajustados por resultado real |
| Memória | `src/ai_brain/learning.py` | Histórico de trades, win-rate, bloqueio por padrão de perda |
| Validador | `src/ai_brain/validator.py` | Consolida votos e define ação final (BUY/SELL/HOLD) |
| Inteligência | `src/intelligence/market_intelligence.py` | Regime de mercado + whales + notícias (score) |
| Notícias | `src/intelligence/news_analyzer.py` | Sentimento de notícias (**assistente, nunca bloqueia**) |
| Banco de dados | `src/database/manager.py` | SQLite em `./data/database.db`: `check_same_thread=False` + `commit` obrigatório em INSERT/UPDATE |
| Config | `src/config/` | Credenciais, URLs, ambiente |

---

## 2. Fluxo de Execução do Radar (passo a passo)

O `sniper_worker_loop` (em `main_web.py`) executa continuamente:

1. **Coleta de mercado** — busca os `SCAN_TOP_COINS` ativos de maior volume em USDT
   (padrão **40** por ciclo).
2. **Pré-carga de módulos** — no boot, `_preload_runtime_modules()` importa broker/IA de
   forma síncrona (single-thread) **antes** de iniciar as threads, evitando *import parcial/circular*.
3. **Para cada moeda:**
   1. Baixa OHLCV (15m/1h) e calcula indicadores.
   2. **Cérebro 1 (SMC):** estrutura de mercado (BOS/CHoCH) e order blocks.
   3. **Cérebro 2 (Volume & Fluxo):** volume clímax e desequilíbrio do livro de ordens.
   4. **Inteligência de Mercado:** regime (tendência/lateral) + whales + notícias (assistente).
   5. **Timing de entrada:** `confirmar_timing_entrada` valida tendência/pullback/momentum.
   6. **Cérebro 3 (Validador + ML local):** consolida votos e emite a decisão soberana com
      uma probabilidade.
4. **Gatilho de entrada:** se `probabilidade ≥ THRESHOLD_ENTRADA` (padrão **48%**) e a decisão
   for `BUY/SELL`, o robô tenta **reservar o slot** do par.
5. **Reserva de slot (lock):** `_reserve_signal_slot(symbol)` marca o par como
   *processando_entrada*. Se já houver reserva ou o limite `MAX_MOEDAS_ATIVAS` for atingido,
   o sinal é descartado.
6. **Execução por cliente:** `_process_client_orders_background` roda em thread separada e
   envia a ordem para cada investidor ativo (ver seção 6). O slot só é liberado no `finally`,
   após a confirmação da corretora.

---

## 3. Arquitetura de Decisão: O Triplo Cérebro

O robô abre operação apenas com **confluência** de dados de alta probabilidade.

* **Cérebro 1 — Estrutura de Mercado (SMC):** analisa quebras de estrutura (*BOS/CHoCH*) e
  identifica *order blocks* institucionais em 15m e 1h.
* **Cérebro 2 — Volume & Fluxo:** monitora *Volume Clímax* (volume financeiro real) e o
  desequilíbrio dinâmico do livro de ordens. Implementado em `confluence_absoluta.py`.
* **Cérebro 3 — Decisão Soberana & Contingência:** consolida os dados e aprova a execução.
  Em caso de falha/limite de requisição das IAs auxiliares (Groq/Gemini), o Cérebro 3 assume
  **autonomamente** usando indicadores matemáticos puramente locais (`local_ml_engine.py`),
  garantindo que o robô **não trave**.

### 3.1 Estratégias com pesos auto-ajustados por aprendizado ⭐

O Cérebro 3 pontua a entrada com **5 estratégias clássicas**, e o **peso de cada uma é
ajustado automaticamente** conforme o histórico de acertos (arquivo
`src/ai_brain/adaptive_weights.py`, tabela SQLite `strategy_weights`):

| # | Estratégia | Sinal "ativo" (alinhado à direção) | Peso base |
|---|---|---|---|
| 1 | **SMA** (tendência macro) | preço acima/abaixo da SMA200 (trend ALTA/BAIXA) | 22 |
| 2 | **SuperTrend** (pivô) | SuperTrend alinhado à tendência (ALTA=+1 / BAIXA=−1) | 18 |
| 3 | **Fibonacci** (Golden Zone) | distância do 0.618 ≤ 1.5% | 13 |
| 4 | **Volume** (institucional) | `volume_ratio` ≥ 1.3 | 10 |
| 5 | **Suporte/Resistência** (pivôs) | perto de suporte/repique (ALTA) ou resistência/rejeição (BAIXA) | 12 |

**Como o aprendizado funciona:**

1. **Na entrada** (`_adaptive_log_entry` no radar): grava quais das 5 estratégias estavam
   ativas naquele sinal (tabela `strategy_signal_log`).
2. **No fechamento** (`_adaptive_record_outcome` no monitor TP/SL): credita **win** (PnL > 0) ou
   **loss** para cada estratégia que estava ativa na entrada e recalcula seu peso.
3. **Peso final** = `peso_base × multiplicador`, onde o multiplicador vem do *win-rate* suavizado
   (Laplace) da estratégia:
   * `peso = base × mult`, com `mult ∈ [0.60, 1.40]`.
   * `win-rate 50% → mult 1.0` · `100% → 1.4` · `0% → 0.6`.
   * Só ajusta após **≥ 10 amostras** (`MIN_SAMPLES`); antes disso usa o peso base
     (comportamento idêntico ao atual — sem choque no robô ao vivo).

Assim, estratégias que historicamente **mais acertam ganham mais peso** e as que erram perdem
peso — a IA "aprende" quais critérios priorizar por conta própria.

**Endpoint:** `GET /api/estrategias/pesos` retorna o relatório dos pesos aprendidos
(base, peso atual, wins, losses, win-rate, se já está aprendendo).

### 3.2 Rastreador Institucional + Hard Gates (Short-Circuit Absoluto) ⭐

Camada **obrigatória** em `rastreador_institucional.py` + `hard_gates.py`.
Se QUALQUER porta falhar → `NEUTRO` e o radar **aborta antes do Cérebro 3**.

| Porta | Regra | Falha |
|---|---|---|
| 1a | ADX(14) ≥ 23 | NEUTRO (ignora volume) |
| 1b | BB Width(20,2σ) > média das últimas 50 larguras | NEUTRO (squeeze) |
| 2 | Amplitude `((Hmax−Lmin)/Lmin)*100` ≥ 0.35% (20 candles) | NEUTRO (acumulação) |
| 3 | Volume > MA(20) + 2.5σ | NEUTRO (só após 1–2) |
| 4 | COMPRA: alta + close > VWAP + spread > 1.5× média; VENDA: espelho | NEUTRO |

Integração:
- Radar: short-circuit imediato após `get_signals()` se portas fechadas.
- Execução: se `structural_signal == NEUTRO`, `return` imediato (não envia ordem).
- Lado: BUY só com `COMPRA_INSTITUCIONAL`; SELL só com `VENDA_INSTITUCIONAL`.
- Cérebro 3: +15 pts quando alinhado; bônus de score +12 no radar.

### 3.3 Cérebro 3 Cauteloso — Anti-Armadilha (Padilha) ⭐

O timing de entrada (`entry_timing` + `cautious_entry_gate`) passou a ser **rigoroso**:

| Regra | Comportamento |
|---|---|
| Nunca comprar com vela vermelha | Bloqueio duro se `close < open` |
| Nunca vender com vela verde | Bloqueio duro se `close > open` |
| Nunca contra tendência | COMPRA só em ALTA+ST; VENDA só em BAIXA+ST |
| Venda no fundo | Exige vela **FORTE VERMELHA** + engolfo/FVG/momentum (não vende no fundo cego) |
| Compra no fundo | Só com vela **FORTE VERDE** (confirmação de mudança de momentum) |
| Armadilha de topo | RSI≥72 exige vela forte + engolfo/FVG |

Estratégias incrementais de confirmação (não substituem as 5 clássicas):
- **Engolfo** bullish/bearish
- **Fair Value Gap (FVG)** SMC
- **Vela forte** + rejeição/bounce de pivô
- **Momentum** de 2–3 velas na direção

Confiança mínima do Cérebro 3 local: **62%** (mais seletivo, mirando qualidade > quantidade).

### Limiares atuais (modo assertivo)

| Componente | Parâmetro | Valor atual | Observação |
|---|---|---|---|
| Gatilho de entrada | `THRESHOLD_ENTRADA` | **48%** | probabilidade mínima do validador |
| ML local | `min_local_confidence` | **52%** | confiança mínima do Cérebro 3 |
| Validador (compra) | `buy_votes ≥ 2` + prob | **≥ 48%** | votos mínimos + probabilidade |
| Validador (soberano) | prob soberana | **≥ 52%** | ação BUY/SELL autônoma |
| Confluência Absoluta | `ENABLE_ABSOLUTE_CONFLUENCE` | **False (off)** | não bloqueia por padrão |
| Volume clímax | ratio | **≥ 1.25** | antes 2.0 |
| Order book | `min_imbalance_ratio` | **≥ 1.20** | ignora se book indisponível |
| ADX (tendência) | `min_adx` | **≥ 14** | antes 22 |
| Inteligência | `intelligence_score` | **≥ 32** | peso de notícias removido |

> Estes limiares foram afrouxados a pedido para tornar o robô **mais assertivo / entradas mais
> rápidas**. Para deixá-lo mais rigoroso, aumente os valores (ex.: `THRESHOLD_ENTRADA=60`,
> `min_local_confidence=80`, `ENABLE_ABSOLUTE_CONFLUENCE=True`).

---

## 4. IA de Notícias — Assistente (nunca bloqueia)

`news_analyzer.py` e `market_intelligence.py` foram ajustados para que a IA de notícias **jamais**
bloqueie uma entrada:

* **Neutralidade no cooldown/degradação:** se a Groq entra em cooldown (`in_cooldown`) ou
  degradada (`cloud_degraded`), o analisador retorna sentimento **NEUTRAL** e
  `ai_status = "degradado"`, com `block_trade = False`.
* **Sem veto por *soft degradation*:** no lugar do bloqueio, registra o aviso:
  `⚠️ [ASSISTENTE IA] Notícias indisponíveis para [MOEDA]. Passando comando para análise técnica do Cérebro 3.`
* **Decisão soberana:** com notícia Neutra/Indisponível, o Cérebro 3 executa análise pura de
  mercado (regime, livro de ordens, volume). Se os critérios técnicos forem preenchidos, entra
  normalmente.
* **Desativada por padrão:** `ENABLE_NEWS_AI = False` (assertividade). O peso de notícias foi
  removido do `intelligence_score`.

---

## 5. Protocolo Rígido de Gerenciamento de Risco

### A. Modo de Margem — ISOLADA obrigatória
* **Proibição absoluta:** nunca operar em Margem Cruzada (*Cross Margin*).
* **Padrão exigido:** toda ordem é executada em **Margem Isolada** com **20x**. O robô força a
  configuração via `set_isolated_margin(symbol, 20)` antes da ordem:
  * CCXT `set_margin_mode('isolated', symbol, {'leverage': 20})`
  * Fallback `pybit switch_margin_mode(category='linear', tradeMode=1, buyLeverage='20', sellLeverage='20')`
  * Idempotente: se já estiver isolada/na alavancagem, ignora o erro (`110026`, "not modified").

### B. Lote Dinâmico — Fórmula dos 3%
A margem de cada trade equivale a **3%** do saldo real do investidor
(`DEFAULT_ENTRY_PCT = 0.03` em `position_sizing.py`):

$$\text{Margem Isolada} = \text{Saldo da Conta} \times 0.03$$
$$\text{Tamanho Nominal} = \text{Margem Isolada} \times 20 \text{ (Alavancagem)}$$
$$\text{Lote Final} = \frac{\text{Tamanho Nominal}}{\text{Preço Atual do Ativo}}$$

O lote é arredondado pelas regras de precisão (Step Size / minOrderQty) da corretora e respeita
um teto de tolerância de banca.

### C. Saída de Emergência — TP/SL vinculados à ordem principal
* **Take Profit:** **+100% de ROI** sobre a margem separada (`DEFAULT_TP_ROI_PCT = 100.0`).
* **Stop Loss:** **-50% de ROI** sobre a margem separada (`DEFAULT_SL_ROI_PCT = -50.0`).
  Com 20x, o SL dispara quando o preço se move **2.5%** contra a entrada.
* **Vínculo à ordem:** TP e SL são enviados **dentro dos parâmetros da ordem de mercado**
  (`takeProfit` / `stopLoss` / `tpslMode='Full'`), não em requisições separadas.
  `set_trading_stop` só é usada como **fallback** se o TP/SL inline for rejeitado.

**Fórmula dos preços de TP/SL** (`calculate_tp_sl_prices`):
```
Δ_preço_TP = preço × (TP_ROI / 100) / alavancagem      # +100%/20 = +5.0% no preço
Δ_preço_SL = preço × (|SL_ROI| / 100) / alavancagem    # 50%/20  = -2.5% no preço
BUY : tp = preço × (1 + 0.05) ; sl = preço × (1 - 0.025)
SELL: tp = preço × (1 - 0.05) ; sl = preço × (1 + 0.025)
```

---

## 6. Segurança Contra Sobrecarga e Duplicação (Anti-Overtrading)

* **Trava de ativo único:** apenas **uma posição aberta por par**. Antes de comprar, o robô
  chama `has_open_position(symbol)` (via `get_positions`/`fetch_positions`) e **aborta** se já
  houver qualquer quantidade aberta no par.
* **Mutex de concorrência:** ao aprovar um sinal, o par é reservado em
  `SNIPER_SIGNAL_RESERVATIONS` e **só é liberado após a confirmação da API**, dentro do
  `finally` de `_process_client_orders_background`. Isso evita ordens fantasmas duplicadas por
  latência de rede.
* **Checagem combinada:** `_can_open_new_signal` considera **posições no banco** + **reservas em
  processamento** + limite global `MAX_MOEDAS_ATIVAS`.
* **`_reserve_signal_slot`** retorna booleano (`True` = reservado / `False` = ocupado) para que a
  verificação seja confiável.

---

## 7. Conta Real (100%)

O sistema opera **exclusivamente em conta real (mainnet)**. Não há paper trading, testnet, demo
ou saldo fictício:

* `USE_TESTNET = False`, `account_mode = 'real'`, `balance_source = 'broker_real_balance'`.
* `manager.py`: `is_test_mode_enabled()` sempre `False`; `enable_test_mode()` é *no-op*; a
  migração força todos os clientes existentes para `is_testnet = 0` / `real` (a coluna é
  preservada, mas neutralizada).
* Dashboard e `/api/status` exibem/consolidam **apenas** saldos e posições reais lidos das APIs.

---

## 8. Parâmetros de Configuração

Valores atuais em `main_web.py` (raiz):

| Parâmetro | Valor | Descrição |
|---|---|---|
| `ALAVANCAGEM` | 20 | Alavancagem de execução (margem isolada) |
| `USE_TESTNET` | False | Sistema 100% real |
| `RISK_MODE` | `aggressive` | `conservative` (1 moeda) ou `aggressive` (5 moedas) |
| `MAX_MOEDAS_ATIVAS` | 5 | Máx. de posições simultâneas |
| `SCAN_TOP_COINS` | 40 | Ativos por ciclo de radar |
| `THRESHOLD_ENTRADA` | 48.0 | Probabilidade mínima para entrar |
| `SNIPER_POSICAO_UNICA` | False | Permite multi-ativo |

Risco (`src/risk/position_sizing.py`):

| Parâmetro | Valor | Descrição |
|---|---|---|
| `DEFAULT_ENTRY_PCT` | 0.03 | 3% da banca por trade |
| `DEFAULT_ENTRY_AFTER_STOP_PCT` | 0.03 | 3% após stop loss |
| `DEFAULT_TP_ROI_PCT` | 100.0 | +100% ROI |
| `DEFAULT_SL_ROI_PCT` | -50.0 | -50% ROI (2.5% de preço a 20x) |

Variáveis de ambiente úteis: `RISK_PER_TRADE_PCT`, `ENABLE_NEWS_AI`, `ENABLE_ABSOLUTE_CONFLUENCE`,
`BLOCK_LATERAL_MARKETS`, `LATERAL_AMPLITUDE_PERIODS` (20), `LATERAL_AMPLITUDE_PCT` (0.35),
`SQLITE_DB_PATH` (`./data/database.db` — evitar `/tmp` no Render), `USE_TESTNET`,
credenciais Bybit por cliente (no banco).

**Anti-acumulação:** se `((High.max - Low.min) / Low.min) * 100` nos últimos X períodos
estiver abaixo de `LATERAL_AMPLITUDE_PCT`, o robô força `NEUTRO` e ignora o sinal.
Sinal institucional só dispara com volume > média + 2.5σ **e** fechamento vs VWAP diária
**e** spread expressivo da vela.
---

## 9. Endpoints da API (Flask)

| Método | Rota | Função |
|---|---|---|
| GET | `/api/status` | Consolida saldos reais + posições reais + últimos trades |
| GET | `/api/estrategias/pesos` | Pesos aprendidos das 5 estratégias (SMA, SuperTrend, Fibonacci, Volume, S/R) |
| GET | `/api/investidores` | Lista investidores conectados (real) |
| POST | `/api/vincular_cliente` | Valida chaves Bybit e cadastra investidor (conta real) |
| GET | `/api/dashboard/balance` | Atualiza/retorna saldo real do dashboard |
| POST | `/api/config/risk-mode` | Alterna `conservative` / `aggressive` |
| POST | `/api/trade/manual-entry` | Entrada manual (usa o mesmo pipeline de execução) |
| PUT | `/api/cliente/<id>/balance-source` | (compat) força `broker_real_balance` |

Notas de validação (`/api/vincular_cliente`):
* Retorna **400** quando a validação das chaves falha (`valid=False`) — o corpo traz a mensagem
  de erro em `msg`/`api_error`.
* Retorna **200** quando as chaves autenticam e o saldo real é lido.

---

## 10. Correções Recentes e Troubleshooting

### 10.1 Erro de API no `/api/vincular_cliente` (import circular) — CORRIGIDO
* **Sintoma:** `cannot import name 'BybitClient' from partially initialized module
  'src.broker.bybit_client' (most likely due to a circular import)`; `POST /api/vincular_cliente`
  retornava **400**.
* **Causa raiz:** no *cold start* do gunicorn, `start_runtime_services()` iniciava a thread do
  radar (que importa `bybit_client`) no mesmo instante em que a primeira requisição chamava
  `_ensure_broker_class()` — as duas corriam para o **primeiro import** do módulo, gerando o
  "módulo parcialmente inicializado".
* **Correção:** `_preload_runtime_modules()` importa `bybit_client`, `indicators`, `validator`,
  `market_intelligence` e `entry_timing` de forma **síncrona (single-thread)** dentro de
  `start_runtime_services()`, **antes** de iniciar as threads e de servir requisições. Assim o
  módulo já está totalmente carregado em `sys.modules`, e o import lazy vira apenas cache hit.

### 10.2 Erro de escopo `gt` no radar — CORRIGIDO
* **Sintoma:** `cannot access local variable 'gt' where it is not associated with a value` em
  todas as moedas do radar.
* **Correção:** `gt` é inicializada no início do escopo:
  `gt = str(ctx.get('global_trend', '') or 'NEUTRAL').upper()`, eliminando o caminho condicional
  que deixava a variável sem valor quando as notícias estavam desativadas (tendência NEUTRAL).

### 10.3 Overtrading / ordens duplicadas — CORRIGIDO
* Ver seção 6. `_reserve_signal_slot` passou a retornar booleano; `_can_open_new_signal` consulta
  reservas + banco + limite global; a liberação do slot foi movida para o `finally` do worker de
  execução; e `has_open_position` aborta compras se já houver posição na corretora.

### 10.4 Encoding no Windows
* Ao rodar scripts localmente: `set PYTHONIOENCODING=utf-8` (evita `UnicodeEncodeError` com
  emojis nos logs).

---

## 11. Resumo da Lógica de Entrada (checklist)

Uma entrada só é enviada quando **todas** as condições abaixo são satisfeitas:

1. ✅ Radar seleciona a moeda (top volume).
2. ✅ **Hard Gates (Portas 1–4)** liberadas — ADX≥23, BB expandindo, amplitude≥0.35%, volume μ+2.5σ, lado vs VWAP.
3. ✅ `sinal_institucional` ≠ NEUTRO e Cérebro 3 emite `BUY`/`SELL` **no mesmo lado** do Smart Money (≥48%).
4. ✅ Timing / anti-armadilha confirmado.
5. ✅ (Se ligada) Confluência Absoluta — filtros técnicos complementares.
6. ✅ Slot reservado + `MAX_MOEDAS_ATIVAS` + sem posição aberta no par.
7. ✅ Margem isolada 20x; lote = 3% × 20x / preço; TP +100% ROI / SL −50% ROI inline (`str()` na Bybit V5).
8. ✅ Execução: se sinal estrutural = NEUTRO → `return` imediato (bloqueio absoluto).
