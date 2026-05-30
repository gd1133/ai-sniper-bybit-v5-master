# 🚀 Motor Sniper V60.7 - Três Correções Críticas Implementadas

## 📋 Resumo Executivo

Foram implementadas **três correções críticas** no backend Python do robô Motor Sniper V60.7 para corrigir divergências de cálculo com a Bybit e adicionar automações de banca:

### ✅ Correção 1: Atualização Automática da Banca a Cada Entrada
### ✅ Correção 2: Correção da Lógica de Lucro/Prejuízo do SHORT
### ✅ Correção 3: Integração das Regras Anteriores (20x + Stop -50%)

---

## 🔥 Correção 1: Atualização Automática da Banca

### O Problema
O robô estava usando um valor **fixo/cacheado** (`saldo_base`) para calcular a margem de entrada. Isso causava:
- Margens erradas se o cliente depositasse mais dinheiro
- Margens erradas se o cliente perdesse capital
- Desalinhamento com o saldo real da corretora

### A Solução Implementada
Agora, **antes de cada ordem de entrada**, o robô:

```python
# Novo fluxo (implementado em _calculate_dynamic_order_quantity)
1. Chama broker.get_balance() → Busca saldo USDT em tempo real da Bybit
2. Se falhar, usa saldo_base como fallback
3. Calcula margem como 5% do saldo atualizado
4. Retorna (margem, qty, saldo_atualizado)
```

### Exemplos de Uso

**Antes (Código Antigo):**
```python
# Saldo fixo em 1000 USDT
margem, qty = _calculate_dynamic_order_quantity(broker, 'ETHUSDT', 1000.0)
# Margem será sempre 50 USDT (5% de 1000)
```

**Depois (Novo Código):**
```python
# Busca saldo real da Bybit
margem, qty, saldo_atualizado = _calculate_dynamic_order_quantity(broker, 'ETHUSDT', 1000.0)
# Se saldo real = 1200 USDT → margem = 60 USDT ✅
# Se saldo real = 800 USDT → margem = 40 USDT ✅
# Se saldo real = 0 (erro) → usa fallback 1000 USDT
```

### Notificação do Telegram Agora Mostra
```
🔥 OPERACAO REAL EXECUTADA

👤 Investidor: João Silva
📦 Ativo: ETHUSDT
📈 Direcao: COMPRAR
📊 Lote: 0.75
💰 Margem Separada: $60.00 USDT
💼 Saldo Atualizado: $1,200.00 USDT  ← NOVO!
🆔 Hash ID: abc123def456
```

### Arquivos Modificados
- `main_web.py` (linhas 718-795)
  - Função `_calculate_dynamic_order_quantity()` atualizada
- `main_web.py` (linhas 854-941)
  - Função `_process_client_orders_background()` adaptada para retorno de 3-tupla

---

## 🔥 Correção 2: Correção da Lógica de P&L do SHORT

### O Problema
O P&L estava sendo armazenado incorretamente para operações SHORT:
- **LONG** (COMPRAR): Lucro = (Saída - Entrada) × Qtd ✅ (já estava certo)
- **SHORT** (VENDER): Lucro = (Entrada - Saída) × Qtd ❌ (estava invertido)

Resultado: Trades SHORT perdedores apareciam com lucro na tela!

### A Solução Implementada

#### 1. Novo Schema do Banco de Dados
Três colunas adicionadas à tabela `trades`:

```sql
ALTER TABLE trades ADD COLUMN exit_price REAL DEFAULT 0;
ALTER TABLE trades ADD COLUMN quantity REAL DEFAULT 0;
ALTER TABLE trades ADD COLUMN margin REAL DEFAULT 0;
```

#### 2. Fórmula Correta Implementada
```python
# Em close_trade():
if side in ('VENDER', 'SELL', 'SHORT'):
    # SHORT: Lucro = (Preço de Entrada - Preço de Saída) × Quantidade
    profit = (entry_price - exit_price) * quantity
else:
    # LONG: Lucro = (Preço de Saída - Preço de Entrada) × Quantidade
    profit = (exit_price - entry_price) * quantity
```

#### 3. Exemplos de Cálculo

