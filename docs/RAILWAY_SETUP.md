# Configuração Railway - Motor Sniper v60.7

## ⚠️ PROBLEMA IDENTIFICADO

Você está com **11 variáveis de ambiente** no Railway, mas existem **3 problemas críticos**:

1. **`VITE_API_BASE` está SEM o protocolo HTTPS**
2. **`DATABASE_URL` não é usada** (o sistema usa `SQLITE_DB_PATH`)
3. **Faltam variáveis do Telegram** para notificações

---

## ✅ CONFIGURAÇÃO CORRETA PARA RAILWAY

### **Variáveis OBRIGATÓRIAS** (Total: 7)

```env
# 1. Ambiente de execução (production = modo real)
ENVIRONMENT=production

# 2. Credenciais Bybit (OBRIGATÓRIAS)
BYBIT_API_KEY=sua_chave_bybit_aqui
BYBIT_API_SECRET=seu_segredo_bybit_aqui

# 3. Validação de sinais com IA (RECOMENDADAS)
GEMINI_API_KEY=sua_chave_gemini
GROQ_API_KEY=sua_chave_groq

# 4. Frontend - URL do seu app Railway (CRÍTICO - ADICIONE HTTPS://)
VITE_API_BASE=https://ai-sniper-bybit-v5-master-production.up.railway.app

# 5. Telegram para notificações (RECOMENDADAS)
TELEGRAM_TOKEN=seu_token_telegram
TELEGRAM_CHAT_ID=seu_chat_id_telegram
```

---

## 🔧 VARIÁVEIS OPCIONAIS

Estas variáveis **NÃO são necessárias** quando `ENVIRONMENT=production`:

```env
# ❌ NÃO PRECISA - já é false em production
USE_TESTNET=false

# ❌ NÃO PRECISA - já é true em production
ALLOW_REAL_TRADING=true

# ❌ NÃO PRECISA - já é true em production
ALLOW_ORDER_EXECUTION=true

# ❌ NÃO PRECISA - Railway define automaticamente
PORT=8080
```

---

## 📊 ANÁLISE DAS SUAS VARIÁVEIS ATUAIS

### ✅ **Corretas (manter):**

1. **`ENVIRONMENT=production`** ✅ Correto
2. **`ALLOW_REAL_TRADING=true`** ✅ OK (mas redundante em production)
3. **`ALLOW_ORDER_EXECUTION=true`** ✅ OK (mas redundante em production)
4. **`BYBIT_API_KEY`** ✅ Obrigatório
5. **`BYBIT_API_SECRET`** ✅ Obrigatório
6. **`GEMINI_API_KEY`** ✅ Recomendado
7. **`GROQ_API_KEY`** ✅ Recomendado

### ⚠️ **Problemas a corrigir:**

8. **`VITE_API_BASE=ai-sniper-bybit-v5-master-production.up.railway.app`** ⚠️
   - **PROBLEMA**: Falta o protocolo `https://`
   - **CORRIGIR PARA**: `https://ai-sniper-bybit-v5-master-production.up.railway.app`
   - **IMPACTO**: Frontend não consegue se conectar ao backend!

9. **`DATABASE_URL=/app/data/database.db`** ⚠️
   - **PROBLEMA**: Nome incorreto de variável
   - **SOLUÇÃO**: Remover esta e adicionar `SQLITE_DB_PATH=/app/data/database.db` (opcional)
   - **NOTA**: O sistema já usa `/app/data/database.db` por padrão se não especificado

### ❓ **Opcionais (Binance):**

10. **`BINANCE_API_KEY`** ❓
11. **`BINANCE_API_SECRET`** ❓
    - **NOTA**: Credenciais Binance são armazenadas **por cliente no banco de dados**
    - **Uso**: Apenas se você quiser uma conta mestra Binance global
    - **Recomendação**: Pode remover se não usar conta mestra Binance

### ❌ **Faltando (Telegram):**

- **`TELEGRAM_TOKEN`** ❌ Faltando
- **`TELEGRAM_CHAT_ID`** ❌ Faltando
  - **IMPACTO**: Sistema não envia notificações de sinais e alertas

---

## 🚀 AÇÕES IMEDIATAS NO RAILWAY

### **Passo 1: CORRIGIR VITE_API_BASE**

No Railway, vá em **Variables** e edite:

```diff
- VITE_API_BASE=ai-sniper-bybit-v5-master-production.up.railway.app
+ VITE_API_BASE=https://ai-sniper-bybit-v5-master-production.up.railway.app
```

