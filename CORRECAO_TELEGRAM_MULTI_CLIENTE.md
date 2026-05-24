# 🔧 Correção: Telegram + Fechamento Manual + Múltiplos Clientes

## 📋 Problemas Reportados e Soluções

### ❌ Problema 1: Notificações Telegram não chegando

**Causa Raiz:** Mapeamento incorreto dos campos do banco de dados SQLite.

#### 🔍 Diagnóstico
- **Banco de dados SQLite** armazena os campos como:
  - `tg_token` ou `tg_api_key` (Token do bot Telegram)
  - `chat_id` (ID do chat/usuário no Telegram)

- **Código anterior** buscava campos inexistentes:
  - `telegram_token` ou `token_telegram` ❌
  - `telegram_chat_id` ❌

#### ✅ Solução Implementada
Atualizado o arquivo `main_web.py` (linhas 697-699):

```python
# Fallback dinâmico: se .env estiver vazio, busca do dicionário do cliente
# CORREÇÃO: campos corretos do banco são 'tg_token', 'tg_api_key' e 'chat_id'
client_tk = tk or f"{c.get('tg_token') or c.get('tg_api_key') or c.get('telegram_token') or c.get('token_telegram') or ''}".strip()
client_chat = chat or f"{c.get('chat_id') or c.get('telegram_chat_id') or ''}".strip()
```

**Prioridade de leitura:**
1. Variável de ambiente `.env` (`TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`)
2. Campo `tg_token` do banco SQLite
3. Campo `tg_api_key` do banco SQLite (alternativo)
4. Campo `chat_id` do banco SQLite

#### 📝 Como Configurar no Banco de Dados

Ao cadastrar um investidor pela interface web, certifique-se de preencher:
- **Token do Bot**: Campo `tg_token` ou `tg_api_key`
- **Chat ID**: Campo `chat_id`

**Exemplo de payload JSON:**
```json
{
  "nome": "João Silva",
  "bybit_key": "SUA_API_KEY",
  "bybit_secret": "SUA_SECRET_KEY",
  "tg_token": "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz",
  "chat_id": "987654321",
  "saldo_base": 5000.0,
  "status": "ativo"
}
```

---

### ❌ Problema 2: Erro ao Fechar Posições Manualmente

**Causa Raiz:** Não existia endpoint REST para fechar posições via interface web.

#### ✅ Solução Implementada
Adicionado novo endpoint `/api/trade/manual-close` no arquivo `main_web.py` (linhas 838-912).

#### 📡 Como Usar o Endpoint

**URL:** `POST /api/trade/manual-close`

**Payload JSON:**
```json
{
  "symbol": "BTCUSDT:USDT",
  "side": "LONG",
  "client_id": 1  // Opcional - se omitido, fecha para TODOS os clientes
}
```

**Parâmetros:**
- `symbol` (obrigatório): Par de trading (ex: `BTCUSDT:USDT`)
- `side` (obrigatório): Lado da posição a fechar
  - Valores aceitos: `BUY`, `SELL`, `COMPRAR`, `VENDER`, `LONG`, `SHORT`
- `client_id` (opcional): ID do cliente específico
  - Se **não fornecido**: fecha a posição para **TODOS os clientes ativos**
  - Se **fornecido**: fecha apenas para o cliente especificado

**Exemplo de Resposta:**
```json
{
  "success": true,
  "message": "2/2 posições fechadas com sucesso",
  "results": [
    {
      "client_id": 1,
      "client_name": "João Silva",
      "success": true,
      "message": "Posição fechada com sucesso"
    },
    {
      "client_id": 2,
      "client_name": "Maria Santos",
      "success": true,
      "message": "Posição fechada com sucesso"
    }
  ]
}
```

#### 🔧 Exemplo de Uso com cURL

```bash
# Fechar posição LONG de BTC para todos os clientes
curl -X POST http://localhost:5000/api/trade/manual-close \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT:USDT",
    "side": "LONG"
  }'

# Fechar posição SHORT de ETH apenas para o cliente ID 1
curl -X POST http://localhost:5000/api/trade/manual-close \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ETHUSDT:USDT",
    "side": "SHORT",
    "client_id": 1
  }'
```

#### 🎯 O que o Endpoint Faz

1. Valida os parâmetros recebidos
2. Identifica o(s) cliente(s) para fechamento
3. Para cada cliente:
   - Cria conexão com o broker (Bybit/Binance)
   - Executa ordem de fechamento via `close_position_with_sl()`
   - Busca o trade correspondente no banco SQLite
   - Atualiza o status para `closed` com nota "FECHAMENTO MANUAL"
   - Sincroniza o estado de trades ativos
4. Retorna resultado detalhado por cliente

---

### ℹ️ Problema 3: Como Funciona com Múltiplos Clientes?

**Comportamento Atual:** Quando um sinal é disparado pelo robô, **cada cliente cadastrado e ativo** executa **simultaneamente** sua própria ordem.

#### 📊 Exemplo Prático

Você cadastrou 2 clientes:
- **Cliente 1 (João):** Banca de $5.000
- **Cliente 2 (Maria):** Banca de $3.000

**O que acontece quando o robô dispara um sinal de COMPRA em BTCUSDT:**

