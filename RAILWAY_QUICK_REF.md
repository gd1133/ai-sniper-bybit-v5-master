# 🎯 Railway - Cartão de Referência Rápida

## ❌ 3 PROBLEMAS CRÍTICOS

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. VITE_API_BASE SEM HTTPS                                      │
│                                                                   │
│ ❌ ERRADO: ai-sniper-bybit-v5-master-production.up.railway.app  │
│ ✅ CERTO:  https://ai-sniper-bybit-v5-master-production...      │
│                                                                   │
│ 🔧 AÇÃO: Adicione https:// no início!                           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 2. DATABASE_URL (NOME INCORRETO)                                │
│                                                                   │
│ ❌ ATUAL: DATABASE_URL=/app/data/database.db                    │
│ ✅ OPÇÃO 1: DELETAR (sistema usa padrão)                        │
│ ✅ OPÇÃO 2: SQLITE_DB_PATH=/app/data/database.db                │
│                                                                   │
│ 🔧 AÇÃO: Delete ou renomeie!                                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 3. TELEGRAM NÃO CONFIGURADO                                     │
│                                                                   │
│ ❌ FALTANDO: TELEGRAM_TOKEN                                     │
│ ❌ FALTANDO: TELEGRAM_CHAT_ID                                   │
│                                                                   │
│ 🔧 AÇÃO: Adicione as 2 variáveis!                               │
│                                                                   │
│ Como obter:                                                      │
│ • Token: @BotFather no Telegram (/newbot)                       │
│ • Chat ID: @userinfobot no Telegram                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✅ CONFIGURAÇÃO FINAL (7 variáveis mínimas)

```env
┌─────────────────────────────────────────────────────────────────┐
│ VARIÁVEIS ESSENCIAIS                                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│ ENVIRONMENT=production                                           │
│ BYBIT_API_KEY=***                                               │
│ BYBIT_API_SECRET=***                                            │
│ GEMINI_API_KEY=***                                              │
│ GROQ_API_KEY=***                                                │
│ TELEGRAM_TOKEN=***                                              │
│ TELEGRAM_CHAT_ID=***                                            │
│ VITE_API_BASE=https://seu-app.railway.app                      │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🗑️ PODE REMOVER (Opcional)

```
┌─────────────────────────────────────────────────────────────────┐
│ VARIÁVEIS REDUNDANTES                                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│ ❌ ALLOW_REAL_TRADING       → já é true em production          │
│ ❌ ALLOW_ORDER_EXECUTION    → já é true em production          │
│ ❌ DATABASE_URL             → nome incorreto                    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔧 PASSO A PASSO (5 minutos)

```
┌─────────────────────────────────────────────────────────────────┐
│ PASSO 1 → VITE_API_BASE                                         │
├─────────────────────────────────────────────────────────────────┤
│ 1. Railway → Variables                                           │
│ 2. Editar VITE_API_BASE                                          │
│ 3. Adicionar https:// no início                                  │
│ 4. Salvar                                                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ PASSO 2 → TELEGRAM                                              │
├─────────────────────────────────────────────────────────────────┤
│ 1. + New Variable                                                │
│ 2. TELEGRAM_TOKEN = seu_token                                    │
│ 3. + New Variable                                                │
│ 4. TELEGRAM_CHAT_ID = seu_chat_id                               │
│ 5. Salvar                                                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ PASSO 3 → DATABASE                                              │
├─────────────────────────────────────────────────────────────────┤
│ 1. Encontrar DATABASE_URL                                        │
│ 2. Clicar no ícone de lixeira                                    │
│ 3. Confirmar deleção                                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ PASSO 4 → VOLUME                                                │
├─────────────────────────────────────────────────────────────────┤
│ 1. Settings → Volumes                                            │
│ 2. Verificar volume em /app/data                                │
│ 3. Se não existir, adicionar                                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ PASSO 5 → REDEPLOY                                              │
├─────────────────────────────────────────────────────────────────┤
│ 1. Deployments → Redeploy                                        │
│ 2. Aguardar build                                                │
│ 3. Verificar logs                                                │
│ 4. Testar dashboard                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✅ CHECKLIST

```
ANTES DO REDEPLOY:
  [ ] VITE_API_BASE começa com https://
  [ ] TELEGRAM_TOKEN adicionado
  [ ] TELEGRAM_CHAT_ID adicionado
  [ ] DATABASE_URL removida
  [ ] Volume configurado em /app/data
  [ ] Chaves Bybit são da conta REAL

APÓS O REDEPLOY:
  [ ] Build completo sem erros
  [ ] Dashboard abre corretamente
  [ ] API responde (sem "Failed to fetch")
  [ ] Moedas aparecem na lista
  [ ] Telegram envia notificações
```

---

## 📚 DOCUMENTAÇÃO COMPLETA

```
┌─────────────────────────────────────────────────────────────────┐
│ GUIAS DISPONÍVEIS                                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│ 📄 CORRECOES_RAILWAY.md     → Resumo executivo completo        │
│ 📖 docs/RAILWAY_SETUP.md    → Guia detalhado (650+ linhas)     │
│ ⚡ docs/RAILWAY_FIX_RAPIDO.md → Fix rápido                      │
│ 🧪 validate_environment.py  → Script de validação              │
│ 📚 README.md                → Instruções gerais                 │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🆘 PROBLEMAS COMUNS

```
┌─────────────────────────────────────────────────────────────────┐
│ ERRO: "Failed to fetch"                                         │
│ CAUSA: VITE_API_BASE sem https://                               │
│ SOLUÇÃO: Adicione https:// no início da URL                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ ERRO: Telegram não envia                                        │
│ CAUSA: Token ou Chat ID incorreto                               │
│ SOLUÇÃO: Verifique as credenciais, envie /start para o bot     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ ERRO: Banco de dados perdido                                    │
│ CAUSA: Volume não configurado                                   │
│ SOLUÇÃO: Monte volume em /app/data no Railway                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 STATUS ATUAL vs IDEAL

```
ATUAL (11 variáveis):                IDEAL (7 variáveis):
┌─────────────────────────┐         ┌─────────────────────────┐
│ ✅ ENVIRONMENT          │         │ ✅ ENVIRONMENT          │
│ ✅ BYBIT_API_KEY        │         │ ✅ BYBIT_API_KEY        │
│ ✅ BYBIT_API_SECRET     │         │ ✅ BYBIT_API_SECRET     │
│ ✅ GEMINI_API_KEY       │         │ ✅ GEMINI_API_KEY       │
│ ✅ GROQ_API_KEY         │         │ ✅ GROQ_API_KEY         │
│ ⚠️  ALLOW_REAL_TRADING  │         │ ✅ TELEGRAM_TOKEN       │
│ ⚠️  ALLOW_ORDER_EXEC    │         │ ✅ TELEGRAM_CHAT_ID     │
│ ❌ VITE_API_BASE        │         │ ✅ VITE_API_BASE        │
│ ❌ DATABASE_URL         │         └─────────────────────────┘
│ ❌ TELEGRAM (faltando)  │
│ ❓ BINANCE_API_KEY      │
│ ❓ BINANCE_API_SECRET   │
└─────────────────────────┘
```

---

**🚀 TEMPO ESTIMADO: 5 minutos**
**✅ RESULTADO: Sistema 100% funcional**

*Para detalhes completos, veja CORRECOES_RAILWAY.md*
