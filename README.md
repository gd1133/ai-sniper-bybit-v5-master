# Motor Sniper v60.9

Bot de trading com dashboard web em tempo real, operacao multiativo e integracao com Bybit e IA para validacao de sinais.

## ⚠️ IMPORTANTE: Configuração Modo Real vs Testnet

**Problema comum:** Ordens aparecem no bot mas não nas exchanges reais.

**Solução:** Configure corretamente as variáveis de ambiente:
```bash
ALLOW_ORDER_EXECUTION=true
ALLOW_REAL_TRADING=true
USE_TESTNET=false  # ⚠️ CRÍTICO: false para contas reais!
```

**Diagnóstico:** Execute `python diagnostico_modo_real.py` para validar a configuração.

📖 **Documentação completa:** Ver `CORRECAO_MODO_REAL_TESTNET.md`

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

Regras do endpoint:

- `ENVIRONMENT=development`: por padrao usa `USE_TESTNET=true`, `ALLOW_REAL_TRADING=false` e `ALLOW_ORDER_EXECUTION=false`
- `ENVIRONMENT=production`: por padrao usa `USE_TESTNET=false`, `ALLOW_REAL_TRADING=true` e `ALLOW_ORDER_EXECUTION=true`
- Se voce precisar de excecao local, ainda pode sobrescrever explicitamente `USE_TESTNET`, `ALLOW_REAL_TRADING` ou `ALLOW_ORDER_EXECUTION`
- `USE_TESTNET=true`: conecta obrigatoriamente em `https://api-testnet.bybit.com`
- `USE_TESTNET=false`: conecta obrigatoriamente em `https://api.bybit.com`

O modo operacional do dashboard (`paper`, `testnet`, `real`) continua sendo controlado pela aplicacao/banco, sem precisar duplicar variaveis de ambiente no deploy.

## Banco de dados SQLite

O projeto usa SQLite local com tabela `clientes_sniper` que inclui os campos:

- `account_mode` (`testnet` ou `real`)
- `is_testnet` (compatibilidade)
- `balance_source`
- `exchange` (`bybit` ou `binance`)

O banco de dados é criado automaticamente em `/app/data/database.db` no primeiro uso.
Para ambientes Railway, certifique-se de montar um volume em `/app/data` para persistir os dados.

## Deploy no Railway / Render

### 🆕 Problema: Frontend não salva no Railway?

Se o frontend está salvando clientes mas eles não aparecem no servidor/banco de dados:

**📖 Guia Rápido**: [docs/GUIA_RAPIDO_RAILWAY.md](docs/GUIA_RAPIDO_RAILWAY.md)

**Verificar configuração**:
```bash
python verify_railway_config.py
```

Este verificador mostra:
- ✅ Quais variáveis estão configuradas corretamente
- ❌ O que está faltando
- ⚠️  Avisos importantes sobre a configuração

### Validacao de ambiente

Antes de fazer deploy, valide sua configuracao local:

```bash
python validate_environment.py
```

### Railway - Configuracao completa

**⚠️ IMPORTANTE**: Para instrucoes detalhadas de configuracao no Railway, consulte:

📖 **[docs/RAILWAY_SETUP.md](docs/RAILWAY_SETUP.md)** - Guia completo com troubleshooting
📖 **[docs/GUIA_RAPIDO_RAILWAY.md](docs/GUIA_RAPIDO_RAILWAY.md)** - Guia rápido para corrigir problemas de salvamento
📖 **[docs/RAILWAY_FRONTEND_FIX.md](docs/RAILWAY_FRONTEND_FIX.md)** - Documentação técnica do sistema de logs

#### Variaveis minimas necessarias (Railway):

```env
ENVIRONMENT=production
BYBIT_API_KEY=sua_chave_bybit
BYBIT_API_SECRET=seu_segredo_bybit
GEMINI_API_KEY=sua_chave_gemini
GROQ_API_KEY=sua_chave_groq
TELEGRAM_TOKEN=seu_token_telegram
TELEGRAM_CHAT_ID=seu_chat_id
VITE_API_BASE=https://seu-app.railway.app
```

**⚠️ ATENCAO**: `VITE_API_BASE` deve incluir `https://` no inicio!

#### Volume no Railway

Configure um volume para persistir o banco de dados:

- **Mount Path**: `/app/data`
- Sem volume = perda de dados a cada deploy

#### Deploy seguro

Para desenvolvimento/testes:

```env
ENVIRONMENT=development
BYBIT_API_KEY=YOUR_BYBIT_API_KEY
BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
```

Para producao com trading real:

```env
ENVIRONMENT=production
# + todas as outras variaveis acima
```

Depois do deploy:

1. Use o dashboard para alternar entre `paper`, `testnet` e `real`
2. Cadastre clientes com `Conta Testnet` ou `Conta Real`
3. Configure credenciais individuais por cliente no dashboard

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
