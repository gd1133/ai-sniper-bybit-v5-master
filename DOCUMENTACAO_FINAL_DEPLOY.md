# AI Sniper Bybit V5 — Documentação Final para Deploy

## 1) Resumo executivo
Esta é a documentação final da versão atual do robô para publicação e deploy.
O sistema opera com scanner de mercado, validação técnica/IA local, execução multi-cliente e painel web.

## 2) Estado atual da versão
- Core web: `main_web.py` (banner interno v61.5)
- Backend: Flask + Python
- Frontend: React + Vite
- Broker principal: Bybit V5 (CCXT/pybit)
- Banco: SQLite
- IA ativa no fluxo principal: local (heurística + aprendizado em SQLite)

## 3) Estratégia usada no robô
- Tendência macro: SMA 200
- Confirmação: SuperTrend
- Momento/exaustão: RSI
- Zona de entrada: Fibonacci 0.618
- Força de movimento: volume ratio

## 4) Regras operacionais atuais (código)
- Threshold de entrada: 70
- Máx posições simultâneas: 1 (conservador) / 5 (agressivo)
- Risco por operação: 5% da banca por cliente
- TP automático: +100%
- SL automático: -50%
- Fechamento manual: endpoint `/api/trade/manual-close`

Observação de risco:
- O SL de 50% é uma configuração agressiva da estratégia atual e deve ser revisado conforme o perfil de risco antes de operar em conta real.

## 5) Multi-cliente
Quando um sinal é aprovado:
- Todos os clientes ativos podem executar em paralelo;
- Cada cliente usa sua própria API key/secret;
- Telegram é opcional por cliente;
- Cada trade é registrado por cliente no SQLite.

## 6) APIs principais
- `GET /api/status`
- `GET /api/investidores`
- `POST /api/vincular_cliente`
- `PUT /api/cliente/<id>`
- `POST /api/trade/manual-entry`
- `POST /api/trade/manual-close`
- `GET/POST /api/config/risk-mode`

## 7) Deploy para conta do cliente (lista de verificação rápida)
1. Criar `.env` a partir de `.env.example`.
2. Definir:
   - `ENVIRONMENT=production`
   - `ALLOW_ORDER_EXECUTION=true`
   - `ALLOW_REAL_TRADING=true`
   - `USE_TESTNET=false` (conta real)
   - `BYBIT_API_KEY` e `BYBIT_API_SECRET` da conta do cliente
3. Configurar Telegram do cliente (opcional).
4. Garantir persistência do SQLite em volume.
5. Subir aplicação e validar endpoints de status.
6. Testar com entrada manual controlada antes da operação contínua.

## 8) Segurança mínima recomendada
- Nunca commitar `.env` e banco local.
- Usar chave Bybit com permissões mínimas.
- Proteger acesso ao painel com camada de autenticação/proxy.
- Separar ambiente de homologação e produção.

## 9) Sobre Groq e Gemini
A arquitetura suporta integração cloud, porém o fluxo principal atual está em modo local-only no validador.
Para ativar Groq/Gemini em produção, deve-se reintroduzir chamadas cloud no consenso e manter fallback local soberano.

## 10) Referências de arquivos
- `main_web.py`
- `src/engine/indicators.py`
- `src/ai_brain/validator.py`
- `src/ai_brain/learning.py`
- `src/broker/bybit_client.py`
- `src/database/manager.py`
