# Guia Completo: Configurar Binance no Motor Sniper v60.7

## 🎯 Por que usar Binance em vez de Bybit?

A **Binance permite API sem restrição de IP**, enquanto a Bybit **obriga** você a configurar whitelist de IPs em contas de produção.

### Comparação Rápida

| Característica | Bybit | Binance |
|---------------|-------|---------|
| **IP Whitelist obrigatório** | ✅ Sim (produção) | ❌ Não (opcional) |
| **"Sem restrição de IP"** | ❌ Não permitido | ✅ Permitido |
| **Suporte no robô** | ✅ Completo | ✅ Completo |
| **Testnet disponível** | ✅ Sim | ✅ Sim |
| **Futures USDT** | ✅ Linear/USDT | ✅ USDⓈ-M |

---

## 📋 Passo a Passo Completo

### **1. Criar API Keys na Binance Futures**

1. **Acesse a Binance:**
   - URL: https://www.binance.com/en/my/settings/api-management
   - Faça login na sua conta

2. **Crie uma Nova API Key:**
   - Clique em **"Create API"**
   - Escolha **"System generated"**
   - Preencha um nome/label (ex: "Motor Sniper Bot")
   - Complete a verificação 2FA

3. **Configure as Permissões:**
   - ✅ **Enable Futures** ← OBRIGATÓRIO
   - ✅ **Enable Reading** ← Recomendado
   - ❌ **Enable Spot & Margin Trading** ← Desativado (não precisa)
   - ❌ **Enable Withdrawals** ← NUNCA ATIVE (segurança)

4. **IP Whitelist:**
   - Selecione **"Unrestricted (Less Secure)"**
   - OU adicione o IP do Railway (se souber)
   - **Importante:** A Binance PERMITE "sem restrição", ao contrário da Bybit

5. **Salve as Chaves:**
   - **API Key:** `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   - **Secret Key:** `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   - ⚠️ **NUNCA compartilhe essas chaves!**

---

### **2. Adicionar Variáveis de Ambiente (Opcional)**

No **Railway**, adicione estas variáveis (opcional, mas útil para testes globais):

```env
BINANCE_API_KEY=sua_chave_api_binance
BINANCE_API_SECRET=seu_secret_binance
```

**Nota:** Estas variáveis são opcionais. As credenciais podem ser configuradas por cliente na dashboard.

---

### **3. Configurar Cliente na Dashboard**

#### **3.1. Acessar o Painel de Gestão**

1. Acesse o robô: `https://ai-sniper-bybit-v5-master-master.up.railway.app`
2. Clique na aba **"GESTÃO"** (ícone de usuários)

#### **3.2. Cadastrar Novo Cliente (ou Editar Existente)**

Preencha os campos:

- **Nome:** Seu nome ou identificador
- **Exchange:** Selecione **"BINANCE"** ⚠️ (NÃO Bybit!)
- **Account Mode:** Selecione **"REAL"** ⚠️ (NÃO testnet!)
- **API Key (Bybit Key):** Cole sua **Binance API Key**
- **API Secret (Bybit Secret):** Cole sua **Binance API Secret**
- **Saldo Base:** Defina o saldo inicial (ex: `1000` para 1000 USDT)
- **Status:** Marque como **ATIVO**
- **Telegram (Opcional):**
  - Token do Bot
  - Chat ID

**Importante:** Mesmo que os campos sejam rotulados como "Bybit Key/Secret", eles são usados para AMBAS as exchanges (Bybit e Binance).

#### **3.3. Salvar o Cliente**

Clique em **"SALVAR"** ou **"ATUALIZAR"**

---

### **4. Verificar se Está Funcionando**

#### **4.1. Logs do Backend**

Ao iniciar/conectar, você deve ver:

```
🔍 [BINANCE ENDPOINT] testnet=False mode=REAL
```

Se aparecer `mode=REAL`, está correto!

#### **4.2. Dashboard - Badge da Exchange**

No painel de gestão, o cliente deve mostrar um badge **LARANJA** escrito **"BINANCE"**.

