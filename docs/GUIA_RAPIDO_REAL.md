# Guia Rápido: Configurar Robô para Operar REAL

## 🎯 Problema: Robô não está executando ordens reais

Se o robô está mostrando trades no frontend mas elas não aparecem na Bybit/Binance, siga este guia.

---

## ✅ Passo 1: Verificar Variáveis de Ambiente

No **Railway**, certifique-se que estas variáveis estão configuradas:

```env
ENVIRONMENT=production
ALLOW_ORDER_EXECUTION=true
ALLOW_REAL_TRADING=true
```

✅ **Você já tem isso configurado!** (conforme suas screenshots)

---

## ✅ Passo 2: Escolher Exchange

### **Opção A: Bybit** (requer configuração de IP)

#### Problema:
A Bybit **OBRIGA** whitelist de IP para contas de produção. Você não pode salvar "Sem restrição de IP".

#### Solução:
1. Descubra o IP do servidor: `https://seu-app.up.railway.app/api/server-ip`
2. Adicione esse IP na Bybit API Management
3. Permissões necessárias: Contract Trading, Position, Order
4. **NÃO ative:** Withdrawals

**Guia completo:** `docs/RESOLVER_IP_BYBIT.md`

---

### **Opção B: Binance** ⭐ **RECOMENDADO**

#### Vantagens:
- ✅ Permite "Unrestricted" (sem whitelist de IP)
- ✅ Configuração mais simples
- ✅ Robô já tem suporte completo
- ✅ Mesmo risco/gestão que Bybit

#### Como Configurar:

**1. Criar API Keys na Binance:**
   - https://www.binance.com/en/my/settings/api-management
   - Create API → System generated
   - Permissões:
     - ✅ Enable Futures
     - ✅ Enable Reading
     - ❌ Enable Withdrawals (NUNCA!)
   - IP Whitelist: **"Unrestricted (Less Secure)"** ← SIM, pode usar!
   - Copie: API Key + Secret Key

**2. No Dashboard do Robô:**
   - Vá em **GESTÃO** (Management)
   - Cadastre ou edite um cliente:
     - **Nome:** Seu nome
     - **Exchange:** Selecione **BINANCE** ⚠️
     - **Account Mode:** Selecione **REAL** ⚠️
     - **API Key:** Cole a Binance API Key
     - **API Secret:** Cole a Binance Secret Key
     - **Saldo Base:** Ex: 1000 USDT
     - **Status:** ATIVO
   - **SALVE**

**3. Verificar:**
   - Badge do cliente deve ser **LARANJA** "BINANCE"
   - Logs devem mostrar: `[BINANCE ENDPOINT] mode=REAL`

**Guia completo:** `docs/CONFIGURAR_BINANCE.md`

---

## ✅ Passo 3: Verificar Cliente no Dashboard

No painel **GESTÃO**, verifique:

- [ ] **Exchange:** BINANCE (não Bybit)
- [ ] **Account Mode:** REAL (não testnet)
- [ ] **API Keys:** Preenchidas corretamente
- [ ] **Status:** ATIVO (não inativo)
- [ ] **Badge:** LARANJA "BINANCE" (não amarelo "BYBIT")

---

## ✅ Passo 4: Testar

1. **Aguarde um sinal** do robô
2. **Verifique os logs:**
   ```
   🚀 [EXECUÇÃO REAL] SeuNome - buy 0.1234 TONUSDT
   ✅ [ORDEM EXECUTADA] ID: 12345678
   ```
3. **Verifique na Exchange:**
   - Bybit: https://www.bybit.com/app/trade/usdt/BTCUSDT → Histórico de ordens
   - Binance: https://www.binance.com/en/futures/BTCUSDT → Order History

---

## 🚨 Checklist de Troubleshooting

Se as ordens ainda não aparecem na exchange:

- [ ] `ENVIRONMENT=production` no Railway?
- [ ] `ALLOW_ORDER_EXECUTION=true` no Railway?
- [ ] `ALLOW_REAL_TRADING=true` no Railway?
- [ ] Cliente configurado com `exchange=binance`?
- [ ] Cliente configurado com `account_mode=real`?
- [ ] API Keys são de **produção** (não testnet)?
- [ ] Permissões corretas na API (Futures habilitado)?
- [ ] Status do cliente é ATIVO?
- [ ] Robô foi reiniciado após mudanças?

---

## 📊 Comparação: Bybit vs Binance

| Aspecto | Bybit | Binance |
|---------|-------|---------|
| **IP Whitelist** | Obrigatório | Opcional |
| **Configuração** | Complexa | Simples |
| **Suporte no Robô** | Completo | Completo |
| **Funcionalidades** | Idênticas | Idênticas |
| **Recomendação** | Se já funciona | ⭐ Primeira escolha |

---

## 🎯 Solução Recomendada (5 minutos)

```bash
1. Criar API na Binance Futures
   - Enable Futures + Enable Reading
   - IP: Unrestricted

2. Railway Environment (já está OK):
   ENVIRONMENT=production
   ALLOW_ORDER_EXECUTION=true
   ALLOW_REAL_TRADING=true

3. Dashboard > GESTÃO > Cadastrar Cliente:
   Exchange: BINANCE
   Account Mode: REAL
   API Keys: [suas chaves Binance]
   Status: ATIVO

4. Aguardar sinal e verificar ordem na Binance
```

---

## 📚 Documentação Completa

- **Configurar Binance:** `docs/CONFIGURAR_BINANCE.md`
- **Resolver IP Bybit:** `docs/RESOLVER_IP_BYBIT.md`
- **Documentação Geral:** `docs/DOCUMENTACAO_COMPLETA.md`

---

## 🆘 Suporte

**Endpoints Úteis:**

- IP do servidor: `https://seu-app.up.railway.app/api/server-ip`
- Status do robô: `https://seu-app.up.railway.app/api/status`
- Modo atual: `https://seu-app.up.railway.app/api/mode/current`

**Logs do Railway:**
- Dashboard > Seu projeto > View Logs

---

**💡 TL;DR:** Use Binance com "Unrestricted IP" e configure o cliente como `exchange=binance` e `account_mode=real`. É mais simples que Bybit e já funciona sem configuração de IP!
