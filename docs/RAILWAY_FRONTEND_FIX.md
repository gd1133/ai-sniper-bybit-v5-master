# Fix: Frontend Save Issue - Railway Configuration

## Problema Identificado

O frontend está salvando dados do cliente mas não está conseguindo se comunicar corretamente com o servidor no Railway. Este documento fornece as configurações necessárias para resolver o problema.

## Diagnóstico Adicionado

Foram adicionados logs completos em todo o fluxo de salvamento para facilitar o diagnóstico:

### Frontend (main.jsx)
- ✅ Logs de início de salvamento
- ✅ Logs de requisição HTTP (POST/PUT)
- ✅ Logs de resposta do servidor
- ✅ Logs de sucesso/erro
- ✅ Mensagens de erro detalhadas incluindo URL da API

### Backend (main_web.py)
- ✅ Logs ao receber requisição
- ✅ Logs durante validação
- ✅ Logs ao salvar no banco
- ✅ Logs de sucesso/erro com stack trace

### Database (src/database/manager.py)
- ✅ Logs ao inserir cliente
- ✅ Logs de ID gerado
- ✅ Logs de erro com stack trace

## Configuração de Variáveis de Ambiente no Railway

### 1. Variáveis OBRIGATÓRIAS para o Frontend se comunicar com o Backend

```bash
# URL da API - IMPORTANTE: Deve incluir o protocolo https://
VITE_API_BASE=https://seu-projeto.up.railway.app

# Ambiente de produção
ENVIRONMENT=production

# Habilitar execução de ordens reais
ALLOW_ORDER_EXECUTION=true
ALLOW_REAL_TRADING=true
```

### 2. Credenciais da Exchange (Bybit ou Binance)

```bash
# Credenciais Bybit (se usar Bybit)
BYBIT_API_KEY=sua_chave_api_bybit
BYBIT_API_SECRET=seu_secret_api_bybit

# Credenciais Binance (se usar Binance) - OPCIONAL
BINANCE_API_KEY=sua_chave_api_binance
BINANCE_API_SECRET=seu_secret_api_binance
```

### 3. Inteligência Artificial

```bash
# Gemini API (Google)
GEMINI_API_KEY=sua_chave_gemini

# Groq API
GROQ_API_KEY=sua_chave_groq
```

### 4. Notificações Telegram (Opcional)

```bash
TELEGRAM_TOKEN=seu_bot_token
TELEGRAM_CHAT_ID=seu_chat_id
```

### 5. Banco de Dados SQLite

```bash
# Caminho do banco de dados SQLite
SQLITE_DB_PATH=/app/data/database.db
```

### 6. Autenticação 2FA (Opcional - apenas se configurado)

```bash
# Deixe em branco para desabilitar 2FA no Railway
TOTP_SECRET=
TOTP_CODE=
```

## Configuração do Volume no Railway

O Railway precisa de um volume persistente para o banco de dados SQLite:

1. No painel do Railway, vá em seu serviço
2. Clique em "Volumes"
3. Adicione um novo volume:
   - **Mount Path**: `/app/data`
   - **Size**: 1GB (ou mais, conforme necessário)

## Verificação da Configuração

### 1. Verificar URL da API no Frontend

O frontend deve estar acessando a URL correta. Verifique no console do navegador:

```javascript
// Deve aparecer algo como:
Dashboard Iniciado - Conectando em: https://seu-projeto.up.railway.app
```

### 2. Verificar Logs do Backend

No Railway, verifique os logs do serviço. Quando você tenta salvar um cliente, deve aparecer:

```
🔵 [BACKEND] Recebida requisição POST /api/vincular_cliente
🔵 [BACKEND] Dados recebidos: nome=Cliente Teste, exchange=bybit
🔵 [BACKEND] Iniciando validação para modo: real
🔵 [BACKEND] _save_client_everywhere: payload id=None, nome=Cliente Teste
🔵 [DATABASE] add_client: Iniciando inserção de cliente: Cliente Teste
🔵 [DATABASE] add_client: Novo cliente sem ID, gerando automaticamente
✅ [DATABASE] add_client: Cliente inserido com sucesso! ID: 1
✅ [BACKEND] Cliente salvo com ID: 1
✅ [BACKEND] Enviando resposta de sucesso ao frontend
```

### 3. Verificar Logs do Frontend

No console do navegador (F12 > Console), deve aparecer:

```
🔵 [FRONTEND] Iniciando salvamento do cliente: {nome: "Cliente Teste", exchange: "bybit", api_base: "https://..."}
🔵 [FRONTEND] Criando novo cliente via /api/vincular_cliente
🔵 [FRONTEND] Resposta do servidor (POST): 200 OK
🔵 [FRONTEND] JSON recebido (POST): {status: "sucesso", ...}
✅ [FRONTEND] Cliente criado com sucesso: {id: 1, nome: "Cliente Teste", ...}
```