**Exemplo 1: LONG Ganhador**
```
Entrada: 100 USDT (preço)
Saída: 110 USDT (preço)
Quantidade: 1 unidade
Lucro = (110 - 100) × 1 = +10 USDT ✅
```

**Exemplo 2: SHORT Ganhador**
```
Entrada: 100 USDT (preço)
Saída: 90 USDT (preço)
Quantidade: 1 unidade
Lucro = (100 - 90) × 1 = +10 USDT ✅ (CORRIGIDO!)
```

**Exemplo 3: SHORT Perdedor (Agora Correto)**
```
Entrada: 100 USDT (preço)
Saída: 110 USDT (preço)
Quantidade: 1 unidade
Lucro = (100 - 110) × 1 = -10 USDT ✅ (Mostra vermelho!)
```

#### 4. Fluxo de Fechamento de Trade

```python
# Na função close_trade():
# 1. Busca preço atual via broker.get_last_price()
# 2. Obtém entrada_price, quantidade e side da tabela trades
# 3. Calcula P&L usando fórmula correta
# 4. Armazena em profit (com sinal correto!)
```

### Arquivos Modificados
- `src/database/manager.py` (linhas 127-151)
  - Schema da tabela trades atualizado
- `src/database/manager.py` (linhas 259-287)
  - Função `record_trade()` adaptada
- `src/database/manager.py` (linhas 290-343)
  - Função `close_trade()` com P&L automático
- `main_web.py` (linhas 1095-1135)
  - Fechamento manual com P&L correto

---

## 🔥 Correção 3: Integração das Regras Anteriores

### Regra 1: Alavancagem 20x ✅ (Já Existia)
```python
# Antes de cada ordem:
broker.set_leverage(category='linear', symbol='ETHUSDT', 
                    buyLeverage='20', sellLeverage='20')
```

✅ **Status**: Já estava implementado, verificado em linhas 876-895 de main_web.py

### Regra 2: Stop Loss Automático -50% da Margem ✅ (Aprimorado)

#### O Problema Anterior
- Monitor apenas verificava PnL % (-50%)
- Não usava a margem específica da entrada

#### A Solução Implementada
```python
# Em _monitor_financial_stop_loss():

# 1. Busca posições abertas via Bybit V5 API
positions = broker.pybit_session.get_positions(category='linear')

# 2. Para cada posição:
margem_utilizada = positionValue / leverage
limite_perda = -0.50 * margem_utilizada  # -50% da margem

# 3. Monitora unrealisedPnl em tempo real
if unrealisedPnl <= limite_perda:
    # Dispara fechamento automático!
    broker.close_position_with_sl(symbol, side)
    
    # Atualiza banco com P&L correto
    profit = unrealisedPnl  # Usa valor real da Bybit
    db.update_trade(profit=profit)
```

#### Exemplo Prático
```
Entrada: 1.5 ETH a 2000 USDT = 3000 USDT
Alavancagem: 20x
Margem utilizada: 3000 / 20 = 150 USDT

Limite de perda: -50% × 150 = -75 USDT

Monitoramento:
- Price 1980 → P&L = -30 USDT (OK)
- Price 1975 → P&L = -75 USDT (⚠️ LIMITE!)
- Price 1970 → P&L = -150 USDT (🚨 FECHA!)
```

#### Fluxo Automático
```
1. Position atinge -50% da margem
2. Broker fecha posição imediatamente via ordem de mercado
3. Calcula P&L com o preço da saída
4. Armazena no banco com side e profit corretos
5. Notifica via Telegram (se configurado)
```

### Arquivos Modificados
- `main_web.py` (linhas 529-654)
  - Função `_monitor_financial_stop_loss()` aprimorada
  - Agora calcula profit ao fechar

---

## 📊 Comparação de Comportamento

### Antes vs. Depois

| Funcionalidade | Antes | Depois |
|---|---|---|
| **Banca** | Fixada em saldo_base | Atualizada via API Bybit |
| **Margem entrada** | Estática | Dinâmica (5% saldo real) |
| **P&L SHORT** | Invertido ❌ | Correto ✅ |
| **Stop Loss** | PnL % | Margem baseado ✅ |
| **P&L armazenado** | Margem | Lucro/Prejuízo real |
| **Notificação TG** | Sem saldo | Com saldo atualizado |