⚠️ **CRÍTICO**: O `https://` é obrigatório!

### **Passo 2: ADICIONAR TELEGRAM**

Adicione estas 2 variáveis:

```env
TELEGRAM_TOKEN=seu_token_do_botfather
TELEGRAM_CHAT_ID=seu_id_de_chat
```

**Como obter:**
1. **Token**: Fale com @BotFather no Telegram e crie um bot
2. **Chat ID**: Fale com @userinfobot no Telegram

### **Passo 3: CORRIGIR DATABASE_URL (Opcional)**

Se você quer manter a variável de banco de dados:

```diff
- DATABASE_URL=/app/data/database.db
+ SQLITE_DB_PATH=/app/data/database.db
```

Ou simplesmente **remova `DATABASE_URL`** - o sistema já usa `/app/data/database.db` por padrão.

### **Passo 4: LIMPAR VARIÁVEIS REDUNDANTES (Opcional)**

Você pode remover estas 3 variáveis (já são padrão em production):

- ❌ `ALLOW_REAL_TRADING`
- ❌ `ALLOW_ORDER_EXECUTION`
- ❌ `USE_TESTNET` (se existir)

### **Passo 5: BINANCE (Se não usar)**

Se você **não** usa Binance como exchange mestra, pode remover:

- ❌ `BINANCE_API_KEY`
- ❌ `BINANCE_API_SECRET`

**Nota**: Contas Binance de clientes são configuradas no dashboard, não aqui.

---

## 📋 CONFIGURAÇÃO FINAL RECOMENDADA

**Total de 9 variáveis** (mínimo essencial):

```env
# Core (3)
ENVIRONMENT=production
BYBIT_API_KEY=***
BYBIT_API_SECRET=***

# IA (2)
GEMINI_API_KEY=***
GROQ_API_KEY=***

# Telegram (2)
TELEGRAM_TOKEN=***
TELEGRAM_CHAT_ID=***

# Frontend (1)
VITE_API_BASE=https://ai-sniper-bybit-v5-master-production.up.railway.app

# Opcional: Database (1) - pode omitir
SQLITE_DB_PATH=/app/data/database.db
```

---

## 🔐 VERIFICAÇÃO DE SEGURANÇA

### ✅ **Suas chaves estão protegidas?**

- ✅ Nunca commit credenciais no Git
- ✅ Use apenas o painel Railway Variables
- ✅ Marque variáveis sensíveis como "hidden"

### ✅ **Volume configurado?**

No Railway, você DEVE ter um **Volume** montado em `/app/data` para persistir o banco SQLite:

1. Vá em **Settings** → **Volumes**
2. Adicione volume: **Mount Path** = `/app/data`
3. **Sem volume = perda de dados a cada deploy!**

---

## 🐛 DIAGNÓSTICO DE ERROS COMUNS

### Erro: "Failed to fetch" no frontend

**Causa**: `VITE_API_BASE` sem `https://`
**Solução**: Adicione `https://` no início da URL

### Erro: "Telegram not configured"

**Causa**: Faltam `TELEGRAM_TOKEN` ou `TELEGRAM_CHAT_ID`
**Solução**: Adicione as variáveis do Telegram

### Erro: "Database locked" ou dados perdidos

**Causa**: Volume não configurado no Railway
**Solução**: Monte volume em `/app/data`

### Erro: "Invalid API credentials"

**Causa**: Chaves Bybit incorretas ou de testnet em modo production
**Solução**: Verifique se está usando chaves da conta REAL da Bybit

---

## 📞 SUPORTE

Se após seguir este guia o problema persistir:

1. Verifique os logs do Railway: **Deployments** → **View Logs**
2. Procure por erros de startup no log
3. Confirme que todas as variáveis foram salvas corretamente
4. Force um novo deploy: **Deployments** → **Redeploy**

---

## 🎯 CHECKLIST FINAL

Antes de fazer deploy, confirme:

- [ ] `VITE_API_BASE` tem `https://` no início
- [ ] `ENVIRONMENT=production`
- [ ] Chaves Bybit são da conta REAL (não testnet)
- [ ] Telegram configurado (token + chat_id)
- [ ] Volume montado em `/app/data`
- [ ] Variáveis redundantes removidas
- [ ] Build e deploy concluídos sem erros

**Após corrigir as variáveis, force um redeploy no Railway!** 🚀
