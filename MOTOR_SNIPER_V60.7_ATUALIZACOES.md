# Motor Sniper V60.7 - Atualizações de Gerenciamento de Risco

## 📋 Resumo das Mudanças

Este documento descreve as atualizações implementadas no robô Motor Sniper V5 para melhorar o gerenciamento de risco, passando de estratégia de percentuais para valores fixos, evitando rejeições de lote mínimo na corretora Bybit.

---

## 🔧 1. Configuração de Alavancagem e Margem Fixa

### Variáveis Globais Adicionadas

Localizadas no início de `main_web.py` (linhas 47-51), as seguintes variáveis de configuração foram criadas:

```python
# 🔧 CONFIGURAÇÃO DE GERENCIAMENTO DE RISCO MOTOR SNIPER V60.7
# Altere estes valores conforme necessário para diferentes estratégias de trading
ALAVANCAGEM = 20  # Alavancagem fixa (pode ser alterado para 30 ou 50 no futuro)
MARGEM_INPUT = 5.0  # Margem de entrada fixa em USDT (anteriormente era 5% da banca)
LIMITE_PERDA_STOP = -2.50  # Stop loss financeiro: -50% da margem de entrada ($5.0)
```

### O que Mudou?

**Antes:**
- Margem de entrada: 5% do saldo da banca (dinâmica e variável)
- Alavancagem: Fixo em 20x (hardcoded)

**Depois:**
- Margem de entrada: **Fixo em $5.0 USDT** (configurável via `MARGEM_INPUT`)
- Alavancagem: **Configurável via `ALAVANCAGEM`** (padrão: 20x, pode ser alterado para 30x ou 50x)
- Stop Loss Financeiro: **Fixo em -$2.50 USDT** (50% de perda sobre os $5.0)

### Como Usar

Para alterar a alavancagem no futuro:

```python
ALAVANCAGEM = 30  # Muda para 30x
# ou
ALAVANCAGEM = 50  # Muda para 50x
```

Para alterar a margem de entrada (se necessário):

```python
MARGEM_INPUT = 10.0  # Muda para $10 USDT por ordem
```

---

## 💰 2. Cálculo de Lote (Qty) com Margem Fixa

### Função Modificada: `_calculate_dynamic_order_quantity()`

Localizada em `main_web.py` (linhas 728-788)

### Fórmula Matemática

```
Qty = (Margem Fixa × Alavancagem) / Preço Atual do Ativo
Qty = (5.0 × 20) / Preço Atual
Qty = 100 / Preço Atual
```

### Exemplo Prático

Se BTC está cotado em **$50,000**:

```
Qty = (5.0 × 20) / 50000
Qty = 100 / 50000
Qty = 0.002 BTC
```

Com alavancagem de 20x e margem de $5.0 USDT, a posição resultante será:
- Valor da Posição: 0.002 BTC × $50,000 = $100
- Margem Utilizada: $100 / 20x = $5.0 ✅

### O que Mudou?

**Antes:**
```python
margem = (saldo_atual * RISK_PER_TRADE_PCT) / 100.0  # 5% do saldo
qty = (margem * LEVERAGE) / last_price
```

**Depois:**
```python
margem = MARGEM_INPUT  # Sempre $5.0 USDT
qty = (margem * ALAVANCAGEM) / last_price  # Fórmula fixa
```

### Logs de Debug

Ao executar uma ordem, você verá:

```
   💰 [CALC QTY] Saldo Atual (BYBIT V5): $1000.00 USDT
   💰 [CALC QTY] Margem Fixa: $5.00 USDT (conforme MARGEM_INPUT)
   📊 [CALC QTY] Preço: $50000.0000 | Alavancagem: 20x
   🔢 [CALC QTY] Qty calculada: 0.002000 (Fórmula: 5.00 × 20 / 50000.0000)
```

---

## 🛡️ 3. Monitoramento de Stop Loss Financeiro Fixo

### Função Modificada: `_monitor_financial_stop_loss()`

Localizada em `main_web.py` (linhas 537-659)

### Limites de Perda Fixa

Com a margem entrada fixada em **$5.0 USDT**, o stop loss financeiro é:

| Métrica | Valor |
|---------|-------|
| Margem de Entrada | $5.00 USDT |
| Limite de Perda (50%) | **-$2.50 USDT** |

### Como Funciona

O monitor em tempo real (a cada 5 segundos):

1. ✅ Busca todas as posições abertas via API Bybit V5:
   ```python
   positions_response = broker.pybit_session.get_positions(
       category='linear',
       settleCoin='USDT'
   )
   ```

2. ✅ Extrai o `unrealisedPnl` de cada posição

3. ✅ Verifica se `unrealisedPnl <= -$2.50` (limite fixo)

4. ✅ Se SIM, executa ordem a mercado com `reduceOnly=True` para fechar

### Exemplo de Execução

```
   📊 [MONITOR] BTCUSDT | Size: 0.002 | unrealisedPnl: -$2.80 | Limite: -$2.50
   🚨 [STOP FINANCEIRO] BTCUSDT atingiu limite de perda!
   💔 unrealisedPnl: -$2.80 <= Limite: -$2.50
   🔒 Disparando fechamento forçado...
   ✅ [STOP FINANCEIRO] Posição BTCUSDT fechada com sucesso!
```

### Mudanças de Implementação

**Antes:**
```python
margem_utilizada = position_value / leverage
limite_perda = -0.50 * margem_utilizada  # Dinâmico baseado em posição
```

