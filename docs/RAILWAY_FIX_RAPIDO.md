# Guia Rápido - Correção Railway

## 🚨 PROBLEMA PRINCIPAL IDENTIFICADO

Seu `VITE_API_BASE` está **SEM o protocolo HTTPS**!

### ❌ Configuração INCORRETA atual:
```
VITE_API_BASE=ai-sniper-bybit-v5-master-production.up.railway.app
```

### ✅ Configuração CORRETA:
```
VITE_API_BASE=https://ai-sniper-bybit-v5-master-production.up.railway.app
```

## 🔧 AÇÕES IMEDIATAS

### 1. Corrigir VITE_API_BASE (CRÍTICO)

No Railway → Variables → Edite:

```
VITE_API_BASE=https://ai-sniper-bybit-v5-master-production.up.railway.app
```

### 2. Adicionar Telegram

Adicione estas variáveis:

```
TELEGRAM_TOKEN=seu_token_bot
TELEGRAM_CHAT_ID=seu_chat_id
```

### 3. Corrigir DATABASE_URL

**Opção A**: Renomear
```
Remova: DATABASE_URL
Adicione: SQLITE_DB_PATH=/app/data/database.db
```

**Opção B**: Deletar (recomendado)
```
Remova: DATABASE_URL
(sistema usa /app/data/database.db por padrão)
```

### 4. Remover Variáveis Redundantes (Opcional)

Estas já são padrão em `ENVIRONMENT=production`:

```
❌ Remova: ALLOW_REAL_TRADING
❌ Remova: ALLOW_ORDER_EXECUTION
```

### 5. Binance (Se não usa)

Se você NÃO usa Binance:

```
❌ Remova: BINANCE_API_KEY
❌ Remova: BINANCE_API_SECRET
```

## 📋 CONFIGURAÇÃO FINAL

**9 variáveis essenciais:**

```env
ENVIRONMENT=production
BYBIT_API_KEY=***
BYBIT_API_SECRET=***
GEMINI_API_KEY=***
GROQ_API_KEY=***
TELEGRAM_TOKEN=***
TELEGRAM_CHAT_ID=***
VITE_API_BASE=https://ai-sniper-bybit-v5-master-production.up.railway.app
SQLITE_DB_PATH=/app/data/database.db  # opcional
```

## ✅ CHECKLIST PÓS-CORREÇÃO

- [ ] `VITE_API_BASE` começa com `https://`
- [ ] Telegram configurado
- [ ] Volume montado em `/app/data`
- [ ] Variáveis redundantes removidas
- [ ] Redeploy forçado no Railway

## 🚀 APÓS CORREÇÃO

1. Salve todas as alterações no Railway
2. Force um novo deploy
3. Aguarde build completar
4. Acesse o dashboard
5. Verifique logs para confirmar que iniciou sem erros

## 📚 DOCUMENTAÇÃO COMPLETA

Para mais detalhes, veja:
- **[docs/RAILWAY_SETUP.md](RAILWAY_SETUP.md)** - Guia completo
- **README.md** - Instruções gerais

## 🆘 PROBLEMAS?

Execute localmente para validar:
```bash
python validate_environment.py
```
