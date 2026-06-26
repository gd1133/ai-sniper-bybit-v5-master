# 🧠 3º CÉREBRO EXECUTOR PRINCIPAL v61.0

## Visão Geral da Refatoração Arquitetural

Este documento descreve a promoção do 3º Cérebro (Análise Matemática Local) de **SIMULADOR** para **EXECUTOR PRINCIPAL DE OPERAÇÕES REAIS** no sistema de trading autônomo Sniper Bybit V5.

---

## 🚀 O Que Mudou

### ANTES (v60.x)
- 3º Cérebro: Análise puramente auxiliar (25% do consenso)
- Dependência total de APIs LLM (Groq + Gemini)
- Sem fallback quando ambas APIs falhavam

### DEPOIS (v61.0)
- 3º Cérebro: **EXECUTOR PRINCIPAL AUTÔNOMO**
- Executa ordens reais quando APIs falham com HTTP 429 (Rate Limit)
- Aprendizado local adaptativo com SQLite
- Anti-rate-limit com espaçamento de 15s entre ciclos
- Bloqueio automático de símbolos com padrão de falha

---

## 🎯 Ativação do 3º Cérebro EXECUTOR

### Condições de Ativação

O 3º Cérebro assume controle real quando:

1. **Groq API retorna 429** (Rate Limit)
2. **Gemini API retorna 429** (Rate Limit)
3. **AMBAS as condições acima são verdadeiras**

```
Groq 429 + Gemini 429 → 🧠 3º CÉREBRO EXECUTOR PRINCIPAL ATIVADO
```

### Fluxo de Ativação

```
┌─────────────────────────────────┐
│  Ciclo de Varredura Normal      │
│  (Gemini 40% + Groq 35% + Local 25%) │
└────────────┬────────────────────┘
             │
             ↓
    ┌─────────────────┐
    │ Groq API 429?   │ ← HTTP 429 Rate Limit
    └────────┬────────┘
             │
             ↓
    ┌─────────────────┐
    │ Gemini API 429? │ ← HTTP 429 Rate Limit
    └────────┬────────┘
             │
        ┌────┴────┐
        │ AMBAS?  │
        └────┬────┘
             │
        ┌────┴─────────────────────────────────┐
        │                                      │
       SIM                                    NÃO
        │                                      │
        ↓                                      ↓
    🧠 ATIVA                          Retry em próximo ciclo
    3º CÉREBRO                        com 60s cooldown
    EXECUTOR!
        │
        ↓
    Cooldown 60s ativado
    (Groq + Gemini em cooldown)
        │
        ↓
    3º CÉREBRO opera
    AUTONOMAMENTE
```

### Confiança Necessária

- **Modo Normal**: 60% confiança mínima
- **Modo 3º Cérebro**: **80% confiança mínima** (mais rigoroso para segurança)

---

## 🧠 Como Funciona o 3º Cérebro Executor

### 1. Análise Técnica Local

O 3º Cérebro calcula confiança usando:

**Indicadores Técnicos:**
- **SMA 200** - Tendência macro (30 pontos)
- **SuperTrend** - Confirmação de tendência (25 pontos)
- **Fibonacci 0.618** - Golden Zone (20 pontos)
- **Volume Institucional** - Ratio > 1.5x (15 pontos)
- **RSI** - Filtro de exaustão 20-80 (10 pontos)

**Total**: Até 100 pontos

**Exemplo de Cálculo:**
```
SMA ALTA (30) + SuperTrend Confirmado (25) + Fib Zone (20) + Volume OK (15) + RSI Safe (10)
= 100% Confiança → EXECUTA
```

### 2. Resolução de Direção (BUY/SELL)

```
IF Trend = ALTA AND SuperTrend = 1 AND RSI < 70:
    Direção = BUY
    Motivo = "Sinal ALTA confirmado"

ELSE IF Trend = BAIXA AND SuperTrend = -1 AND RSI > 30:
    Direção = SELL
    Motivo = "Sinal BAIXA confirmado"

ELSE:
    Direção = WAIT
    Motivo = "Sem sinal claro nos indicadores"
```

### 3. Validação de Entrada

Antes de executar, o 3º Cérebro verifica:

✅ **Macro Tendência Válida** (SMA 200 confirmada)
✅ **Confiança >= 80%** (threshold elevado)
✅ **Símbolo não está bloqueado** (por padrão de perda)
✅ **Notional mínimo respeitado** ($2.50 Bybit / $5.50 Binance)
✅ **Precisão decimal CCXT** (amount_to_precision)

### 4. Tamanho Dinâmico da Ordem