1. 🔔 **Sinal detectado:** BTC rompeu resistência com 85% de confiança
2. 🔄 **Broadcast global:** `broadcast_ordem_global()` é chamado
3. 🎯 **Processamento por cliente:** `_process_client_orders_background()` processa cada cliente:

   **Cliente 1 (João):**
   - Capital: $5.000
   - Risco: 5% = $250
   - Ordem executada: Compra de BTC com margem de $250
   - Telegram enviado para o `chat_id` de João ✅

   **Cliente 2 (Maria):**
   - Capital: $3.000
   - Risco: 5% = $150
   - Ordem executada: Compra de BTC com margem de $150
   - Telegram enviado para o `chat_id` de Maria ✅

#### 🔑 Pontos Importantes

✅ **Independência:** Cada cliente opera com seu próprio capital e credenciais API
✅ **Simultaneidade:** Todas as ordens são executadas ao mesmo tempo (threads paralelas)
✅ **Isolamento:** Erros em um cliente não afetam os outros
✅ **Notificações individuais:** Cada cliente recebe sua própria notificação no Telegram
✅ **Gestão de risco separada:** Cada cliente usa 5% do **seu próprio** capital

#### ⚙️ Configuração de Risco por Cliente

O cálculo de quantidade por ordem está em `_calculate_dynamic_order_quantity()`:

```python
# Cada cliente arrisca 5% da sua banca
margem = banca * 0.05  # Ex: $5.000 * 0.05 = $250
```

Se você quiser ajustar o percentual de risco:
- Edite o valor `0.05` (5%) para `0.10` (10%), `0.02` (2%), etc.
- Ou crie uma configuração por cliente no banco de dados

---

## 🧪 Como Testar as Correções

### 1️⃣ Testar Notificações Telegram

1. Cadastre um cliente com `tg_token` e `chat_id` válidos
2. Force uma entrada manual via `/api/trade/manual-entry`:
   ```bash
   curl -X POST http://localhost:5000/api/trade/manual-entry \
     -H "Content-Type: application/json" \
     -d '{
       "symbol": "BTCUSDT:USDT",
       "side": "BUY",
       "force_execute": true
     }'
   ```
3. Verifique o console para logs:
   ```
   ✅ [TELEGRAM] Notificação enviada com sucesso para João Silva (chat_id: 987654321)
   ```
4. Confirme que a mensagem chegou no Telegram

### 2️⃣ Testar Fechamento Manual

1. Abra uma posição (via entrada manual ou sinal automático)
2. Feche a posição:
   ```bash
   curl -X POST http://localhost:5000/api/trade/manual-close \
     -H "Content-Type: application/json" \
     -d '{
       "symbol": "BTCUSDT:USDT",
       "side": "LONG"
     }'
   ```
3. Verifique no console:
   ```
   ✅ [MANUAL CLOSE] Posição BTCUSDT:USDT fechada para João Silva
   ```
4. Confirme na interface web que o trade foi marcado como `closed`

### 3️⃣ Testar Múltiplos Clientes

1. Cadastre 2 ou mais clientes com credenciais válidas
2. Ative todos os clientes (`status: "ativo"`)
3. Force uma entrada manual
4. Verifique que:
   - Cada cliente executou sua própria ordem na Bybit
   - Cada cliente recebeu notificação no seu Telegram
   - As quantidades foram calculadas proporcionalmente à banca de cada um

---

## 🔍 Logs de Depuração

Todos os logs importantes agora incluem `flush=True` para saída imediata:

```python
✅ [TELEGRAM] Notificação enviada com sucesso para João Silva (chat_id: 987654321)
❌ [TELEGRAM ERROR] Falha ao enviar notificação para Maria Santos: HTTPError 401 Unauthorized
⚠️ [CLIENT ERROR] Falha ao processar ordem para cliente Pedro: Insufficient balance
❌ [PROCESS ERROR] Erro geral no processamento de ordens: KeyError 'symbol'
✅ [MANUAL CLOSE] Posição BTCUSDT:USDT fechada para João Silva
❌ [MANUAL CLOSE ERROR] Erro ao fechar para Maria: No open position found
```

---

## 📚 Arquivos Modificados

- `main_web.py`:
  - Linhas 697-699: Correção do mapeamento Telegram
  - Linhas 838-912: Novo endpoint `/api/trade/manual-close`

---

## 🎉 Resumo das Melhorias

| Problema | Status | Solução |
|----------|--------|---------|
| Telegram não envia | ✅ Corrigido | Mapeamento correto dos campos SQLite |
| Erro ao fechar manual | ✅ Corrigido | Endpoint `/api/trade/manual-close` adicionado |
| Dúvida múltiplos clientes | ℹ️ Documentado | Cada cliente opera independentemente |

---

## 🚀 Próximos Passos

1. Teste as correções em ambiente de desenvolvimento
2. Valide que as notificações Telegram chegam corretamente
3. Confirme que o fechamento manual funciona via API
4. Monitore os logs para identificar possíveis novos erros
5. Se tudo estiver OK, faça deploy em produção

---

**Versão:** 1.0
**Data:** 2026-05-24
**Autor:** Claude Sonnet 4.5
