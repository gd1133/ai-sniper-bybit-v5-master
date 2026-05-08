# 📊 Configuração Binance - AI Sniper Bot

## 🎯 Visão Geral

O **AI Sniper Bot** agora suporta completamente a **Binance Futures (USDM)**, permitindo que você opere tanto na Bybit quanto na Binance com a mesma interface e funcionalidades.

### Características Principais

✅ **Suporte Completo Binance Futures**
- Binance Futures Testnet (para testes)
- Binance Futures Real (conta de produção)
- Interface idêntica ao Bybit para troca transparente

✅ **Stop Loss Atualizado**
- **-50% de margem** (-5% de preço com alavancagem 10x)
- **+100% de margem** (+10% de preço) para Take Profit
- Proteção automática em todas as operações

✅ **Multi-Exchange**
- Suporte a múltiplas contas (Bybit + Binance)
- Troca fácil entre exchanges no dashboard
- Configuração independente por cliente

---

## 🔐 Como Obter Chaves API da Binance

### 1. Acesse sua conta Binance

- **Testnet**: https://testnet.binancefuture.com
- **Real**: https://www.binance.com

### 2. Crie uma API Key

1. Vá em **Perfil** → **API Management**
2. Clique em **Create API**
3. Escolha um nome para sua API Key
4. Complete a verificação de segurança (2FA)

### 3. Configure as Permissões

⚠️ **IMPORTANTE**: Configure as permissões corretas:

- ✅ **Enable Reading** (Obrigatório)
- ✅ **Enable Spot & Margin Trading** (Obrigatório)
- ✅ **Enable Futures** (Obrigatório)
- ❌ **Disable Withdrawals** (Por segurança)

### 4. Restrinja por IP (Opcional mas Recomendado)

- Configure os IPs permitidos para maior segurança
- Se usar Railway/Render, pode precisar deixar irrestrito (não recomendado)

### 5. Salve suas Chaves

```
API Key: sua_api_key_aqui
Secret Key: sua_secret_key_aqui
```

⚠️ **NUNCA COMPARTILHE** suas chaves com ninguém!

---

## 🖥️ Configuração no Dashboard

### Passo 1: Acesse o Dashboard

Abra o dashboard web do AI Sniper Bot.

### Passo 2: Cadastre um Novo Cliente

1. Clique em **"Adicionar Cliente"**
2. Preencha o nome do cliente

### Passo 3: Selecione a Exchange

Você verá dois botões:

- 🟡 **Bybit** - Para usar Bybit
- 🟠 **Binance** - Para usar Binance Futures

Clique em **🟠 Binance**.

### Passo 4: Selecione o Modo da Conta

- **TESTNET** - Para testes (use chaves da testnet.binancefuture.com)
- **REAL** - Para conta real (use chaves da binance.com)

### Passo 5: Insira as Credenciais

```
API Key: Cole sua Binance API Key
API Secret: Cole sua Binance Secret Key
```

### Passo 6: Valide e Salve

Clique em **"Validar e Salvar"**. O sistema irá:

1. ✅ Validar conectividade com Binance
2. ✅ Verificar autenticação
3. ✅ Confirmar saldo USDT
4. ✅ Salvar configuração

Se tudo estiver correto, você verá: **"Conta Binance TESTNET/REAL validada OK"**

---

## 📋 Configurações de Risco (Atualizadas)

### Stop Loss: -50% de Margem

Com alavancagem de 10x:
- **-5% de preço** = **-50% da margem**
- Exemplo: Entrada em $2000, SL em $1900

### Take Profit: +100% de Margem

Com alavancagem de 10x:
- **+10% de preço** = **+100% de margem** (dobro do investimento)
- Exemplo: Entrada em $2000, TP em $2200

### Alavancagem

- **10x** (fixa)
- **Modo: Cross Margin**

### Gestão de Entrada

- **5% do saldo** após operações com lucro
- **3% do saldo** após Stop Loss (redução de risco)
- Retorna a 5% na primeira operação com lucro

---

## 🔄 Diferenças entre Bybit e Binance

### Bybit
- API mais simples
- Menor latência em alguns casos
- Interface mais amigável

### Binance
- Maior liquidez
- Mais pares disponíveis
- Spread geralmente menor

### No AI Sniper Bot

**Ambas funcionam de forma idêntica!**
- Mesma lógica de trading
- Mesmos indicadores (Triple Brain)
- Mesma proteção de risco
- Mesma interface de dashboard

---

## 🛠️ Resolução de Problemas

### Erro: "Chave API Binance inválida"

**Causas comuns:**

1. ✗ Chave copiada incorretamente
2. ✗ Permissões de Futures não habilitadas
3. ✗ Usando chaves de Testnet em modo Real (ou vice-versa)
4. ✗ Restrição de IP bloqueando