```python
# Cálculo do tamanho da ordem
balance = account_balance
risk_pct = RISK_PER_TRADE_PCT  # Default 15%
entry_price = current_price
margin = balance * risk_pct
qty = margin / entry_price

# Validação de mínimo nocional
if qty * entry_price < MIN_NOTIONAL:
    qty = MIN_NOTIONAL / entry_price

# Precisão CCXT (floor para decimal válido)
qty = exchange.amount_to_precision(symbol, qty)

# Executa ordem real
order = create_market_order(symbol, qty, side)
```

---

## 📚 Aprendizado Adaptativo Local (SQLite)

### Banco de Dados do 3º Cérebro

O sistema mantém duas tabelas principais:

#### 1. `local_ml_trades` - Histórico de Operações

```sql
CREATE TABLE local_ml_trades (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    symbol TEXT,
    side TEXT (BUY/SELL),
    entry_price REAL,
    entry_indicators JSON,
    sma_200_price REAL,
    supertrend_value REAL,
    rsi_value REAL,
    entry_margin REAL,
    entry_qty REAL,
    exit_price REAL,
    exit_time DATETIME,
    pnl_pct REAL,
    status TEXT (OPEN/CLOSED),
    brain_mode TEXT (LOCAL)
)
```

**O que é registrado:**
- Par, lado, preço de entrada
- Todos os indicadores técnicos no momento
- Tamanho da ordem + margem utilizada
- Resultado final (PnL %)

#### 2. `symbol_blocks` - Bloqueios Temporários

```sql
CREATE TABLE symbol_blocks (
    symbol TEXT PRIMARY KEY,
    block_until DATETIME,
    reason TEXT,
    consecutive_losses INTEGER,
    last_updated DATETIME
)
```

### Detecção de Padrões de Falha

O 3º Cérebro analisa as últimas **50 operações** de cada símbolo:

```
Lógica de Bloqueio:

FOR each trade in LAST_50_TRADES:
    IF pnl < 0:  # Perda
        IF same_sma_200_condition:
            consecutive_losses += 1
        ELSE:
            consecutive_losses = 1
    ELSE:  # Lucro
        consecutive_losses = 0
    
    IF consecutive_losses >= 3:
        BLOCK(symbol, reason="3+ perdas", duration=1800s)
        SKIP nova entrada neste símbolo
```

### Exemplo Prático

```
ETHUSDT histórico (últimas operações):

[1] BUY @ SMA 200 = $1900 → PERDA -2% ❌
[2] BUY @ SMA 200 = $1901 → PERDA -1.5% ❌
[3] BUY @ SMA 200 = $1899 → PERDA -3% ❌

3ª perda consecutiva sob MESMA condição de SMA!

RESULTADO: ETHUSDT bloqueado por 30 minutos
Próxima entrada só após desbloqueio automático
```

---

## ⏸️ Gerenciamento de Rate Limit e Timing

### Anti-Rate-Limit Spacing

A cada ciclo de varredura, o sistema aguarda:

**Entre ciclos normais**: SCAN_INTERVAL (30s padrão)
**Adicionalmente**: +15s de espaçamento anti-rate-limit

**Total**: 45s entre ciclos

```
Ciclo 1 → SCAN_INTERVAL (30s) → ANTI_RATE_LIMIT (15s) = 45s
Ciclo 2 → SCAN_INTERVAL (30s) → ANTI_RATE_LIMIT (15s) = 45s
...
```

### Cooldown em Erro 429

Quando 429 é detectado:

```python
# Primeira vez (Retry após 1s)
if attempt == 0:
    sleep(1)
    retry()

# Segunda vez (Ativa cooldown)
elif attempt == 1:
    cooldown_until = now + 60  # 60 segundos
    print("🔴 [429 DETECTADO] Cooldown 60s ativado")
    print("🧠 3º CÉREBRO assume operação autônoma")
    force_local_only = True
```

---

## 📊 Monitoramento via Dashboard Streamlit

### Acesso em Tempo Real

```bash
streamlit run dashboard.py
```

**Exibe em tempo real:**
- ✅ Status do 3º Cérebro (ATIVO REAL)
- 📈 Total de trades e win rate
- 💰 PnL acumulado
- ⛔ Símbolos bloqueados e motivos
- 🤖 Histórico de decisões
- 📊 Performance por símbolo

### Tema Premium Dark

