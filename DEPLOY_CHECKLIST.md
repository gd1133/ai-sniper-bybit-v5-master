# 🚀 CHECKLIST DE DEPLOY - Correção de Ambientes

## ✅ Pré-Deploy (Antes de enviar para Render)

### 1. Verificar Mudanças em Arquivo Local

```bash
# Confirmar que todos os arquivos foram editados
git status
```

Arquivos que devem aparecer como modificados:

- [x] src/broker/bybit_client.py
- [x] src/broker/binance_client.py
- [x] src/database/manager.py
- [x] main_web.py

### 2. Rodar Testes Locais (Opcional)

```bash
# Se tiver testes em src/
python -m pytest tests/ -v
```

### 3. Executar Script de Validação

```bash
python validate_client_isolation.py
```

Esperado: Todos os checks passar

### 4. Iniciar Servidor Local

```bash
python main_web.py
```

Procurar nos logs por:

```
🔴 [CONTA REAL] [BYBIT] Instanciando cliente...
🧪 [SIMULAÇÃO] [BYBIT] Instanciando cliente...
```

---

## 📤 Deploy no Render

### 1. Fazer Commit

```bash
git add .
git commit -m "Fix: Isolamento de ambientes (real vs testnet) por cliente

- BybitClient e BinanceClient agora aceitam client_name
- Logs claros identificando 🔴 CONTA REAL ou 🧪 SIMULAÇÃO
- BrokerManager lê account_mode do banco de dados por cliente
- Removido hardcoded testnet=False em _make_broker()
- Database manager suporta múltiplos modos: 'real' e 'testnet'
- Cada cliente agora usa seu próprio ambiente

Fecha: Erro 10003 em clientes Real conectando em Testnet"
```

### 2. Push para GitHub

```bash
git push origin main
```

Render será acionado automaticamente.

### 3. Monitorar Deploy

1. Abra https://dashboard.render.com
2. Selecione seu serviço
3. Vá para "Logs"
4. Aguarde a linha: "Web service is live"

---

## 🧪 Testes Pós-Deploy

### Teste 1: Logs de Inicialização

1. Abra o dashboard Render
2. Vá para "Logs"
3. Procure por:
   ```
   🔴 [CONTA REAL] [BYBIT] Instanciando cliente 'Paulo'
   🧪 [SIMULAÇÃO] [BYBIT] Instanciando cliente 'João'
   ```

✅ **Esperado:** Cada cliente com seu ambiente correto

### Teste 2: Verificar Chave Real em Produção

1. Acesse o dashboard React em produção
2. Clique no card do cliente Paulo
3. Procure por transações

✅ **Esperado:** Transações funcionam sem erro 10003

### Teste 3: Validar Endpoint Correto

1. No servidor (terminal Render), procure por:
   ```
   endpoint=https://api.bybit.com       ← Real
   endpoint=https://api-testnet.bybit.com  ← Testnet
   ```

✅ **Esperado:** Cada cliente com endpoint correto

---

## 🔄 Rollback (Se Necessário)

Se algo der errado:

```bash
# Ver commits anteriores
git log --oneline -n 5

# Reverter para antes da mudança
git revert HEAD

# Ou, se não foi feito push ainda
git reset --hard HEAD~1
```

---

## 📊 Indicadores de Sucesso

✅ **Verde:**

- Logs com 🔴 e 🧪 aparecem
- Sem erro 10003 em clientes real
- Transações funcionam normalmente
- Dashboard carrega saldos corretamente

❌ **Vermelho (Rollback):**

- Erro 10003 em clientes real
- Logs não mostram cliente ou ambiente
- Transações falhando
- Dashboard não carrega

---

## 📋 Documentação para Time

Após deploy bem-sucedido, compartilhe com o time:

1. **GUIA_CORRECAO_AMBIENTES.md** - Como funciona (PT-BR)
2. **RESUMO_CORRECAO_AMBIENTES.md** - Resumo visual
3. **CORRECAO_CRUZAMENTO_AMBIENTES_v61.md** - Técnico completo

---

## 🎯 Após Deploy bem-sucedido

### Para Investidores:

"Seu cliente agora detecta automaticamente se você está em CONTA REAL ou SIMULAÇÃO baseado no banco de dados. Se vê 🔴, está em REAL. Se vê 🧪, está em SIMULAÇÃO."

### Para Desenvolvedores:

"Cada cliente agora lê seu `account_mode` do banco. Suporte para múltiplos ambientes no mesmo robô. Cache invalidado automaticamente se alterar account_mode."

---

## 📞 Troubleshooting

### Problema: Logs não mostram 🔴 ou 🧪

**Solução:** Verifique se os arquivos foram atualizados no Render

```bash
git log --oneline -n 1  # Deve mostrar o commit da correção
```

### Problema: Ainda vendo erro 10003

**Solução:**

1. Verifique `account_mode` no banco:
   ```sql
   SELECT nome, account_mode FROM clientes_sniper WHERE status='ativo';
   ```
2. Deve mostrar 'real' para clientes com chave real
3. Se não, atualize:
   ```sql
   UPDATE clientes_sniper SET account_mode='real' WHERE nome='Paulo';
   ```

### Problema: Cliente não conecta depois da mudança

**Solução:** O cache foi invalidado e uma nova conexão é criada. Aguarde 10 segundos.

---

## ✨ Próximas Melhorias (Opcional)

1. **UI para alterar account_mode**
   - Dropdown no dashboard para cada cliente
   - Mostrar badge 🔴 ou 🧪 na lista

2. **Validação de chave**
   - Ao cadastrar cliente, testar se chave é real ou testnet
   - Alertar se houver mismatch

3. **Audit log**
   - Registrar quando um cliente muda de ambiente
   - Histórico de mudanças

---

**Deploy Date:** Junho 2026  
**Expected Downtime:** ~30 segundos (redeploy Render)  
**Rollback Difficulty:** Fácil (git revert)  
**Risk Level:** Baixo (lê banco, sem mudança schema)
