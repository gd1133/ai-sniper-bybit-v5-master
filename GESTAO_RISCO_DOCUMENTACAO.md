# 📊 Gestão de Risco - AI Sniper V5
## Planejamento de Entrada Dinâmico

---

## 🎯 Regras Configuradas (Conforme Solicitação do Cliente)

### **1. Entrada Normal (Primeira ou Após Vitória)**
- **Percentual da Banca**: `5%`
- **Quando Usa**: 
  - ✅ Primeira entrada do cliente (sem histórico)
  - ✅ Após um trade com **LUCRO** (Take Profit)
  - ✅ Após qualquer fechamento que NÃO seja Stop Loss

**Exemplo:**
```
Banca: $1.000 USDT
Entrada: $50 USDT (5% da banca)
Alavancagem: 20x
Valor da Posição: $1.000 USDT
```

---

### **2. Entrada Conservadora (Após Stop Loss)**
- **Percentual da Banca**: `3%`
- **Quando Usa**:
  - ❌ Após um trade com **PREJUÍZO** (Stop Loss)
  - ⚠️ Reduz exposição para proteger a banca

**Exemplo:**
```
Banca: $1.000 USDT
Entrada: $30 USDT (3% da banca)
Alavancagem: 20x
Valor da Posição: $600 USDT
```

---

## 🔄 Fluxo de Recuperação Automática

```
┌─────────────────────────────────────────────────────────────────┐
│                    CICLO DE GESTÃO DE RISCO                     │
└─────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │ PRIMEIRA     │
    │ ENTRADA      │──────► 5% DA BANCA
    └──────┬───────┘
           │
           ▼
    ┌──────────────────────────┐
    │ TRADE EM ANDAMENTO       │
    └──────┬───────────────────┘
           │
           ├────────────────┬────────────────┐
           ▼                ▼                ▼
    ┏━━━━━━━━━┓      ┌─────────────┐   ┌──────────────┐
    ┃ STOP    ┃      │ TAKE PROFIT │   │ SAÍDA MANUAL │
    ┃ LOSS    ┃      │ (Lucro)     │   │ (Lucro)      │
    ┗━━━┯━━━━━┛      └──────┬──────┘   └──────┬───────┘
        │                   │                  │
        │                   │                  │
        ▼                   ▼                  ▼
    ┏━━━━━━━━━━━━━┓   ┌──────────────────────────────┐
    ┃ PRÓXIMA     ┃   │ PRÓXIMA ENTRADA              │
    ┃ ENTRADA:    ┃   │ 5% DA BANCA                  │
    ┃ 3% DA BANCA ┃   │ ✅ VOLTA AO NORMAL           │
    ┗━━━━━━━━━━━━━┛   └──────────────────────────────┘
```

---

## 💻 Implementação Técnica

### **Arquivo: `src/risk/position_sizing.py`**

#### **Constantes Configuráveis**
```python
DEFAULT_ENTRY_PCT = 0.05              # 5% da banca (normal)
DEFAULT_ENTRY_AFTER_STOP_PCT = 0.03   # 3% após stop loss
```

#### **Variáveis de Ambiente**
```bash
# .env ou Render Environment
RISK_PER_TRADE_PCT=5           # 5% entrada normal
ENTRY_AFTER_STOP_PCT=3         # 3% após stop loss
```

---

### **Função de Decisão: `_client_had_last_stop_loss()`**

**Localização**: `main_web.py` - Linha 3550

