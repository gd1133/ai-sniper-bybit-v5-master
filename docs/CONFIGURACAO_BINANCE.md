# Configuração da API Binance

## Visão Geral

O sistema **Motor Sniper V60.7** suporta tanto a **Bybit** quanto a **Binance** (Binance Futures USDM). Este documento explica como configurar as credenciais da API Binance para que seus investidores possam operar na plataforma Binance.

## Como Funciona

1. **Multi-Exchange**: O sistema detecta automaticamente qual exchange usar baseado no campo `exchange` do cliente no banco de dados
2. **Credenciais Unificadas**: As chaves da API (tanto Bybit quanto Binance) são armazenadas nos mesmos campos do banco de dados (`bybit_key` e `bybit_secret`)
3. **Interface Idêntica**: Ambas as exchanges usam a mesma interface, permitindo troca transparente entre elas

## Variáveis de Ambiente Necessárias

### Para usar Binance em TESTNET (conta de teste):

```bash
# Nenhuma variável necessária - as credenciais são armazenadas por cliente no banco de dados
# O sistema usa automaticamente o testnet da Binance quando o cliente tem account_mode='paper'
```

### Para usar Binance em PRODUÇÃO (conta real):

```bash
# As credenciais são armazenadas no banco de dados para cada cliente individual
# Não é necessário configurar variáveis de ambiente globais para a Binance
```

### Opcional - Credenciais Padrão (Fallback):

Se você quiser definir credenciais padrão da Binance no servidor (para testes ou desenvolvimento), você pode adicionar estas variáveis opcionais:

```bash
BINANCE_API_KEY=sua_chave_api_binance_aqui
BINANCE_API_SECRET=seu_secret_binance_aqui
```

**Nota**: Estas variáveis são opcionais. O sistema usa as credenciais armazenadas no banco de dados para cada cliente individual.

## Configuração no Banco de Dados

### Estrutura da Tabela `clientes`

Cada cliente tem os seguintes campos relevantes:

```sql
- exchange: TEXT NOT NULL DEFAULT 'bybit'  -- 'bybit' ou 'binance'
- bybit_key: TEXT                          -- API Key (usado para ambas exchanges)
- bybit_secret: TEXT                       -- API Secret (usado para ambas exchanges)
- account_mode: TEXT DEFAULT 'paper'       -- 'paper' (testnet) ou 'real' (produção)
```

### Exemplo de Cliente Configurado para Binance

```python
{
  "id": 1,
  "nome": "João Silva",
  "exchange": "binance",           # Define que usará Binance
  "bybit_key": "SUA_BINANCE_API_KEY",      # Chave da API Binance
  "bybit_secret": "SUA_BINANCE_SECRET",    # Secret da API Binance
  "account_mode": "paper",         # 'paper' = testnet, 'real' = produção
  "ativo": true
}
```

## Como Obter Credenciais da API Binance

### 1. Acesse o Painel da Binance
- **Testnet**: https://testnet.binancefuture.com/
- **Produção**: https://www.binance.com/

### 2. Crie uma API Key
1. Faça login na sua conta Binance
2. Vá em **Gerenciamento de API** (API Management)
3. Clique em **Criar API** (Create API)
4. Escolha **System generated** 
5. Dê um nome para sua API Key (ex: "Motor Sniper")
6. Complete a verificação de segurança (2FA)

### 3. Configure as Permissões
Para o Motor Sniper funcionar corretamente, você precisa habilitar:

- ✅ **Enable Reading** (Leitura)
- ✅ **Enable Futures** (Futuros)
- ✅ **Enable Spot & Margin Trading** (Opcional, mas recomendado)

⚠️ **IMPORTANTE**: 
- **NÃO** habilite "Enable Withdrawals" por segurança
- Configure IP whitelist se possível para maior segurança

### 4. Salve suas Credenciais
Após criar, você receberá:
- **API Key**: Uma string longa (ex: `WkXYZ...`)
- **Secret Key**: Outra string longa (ex: `abc123...`)

