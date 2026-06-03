# 🎯 REFERÊNCIA RÁPIDA - Correção de Ambientes

## O Problema em 1 Linha

Investidor com `account_mode='real'` era forçado a usar testnet → Erro 10003.

## A Solução em 1 Linha

Cada cliente agora lê seu ambiente do banco de dados em vez de usar valor global.

---

## 🔧 O Que Mudou

### Antes (❌)

```python
# main_web.py
def _make_broker(client):
    return get_broker(client, BybitClient, False)  # ← HARDCODED!
```

### Depois (✅)

```python
# main_web.py
def _make_broker(client):
    return get_broker(client, BybitClient, testnet_override=None)  # ← Lê do banco
```

---

## 📊 Fluxo Simplificado

```
┌─────────────────────────────────┐
│  Cliente Paulo                  │
│  account_mode = 'real'          │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│  resolve_client_testnet_flag()  │
│  'real' → False                 │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│  BybitClient(                   │
│    testnet=False,               │
│    client_name='Paulo'          │
│  )                              │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│  🔴 [CONTA REAL] [BYBIT]        │
│  Instanciando cliente 'Paulo'   │
│  endpoint=https://api.bybit.com │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│  ✅ Conectado!                  │
│  Transações funcionam           │
└─────────────────────────────────┘
```

---

## 📝 Arquivos Editados

| Arquivo                        | O Que Mudou                                               |
| ------------------------------ | --------------------------------------------------------- |
| `src/broker/bybit_client.py`   | `client_name` + logs claros                               |
| `src/broker/binance_client.py` | `client_name` + logs claros                               |
| `src/database/manager.py`      | `resolve_client_testnet_flag()` função                    |
| `main_web.py`                  | `get_broker()` lê do banco, `_make_broker()` sem hardcode |

---

## 🧪 Como Verificar

**Teste 1:** Iniciar servidor

```bash
python main_web.py
```

**Teste 2:** Procurar nos logs

```
🔴 [CONTA REAL] [BYBIT] Instanciando cliente 'Paulo'
🧪 [SIMULAÇÃO] [BYBIT] Instanciando cliente 'João'
```

**Teste 3:** Se aparecem, está funcionando ✅

---

## 🚀 Deploy

```bash
git add .
git commit -m "Fix: Isolamento de ambientes por cliente"
git push origin main
# Render redeploy automático
```

---

## 🎓 Entender Melhor

**Arquivo:** `main_web.py`  
**Classe:** `BrokerManager`  
**Método:** `get_broker()` (linhas ~69-100)

Este é o ponto central. Antes:

```python
use_testnet = testnet  # ← Usa parâmetro (sempre False)
```

Depois:

```python
if testnet_override is not None:
    use_testnet = bool(testnet_override)
else:
    account_mode = client.get('account_mode', 'real')
    use_testnet = resolve_client_testnet_flag(account_mode)  # ← Lê do banco
```

---

## ✨ Resultado

| Antes               | Depois                     |
| ------------------- | -------------------------- |
| ❌ Erro 10003       | ✅ Sem erro                |
| ❌ Todos em testnet | ✅ Cada um em seu lugar    |
| ❌ Logs genéricos   | ✅ "Cliente Paulo" visível |
| ❌ Hardcoded        | ✅ Dinâmico (lê banco)     |

---

## 📞 FAQ Rápido

**P: Preciso atualizar o banco?**  
R: Não. Coluna `account_mode` já existe.

**P: E os clientes existentes?**  
R: Assumem `'real'` (padrão). Sem mudança.

**P: Posso ter real e testnet juntos?**  
R: Sim! Esse é o objetivo.

**P: Como mudar cliente para testnet?**  
R: `UPDATE clientes_sniper SET account_mode='testnet' WHERE id=5;`

---

## 🎯 Próximo Passo

1. Verifique os logs após deploy
2. Se OK, continue usando normalmente
3. Se erro, rollback com: `git revert HEAD`

---

**Version:** V60.7.1  
**Status:** ✅ Pronto  
**Risk:** Baixo