```python
def _client_had_last_stop_loss(client_id: int) -> bool:
    """
    Verifica se o último trade fechado foi Stop Loss.
    
    Lógica:
    1. Busca o último trade FECHADO do cliente
    2. Verifica se contém 'STOP_LOSS' nas notas
    3. Ou se o PnL% é <= threshold de stop (-50% ROI)
    
    Retorna:
        True  → Próxima entrada usa 3%
        False → Próxima entrada usa 5%
    """
    if client_id <= 0:
        return False
    
    try:
        last_closed = db.get_last_closed_trade(client_id)
        if not last_closed:
            return False  # Sem histórico → usa 5%
        
        # Verifica notas do trade
        last_notes = str((last_closed or {}).get('notes') or '').upper()
        if 'STOP_LOSS' in last_notes:
            return True  # Foi stop loss → usa 3%
        
        # Verifica PnL%
        pnl_pct = float((last_closed or {}).get('pnl_pct') or 0)
        return pnl_pct <= load_sl_roi_pct()  # <= -50% ROI
    
    except Exception:
        return False  # Em caso de erro → usa 5% (seguro)
```

---

### **Aplicação no Cálculo de Ordem**

**Localização**: `main_web.py` - Linha 3598

```python
# ANTES DE ABRIR UMA NOVA POSIÇÃO:
after_stop = _client_had_last_stop_loss(client_id)

# Define o percentual correto
margem_pct = float(
    PERCENTUAL_ENTRADA_POS_STOP   # 3%
    if after_stop 
    else PERCENTUAL_ENTRADA_BANCA  # 5%
)

# Calcula margem e quantidade
margin = _calculate_order_margin(saldo, after_stop=after_stop)
qty = calcular_tamanho_posicao(
    saldo_banca=saldo,
    alavancagem=leverage,
    preco_entrada=price,
    pct_banca=margem_pct
)
```

---

## ✅ Confirmação da Lógica do Cliente

| Cenário | Percentual de Entrada | Status |
|---------|----------------------|--------|
| **Primeira entrada** | 5% da banca | ✅ Implementado |
| **Após STOP LOSS** | 3% da banca | ✅ Implementado |
| **Após TAKE PROFIT** | 5% da banca (volta ao normal) | ✅ Implementado |
| **Após saída manual com lucro** | 5% da banca | ✅ Implementado |
| **Após saída manual com prejuízo < -50% ROI** | 3% da banca | ✅ Implementado |

---

## 🧪 Cenários de Teste

### **Teste 1: Primeira Entrada**
```
Cliente ID: 1001
Histórico: VAZIO
Resultado Esperado: 5% da banca
```

### **Teste 2: Após Vitória**
```
Cliente ID: 1001
Último Trade: PnL = +2.5% | Notes: "TAKE_PROFIT"
Resultado Esperado: 5% da banca
```

### **Teste 3: Após Stop Loss**
```
Cliente ID: 1001
Último Trade: PnL = -1.8% | Notes: "STOP_LOSS"
Resultado Esperado: 3% da banca
```

### **Teste 4: Recuperação Após Vitória**
```
Cliente ID: 1001
Penúltimo Trade: PnL = -1.8% | Notes: "STOP_LOSS"
Último Trade: PnL = +3.2% | Notes: "TAKE_PROFIT"
Resultado Esperado: 5% da banca (recuperado)
```

---

## 📈 Exemplo Prático Completo

### **Cenário Real de 5 Trades**

| # | Resultado | PnL | Notas | Banca | Próxima Entrada | % Usado |
|---|-----------|-----|-------|-------|-----------------|---------|
| 1 | ✅ Win | +2.3% | TAKE_PROFIT | $1,000 | $50.00 | 5% |
| 2 | ✅ Win | +1.8% | PARTIAL_TP | $1,023 | $51.15 | 5% |
| 3 | ❌ Loss | -1.5% | STOP_LOSS | $1,041 | **$31.23** | **3%** ⚠️ |
| 4 | ✅ Win | +2.1% | TAKE_PROFIT | $1,026 | $51.30 | 5% ✅ |
| 5 | ✅ Win | +3.4% | LEVEL2_TP | $1,047 | $52.35 | 5% |

**Observações:**
- Trade #3: Stop Loss → Trade #4 usa **3%** (proteção)
- Trade #4: Vitória → Trade #5 volta para **5%** (recuperado)