Se mostrar badge **AMARELO** escrito **"BYBIT"**, o cliente está configurado errado.

#### **4.3. Quando uma Ordem For Executada**

Nos logs, você deve ver:

```
🚀 [EXECUÇÃO REAL] SeuNome - buy 0.1234 TONUSDT
✅ [ORDEM EXECUTADA] ID: 12345678
```

No **Binance Futures**, acesse:
- https://www.binance.com/en/futures/BTCUSDT
- Aba **"Order History"** ou **"Position History"**
- Você deve ver as ordens do robô

---

## 🔧 Solução de Problemas

### **Erro: "API key does not exist"**

- Verifique se copiou a API Key corretamente (sem espaços)
- Certifique-se de que a chave foi criada para **Binance Futures**

### **Erro: "Signature invalid"**

- Verifique se o Secret está correto
- Confirme que o **horário do servidor** está sincronizado (o robô usa `adjustForTimeDifference: true`)

### **Erro: "IP not whitelisted"**

- Se você configurou IP whitelist na Binance, adicione o IP do Railway
- **Recomendação:** Use "Unrestricted" para evitar problemas

### **Ordem não aparece na Binance**

1. Verifique se o modo de operação está em **"REAL"** (não "PAPER" ou "TESTNET")
2. Confirme que `ENVIRONMENT=production` no Railway
3. Verifique se `ALLOW_ORDER_EXECUTION=true` e `ALLOW_REAL_TRADING=true`

### **Cliente está usando Bybit em vez de Binance**

- Verifique se o campo **"Exchange"** está marcado como **"BINANCE"**
- Edite o cliente e salve novamente
- Reinicie o robô se necessário

---

## 🚀 Modo Testnet da Binance (Opcional)

Se quiser testar sem usar dinheiro real:

1. **Acesse o Binance Testnet:**
   - URL: https://testnet.binancefuture.com
   - Faça login (use uma conta separada)

2. **Crie API Keys de Testnet**

3. **Configure um cliente:**
   - **Exchange:** BINANCE
   - **Account Mode:** TESTNET
   - **API Keys:** Use as chaves do testnet

O robô conectará em `https://testnet.binancefuture.com` automaticamente.

---

## ⚠️ Avisos de Segurança

1. **NUNCA ative "Enable Withdrawals"** nas permissões da API
2. **Use IP whitelist** se possível (mais seguro que "unrestricted")
3. **Comece com saldo pequeno** até confirmar que está funcionando
4. **Monitore as primeiras operações** de perto
5. **Verifique Stop Loss e Take Profit** antes de deixar o robô operando sozinho

---

## 📊 Configurações de Risco Atuais do Robô

- **Entrada por trade:** 5% do saldo base
- **Take Profit:** +100% (dobro do lucro)
- **Stop Loss:** -5% do preço de entrada (50% da margem com 10x leverage)
- **Max moedas ativas:** 1 trade por vez (modo conservador)
- **Cooldown:** 10 minutos após fechamento

---

## 🆘 Suporte

Se ainda tiver problemas:

1. Verifique os logs do Railway
2. Confirme que todas as variáveis de ambiente estão corretas
3. Teste primeiro com **testnet** da Binance
4. Verifique se o cliente está com **Status: ATIVO**

---

## 📝 Resumo Rápido

```bash
# 1. Criar API na Binance Futures
#    - Enable Futures: ✅
#    - Enable Reading: ✅
#    - IP: Unrestricted

# 2. Railway Environment Variables
ENVIRONMENT=production
ALLOW_ORDER_EXECUTION=true
ALLOW_REAL_TRADING=true

# 3. Dashboard - Cadastrar Cliente
Exchange: BINANCE
Account Mode: REAL
API Key: [sua chave Binance]
API Secret: [seu secret Binance]
Status: ATIVO

# 4. Verificar
Badge LARANJA "BINANCE" no dashboard
Logs mostram: [BINANCE ENDPOINT] mode=REAL
Ordens aparecem no Binance Futures
```

---

**Pronto!** Agora seu robô está configurado para operar na **Binance Futures** com ordens reais! 🎉
