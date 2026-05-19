# 🔧 REFATORAÇÃO COMPLETA: Sistema de Cálculo de Ordens v61.1

## ✅ Implementado

### 1. FIM DO VALOR FIXO DE 5% (Cálculo Baseado no Mínimo do Ativo)

**ANTES:**
```python
# Cálculo baseado em percentual fixo da banca
entry_value = balance * 0.15  # 15% fixo
qty = entry_value / price
```

**DEPOIS:**
```python
# Cálculo dinâmico baseado nos limites da exchange
qty, metadata = broker.calculate_dynamic_order_qty(symbol, balance)
# Busca: market["limits"]["amount"]["min"] e market["limits"]["cost"]["min"]
# Calcula quantidade EXATA para nocional mínimo + margem de segurança
```

**Onde foi aplicado:**
- ✅ `src/broker/order_calculator.py` - Novo módulo criado
- ✅ `main.py` - Função `calculate_entry_qty()` refatorada
- ✅ `main_web.py` - Funções `_calculate_dynamic_order_quantity()` implementadas
- ✅ `main_web.py` - Broadcast orders usando cálculo dinâmico

**Margens de segurança configuradas:**
- Binance: Mínimo + $0.50 USDT
- Bybit: Mínimo + $0.50 USDT

### 2. FORMATADOR DE PRECISÃO DO CCXT

**Implementado:**
```python
# Aplica obrigatoriamente antes de disparar create_market_order
final_qty = float(exchange.amount_to_precision(symbol, quantidade_calculada))
```

**Onde foi aplicado:**
- ✅ `src/broker/order_calculator.py:146` - Aplicação em calculate_minimum_order_qty()
- ✅ `src/broker/order_calculator.py:247` - Aplicação em calculate_order_qty_from_balance()
- ✅ `src/broker/bybit_client.py` - Usa _normalize_order_qty que aplica precisão
- ✅ `src/broker/binance_client.py` - Usa _normalize_order_qty que aplica precisão

**Tratamento de erros decimais:**
```python
from src.broker.order_calculator import sanitize_numeric_string

# Limpa strings: remove espaços, troca vírgulas por pontos
cleaned = sanitize_numeric_string("1,234.56")  # "1234.56"
```

### 3. CORREÇÃO DE TIMEOUT E DESCONEXÃO (TIME SYNC E COOLDOWN)

**Flags CCXT implementadas:**
```python
cfg = {
    'options': {
        'adjustForTimeDifference': True,  # ✅ OBRIGATÓRIO
        'recvWindow': 10000,              # ✅ 10s de tolerância (não 20s)
    }
}
```

**Onde foi aplicado:**
- ✅ `src/broker/bybit_client.py:75-76` - Configuração CCXT
- ✅ `src/broker/binance_client.py:107-108` - Configuração CCXT

**Time Sync na inicialização:**
```python
# Sincronização automática ao inicializar
if api_key and api_secret:
    self.exchange.load_time_difference()
    print("✅ [BYBIT TIME SYNC] Diferença de tempo sincronizada")
```

**Cooldown de 15s entre ciclos:**
```python
# Em main.py linha 639
ANTI_RATE_LIMIT_SLEEP = 15  # ⏸️ Espaçamento obrigatório
time.sleep(ANTI_RATE_LIMIT_SLEEP)
```

**Status:** ✅ JÁ IMPLEMENTADO no main.py

**Tratamento de Rate Limit 429:**
```python
# src/ai_brain/validator.py linhas 171-182 (Groq)
if '429' in error_str or 'rate' in error_str.lower():
    self.groq_cooldown_until = time.time() + 60
    print("🔴 [GROQ 429] Cooldown 60s ativado. 3º Cérebro operará sozinho.")
    return 45, 'WAIT', "429_RATE_LIMIT"

# src/ai_brain/validator.py linhas 224-229 (Gemini)
elif res.status_code == 429:
    self.global_cooldown_until = time.time() + 60
    print("🔴 [GEMINI 429] Cooldown 60s ativado. 3º Cérebro operará sozinho.")
    return self.gemini_min_confidence, "429_RATE_LIMIT", "WAIT", True
```

**Status:** ✅ JÁ IMPLEMENTADO no validator.py

### 4. HIERARQUIA SEM SIMULAÇÃO OPERACIONAL

**Verificação ALLOW_REAL_TRADING:**
```python
# Em main_web.py linha 2556
if _is_order_execution_enabled(APP_MODE):
    # Ordem transmitida via API real para corretora
    order_result = broker.execute_market_order(
        symbol, side.lower(), qty,
        raise_on_error=ALLOW_REAL_TRADING  # 🔴 Expõe erro bruto se True
    )
```

**Tratamento de erros em produção:**
```python
# Em main_web.py linhas 2531-2535
except Exception as preflight_err:
    # 🚫 FALLBACK DESATIVADO: Sempre joga erro bruto no log
    print(f"❌ [ERRO PRÉ-VOO REAL] Cliente: {cliente_nome}")
    print(f"   🔍 ERRO BRUTO DA CORRETORA: {preflight_err}")
    raise  # Força propagação do erro sem silenciar
```

