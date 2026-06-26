# ⚡ Motor Sniper V60.7 - Quick Start Guide

## 🎯 What Was Fixed?

### 1. **Banca Agora Atualiza Automaticamente** ✅
- Antes: Margem era 5% de `saldo_base` (fixo)
- Agora: Margem é 5% do saldo **real da Bybit** (dinâmico)
- Resultado: Robô ajusta automaticamente o tamanho das posições conforme você ganha/perde

### 2. **P&L do SHORT Agora Está Correto** ✅
- Antes: SHORT ganhador podia aparecer como perdedor
- Agora: LONG e SHORT mostram o sinal correto (+ verde, - vermelho)
- Fórmula:
  - LONG: lucro = (saída - entrada) × qtd
  - SHORT: lucro = (entrada - saída) × qtd

### 3. **Stop Loss -50% Automático** ✅
- Monitora prejuízo flutuante em tempo real
- Se atingir -50% da margem: fecha posição automaticamente
- Calcula P&L correto ao fechar

---

## 📦 O Que Mudar no Seu Código?

### Se Você Chama `_calculate_dynamic_order_quantity()`

**Antes:**
```python
margem, qty = _calculate_dynamic_order_quantity(broker, symbol, 1000.0)
```

**Agora:**
```python
margem, qty, saldo = _calculate_dynamic_order_quantity(broker, symbol, 1000.0)
# Use 'saldo' para ver o saldo atualizado!
```

---

## 🧪 Como Testar?

### Teste 1: Banca Dinâmica
```
1. Abrir uma posição pequena (ex: 0.1 ETH)
2. Ver notificação do Telegram
3. Verificar se mostra saldo correto

4. Depositar $500 na conta Bybit
5. Abrir outra posição
6. Verificar se margem aumentou (5% do novo saldo)
```

### Teste 2: P&L Correto
```
1. LONG: entrada 100, saída 110, qtd 1 → Lucro deve ser +10 ✅
2. SHORT: entrada 100, saída 90, qtd 1 → Lucro deve ser +10 ✅
3. SHORT: entrada 100, saída 110, qtd 1 → Lucro deve ser -10 ✅ (VERMELHO!)
```

### Teste 3: Stop Loss
```
1. Abrir posição pequena
2. Esperar preço ir contra
3. Quando atingir -50% da margem: deve fechar automaticamente!
```

---

## ⚡ Mudanças no Banco de Dados

Três colunas novas foram adicionadas automaticamente:
```sql
ALTER TABLE trades ADD COLUMN exit_price REAL DEFAULT 0;
ALTER TABLE trades ADD COLUMN quantity REAL DEFAULT 0;
ALTER TABLE trades ADD COLUMN margin REAL DEFAULT 0;
```

✅ Nada precisa ser feito - acontece automaticamente!

---

## 🚀 Deploy Checklist

```
☐ Fazer backup do database.db
☐ Testar com posição pequena
☐ Verificar P&L no painel de EVIDÊNCIA
☐ Verificar notificação do Telegram (mostra saldo?)
☐ Deixar rodar por 1 hora
☐ Verificar se stop loss funciona
☐ Fazer deploy em produção
```

---

## 📊 Arquivos Modificados

| Arquivo | Linhas | Mudança |
|---------|--------|---------|
| `main_web.py` | 718-795 | Busca saldo Bybit V5 |
| `main_web.py` | 854-941 | Integra novo retorno |
| `main_web.py` | 1095-1135 | P&L manual close |
| `main_web.py` | 529-654 | Stop loss melhorado |
| `src/database/manager.py` | 127-151 | Schema nova |
| `src/database/manager.py` | 259-287 | record_trade nova |
| `src/database/manager.py` | 290-343 | close_trade com P&L |

---

## ⚠️ Atenção!

1. **Breaking Change**: `_calculate_dynamic_order_quantity()` agora retorna 3 valores (era 2)
2. **Backup**: Faça backup do database antes de fazer deploy
3. **Testes**: Teste com posição pequena primeiro
4. **API Bybit**: Precisa estar funcional para buscar saldo

---

## 🎓 Exemplos Práticos

### Exemplo 1: Banca Crescente
```
Start: Saldo $1000 → Margem = $50
Trade 1: Lucro $100 → Saldo $1100 → Nova margem = $55 ✅

Seu robô vai aumentar automaticamente os tamanhos das próximas posições!
```

### Exemplo 2: SHORT Correto
```
Você vende 1 BTC a $50.000 (SHORT)
Preço cai para $45.000
Você fecha em $45.000

Lucro = (50.000 - 45.000) × 1 = +$5.000 ✅ (VERDE!)

Antes teria mostrado -$5.000 (VERMELHO) ❌
```

### Exemplo 3: Stop Loss Automático
```
Margem usada: $200
Stop loss = -50% × $200 = -$100

Quando P&L flutuante atingir -$100:
→ Posição fecha automaticamente ✅
→ P&L salvo corretamente no banco
```

---

## 🔗 Documentação Completa

Leia o arquivo `MOTOR_SNIPER_V60.7_CORRECOES.md` para detalhes técnicos completos.

---

**Status:** ✅ PRONTO PARA DEPLOY  
**Data:** 2026-05-30  
**Versão:** Motor Sniper V60.7.1