## Problemas Comuns e Soluções

### ❌ Erro: "Failed to fetch" ou "Network Error"

**Causa**: Frontend não consegue conectar ao backend

**Solução**:
1. Verifique se `VITE_API_BASE` está configurado com `https://` no início
2. Verifique se a URL está correta (deve ser a URL do seu projeto no Railway)
3. Verifique se o serviço está rodando no Railway

### ❌ Erro: "Erro de conexão: TypeError: Failed to fetch"

**Causa**: CORS ou URL inválida

**Solução**:
1. Certifique-se de que o backend está rodando
2. Verifique se CORS está habilitado no Flask (já está configurado com `flask-cors`)
3. Teste a URL da API diretamente no navegador: `https://seu-projeto.up.railway.app/api/status`

### ❌ Cliente salva mas não aparece na lista

**Causa**: Banco de dados sem persistência

**Solução**:
1. Configure o volume no Railway (veja seção acima)
2. Certifique-se de que `SQLITE_DB_PATH=/app/data/database.db`
3. Reinicie o serviço após adicionar o volume

### ❌ "Salvo, mas API inválida"

**Causa**: Credenciais da exchange incorretas ou expiradas

**Solução**:
1. Verifique se as chaves API estão corretas
2. Verifique se a chave não está expirada
3. Certifique-se de que está usando chaves da conta REAL (não testnet)
4. Verifique as permissões da API Key:
   - Bybit: "Read Position" + "Trade Orders"
   - Binance: "Enable Futures" + "Enable Reading"

### ❌ Erro 500 ao salvar

**Causa**: Erro no backend ou banco de dados

**Solução**:
1. Verifique os logs do Railway
2. Procure por mensagens com `❌ [BACKEND]` ou `❌ [DATABASE]`
3. O stack trace completo ajudará a identificar o problema

## Testando a Configuração

### 1. Teste de Conectividade

Abra o console do navegador e execute:

```javascript
fetch('https://seu-projeto.up.railway.app/api/status')
  .then(r => r.json())
  .then(console.log)
  .catch(console.error);
```

Deve retornar os dados do status do sistema.

### 2. Teste de Salvamento

1. Acesse a aba "GESTÃO" no dashboard
2. Clique em "+ Novo Investidor"
3. Preencha os dados:
   - Nome: "Teste Railway"
   - API Key e Secret da exchange
   - (Opcional) Token e Chat ID do Telegram
4. Clique em "Guardar Investidor"
5. Observe o console do navegador (F12) e os logs do Railway

### 3. Verificar Logs

**Frontend (Console do Navegador)**:
- Deve mostrar `🔵 [FRONTEND]` logs
- Deve mostrar `✅ [FRONTEND]` em caso de sucesso
- Deve mostrar `❌ [FRONTEND]` em caso de erro

**Backend (Railway Logs)**:
- Deve mostrar `🔵 [BACKEND]` logs
- Deve mostrar `✅ [BACKEND]` em caso de sucesso
- Deve mostrar `❌ [BACKEND]` em caso de erro

## Comandos Úteis para Diagnóstico

### Verificar Variáveis de Ambiente

No Railway CLI ou no painel web, verifique se todas as variáveis estão configuradas:

```bash
railway vars
```

### Ver Logs em Tempo Real

```bash
railway logs
```

### Reiniciar Serviço

Após alterar variáveis de ambiente:

```bash
railway up --detach
```

## Checklist de Configuração

- [ ] `VITE_API_BASE` configurado com `https://` e URL correta
- [ ] `ENVIRONMENT=production`
- [ ] `ALLOW_ORDER_EXECUTION=true`
- [ ] `ALLOW_REAL_TRADING=true`
- [ ] Credenciais da exchange configuradas (Bybit ou Binance)
- [ ] Gemini e Groq API keys configuradas
- [ ] `SQLITE_DB_PATH=/app/data/database.db`
- [ ] Volume montado em `/app/data` no Railway
- [ ] Serviço reiniciado após configurar variáveis
- [ ] Logs do frontend mostram conexão bem-sucedida
- [ ] Logs do backend mostram salvamento bem-sucedido
- [ ] Cliente aparece na lista após salvar

## Suporte Adicional

Se o problema persistir após seguir este guia:

1. Capture os logs completos:
   - Console do navegador (F12 > Console)
   - Logs do Railway
2. Verifique se há mensagens de erro específicas
3. Compartilhe os logs (remova dados sensíveis como API keys)

## Referências

- Railway Documentation: https://docs.railway.app/
- Flask-CORS: https://flask-cors.readthedocs.io/
- Vite Environment Variables: https://vitejs.dev/guide/env-and-mode.html