**Status:** ✅ JÁ IMPLEMENTADO no main_web.py

## 📊 Resumo das Mudanças

### Arquivos Criados
- `src/broker/order_calculator.py` - Módulo de cálculo dinâmico (331 linhas)

### Arquivos Modificados
- `src/broker/bybit_client.py` - Adicionado OrderCalculator, flags CCXT, método calculate_dynamic_order_qty()
- `src/broker/binance_client.py` - Adicionado OrderCalculator, flags CCXT
- `main.py` - Refatorado calculate_entry_qty(), atualizado para v61.1
- `main_web.py` - Refatoradas funções de cálculo, broadcast orders usando cálculo dinâmico

### Funções Deprecadas (mantidas para compatibilidade)
- `main_web.py:_calculate_order_quantity()` - Emite warning, retorna qty=0
- `main_web.py:_calculate_webhook_order_quantity()` - Emite warning, retorna qty=0
- `main_web.py:_calculate_order_margin()` - Retorna saldo completo (não aplica % fixo)

### Novas Funções
- `src/broker/order_calculator.py:OrderCalculator.calculate_minimum_order_qty()` - Cálculo com mínimo absoluto
- `src/broker/order_calculator.py:OrderCalculator.calculate_order_qty_from_balance()` - Cálculo com múltiplo do mínimo
- `src/broker/order_calculator.py:sanitize_numeric_string()` - Limpeza de strings numéricas
- `src/broker/bybit_client.py:calculate_dynamic_order_qty()` - Interface pública do broker
- `main_web.py:_calculate_dynamic_order_quantity()` - Nova função para broadcast orders

## 🎯 Resultados Esperados

1. **Ordens sempre respeitam limites da exchange:**
   - Nenhuma rejeição por lote mínimo inválido
   - Nenhuma rejeição por nocional mínimo inválido

2. **Cálculo transparente e auditável:**
   - Logs detalhados de limites, nocional, margem de segurança
   - Metadados completos retornados em cada cálculo

3. **Sincronização de tempo robusta:**
   - Flags CCXT obrigatórias (adjustForTimeDifference, recvWindow)
   - Elimina erros de InvalidNonce (10002)

4. **Cooldown inteligente:**
   - 15s entre ciclos de varredura
   - 60s de cooldown em caso de 429
   - Fallback automático para 3º Cérebro

5. **Sem modo simulado em produção:**
   - ALLOW_REAL_TRADING=true → erros expostos, sem fallback silencioso
   - Todas as ordens transmitidas via API real

## 🔍 Validação

### Teste 1: Cálculo Dinâmico
```python
from src.broker.bybit_client import BybitClient

client = BybitClient(api_key="...", api_secret="...", testnet=False)
qty, metadata = client.calculate_dynamic_order_qty('DOGEUSDT', balance=10.0)

# Esperado:
# qty: quantidade calculada respeitando mínimos
# metadata['calculated_cost']: valor nocional >= min_cost + safety_margin
# metadata['min_cost']: limite mínimo da Bybit (ex: 5.0)
# metadata['safety_margin']: 0.50 USDT
```

### Teste 2: Flags CCXT
```python
# Verificar configuração do exchange
print(client.exchange.options['adjustForTimeDifference'])  # True
print(client.exchange.options['recvWindow'])  # 10000
```

### Teste 3: Cooldown e Fallback
```python
# Simular erro 429 em Groq e Gemini
# Verificar se validator ativa 3º Cérebro
# Verificar se cooldown de 60s é aplicado
```

## 🚀 Deployment

1. **Backup da versão atual:**
   ```bash
   git tag v60.8-pre-refactor
   git push origin v60.8-pre-refactor
   ```

2. **Deploy da nova versão:**
   ```bash
   git checkout claude/refactor-order-calculation-logic
   git tag v61.1
   git push origin v61.1
   ```

3. **Validação pós-deploy:**
   - Monitorar logs por 24h
   - Verificar ausência de erros de lote mínimo
   - Confirmar 0% de ordens rejeitadas por nocional
   - Validar funcionamento do 3º Cérebro em caso de 429

## 📝 Notas Técnicas

### Diferenças por Exchange

**Bybit V5:**
- Mínimo nocional padrão: $5.00 USDT (alguns pares: $2.00 USDT)
- Margem de segurança: $0.50 USDT
- recvWindow: 10000ms

**Binance Futures:**
- Mínimo nocional padrão: $5.00 USDT
- Margem de segurança: $0.50 USDT
- recvWindow: 10000ms

### Compatibilidade

- ✅ Python 3.8+
- ✅ CCXT 4.x
- ✅ pybit 5.x (Bybit V5 API)
- ✅ Decimal arithmetic para precisão financeira

---

**Versão:** v61.1
**Data:** 2026-05-19
**Autor:** Claude Code (Anthropic)
**Status:** ✅ IMPLEMENTADO
