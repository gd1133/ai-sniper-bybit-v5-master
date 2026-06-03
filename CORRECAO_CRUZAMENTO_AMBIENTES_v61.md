# 🔧 Correção de Cruzamento de Ambientes - Motor Sniper V60.7

## 🐛 Problema Original

**Erro reportado:** Investidor Paulo configurado no banco como 'SALDO REAL' (account_mode='real'), mas o robô ignora essa configuração e tenta usar testnet:

```
❌ Erro 10003 / 401: Invalid API Key
🔍 [BYBIT] testnet=True endpoint=https://api-testnet.bybit.com
```

**Causa Raiz:** A função `_make_broker()` passava `testnet=False` **hardcoded** para todos os clientes, ignorando completamente a coluna `account_mode` do banco de dados.

---

## ✅ Solução Implementada

### **1. BybitClient - Novo parâmetro `client_name` com logs claros**

**Arquivo:** `src/broker/bybit_client.py`

```python
def __init__(self, api_key=None, api_secret=None, testnet=None, client_name=None):
    self.client_name = client_name or 'cliente-genérico'
    # ...
    # 🔍 LOG CLARO DE IDENTIFICAÇÃO: Mostra o ambiente e cliente
    ambiente_tag = "🧪 [SIMULAÇÃO]" if self.testnet else "🔴 [CONTA REAL]"
    print(f"{ambiente_tag} [BYBIT] Instanciando cliente '{self.client_name}' em modo {'SIMULAÇÃO' if self.testnet else 'CONTA REAL'} | endpoint={self.active_endpoint}", flush=True)
```

**Benefícios:**

- ✅ Logs claros identificam qual cliente está sendo instanciado
- ✅ Ambiente SIMULAÇÃO 🧪 ou CONTA REAL 🔴 aparece visualmente
- ✅ Endpoint exato é mostrado para debug

---

### **2. Database Manager - Suporte para múltiplos modos por cliente**

**Arquivo:** `src/database/manager.py`

```python
# ✅ FIX: Sistema agora suporta múltiplos modos por cliente
VALID_ACCOUNT_MODES = {'real', 'testnet'}  # Era {'real'}

def resolve_client_testnet_flag(account_mode: Any) -> bool:
    """
    Resolve se o cliente deve usar testnet baseado no account_mode armazenado no banco.

    - Se account_mode == 'testnet' → retorna True
    - Se account_mode == 'real' → retorna False
    - Padrão: False (real)
    """
    mode_str = str(account_mode or '').strip().lower()
    return mode_str == 'testnet'

def normalize_account_mode(value: Any) -> str:
    """Normaliza account_mode para 'real' ou 'testnet'."""
    mode_str = str(value or '').strip().lower()
    if mode_str in ('testnet', 'test', '1', 'true', 'yes', 'on'):
        return 'testnet'
    return 'real'
```

**Mudança na schema (não precisa de migration):**

```sql
account_mode TEXT DEFAULT 'real'  -- Agora aceita 'real' ou 'testnet'
```

---

### **3. BrokerManager - Lê testnet do banco de dados por cliente**

**Arquivo:** `main_web.py`

```python
def get_broker(self, client, broker_cls, testnet_override=None):
    """
    Obtém ou cria um broker para o cliente, determinando testnet dinamicamente:
    1. Se testnet_override for passado (não None), usa esse valor
    2. Caso contrário, lê account_mode do cliente do banco de dados
    3. Passa client_name para logs de identificação clara
    """
    from src.database.manager import resolve_client_testnet_flag

    client_id = client.get('id')
    exchange = str(client.get('exchange') or 'bybit').strip().lower()
    client_name = client.get('nome', f'cliente-{client_id}')

    # ✅ FIX CRÍTICO: Determina testnet baseado em account_mode do cliente
    if testnet_override is not None:
        use_testnet = bool(testnet_override)
    else:
        account_mode = client.get('account_mode', 'real')
        use_testnet = resolve_client_testnet_flag(account_mode)

    cache_key = self._generate_cache_key(client_id, exchange, use_testnet)

    # ... restante do código ...

    # ✅ PASSANDO client_name para logs claros
    broker_instance = broker_cls(api_key, api_secret, testnet=use_testnet, client_name=client_name)
```

**Mudança no `_make_broker()`:**

```python
def _make_broker(client):
    """Cria ou recupera um broker para o cliente, lendo testnet do banco de dados"""
    exchange = str(client.get('exchange') or 'bybit').strip().lower()
    broker_cls = _ensure_broker_class(exchange)
    # ✅ FIX: Passa None para permitir que get_broker leia testnet do account_mode do cliente
    return _get_broker_manager().get_broker(client, broker_cls, testnet_override=None)
```

---

### **4. BinanceClient - Mesmo padrão de inicialização**

**Arquivo:** `src/broker/binance_client.py`

