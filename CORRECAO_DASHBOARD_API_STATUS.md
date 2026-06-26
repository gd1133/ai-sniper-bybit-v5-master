# Correção do Dashboard API Status - Motor Sniper V60.7

## 🎯 Problema Identificado

O Dashboard do Motor Sniper V60.7 estava travado exibindo:
- ❌ Saldo: $0.00 USDT (mesmo com $27.93 USDT na conta real)
- ❌ Status: "Iniciando sistema..." (travado)
- ❌ Monitor Sniper Multi-Ativo: Vazio (sem exibir BEAT, ONDO, SUI, BNB)

### Causa Raiz

1. **Falta de sincronização em tempo real**: Não havia uma rotina de background buscando posições abertas diretamente da API da Bybit para alimentar o frontend
2. **Parâmetros incorretos na API V5**: Chamadas para `get_positions()` sem `settleCoin='USDT'` causavam erro 10001
3. **Método de busca de saldo**: O saldo estava sendo lido de forma indireta, sem acessar os campos corretos `walletBalance` ou `equity`

---

## ✅ Solução Implementada

### 1. Nova Função de Monitoramento: `_monitor_dashboard_positions()`

Criada uma nova rotina de background que executa a cada **10 segundos** e:

#### 🔹 Busca o Saldo Real da Conta
```python
wallet_response = broker.pybit_session.get_wallet_balance(
    accountType='UNIFIED'
)
```

- Lê o campo `walletBalance` ou `equity` do objeto USDT
- Atualiza `central_state['balance']` com o valor real
- Suporta múltiplos investidores (soma os saldos)

#### 🔹 Busca as Posições Abertas
```python
positions_response = broker.pybit_session.get_positions(
    category='linear',
    settleCoin='USDT'  # 🔥 CORREÇÃO CRÍTICA
)
```

- **Parâmetros obrigatórios da API V5**:
  - `category='linear'` → Contratos perpétuos USDT
  - `settleCoin='USDT'` → Evita erro 10001

- Extrai dados de cada posição:
  - `symbol` (ex: BEATUSDT, ONDOUSDT)
  - `size` (quantidade)
  - `side` (buy/sell)
  - `avgPrice` (preço de entrada)
  - `unrealisedPnl` (lucro/prejuízo não realizado)

#### 🔹 Atualiza o Estado do Dashboard
```python
central_state['balance'] = total_wallet_balance
central_state['active_trades'] = active_trades_list
central_state['status'] = "✅ ONLINE | 4 posição(ões) ativa(s)"
```

- Agrupa posições por símbolo
- Calcula PnL% em tempo real usando preço atual
- Exibe cards visuais no painel React

---

### 2. Melhorias no Método `get_balance()`

Adicionado **Fallback 0** usando pybit diretamente:

```python
# Fallback 0: Tenta usar pybit diretamente (mais confiável para saldo)
if self.pybit_session and self.authenticated:
    wallet_response = self.pybit_session.get_wallet_balance(accountType='UNIFIED')
    # ... busca walletBalance do coin USDT
```

**Ordem de tentativas**:
1. ✅ pybit `get_wallet_balance(accountType='UNIFIED')` ← **NOVO**
2. CCXT `fetch_balance(accountType='UNIFIED')`
3. CCXT `fetch_balance(accountType='CONTRACT')`
4. CCXT `fetch_balance(type='swap')`

---

### 3. Inicialização do Serviço

Adicionada linha em `start_runtime_services()`:

```python
threading.Thread(target=_monitor_dashboard_positions, daemon=True).start()
```

O monitor inicia automaticamente junto com:
- `sniper_worker_loop`
- `_monitor_sl_tp_automatico`
- `_monitor_financial_stop_loss`
- `_fetch_active_client_balances`

---

## 📊 Resultado Esperado

Após o deploy, o Dashboard deve exibir:

### Antes (❌)
```
SALDO REAL (USDT): $0.00
Status: Iniciando sistema...
Monitor Sniper Multi-Ativo: [vazio]
```

### Depois (✅)
```
SALDO REAL (USDT): $27.93
Status: ✅ ONLINE | 4 posição(ões) ativa(s)
Monitor Sniper Multi-Ativo:
  📊 BEAT | COMPRAR | Entry: $0.1234 | PnL: +2.50%
  📊 ONDO | VENDER  | Entry: $0.5678 | PnL: -1.20%
  📊 SUI  | COMPRAR | Entry: $1.2345 | PnL: +0.80%
  📊 BNB  | COMPRAR | Entry: $620.50 | PnL: +3.10%
```

---

## 🔍 Como Verificar se Está Funcionando

### 1. Verificar logs do servidor
```bash
# Procurar por estas mensagens nos logs:
🔄 [DASHBOARD MONITOR] Iniciado - Sincronização de posições Bybit → Frontend
💰 [DASHBOARD] GIVALDO: $27.93 USDT
📊 [DASHBOARD] BEATUSDT: COMPRAR | Size: 100 | Entry: $0.1234 | PnL: $1.25
🔄 [DASHBOARD] Estado atualizado: Saldo=$27.93 | Posições=4
```

