# Guia Rápido: Configurar Railway para Salvar Clientes

## 🚨 Problema
Frontend salva o cliente mas não chega no servidor/banco de dados Railway.

## ✅ Solução: 3 Passos Simples

### PASSO 1: Configurar Variáveis de Ambiente no Railway

Acesse seu projeto no Railway > Clique no serviço > Aba "Variables"

**COPIE E COLE estas variáveis** (substitua os valores com os seus):

```bash
# ====================================
# CONEXÃO FRONTEND ⚠️ MAIS IMPORTANTE
# ====================================
VITE_API_BASE=https://SEU-PROJETO.up.railway.app
# ⚠️ IMPORTANTE: Troque SEU-PROJETO pela URL real do seu Railway!
# ⚠️ DEVE incluir https:// no início!

# ====================================
# AMBIENTE E EXECUÇÃO
# ====================================
ENVIRONMENT=production
ALLOW_ORDER_EXECUTION=true
ALLOW_REAL_TRADING=true

# ====================================
# BANCO DE DADOS
# ====================================
SQLITE_DB_PATH=/app/data/database.db

# ====================================
# BYBIT (se usar Bybit)
# ====================================
BYBIT_API_KEY=SUA_CHAVE_BYBIT
BYBIT_API_SECRET=SEU_SECRET_BYBIT

# ====================================
# BINANCE (se usar Binance) - OPCIONAL
# ====================================
BINANCE_API_KEY=SUA_CHAVE_BINANCE
BINANCE_API_SECRET=SEU_SECRET_BINANCE

# ====================================
# INTELIGÊNCIA ARTIFICIAL
# ====================================
GEMINI_API_KEY=SUA_CHAVE_GEMINI
GROQ_API_KEY=SUA_CHAVE_GROQ

# ====================================
# TELEGRAM (Opcional)
# ====================================
TELEGRAM_TOKEN=SEU_BOT_TOKEN
TELEGRAM_CHAT_ID=SEU_CHAT_ID

# ====================================
# 2FA (deixe vazio para desabilitar)
# ====================================
TOTP_SECRET=
TOTP_CODE=
```

### PASSO 2: Configurar Volume (Para Persistir o Banco de Dados)

No Railway:
1. Clique no seu serviço
2. Vá na aba "Volumes"
3. Clique "+ New Volume"
4. Configure:
   - **Mount Path**: `/app/data`
   - **Size**: 1GB
5. Clique "Add"

### PASSO 3: Reiniciar o Serviço

1. Clique nos 3 pontinhos (...) do serviço
2. Clique "Restart"
3. Aguarde o deploy terminar

---

## 🔍 Como Verificar se Funcionou

### 1. Abrir Console do Navegador

1. Abra seu dashboard no navegador
2. Pressione **F12** para abrir DevTools
3. Vá na aba "Console"

### 2. Tentar Salvar um Cliente

1. Vá na aba "GESTÃO"
2. Clique "+ Novo Investidor"
3. Preencha os dados:
   - Nome: "Teste Railway"
   - Selecione a corretora (Bybit ou Binance)
   - Coloque suas API Keys da exchange
4. Clique "Guardar Investidor"

### 3. Verificar Logs no Console

**✅ Se funcionou, você verá:**

```
🔵 [FRONTEND] Iniciando salvamento do cliente: {nome: "Teste Railway", exchange: "bybit", api_base: "https://..."}
🔵 [FRONTEND] Criando novo cliente via /api/vincular_cliente
🔵 [FRONTEND] Resposta do servidor (POST): 200 OK
✅ [FRONTEND] Cliente criado com sucesso: {id: 1, nome: "Teste Railway", ...}
```

E o cliente aparecerá na tabela de investidores!

**❌ Se NÃO funcionou, você verá:**

```
❌ [FRONTEND] Erro de rede ou exceção ao vincular: Failed to fetch
❌ [FRONTEND] Erro de conexão: ... Verifique se o servidor está acessível em https://...
```

### 4. Verificar Logs do Railway

No painel do Railway:
1. Clique no seu serviço
2. Vá na aba "Logs"
3. Procure por:

**✅ Sucesso:**
```
🔵 [BACKEND] Recebida requisição POST /api/vincular_cliente
🔵 [DATABASE] add_client: Iniciando inserção de cliente: Teste Railway
✅ [DATABASE] add_client: Cliente inserido com sucesso! ID: 1
✅ [BACKEND] Cliente salvo com ID: 1
```

**❌ Erro:**
```
❌ [BACKEND] Exceção ao processar vincular_cliente: ...
❌ [DATABASE] add_client: Erro ao adicionar cliente: ...
```

---

## 🔥 Problemas Comuns

### ❌ "Failed to fetch" no Console

**Causa**: Frontend não consegue acessar o backend

**Solução**:
- ✅ Verifique se `VITE_API_BASE` está correto
- ✅ Certifique-se de incluir `https://` no início
- ✅ Teste abrir a URL no navegador: `https://seu-projeto.up.railway.app/api/status`
- ✅ Se não abrir, o serviço não está rodando - verifique os logs do Railway

### ❌ Cliente salva mas não aparece na lista

**Causa**: Banco de dados sem persistência (volume não configurado)

**Solução**:
- ✅ Configure o volume (Passo 2 acima)
- ✅ Certifique-se que `SQLITE_DB_PATH=/app/data/database.db`
- ✅ Reinicie o serviço após adicionar o volume

### ❌ "Salvo, mas API inválida"

**Causa**: Chaves da exchange incorretas

**Solução**:
- ✅ Verifique se copiou as chaves corretamente (sem espaços extras)
- ✅ Certifique-se de usar chaves da conta REAL (não testnet)
- ✅ Verifique permissões da API Key:
  - **Bybit**: "Read Position" + "Trade Orders"
  - **Binance**: "Enable Futures" + "Enable Reading"
- ✅ Certifique-se de que a chave não está expirada

### ❌ Erro 500 ou 400 ao salvar

**Causa**: Erro no backend

**Solução**:
- ✅ Verifique os logs do Railway (aba "Logs")
- ✅ Procure por linhas com `❌ [BACKEND]` ou `❌ [DATABASE]`
- ✅ O erro mostrará exatamente o problema

---

## 📋 Checklist Rápido

Antes de testar, certifique-se de que:

- [ ] `VITE_API_BASE` configurado com `https://` e URL correta
- [ ] `ENVIRONMENT=production`
- [ ] `ALLOW_ORDER_EXECUTION=true`
- [ ] `ALLOW_REAL_TRADING=true`
- [ ] Credenciais da exchange configuradas (Bybit ou Binance)
- [ ] Gemini e Groq API keys configuradas
- [ ] `SQLITE_DB_PATH=/app/data/database.db`
- [ ] Volume montado em `/app/data`
- [ ] Serviço reiniciado após configurar tudo

---

## 🆘 Ainda Não Funcionou?

Se seguiu todos os passos e ainda não funciona:

1. **Capture os Logs**:
   - Console do navegador (F12 > Console) - copie tudo
   - Logs do Railway - copie as últimas 50 linhas

2. **Compartilhe os Logs**:
   - Remova dados sensíveis (API Keys, Secrets)
   - Compartilhe para análise

3. **Verifique**:
   - URL do Railway está correta?
   - Serviço está rodando (não crashed)?
   - Deploy completou com sucesso?

---

## 📚 Documentação Completa

Para mais detalhes técnicos, veja:
- `docs/RAILWAY_FRONTEND_FIX.md` - Documentação técnica completa
- `docs/RAILWAY_SETUP.md` - Setup geral do Railway
- `.env.example` - Exemplo de todas as variáveis disponíveis

---

## ✅ Resumo

1. Configure `VITE_API_BASE` com `https://` e sua URL do Railway
2. Configure volume em `/app/data`
3. Configure as outras variáveis de ambiente
4. Reinicie o serviço
5. Teste salvando um cliente
6. Verifique os logs (console do navegador + Railway)

Se os logs mostram `✅` em verde, está funcionando! 🎉
