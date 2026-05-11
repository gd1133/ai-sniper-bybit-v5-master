# Como Resolver Problema de IP Whitelist na Bybit

## 🚨 Problema

Ao tentar configurar API Keys na Bybit para **conta de produção (REAL)**, você não consegue salvar a opção **"Sem restrição de IP"**. A Bybit força você a adicionar IPs permitidos na whitelist.

### Por que isso acontece?

A Bybit **OBRIGA** whitelist de IP para chaves de API de produção por segurança. Você **DEVE** adicionar o IP do servidor onde o robô está rodando (Railway, Heroku, etc.).

---

## ✅ Solução 1: Adicionar IP do Servidor na Whitelist

### **Passo 1: Descobrir o IP do Servidor**

#### **Opção A: Usar o Endpoint do Robô**

1. Acesse: `https://ai-sniper-bybit-v5-master-master.up.railway.app/api/server-ip`
2. Você verá algo como:
   ```json
   {
     "server_ip": "35.192.168.1"
   }
   ```
3. **Copie este IP**

#### **Opção B: Verificar nos Logs do Railway**

1. Vá para o Railway Dashboard
2. Clique em "Logs" ou "View Logs"
3. Procure por mensagens que mostrem o IP de saída

#### **Opção C: Adicionar Endpoint Temporário**

Se o endpoint acima não funcionar, adicione este código em `main_web.py`:

```python
@app.route('/api/my-ip', methods=['GET'])
def get_my_ip():
    try:
        import urllib.request
        with urllib.request.urlopen('https://api.ipify.org', timeout=5) as resp:
            ip = resp.read().decode('utf-8').strip()
        return jsonify({
            'ip': ip,
            'headers': dict(request.headers),
            'remote_addr': request.remote_addr
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

### **Passo 2: Adicionar IP na Bybit**

1. **Acesse Bybit API Management:**
   - URL: https://www.bybit.com/app/user/api-management

2. **Edite sua API Key:**
   - Clique em **"Edit"** ou **"Editar"** na sua chave de API

3. **Configure IP Whitelist:**
   - Selecione: **"Apenas IPs com permissão podem acessar a OpenAPI"**
   - No campo de texto, adicione o IP que você descobriu
   - Exemplo: `35.192.168.1`

4. **Salve as Configurações:**
   - Clique em **"Enviar"** ou **"Submit"**
   - Complete a verificação 2FA se solicitado

### **Passo 3: Testar**

Reinicie o robô no Railway e verifique se as ordens são executadas com sucesso.

---

## ✅ Solução 2: Usar Binance (RECOMENDADO)

A **Binance permite "Unrestricted"** (sem restrição de IP) para API Keys de produção. Isso é mais conveniente para deployments na nuvem.

**Consulte o guia completo em:** `docs/CONFIGURAR_BINANCE.md`

### Comparação Rápida

| Característica | Bybit | Binance |
|---------------|-------|---------|
| IP Whitelist obrigatório | ✅ Sim (produção) | ❌ Não (opcional) |
| "Sem restrição de IP" | ❌ Não permitido | ✅ Permitido |
| Dificuldade de configuração | 🔴 Média (precisa IP) | 🟢 Fácil |

---

## 🔧 Configurações Adicionais da Bybit

### **Permissões Necessárias**

Ao criar/editar a API Key na Bybit, habilite:

- ✅ **Contract Trading** (Futures Trading)
- ✅ **Position** (Read/Write)
- ✅ **Order** (Read/Write)
- ❌ **Withdrawal** (NUNCA ATIVE - por segurança)

### **2FA (Autenticação de Dois Fatores)**

Se a Bybit solicitar 2FA:

1. Use Google Authenticator ou similar
2. Digite o código de 6 dígitos ao salvar configurações de API

### **Rate Limits**

A Bybit tem limites de requisições por segundo. O robô já está configurado com:

```python
'enableRateLimit': True,
'rateLimit': 100,  # Delay mínimo de 100ms entre requisições
```

---

## 🚧 Problemas Comuns

### **1. "IP not whitelisted" ou "10003: Invalid API key"**

**Causa:** IP do servidor não está na whitelist da Bybit

**Solução:**
1. Descubra o IP real do servidor usando `/api/server-ip`
2. Adicione esse IP na whitelist da Bybit
3. Aguarde alguns minutos (propagação)
4. Reinicie o robô

### **2. IP muda frequentemente (Railway/Heroku)**

**Causa:** Serviços de cloud podem mudar o IP de saída

**Soluções:**
- **Opção A:** Usar Binance (permite "unrestricted")
- **Opção B:** Usar serviço de proxy fixo
- **Opção C:** Adicionar múltiplos IPs na whitelist da Bybit

### **3. "Sem restrição de IP" não fica salvo**

**Causa:** Bybit não permite essa opção para contas de produção (é uma limitação da plataforma)

**Solução:** Você **DEVE** adicionar pelo menos um IP. Não há como contornar isso na Bybit para contas reais.

### **4. Testnet funciona, mas conta real não**

**Causa:** Testnet permite "sem restrição de IP", mas produção não

**Solução:**
- Para produção: adicione IP na whitelist
- Para testes: use testnet (não precisa whitelist)

---

## 📝 Comandos Úteis

### **Ver IP do Servidor (via curl)**

```bash
curl https://ai-sniper-bybit-v5-master-master.up.railway.app/api/server-ip
```

### **Testar Conexão com Bybit**

```bash
# No logs do Railway, procure por:
🔍 [BYBIT ENDPOINT] testnet=False endpoint=https://api.bybit.com
```

Se aparecer `testnet=False` e `endpoint=https://api.bybit.com`, está conectando em produção.

---

## 🆘 Ainda Não Funciona?

Se depois de adicionar o IP na whitelist ainda não funcionar:

1. **Aguarde 5-10 minutos** (propagação da configuração)
2. **Reinicie o robô** completamente no Railway
3. **Verifique os logs** para mensagens de erro específicas
4. **Considere usar Binance** (mais simples, sem restrição de IP)

---

## 📚 Links Úteis

- **Bybit API Management:** https://www.bybit.com/app/user/api-management
- **Bybit API Documentation:** https://bybit-exchange.github.io/docs/v5/intro
- **Descobrir seu IP:** https://api.ipify.org
- **Endpoint do Robô:** `https://seu-app.up.railway.app/api/server-ip`

---

## 💡 Recomendação Final

Se você está tendo problemas com a whitelist de IP da Bybit, considere **migrar para Binance**. A Binance:

- Permite "unrestricted" IP access
- Não obriga whitelist para contas de produção
- É mais conveniente para deployments na nuvem
- **O robô já tem suporte completo para Binance!**

**Consulte:** `docs/CONFIGURAR_BINANCE.md` para o guia completo.

---

**✅ Resumo da Solução:**

```
1. Descubra o IP: https://seu-app.up.railway.app/api/server-ip
2. Adicione na Bybit: API Management > Edit > IP Whitelist > Adicionar IP
3. Salve e aguarde 5 minutos
4. Reinicie o robô
5. OU migre para Binance (mais fácil!)
```
