# 🚀 Guia Rápido: Suporte Binance e Bybit

## ⚠️ IMPORTANTE: Execute ANTES do Deploy

Você **DEVE** executar o script de migração no Supabase **ANTES** de fazer o deploy do código atualizado.

## Passo 1: Migração do Banco de Dados (OBRIGATÓRIO)

### Usando o Supabase Dashboard (Recomendado)

1. Acesse seu Supabase: https://app.supabase.com
2. Clique em **SQL Editor** (menu lateral esquerdo)
3. Clique em **New Query**
4. Copie todo o conteúdo do arquivo: `tools/migrate_add_exchange_column.sql`
5. Cole no editor SQL
6. Clique em **Run** (ou Ctrl+Enter)
7. Aguarde a mensagem de sucesso

**Mensagem esperada:**
```
========================================
Exchange Column Migration Complete
========================================
Total records: X
Bybit clients: X
Binance clients: 0
========================================
```

## Passo 2: Deploy no Railway

Depois que a migração for aplicada com sucesso:

1. O Railway irá detectar automaticamente as mudanças no GitHub
2. Aguarde o deploy automático completar
3. Ou faça deploy manual no dashboard do Railway
4. Aguarde a mensagem "Deployment successful"

## Passo 3: Testar o Sistema

1. Acesse: https://web-production-cc471.up.railway.app
2. Vá para a aba **GESTÃO**
3. Clique em **"+ NOVO INVESTIDOR"**
4. Verifique se aparece:
   - ✅ Opção **"🟡 Bybit"**
   - ✅ Opção **"🟠 Binance"**

## Criando um Cliente Binance

### Usando Binance Testnet (Para Testar)

1. Acesse: https://testnet.binancefuture.com
2. Faça login com GitHub
3. Vá em **API Key**
4. Crie uma nova chave
5. Copie a **API Key** e **Secret Key**
6. No Motor Sniper:
   - Selecione **"🟠 Binance"**
   - Selecione **"🛰️ Conta Testnet"**
   - Cole as chaves
   - Clique em **"Guardar Investidor"**

### Usando Binance Real (Para Produção)

1. Acesse: https://www.binance.com
2. Faça login
3. Vá em **API Management**
4. Crie uma chave para **Futures Trading**
5. Ative: "Enable Reading" e "Enable Futures"
6. Copie a **API Key** e **Secret Key**
7. No Motor Sniper:
   - Selecione **"🟠 Binance"**
   - Selecione **"💼 Conta Real"**
   - Cole as chaves
   - Clique em **"Guardar Investidor"**

## O Que Mudou?

### ✅ Agora Funciona

- **Salvar clientes Binance**: Antes só salvava Bybit
- **Ver distintivo correto**: BYBIT (amarelo) ou BINANCE (laranja)
- **Validação de credenciais**: Funciona para ambas exchanges
- **Sincronização de saldo**: Busca saldo real da exchange selecionada

### ✅ Clientes Antigos

- Todos os clientes antigos vão aparecer como **BYBIT** (padrão)
- Você pode editar e mudar para Binance se quiser
- Não precisa recriar os clientes existentes

## Problemas Comuns

### "API inválida" ao salvar cliente Binance

**Solução**: 
- Verifique se está usando chaves da **Binance Futures** (não Spot)
- Se selecionou Testnet, use chaves do **Testnet**
- Se selecionou Real, use chaves da **conta Real**

### Clientes Binance aparecem como "Bybit"

**Solução**:
- Execute a migração do banco (Passo 1)
- Limpe o cache do navegador
- Recarregue a página

### Deploy falhou no Railway

**Solução**:
- Verifique se executou a migração **ANTES** do deploy
- Verifique as variáveis de ambiente no Railway
- Veja os logs do Railway para detalhes do erro

## Verificação de Sucesso

Após o deploy, verifique:

- ✅ Formulário mostra opções Bybit e Binance
- ✅ Consegue criar cliente Bybit
- ✅ Consegue criar cliente Binance
- ✅ Distintivos aparecem corretos (BYBIT/BINANCE)
- ✅ Saldo sincroniza automaticamente

## Arquivos Importantes

- `tools/migrate_add_exchange_column.sql` - Script de migração
- `docs/DEPLOYMENT_GUIDE.md` - Guia completo em inglês
- `docs/EXCHANGE_MIGRATION.md` - Documentação técnica

## Ajuda

Se tiver problemas:

1. Verifique os logs do Railway
2. Verifique os logs do Supabase
3. Leia o `DEPLOYMENT_GUIDE.md` completo
4. Abra uma issue no GitHub

---

**Servidor**: web-production-cc471.up.railway.app  
**Versão**: Motor Sniper V60.7  
**Data**: 07/05/2026