**Solução:**
- Verifique se copiou as chaves completas
- Confirme que Futures está habilitado na API
- Use chaves de Testnet apenas em modo TESTNET
- Verifique restrições de IP

### Erro: "Erro ao criar ordem"

**Causas comuns:**

1. ✗ Saldo USDT insuficiente
2. ✗ Par não disponível em Futures
3. ✗ Posição já aberta no par

**Solução:**
- Verifique seu saldo USDT em Futures
- Certifique-se de que está usando pares USDT Perpetual
- Feche posições existentes antes de abrir novas

### Erro: "Rate limit excedido"

**Causa:**
- Muitas requisições em curto período

**Solução:**
- O sistema tem rate limiting automático
- Aguarde alguns segundos
- Se persistir, reinicie o bot

---

## 🔒 Segurança

### Boas Práticas

1. ✅ **Use 2FA** na sua conta Binance
2. ✅ **Restrinja IPs** sempre que possível
3. ✅ **Desabilite Withdrawals** na API Key
4. ✅ **Use Testnet** antes de operar em Real
5. ✅ **Monitore regularmente** suas operações
6. ✅ **Nunca compartilhe** suas chaves

### Armazenamento de Chaves

- As chaves são armazenadas criptografadas no banco de dados
- Nunca exponha suas chaves em logs ou código
- Use variáveis de ambiente para configurações sensíveis

---

## 📊 Monitoramento

### Dashboard

O dashboard mostra:

- 🟠 **Badge laranja** para contas Binance
- 🟡 **Badge amarelo** para contas Bybit
- Status da conta (Testnet/Real)
- Saldo disponível
- Posições abertas
- Histórico de trades

### Sinais

Quando o bot detecta uma oportunidade:

1. 📊 **Análise Triple Brain** (3 IAs analisam)
2. 🎯 **Confiança ≥ 60%** necessária
3. ✅ **Confluências aprovadas**
4. 🔥 **Ordem executada** automaticamente
5. 🛡️ **TP/SL aplicados** imediatamente

---

## 🚀 Começando a Operar

### Modo Testnet (Recomendado primeiro)

1. Crie conta em https://testnet.binancefuture.com
2. Obtenha fundos de teste (testnet faucet)
3. Crie API Keys na testnet
4. Configure cliente no dashboard (modo TESTNET)
5. Ative o bot e monitore

### Modo Real (Após testar)

1. Use sua conta Binance real
2. Deposite USDT em Futures Wallet
3. Crie API Keys com permissões corretas
4. Configure cliente no dashboard (modo REAL)
5. **Comece com valores pequenos**
6. Monitore de perto os primeiros trades

---

## 📞 Suporte

### Recursos

- **Documentação Completa**: `/docs/DOCUMENTACAO_COMPLETA.md`
- **GitHub**: Issues e Pull Requests
- **Logs**: Monitore os logs do sistema para debug

### Informações de Debug

Se tiver problemas, verifique:

```bash
# Logs do sistema
tail -f logs/ai_sniper.log

# Status do bot
curl http://localhost:5000/api/health

# Clientes configurados
curl http://localhost:5000/api/clientes
```

---

## ✨ Novidades nesta Versão

### Stop Loss Otimizado

- ✅ **-50% de margem** (anteriormente -30%)
- ✅ Melhor gestão de risco
- ✅ Proteção automática em Bybit + Binance

### Dependências Atualizadas

**Python:**
- ccxt 4.6.8 (atualizado)
- flask 3.1.0 (atualizado)
- flask-cors 5.0.0 (atualizado)
- requests 2.32.3 (atualizado)
- httpx 0.28.1 (atualizado)
- gunicorn 23.0.0 (atualizado)

**Node.js:**
- Vite 6.0.3 (atualizado)
- React 18.3.1 (atualizado)
- Lucide React 0.460.0 (atualizado)
- Recharts 2.13.3 (atualizado)

---

## 📝 Changelog

### v60.7 - 2026-05-08

✅ **Stop Loss atualizado para -50% de margem**
- Anteriormente -30% de margem (-3% de preço)
- Agora -50% de margem (-5% de preço)
- Aplicado em Bybit e Binance

✅ **Dependências atualizadas**
- Todas as bibliotecas Python e Node.js atualizadas
- Melhor segurança e performance
- Compatibilidade com versões mais recentes

✅ **Documentação Binance**
- Guia completo de configuração
- Passo a passo detalhado
- Resolução de problemas

---

## 🎓 Conclusão

Agora você está pronto para operar com **Binance Futures** no **AI Sniper Bot**!

**Lembre-se:**
1. ✅ Sempre teste em Testnet primeiro
2. ✅ Comece com valores pequenos
3. ✅ Monitore regularmente
4. ✅ Nunca arrisque mais do que pode perder
5. ✅ Mantenha suas chaves seguras

**Boas operações! 🚀📈**
