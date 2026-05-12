# Motor Sniper v60.7

Bot de trading com dashboard web em tempo real, operacao multiativo e integracao com Bybit e IA para validacao de sinais.

## Documentacao completa

Para a documentacao tecnica, operacional e comercial completa, consulte:

- `docs/DOCUMENTACAO_COMPLETA.md`

## Stack

- **Backend:** Python, Flask, SQLite
- **Frontend:** React, Vite
- **Trading/mercado:** CCXT / Bybit
- **IA:** Groq + Gemini + motor local
- **Persistencia:** SQLite local em /app/data/database.db

## Logica estrategica

O motor combina:

- **SMA 200** para contexto de tendencia
- **Fibonacci 0.618** para zona de entrada
- **RSI** para leitura de momentum
- **Volume** para confirmar forca
- **Fluxo institucional** para procurar onde o grande dinheiro esta entrando ou saindo
- **Consenso de IA** com validacao entre radar tatico, estrategista cloud e logica local
- **Fallback soberano do 3º cerebro** quando Gemini e Groq falham, com execucao local a partir de 80% de confianca

## Regras operacionais atuais

- Ate **5 moedas simultaneas**
- Sem repetir moeda ja aberta
- **Valor da ordem:** 5% da banca total do cliente
- **Take Profit:** 100%
- **Stop Loss:** 3%
- **Saida manual:** disponivel no painel para encerrar operacao antes do TP/SL
- Modo teste e modo real
- Gestao de investidores/clientes com armazenamento seguro de credenciais
- Telegram do cliente opcional: so recebe sinal privado se preencher token e chat id

## Seguranca

- Credenciais sensiveis ficam fora do Git
- `.env` e bancos locais estao ignorados no versionamento
- Campos sensiveis de clientes no banco SQLite sao protegidos no aplicativo
- Banco de dados local em /app/data/database.db com persistencia em volume

## Escalabilidade

- Painel e backend separados
- Suporte a monitoramento multiativo
- Cache de tickers e filtros locais para reduzir chamadas externas
- Estrutura pronta para evoluir regras de consenso, filas e workers

## Variaveis de ambiente

Copie `.env.example` para `.env` e preencha com suas chaves.

Variavel mestre do ambiente:

- `ENVIRONMENT=development|production`

Padrao unico das credenciais Bybit:

- `BYBIT_API_KEY`
- `BYBIT_API_SECRET`
- `PROXY_URL` (opcional): endereço do proxy para conectar à Bybit (ex: `http://user:pass@proxy.com:port` ou `socks5://proxy.com:port`)

Regras do endpoint:

- `ENVIRONMENT=development`: por padrao usa `USE_TESTNET=true`, `ALLOW_REAL_TRADING=false` e `ALLOW_ORDER_EXECUTION=false`
- `ENVIRONMENT=production`: por padrao usa `USE_TESTNET=false`, `ALLOW_REAL_TRADING=true` e `ALLOW_ORDER_EXECUTION=true`
- Se voce precisar de excecao local, ainda pode sobrescrever explicitamente `USE_TESTNET`, `ALLOW_REAL_TRADING` ou `ALLOW_ORDER_EXECUTION`
- `USE_TESTNET=true`: conecta obrigatoriamente em `https://api-testnet.bybit.com`
- `USE_TESTNET=false`: conecta obrigatoriamente em `https://api.bybit.com`

O modo operacional do dashboard (`paper`, `testnet`, `real`) continua sendo controlado pela aplicacao/banco, sem precisar duplicar variaveis de ambiente no deploy.

### Usando Proxy para conectar à Bybit e Binance

Se sua exchange requer um IP fixo e você precisa usar um proxy, configure a variável `PROXY_URL`:

```env
PROXY_URL=http://usuario:senha@seu-proxy.com:8080
```

Formatos suportados:
- HTTP/HTTPS: `http://proxy.com:port` ou `https://proxy.com:port`
- SOCKS5: `socks5://proxy.com:port`
- Com autenticação: `http://usuario:senha@proxy.com:port`

O bot irá:
- Conectar automaticamente via proxy quando `PROXY_URL` estiver configurado
- Usar o proxy para conexões com Bybit e Binance
- Exibir logs indicando que está usando o proxy
- Mostrar erros detalhados se a conexão via proxy falhar

**Nota:** Deixe `PROXY_URL` em branco ou remova a variável se não usar proxy.

## Banco de dados SQLite

O projeto usa SQLite local com tabela `clientes_sniper` que inclui os campos:

- `account_mode` (`testnet` ou `real`)
- `is_testnet` (compatibilidade)
- `balance_source`
- `exchange` (`bybit` ou `binance`)

O banco de dados é criado automaticamente em `/app/data/database.db` no primeiro uso.
Para ambientes Railway, certifique-se de montar um volume em `/app/data` para persistir os dados.

## Deploy no Railway / Render

Valores recomendados para subir com seguranca:

```env
ENVIRONMENT=development
BYBIT_API_KEY=YOUR_BYBIT_API_KEY
BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
```

Depois do deploy:

1. Use o dashboard para alternar entre `paper`, `testnet` e `real`
2. Cadastre clientes com `Conta Testnet` ou `Conta Real`
3. Ajuste `ENVIRONMENT` para `production` quando quiser subir com execucao real por padrao

## Como rodar

### Backend

```bash
pip install -r requirements.txt
python main_web.py
```

### Frontend

```bash
npm install
npm run build
```
