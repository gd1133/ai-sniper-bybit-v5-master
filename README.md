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