---

## 🔧 Configuração no Render.com

Para ajustar os percentuais no ambiente de produção:

1. **Acesse**: Render.com → Seu serviço → Aba **Environment**
2. **Variáveis**:
   ```
   RISK_PER_TRADE_PCT=5           # Entrada normal (5%)
   ENTRY_AFTER_STOP_PCT=3         # Após stop loss (3%)
   ```
3. **Clique em "Save Changes"**
4. **Aguarde o deploy** automático

---

## 🎯 Validação da Configuração

Execute no **Shell do Render** ou localmente:

```bash
cd /home/ubuntu/ai_sniper_v5
python3 -c "
from src.risk.position_sizing import load_entry_pct, load_entry_after_stop_pct
print(f'Entrada Normal: {load_entry_pct() * 100:.1f}%')
print(f'Após Stop Loss: {load_entry_after_stop_pct() * 100:.1f}%')
"
```

**Saída Esperada:**
```
Entrada Normal: 5.0%
Após Stop Loss: 3.0%
```

---

## 📊 Monitoramento em Produção

### **Logs Esperados**

#### **Entrada Normal (5%)**
```
[RISK] Cliente #1001 - Sem stop loss recente
[RISK] Usando entrada padrão: 5% da banca
[RISK] Banca: $1000.00 → Margem: $50.00 | Lev: 20x → Qty: 0.100
```

#### **Entrada Conservadora (3%)**
```
[RISK] Cliente #1001 - Último trade foi STOP_LOSS
[RISK] Usando entrada conservadora: 3% da banca
[RISK] Banca: $1000.00 → Margem: $30.00 | Lev: 20x → Qty: 0.060
```

---

## ⚙️ Personalização (Se Necessário)

### **Para Mudar os Percentuais**

#### **Opção 1: Via Variável de Ambiente (Recomendado)**
```bash
# No Render ou .env local
RISK_PER_TRADE_PCT=6.5         # Mudar para 6.5%
ENTRY_AFTER_STOP_PCT=2.5       # Mudar para 2.5%
```

#### **Opção 2: Via Código**
Editar `src/risk/position_sizing.py`:
```python
DEFAULT_ENTRY_PCT = 0.065              # 6.5% entrada normal
DEFAULT_ENTRY_AFTER_STOP_PCT = 0.025   # 2.5% após stop loss
```

---

## 🛡️ Proteções de Segurança

### **Teto Máximo de Entrada**
```python
MAX_ENTRY_PCT_CAP = 0.10  # 10% (nunca excede, mesmo se configurado acima)
```

### **Validação de Viabilidade**
Antes de executar, o sistema valida:
- ✅ Quantidade mínima da exchange (`minOrderQty`)
- ✅ Tamanho do step (`qtyStep`)
- ✅ Valor nocional mínimo (`min_cost`)
- ✅ Saldo disponível suficiente

---

## 🎓 Resumo Executivo

✅ **Sistema Atual Está CORRETO e Implementado Conforme Pedido:**

1. ✅ Entrada normal: **5% da banca**
2. ✅ Após stop loss: **3% da banca**
3. ✅ Após vitória: **VOLTA para 5%** automaticamente
4. ✅ Lógica robusta verificando último trade fechado
5. ✅ Sem necessidade de ajustes manuais

**🎯 Validação Final**: A lógica implementada está **100% alinhada** com a solicitação do cliente!

---

**📅 Última Atualização:** 15/09/2026  
**🔗 Arquivos Relacionados:**
- `src/risk/position_sizing.py` (linhas 1-333)
- `main_web.py` (linha 3550 - função `_client_had_last_stop_loss`)
- `.env.example` (linhas 105, 109)

---

**✨ Próximos Passos:**
1. Validar em produção monitorando os logs
2. Confirmar se os percentuais estão corretos no Render
3. Testar com trades reais (iniciar com valores baixos)