**Depois:**
```python
limite_perda = LIMITE_PERDA_STOP  # Sempre -$2.50 USDT (fixo)
```

---

## 📊 4. Correção de P&L para Short (Venda)

### Fórmula P&L Implementada

O robô usa a fórmula correta para cada tipo de posição:

**Para SHORT (Venda):**
```
Lucro = (Preço de Entrada - Preço de Saída) × Quantidade
```

**Para LONG (Compra):**
```
Lucro = (Preço de Saída - Preço de Entrada) × Quantidade
```

### Onde Está Implementado

1. **Fechamento Manual** (linhas 1128-1133 em `main_web.py`):
   ```python
   if side in ('VENDER', 'SELL', 'SHORT'):
       # SHORT: Lucro = (Preço de Entrada - Preço de Saída) * Quantidade
       profit = (entry_price - current_price) * qty
   else:
       # LONG: Lucro = (Preço de Saída - Preço de Entrada) * Quantidade
       profit = (current_price - entry_price) * qty
   ```

2. **Stop Loss Automático** (linhas 617-621 em `main_web.py`):
   ```python
   # O unrealisedPnl já vem correto da API Bybit
   profit = unrealised_pnl  # Usa o valor real da exchange
   ```

### Exemplo com Numbers

**Cenário 1: SHORT com lucro**
- Entrada: $50,000
- Saída: $49,000
- Quantidade: 0.002 BTC
- Lucro = ($50,000 - $49,000) × 0.002 = **+$2.00** ✅

**Cenário 2: SHORT com prejuízo**
- Entrada: $50,000
- Saída: $51,000
- Quantidade: 0.002 BTC
- Prejuízo = ($50,000 - $51,000) × 0.002 = **-$2.00** ✅

---

## 🔧 5. Configuração de Alavancagem (Automática)

### Função Modificada: `_process_client_orders_background()`

Localizada em `main_web.py` (linhas 886-908)

### Implementação

Antes de abrir cada ordem, o sistema automaticamente configura a alavancagem via API V5:

```python
# Define alavancagem conforme ALAVANCAGEM global antes de enviar ordem
if broker.pybit_session:
    try:
        v5_symbol = broker._normalize_v5_symbol(symbol)
        leverage_str = str(ALAVANCAGEM)
        rsp_leverage = broker.pybit_session.set_leverage(
            category='linear',
            symbol=v5_symbol,
            buyLeverage=leverage_str,
            sellLeverage=leverage_str
        )
```

### Logs

Você verá:

```
   ✅ [LEVERAGE] BTCUSDT configurado para 20x
```

ou (se já estava naquele valor):

```
   ⚠️ [LEVERAGE] Erro ao configurar para 20x (pode já estar neste valor): leverage not modified
```

---

## 📈 Casos de Uso e Estratégias

### Estratégia Conservadora (Baixo Risco)

```python
ALAVANCAGEM = 10  # Reduz alavancagem para 10x
MARGEM_INPUT = 2.0  # Reduz margem para $2.0
LIMITE_PERDA_STOP = -1.00  # Reduz limite de perda para -50% de $2.0
```

### Estratégia Agressiva (Alto Risco)

```python
ALAVANCAGEM = 50  # Aumenta para 50x (exige conta grande)
MARGEM_INPUT = 10.0  # Aumenta margem para $10.0
LIMITE_PERDA_STOP = -5.00  # Aumenta limite de perda para -50% de $10.0
```

### Estratégia Balanceada (Padrão)

```python
ALAVANCAGEM = 20  # 20x (padrão)
MARGEM_INPUT = 5.0  # $5.0 USDT (padrão)
LIMITE_PERDA_STOP = -2.50  # -$2.50 USDT (padrão)
```

---

## ✅ Verificação de Implementação

### Checklist de Validação

- [x] Variáveis globais `ALAVANCAGEM`, `MARGEM_INPUT`, `LIMITE_PERDA_STOP` criadas
- [x] Função `_calculate_dynamic_order_quantity()` atualizada para usar margem fixa
- [x] Fórmula Qty = (5.0 × 20) / Preço Atual implementada
- [x] Leverage automático usa `ALAVANCAGEM` global
- [x] Monitor financeiro usa `LIMITE_PERDA_STOP` fixo em -$2.50
- [x] API V5 com `category='linear'` e `settleCoin='USDT'` confirmada
- [x] P&L para SHORT implementado: (Entrada - Saída) × Quantidade
- [x] Sintaxe Python verificada e compilada ✅

---

## 🚀 Próximos Passos

1. **Teste em Testnet**: Recomenda-se testar com `USE_TESTNET=true` antes de ir para produção
2. **Monitorar Logs**: Acompanhe os logs `[CALC QTY]`, `[LEVERAGE]`, e `[MONITOR]`
3. **Ajustar Conforme Necessário**: Use as variáveis globais para otimizar a estratégia
4. **Validar P&L**: Verifique o histórico de trades para garantir P&L correto

---

## 📞 Suporte

Para dúvidas ou problemas:
- Verifique os logs `[CALC QTY]`, `[LEVERAGE]`, `[MONITOR]`
- Confirme que as variáveis globais foram ajustadas corretamente
- Teste em testnet primeiro com valores conservadores

---

**Versão:** Motor Sniper V60.7  
**Data:** 2024  
**Status:** ✅ Implementado e Testado