---

## 🧪 Como Testar

### 1. Teste de Banca Dinâmica
```python
# Abrir posição pequena
# Verificar Telegram notificação
# Confirmar se mostra saldo correto

# Depositar mais dinheiro na conta Bybit
# Abrir outra posição
# Verificar se margem aumentou (5% do novo saldo)
```

### 2. Teste de P&L Correto
```python
# Abrir LONG: entrada 2000, saída 2100 (ganho 100)
# Verificar se profit = +100 ✅

# Abrir SHORT: entrada 2000, saída 1900 (ganho 100)
# Verificar se profit = +100 ✅

# SHORT perdedor: entrada 2000, saída 2100 (perda 100)
# Verificar se profit = -100 ✅ (vermelho!)
```

### 3. Teste de Stop Loss
```python
# Abrir posição pequena
# Esperar preço ir contra
# Monitorar logs em "MONITOR FINANCEIRO"
# Verificar se fecha quando atinge -50% da margem
```

---

## ⚠️ Notas Importantes

### 1. Backup do Database
```bash
# Antes de deploy em produção:
cp database.db database.db.backup
```

### 2. Compreensão de Mudanças
- `_calculate_dynamic_order_quantity()` agora retorna **3-tupla** (era 2-tupla)
- Código antigo que chama com `margem, qty = ...` pode quebrar!
- **Solução**: Usar `margem, qty, saldo = ...`

### 3. Impacto no Banco de Dados
- Novas colunas criadas automaticamente via `_ensure_column()`
- Trades antigos terão `exit_price=0`, `quantity=0`, `margin=0`
- Histórico não será recalculado (apenas novos trades)

### 4. API Bybit - Requisitos
- `accountType='UNIFIED'` obrigatório para get_balance()
- `category='linear'` obrigatório para get_positions()
- recvWindow=20000ms para tolerar latência

---

## 📝 Código de Referência Rápida

### Buscar Saldo Atualizado
```python
saldo = broker.get_balance()  # Retorna float ou None
```

### Registrar Trade com Novos Campos
```python
db.record_trade(
    client_id=1,
    pair='ETHUSDT',
    side='COMPRAR',
    pnl_pct=0.0,
    profit=0.0,
    closed_at=time.strftime("%d/%m %H:%M"),
    notes='AUTO SNIPER',
    status='open',
    entry_price=2000.0,
    exit_price=0.0,  # Será preenchido ao fechar
    quantity=1.5,
    margin=150.0
)
```

### Fechar Trade com P&L Automático
```python
db.close_trade(
    trade_id=123,
    pnl_pct=5.0,
    exit_price=2100.0,
    closed_at=time.strftime("%d/%m %H:%M"),
    notes='MANUAL CLOSE',
    entry_price=2000.0,
    quantity=1.5,
    side='COMPRAR'
    # profit será calculado automaticamente!
)
```

---

## 🚀 Roadmap Futuro

- [ ] Histórico de saldo (para gráficos)
- [ ] Alerts customizáveis de P&L %
- [ ] Estatísticas de win rate por margem
- [ ] Backtest com novo algoritmo de P&L
- [ ] Export de relatório em PDF

---

## 📞 Suporte

Se encontrar problemas:

1. **P&L errado**: Verifique se `quantity` e `exit_price` estão sendo salvos
2. **Banca não atualiza**: Confirme se credenciais Bybit têm permissão de leitura
3. **Stop loss não fecha**: Verifique logs de "MONITOR FINANCEIRO"

---

## 📄 Documentação Técnica

**Arquivos Modificados:**
- `main_web.py` - 200+ linhas de código
- `src/database/manager.py` - 100+ linhas de código

**Testes Executados:**
- ✅ Schema database valida
- ✅ P&L LONG correto
- ✅ P&L SHORT correto
- ✅ Imports sem erro
- ✅ Sintaxe Python válida

**Data de Implementação:** 2026-05-30
**Versão:** Motor Sniper V60.7.1

---

**Fim do Documento**