⚠️ **ATENÇÃO**: O Secret Key é mostrado **apenas uma vez**. Guarde em local seguro!

## Como Cadastrar um Cliente para Usar Binance

### Via API (Recomendado)

```bash
curl -X POST http://seu-servidor.com/api/clients \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "João Silva",
    "exchange": "binance",
    "bybit_key": "sua_binance_api_key",
    "bybit_secret": "sua_binance_secret",
    "account_mode": "paper",
    "ativo": true
  }'
```

### Via Interface Web

1. Acesse a interface de **GESTÃO** no frontend
2. Clique em **+ NOVO INVESTIDOR**
3. Preencha:
   - **Nome**: Nome do investidor
   - **Exchange**: Selecione **BINANCE** (botão laranja)
   - **API Key**: Cole a Binance API Key
   - **API Secret**: Cole a Binance Secret
   - **Modo Conta**: Selecione **PAPER** (testnet) ou **REAL** (produção)
4. Clique em **Salvar**

## Diferenças entre Bybit e Binance

### Endpoints

| Exchange | Testnet | Produção |
|----------|---------|----------|
| **Bybit** | `https://api-testnet.bybit.com` | `https://api.bybit.com` |
| **Binance** | `https://testnet.binancefuture.com` | `https://fapi.binance.com` |

### Alavancagem

Ambas suportam até **125x** de alavancagem (configurável por símbolo).

O sistema usa **10x** por padrão:
- `LEVERAGE = 10` (configurado em `main.py`)

### Timeframe

O sistema usa **30 minutos** por padrão:
- `TIMEFRAME = "30m"` (configurado em `main.py`)

## Parâmetros de Risco

O sistema agora usa os seguintes parâmetros de risco:

### Stop Loss (SL)
- **5% de preço** = 50% da margem (com alavancagem 10x)
- Calculado como: `sl_price = entry_price * 0.95`

### Take Profit (TP)
- **10% de preço** = 100% de lucro sobre margem (com alavancagem 10x)
- Calculado como: `tp_price = entry_price * 1.10`

### Entrada
- **5% da banca** após lucros (modo padrão)
- **3% da banca** após stop loss (modo conservador)

## Verificação de Configuração

### 1. Teste de Conectividade

O sistema faz verificação automática antes de cada ordem:

```python
# Verifica:
✅ Conectividade com a exchange
✅ Autenticação (API Key válida)
✅ Saldo disponível
✅ Símbolo válido e ativo
```

### 2. Logs

Verifique os logs do sistema para confirmar:

```
🔍 [BINANCE ENDPOINT] testnet=False mode=REAL
✅ Cliente João Silva (BINANCE/REAL) → Broker criado
```

### 3. Teste Manual

Execute um teste de conexão:

```bash
python test_bybit_wsl.py
```

O script testará a conectividade com ambas as exchanges.

## Troubleshooting

### Erro: "Authentication failed"
**Causa**: API Key ou Secret inválidos  
**Solução**: Verifique se copiou as credenciais corretamente, sem espaços extras

### Erro: "Insufficient balance"
**Causa**: Saldo insuficiente na conta  
**Solução**: Deposite fundos na sua conta Binance Futures

### Erro: "Invalid symbol"
**Causa**: Par de negociação não disponível na Binance  
**Solução**: Verifique se o símbolo está disponível (ex: use `BTCUSDT` ao invés de `BTCUSD`)

### Erro: "IP not whitelisted"
**Causa**: O IP do servidor não está na whitelist da API  
**Solução**: Adicione o IP do servidor nas configurações da API ou desabilite a whitelist

## Suporte

Para dúvidas ou problemas:
1. Verifique os logs do sistema (`/var/log/sniper.log`)
2. Consulte a documentação da Binance: https://binance-docs.github.io/apidocs/futures/en/
3. Entre em contato com o suporte técnico

---

**Última atualização**: 2026-05-07  
**Versão**: Motor Sniper V60.7