### 2. Verificar endpoint /api/status
```bash
curl https://seu-app.onrender.com/api/status | jq '.balance, .active_trades'
```

**Resposta esperada**:
```json
{
  "balance": 27.93,
  "status": "✅ ONLINE | 4 posição(ões) ativa(s)",
  "active_trades": [
    {
      "symbol": "BEAT",
      "side": "COMPRAR",
      "entry_price": 0.1234,
      "current_price": 0.1264,
      "pnl_pct": 2.50,
      "open_pnl_value": 1.25
    }
  ]
}
```

### 3. Verificar no navegador
Abra o Dashboard e observe:
- ✅ Saldo diferente de $0.00
- ✅ Cards das moedas aparecendo dinamicamente
- ✅ PnL% oscilando em tempo real
- ✅ Status mudou de "Iniciando sistema..." para "ONLINE"

---

## 🚀 Deploy

Os arquivos modificados foram:

1. **main_web.py** (linha 223, 718-920)
   - Nova função `_monitor_dashboard_positions()`
   - Registro do thread em `start_runtime_services()`

2. **src/broker/bybit_client.py** (linha 344-418)
   - Fallback 0 adicionado ao método `get_balance()`
   - Uso de `get_wallet_balance()` via pybit

### Comandos de Deploy
```bash
# 1. Fazer commit das alterações
git add main_web.py src/broker/bybit_client.py
git commit -m "Fix: Dashboard API status update com sync em tempo real"
git push origin main

# 2. No Render, o deploy automático será acionado
# 3. Aguardar 2-3 minutos para restart do serviço
# 4. Verificar logs para confirmar inicialização
```

---

## 🔧 Troubleshooting

### Se o saldo ainda aparecer $0.00:

1. **Verificar chaves API**:
   - Tem permissão de leitura de conta?
   - É chave de produção (não testnet)?
   - 2FA está ativo na Bybit?

2. **Verificar tipo de conta**:
   - O script suporta contas Unified Trading Account (UTA)
   - Se for conta clássica, pode precisar de ajustes

3. **Verificar logs de erro**:
   ```bash
   grep "DASHBOARD.*Erro" logs.txt
   grep "get_wallet_balance" logs.txt
   ```

### Se as posições não aparecerem:

1. **Verificar se as posições existem**:
   ```python
   # No terminal Python da Bybit:
   positions = session.get_positions(category='linear', settleCoin='USDT')
   print(positions)
   ```

2. **Verificar erro 10001**:
   - Se aparecer, significa que faltou `settleCoin='USDT'`
   - Certifique-se de que a correção foi aplicada

3. **Verificar intervalo de atualização**:
   - O loop executa a cada 10 segundos
   - Aguardar pelo menos 20 segundos após inicialização

---

## 📝 Notas Técnicas

### Parâmetros Obrigatórios da API Bybit V5

| Endpoint | Parâmetros Obrigatórios |
|----------|------------------------|
| `get_wallet_balance()` | `accountType='UNIFIED'` |
| `get_positions()` | `category='linear'`, `settleCoin='USDT'` |
| `fetch_balance()` | `accountType='UNIFIED'` ou `CONTRACT` |
| `set_leverage()` | `category='linear'` |
| `place_order()` | `category='linear'` |

### Campos de Saldo Disponíveis

```json
{
  "coin": "USDT",
  "walletBalance": "27.93",      // ← Saldo principal
  "equity": "28.15",              // ← Patrimônio total (saldo + PnL)
  "availableToWithdraw": "22.50", // Disponível para saque
  "totalPositionIM": "5.00"       // Margem usada
}
```

### Estrutura da Posição Retornada

```json
{
  "symbol": "BEATUSDT",
  "side": "Buy",
  "size": "100",
  "avgPrice": "0.1234",
  "unrealisedPnl": "1.25",
  "leverage": "20",
  "positionValue": "12.34"
}
```

---

## ✅ Checklist de Validação

- [x] Código compila sem erros de sintaxe
- [x] Função `_monitor_dashboard_positions()` criada
- [x] Thread registrado em `start_runtime_services()`
- [x] Método `get_balance()` atualizado com fallback pybit
- [x] Parâmetros `category='linear'` e `settleCoin='USDT'` adicionados
- [x] Logs detalhados para debugging
- [ ] Testado em ambiente de produção
- [ ] Dashboard exibindo saldo real
- [ ] Posições aparecendo no Monitor Multi-Ativo
- [ ] PnL oscilando em tempo real

---

## 🎓 Aprendizados

1. **Sempre use pybit para operações V5 críticas**: CCXT pode ter delays ou incompatibilidades
2. **API V5 é rigorosa com parâmetros**: `settleCoin` não é opcional em `get_positions()`
3. **Background loops devem ter try-catch amplos**: Um erro não deve travar o loop inteiro
4. **Logs detalhados são essenciais**: Facilita debug em produção onde não há acesso direto

---

**Desenvolvido por**: Claude AI (Anthropic)
**Data**: 30/05/2026
**Versão do Motor**: Sniper V60.7
**Ticket**: Dashboard API Status Update Fix
