# Motor Sniper v60.7

Bot de trading com dashboard web em tempo real, operacao multiativo e integracao com Bybit, Supabase e IA para validacao de sinais.

## Documentacao completa

Para a documentacao tecnica, operacional e comercial completa, consulte:

- `docs/DOCUMENTACAO_COMPLETA.md`

## Stack

- **Backend:** Python, Flask, SQLite
- **Frontend:** React, Vite
- **Trading/mercado:** CCXT / Bybit
- **IA:** Groq + Gemini + motor local
- **Persistencia cloud:** Supabase

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
- Campos sensiveis de clientes no Supabase sao protegidos no aplicativo
- Projeto preparado para operar com fallback local quando a nuvem estiver indisponivel

## Escalabilidade

- Painel e backend separados
- Suporte a monitoramento multiativo
- Cache de tickers e filtros locais para reduzir chamadas externas
- Estrutura pronta para evoluir regras de consenso, filas e workers

## Variaveis de ambiente

Copie `.env.example` para `.env` e preencha com suas chaves.

Padrao unico das credenciais Bybit:

- `BYBIT_API_KEY`
- `BYBIT_API_SECRET`
- `USE_TESTNET=true|false`

Regras do endpoint:

- `USE_TESTNET=true`: conecta obrigatoriamente em `https://api-testnet.bybit.com`
- `USE_TESTNET=false`: conecta obrigatoriamente em `https://api.bybit.com`

O modo operacional do dashboard (`paper`, `testnet`, `real`) continua sendo controlado pela aplicacao/banco, sem precisar duplicar variaveis de ambiente no deploy.

## Supabase

O projeto usa a tabela `clientes` com os campos:

- `account_mode` (`testnet` ou `real`)
- `is_testnet` (compatibilidade)
- `balance_source`

Se o schema da nuvem estiver desatualizado, aplique `tools/supabase_schema.sql`.

## Deploy no Render / GitHub

Valores recomendados para subir com seguranca:

```env
USE_TESTNET=true
BYBIT_API_KEY=YOUR_BYBIT_API_KEY
BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
```

Depois do deploy:

1. Use o dashboard para alternar entre `paper`, `testnet` e `real`
2. Cadastre clientes com `Conta Testnet` ou `Conta Real`
3. Ajuste `USE_TESTNET` apenas quando quiser trocar o ambiente padrao da conexao master

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