- Fundo preto (#0a0a0a)
- Textos brancos/cinza claro
- Bordas refinadas de 1px
- Status badges coloridas
- **Sem termos de "Inteligência Artificial"**

---

## 🔒 Segurança e Verificações

### Antes de Cada Execução

```
1. ✅ Macro tendência válida?
2. ✅ Confiança >= 80%?
3. ✅ Símbolo não bloqueado?
4. ✅ Notional mínimo OK?
5. ✅ Precisão CCXT OK?
6. ✅ Único trade ativo? (max 1)
7. ✅ Autenticação válida?
```

### Trava Soberana

A ordem é ABORTADA se:

```python
# Conflito com tendência macro
if (direction == "BUY" and trend == "BAIXA") or \
   (direction == "SELL" and trend == "ALTA"):
    ABORT("Trava Soberana: Lado conflita com SMA 200")

# Sem direção clara
if direction == "WAIT":
    ABORT("Trava Soberana: Sem direção no 3º Cérebro")
```

---

## 📋 Checklist de Implementação

✅ SQLite schema expandido (2 novas tabelas)
✅ LocalMLEngine criado com toda lógica
✅ Validator.py atualizado com 429 detection
✅ Main.py integrado com LocalMLEngine
✅ Anti-rate-limit timing implementado
✅ Streamlit dashboard com dark theme
✅ Documentação completa (este arquivo)
✅ Requirements.txt atualizado

---

## 🚀 Como Colocar em Produção

### 1. Variáveis de Ambiente

```bash
# .env
ALLOW_REAL_TRADING=true
USE_TESTNET=false
RISK_PER_TRADE_PCT=15
SCAN_INTERVAL=30
```

### 2. Iniciar o Bot

```bash
python main.py ETHUSDT
```

### 3. Monitorar via Dashboard

```bash
streamlit run dashboard.py
```

### 4. Railway Deploy

```yaml
# railway.json
{
  "build": {
    "builder": "nixpacks"
  },
  "deploy": {
    "startCommand": "python main.py ETHUSDT",
    "restartPolicyMaxRetries": 5
  }
}
```

---

## 📊 Métricas de Performance

O 3º Cérebro rastreia:

- **Total Trades**: Número total de operações
- **Win Rate**: % de trades vencedores
- **PnL %**: Ganho/Perda acumulado
- **Consecutive Losses**: Perdas seguidas (trigger de bloqueio)
- **Symbols Blocked**: Quantos pares estão bloqueados

---

## 🔄 Ciclo de Vida de uma Operação

```
1. MERCADO
   ↓ Busca OHLCV 30m
   ↓ Calcula indicadores
   
2. DECISÃO
   ↓ Tenta Groq (se não em cooldown)
   ↓ Tenta Gemini (se não em cooldown)
   ↓ Se AMBOS 429 → Ativa 3º Cérebro
   
3. VALIDAÇÃO
   ↓ Confiança >= 80%?
   ↓ Símbolo bloqueado?
   ↓ Confluências OK?
   
4. EXECUÇÃO
   ↓ Calcula tamanho dinâmico
   ↓ Valida notional mínimo
   ↓ Registra no SQLite
   ↓ Executa ordem real
   
5. MONITORAMENTO
   ↓ Aguarda saída (SL/TP)
   ↓ Registra resultado
   ↓ Atualiza aprendizado
   
6. ANÁLISE
   ↓ Detecta padrões de falha?
   ↓ Bloqueia símbolo se 3+ perdas?
   ↓ Próximo ciclo...
```

---

## 🎓 Aprendizados Chave

O sistema aprenhe que:

✅ "Quando SMA 200 ≈ $1900, ETHUSDT perdeu 3x. Bloquear."
✅ "Volume < 1.5x = entrada fraca. Aumentar threshold."
✅ "RSI > 75 em ALTA = exaustão. Não entrar."
✅ "SuperTrend em divergência com SMA = evitar."

---

## 🛟 Troubleshooting

### 3º Cérebro não está ativando

```
1. Verifique se APIs realmente retornam 429
2. Confirme que ALLOW_REAL_TRADING=true
3. Verifique logs para "429_RATE_LIMIT"
```

### Muitos símbolos bloqueados

```
1. Revise confiança mínima (talvez 80% seja alto)
2. Analise histórico de trades no dashboard
3. Considere aumentar duration de bloqueio
```

### Performance ruim do 3º Cérebro

```
1. Verifique indicadores (SMA, Supertrend, RSI)
2. Analyze win rate por símbolo
3. Considere ajustar pesos dos indicadores
```

---

## 📞 Suporte

Veja documentação completa em:
- `STREAMLIT_DASHBOARD.md` - Dashboard
- `README.md` - Setup geral
- `RAILWAY_QUICK_REF.md` - Deploy

---

**Versão**: v61.0
**Status**: Production Ready
**Última Atualização**: 2025-05-19

🧠 **3º CÉREBRO: EXECUTOR PRINCIPAL (ATIVO REAL)**