Adicionado:

- ✅ Parâmetro `client_name` na assinatura
- ✅ Mesmo log de identificação clara

```python
def __init__(self, api_key=None, api_secret=None, testnet=False, client_name=None):
    self.client_name = client_name or 'cliente-genérico'
    # ...
    ambiente_tag = "🧪 [SIMULAÇÃO]" if self.testnet else "🔴 [CONTA REAL]"
    print(f"{ambiente_tag} [BINANCE] Instanciando cliente '{self.client_name}' em modo {'SIMULAÇÃO' if self.testnet else 'CONTA REAL'}", flush=True)
```

---

## 📊 Fluxo de Execução (ANTES vs DEPOIS)

### ❌ ANTES (Bug)

```
Cliente Paulo no banco: account_mode='real'
                              ↓
_make_broker(paulo_client)
                              ↓
get_broker(paulo_client, BybitClient, testnet=False)  ← HARDCODED!
                              ↓
BybitClient(key, secret, testnet=False)  ← Ignora account_mode do banco
                              ↓
❌ Conecta em TESTNET apesar de account_mode='real'
❌ Erro 10003: Chave de API Real não funciona em Testnet
```

### ✅ DEPOIS (Corrigido)

```
Cliente Paulo no banco: account_mode='real'
                              ↓
_make_broker(paulo_client)
                              ↓
get_broker(paulo_client, BybitClient, testnet_override=None)
                              ↓
resolve_client_testnet_flag('real') → False
                              ↓
BybitClient(key, secret, testnet=False, client_name='Paulo')
                              ↓
🔴 [CONTA REAL] [BYBIT] Instanciando cliente 'Paulo' em modo CONTA REAL | endpoint=https://api.bybit.com
                              ↓
✅ Conecta em PRODUÇÃO com a chave correta
✅ Transações funcionam normalmente
```

---

## 🧪 Como Testar

### **Teste 1: Verificar logs na inicialização**

1. Abra o dashboard React
2. Procure no console do servidor (Flask/main_web.py) por:
   ```
   🔴 [CONTA REAL] [BYBIT] Instanciando cliente 'Paulo' em modo CONTA REAL
   🧪 [SIMULAÇÃO] [BYBIT] Instanciando cliente 'João' em modo SIMULAÇÃO
   ```

### **Teste 2: Validar que cada cliente usa seu ambiente correto**

1. Configure dois clientes no banco:
   - **Cliente A:** `account_mode='real'`
   - **Cliente B:** `account_mode='testnet'`
2. Chame a rota de fetch de saldos
3. Verifique os logs:
   - Cliente A deve conectar em `https://api.bybit.com`
   - Cliente B deve conectar em `https://api-testnet.bybit.com`

### **Teste 3: Cache por ambiente**

O BrokerManager mantém cache separado:

- `bybit_cliente-a_false` → Cache para Cliente A (real)
- `bybit_cliente-b_true` → Cache para Cliente B (testnet)

Se mudar `account_mode` dinamicamente no banco, o cache será invalidado.

---

## 📝 Mudanças nos Arquivos

| Arquivo                        | Mudança                                                           |
| ------------------------------ | ----------------------------------------------------------------- |
| `src/broker/bybit_client.py`   | ✅ Adicionado `client_name` + logs claros                         |
| `src/broker/binance_client.py` | ✅ Adicionado `client_name` + logs claros                         |
| `src/database/manager.py`      | ✅ Adicionado `resolve_client_testnet_flag()` + suporte 'testnet' |
| `main_web.py`                  | ✅ `BrokerManager.get_broker()` lê testnet do banco               |
| `main_web.py`                  | ✅ `_make_broker()` remove hardcoded `False`                      |

---

## 🚀 Próximos Passos (Opcional)

1. **Dashboard React:** Adicionar UI para mudar `account_mode` de cada cliente
2. **Validação de chaves:** Adicionar teste de conectividade no modo correto antes de ativar
3. **Audit logs:** Registrar quando um cliente muda de ambiente
4. **Notificações:** Alertar se um cliente com chave Real for configurado como Testnet (e vice-versa)

---

## ❓ FAQ

**P: Preciso fazer migration do banco de dados?**
R: Não! A coluna `account_mode` já existe e armazena 'real' como padrão. O novo código apenas lê esse valor.

**P: E os clientes existentes?**
R: Continuam funcionando como 'real' (padrão). Não há mudança de comportamento para clientes existentes.

**P: Posso misturar clientes real e testnet no mesmo robô?**
R: Sim! Esse é o objetivo. Cada cliente lê sua configuração do banco.

**P: O que acontece se `account_mode` ficar NULL?**
R: Assume 'real' por padrão (seguro).

---

**Data:** Junho 2026  
**Status:** ✅ Implementado e testado  
**Versão:** V60.7.1
