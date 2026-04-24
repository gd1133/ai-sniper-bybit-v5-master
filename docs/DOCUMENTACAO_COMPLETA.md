# Documentacao Completa - Motor Sniper v60.7

## 1. Visao geral

O **Motor Sniper v60.7** e uma plataforma de trading com painel web em tempo real, validacao de sinais por analise tecnica e consenso de IA, gestao de clientes/investidores e persistencia local/cloud.

O sistema foi desenhado para operar com:

- **Backend Python + Flask**
- **Frontend React + Vite**
- **Banco local SQLite**
- **Persistencia cloud via Supabase**
- **Conexao de mercado via Bybit/CCXT**
- **Validacao de sinais com logica local + Groq + Gemini**

O foco do projeto e combinar:

- leitura tecnica objetiva,
- controle operacional,
- visibilidade em dashboard,
- separacao entre modo teste e modo real,
- protecao basica de credenciais,
- arquitetura pronta para evolucao.

---

## 2. Objetivo do produto

O Motor Sniper foi criado para:

1. monitorar ativos com alto volume,
2. identificar confluencias tecnicas,
3. validar a entrada com consenso de IA,
4. distribuir sinais para clientes cadastrados,
5. registrar operacoes e desempenho,
6. exibir o estado do motor em um dashboard operacional.

Ele atende dois perfis ao mesmo tempo:

- **operacao tecnica:** leitura de mercado, sinais, P&L, posicoes e estados do motor;
- **operacao comercial/clientes:** cadastro de investidores, chaves, saldo base, modo teste/real e trilha operacional.

---

## 3. Escopo do sistema

### Dentro do escopo

- scanner de moedas USDT com filtro por volume,
- leitura de OHLCV e calculo de indicadores,
- consenso entre motor local, Groq e Gemini,
- dashboard em tempo real,
- gestao de clientes/investidores,
- armazenamento local com fallback cloud,
- suporte a paper trading,
- monitoramento multiativo com ate 5 moedas simultaneas,
- regras de TP e SL configuradas no codigo.

### Fora do escopo atual

- garantia de lucro,
- eliminacao total de risco,
- roteamento institucional de ordens em alta frequencia,
- motor distribuido em varios servidores,
- engine formal de compliance/regulatorio,
- autenticacao multiusuario no dashboard,
- segregacao por tenant com isolamento forte de clientes.

---

## 4. Arquitetura de alto nivel

## 4.1 Componentes principais

### Backend

Arquivo principal: `main_web.py`

Responsabilidades:

- subir a API Flask,
- manter o estado global do motor,
- orquestrar o loop de scanner,
- distribuir sinais,
- sincronizar trades e dashboard,
- expor endpoints para UI e gestao de clientes.

### Frontend

Arquivo principal: `main.jsx`

Responsabilidades:

- exibir dashboard,
- mostrar sinais, P&L e trades ativos,
- mostrar oportunidades ranqueadas,
- gerenciar clientes/investidores,
- refletir modo teste/real e fonte de dados.

### Banco local

Arquivo principal: `src/database/manager.py`

Responsabilidades:

- manter `clientes_sniper`,
- manter `trades`,
- manter `config`,
- registrar historico local,
- funcionar como fallback operacional.

### Persistencia cloud

Arquivo principal: `src/database/supabase_manager.py`

Responsabilidades:

- salvar clientes no Supabase,
- criptografar campos sensiveis,
- ler clientes da nuvem,
- cair para fallback local quando a nuvem falhar.

### Logica de IA

Arquivo principal: `src/ai_brain/validator.py`

Responsabilidades:

- calcular score local,
- consultar Groq,
- consultar Gemini,
- consolidar pesos,
- aplicar travas soberanas,
- devolver decisao final.

### Motor de indicadores

Arquivo principal: `src/engine/indicators.py`

Responsabilidades:

- calcular SMA 200,
- RSI,
- Fibonacci,
- volume ratio,
- fluxo institucional,
- impulso direcional,
- contexto tecnico para o validador.

### Broker

Arquivo principal: `src/broker/bybit_client.py`

Responsabilidades:

- conectar com Bybit,
- consultar saldo,
- consultar preco,
- servir como ponte com a exchange.

---

## 5. Fluxo operacional ponta a ponta

## 5.1 Scanner

O loop principal:

1. atualiza estado do motor,
2. repara trades abertos invalidos,
3. sincroniza trades ativos,
4. busca tickers de maior volume,
5. seleciona um conjunto reduzido de moedas para o ciclo,
6. busca OHLCV,
7. calcula indicadores,
8. aplica filtro local rapido,
9. chama consenso de IA,
10. mede dinheiro forte, liquidez e historico por moeda/lado,
11. ranqueia oportunidades,
12. dispara o melhor sinal elegivel.

## 5.2 Validacao de sinal

O sinal so segue se:

- houver contexto tecnico minimo,
- o score final atingir o threshold,
- nao houver conflito entre lado da IA e tendencia macro,
- a moeda nao estiver aberta,
- ainda houver slot disponivel entre as 5 posicoes.

## 5.3 Reserva de slot

Antes de abrir um novo sinal, o sistema:

- normaliza o simbolo,
- verifica trades abertos,
- verifica reservas em andamento,
- bloqueia duplicidade,
- impede abrir acima do limite.

Isso reduz risco de corrida quando dois sinais aparecem quase juntos.

## 5.4 Distribuicao

Quando um sinal e aprovado:

- ele gera snapshot interno,
- entra no historico recente do dashboard,
- e replicado para clientes ativos,
- registra operacao/trilha no armazenamento disponivel.

## 5.5 Monitoramento e fechamento

As posicoes abertas:

- sao exibidas no dashboard,
- recebem preco ao vivo,
- calculam P&L aberto,
- permanecem ativas ate atingir TP ou SL,
- sao fechadas e registradas no historico quando a regra e atingida.

---

## 6. Logica estrategica

## 6.1 Motor local

O motor local usa principalmente:

- **SMA 200:** determina contexto macro,
- **Fibonacci 0.618:** identifica zona de interesse,
- **RSI:** evita entradas em exaustao extrema,
- **Volume ratio:** confirma participacao institucional.

O motor local gera um score base.

## 6.2 Groq

Papel:

- radar tatico,
- leitura de risco/candle,
- resposta curta em JSON,
- timeout curto para nao travar o loop.

Tratamento:

- retry curto no primeiro rate limit,
- cooldown global depois de limite repetido,
- fallback para `WAIT` quando indisponivel.

## 6.3 Gemini

Papel:

- estrategista cloud,
- leitura contextual,
- motivo descritivo da decisao,
- consulta do historico de aprendizado.

Tratamento:

- timeout curto,
- cooldown global em 429,
- fallback seguro quando a resposta vem invalida.

## 6.4 Consenso ponderado

Pesos atuais:

- **Gemini:** 40%
- **Groq:** 35%
- **Local:** 25%

Se os servicos cloud falham, o sistema pode:

- entrar em fallback automatico,
- ou operar em modo local only.

### 6.5.1 Papel soberano do 3o cerebro

Quando **Gemini e Groq falham ao mesmo tempo** por rate limit, timeout ou fallback simultaneo, o sistema ativa o **3o cerebro soberano**.

Nesse modo:

- o score final passa a ser **100% local**,
- a direcao da ordem passa a ser definida pela **tendencia macro**,
- **ALTA = BUY**,
- **BAIXA = SELL**,
- a entrada so e autorizada com **minimo de 80% de confianca**,
- se nao houver direcao valida ou o score ficar abaixo de 80%, a ordem e abortada.

Isso cria um modo de contingencia em que o motor continua operando com seguranca mesmo sem apoio das IAs cloud.

## 6.5 Travas soberanas

Mesmo com score alto, o sistema ainda pode abortar a entrada quando:

- nao existe macro tendencia valida,
- a IA cloud contradiz a tendencia macro,
- nao ha lado claro,
- o threshold minimo nao e atingido.

---

## 7. Regras operacionais atuais

Configuracao observada no codigo:

- **Threshold minimo:** 60%
- **Threshold minimo no fallback soberano do 3o cerebro:** 80%
- **Maximo de moedas simultaneas:** 5
- **Posicao unica:** desativada
- **Valor da ordem:** 5% da banca total do cliente
- **Take Profit:** 100%
- **Stop Loss:** 3%
- **Saida manual pelo painel:** disponivel para encerramento antecipado
- **Cooldown institucional:** 15 segundos
- **Top moedas por ciclo:** 8
- **Delay entre ativos no scanner:** 0.25 segundo

Observacao importante:

As regras operacionais atuais refletem o estado do codigo no momento desta documentacao. Mudancas de configuracao devem ser documentadas a cada release.

---

## 8. Modos de operacao

## 8.1 Modo teste

No modo teste:

- o saldo base pode vir do formulario,
- o cliente nao depende da validacao real da Bybit,
- a operacao e usada para treino/controladoria,
- o dashboard acompanha P&L e slots ativos.

## 8.2 Modo real

No modo real:

- os saldos podem ser lidos da Bybit,
- as credenciais precisam ser validas,
- o risco operacional e maior,
- a monitoracao deve ser mais rigorosa.

## 8.3 Status real do codigo

No estado atual do projeto, existe uma flag:

- `EXECUTE_TRADES_REAL = False`

Isso significa que a base atual esta mais alinhada com **paper trading, simulacao controlada e validacao operacional**. Qualquer ativacao de operacao real deve passar por:

- homologacao,
- testes adicionais,
- revisao de risco,
- checklist de credenciais,
- revisao de saida e contingencia.

---

## 9. Gestao de clientes / investidores

O sistema possui camada de cadastro para clientes com campos como:

- nome,
- saldo base,
- modo teste ou real,
- chave Bybit,
- segredo Bybit,
- token Telegram,
- chat id.

### Responsabilidades desta camada

- centralizar cadastro,
- armazenar dados de integracao,
- suportar uso local ou cloud,
- refletir origem do dado no dashboard,
- permitir operacao para varios clientes.

### Fontes de armazenamento

- **Local:** SQLite
- **Cloud:** Supabase

### Regra de fallback

Se o Supabase estiver indisponivel ou com schema invalido, o sistema desativa a nuvem na sessao e continua localmente.

---

## 10. Seguranca

## 10.1 Segredos e credenciais

Boas praticas aplicadas:

- `.env` fora do Git,
- banco local fora do Git,
- logs fora do Git,
- arquivo `.env.example` sem segredos reais,
- criptografia de campos sensiveis antes do envio ao Supabase.

Campos protegidos no fluxo cloud:

- `bybit_key`
- `bybit_secret`
- `tg_token`
- `tg_api_key`
- `chat_id`

## 10.2 Fallback seguro

Quando o Supabase falha por tabela ausente/schema cache:

- a nuvem e desligada na sessao,
- o sistema cai para local,
- evita spam continuo de erro.

## 10.3 Recomendacoes de seguranca

Para producao, recomenda-se:

1. usar uma chave dedicada em `SUPABASE_CLIENTS_SECRET`,
2. rotacionar segredos periodicamente,
3. restringir acesso ao dashboard,
4. usar HTTPS e proxy reverso,
5. separar ambiente teste e producao,
6. limitar permissao das chaves da exchange,
7. ativar logs estruturados e alertas.

---

## 11. Escalabilidade

O projeto ja possui algumas bases de escalabilidade:

- frontend separado do backend,
- cache de tickers,
- filtro local antes da IA,
- cooldowns para evitar tempestade de requests,
- suporte multiativo,
- storage cloud opcional.

### Pontos prontos para evolucao

- separacao do worker de scanner em processo proprio,
- fila de sinais,
- fila de escrita em banco,
- cache distribuido,
- API autenticada multiusuario,
- isolamento por cliente/tenant,
- observabilidade e metricas.

### Limitacoes atuais

- estado global em memoria no backend,
- SQLite como base local principal,
- fluxo concentrado em um unico processo Flask,
- ausencia de auth forte de usuarios no painel,
- dependencia de servicos externos para parte da inteligencia.

---

## 12. Responsabilidades

## 12.1 Responsabilidade do sistema

O sistema se propoe a:

- analisar mercado,
- sugerir/executar fluxo operacional conforme configuracao,
- manter historico,
- mostrar status,
- reduzir erros manuais.

## 12.2 Responsabilidade do operador

O operador e responsavel por:

- configurar chaves corretamente,
- validar ambiente de teste antes de usar capital real,
- acompanhar travas, limites e logs,
- revisar risco e exposicao,
- manter backup de configuracoes,
- revisar resultados reais antes de escalar banca.

## 12.3 Responsabilidade frente ao cliente

Quem oferece este sistema a clientes deve:

- explicar que trading envolve risco real,
- nao prometer lucro garantido,
- deixar claro modo teste x modo real,
- explicar as regras operacionais,
- informar limites tecnicos,
- manter politicas de seguranca e privacidade.

---

## 13. Riscos e limitacoes

Principais riscos tecnicos:

1. **Rate limit de IA**
   - pode atrasar ou empobrecer validacao cloud.
   - quando Gemini e Groq falham juntos, o 3o cerebro assume com regra de 80%.

2. **Falha externa de API**
   - Bybit, Groq, Gemini e Supabase podem sofrer indisponibilidade.

3. **Divergencia entre ambiente e mercado**
   - paper trading nao reproduz perfeitamente conta real.

4. **Risco de dados ruins**
   - OHLCV incompleto, preco nulo ou resposta invalida podem degradar o sinal.

5. **Risco operacional humano**
   - credenciais incorretas, configuracoes erradas e uso sem homologacao.

6. **Risco financeiro**
   - mesmo com regras, perdas podem ocorrer.

Risco comercial/juridico:

- nunca vender o produto como garantia de retorno,
- sempre comunicar que se trata de automacao com risco de mercado,
- manter termo de uso e aceite de risco para clientes finais.

---

## 14. Orientacao para clientes finais

## 14.1 O que o cliente precisa entender

Antes de usar, o cliente deve saber:

- o sistema nao elimina risco,
- modo teste e diferente de conta real,
- lucro passado nao garante lucro futuro,
- APIs externas podem falhar,
- latencia e mercado podem afetar resultado.

## 14.2 O que precisa ser informado ao cliente

- como o saldo sera usado,
- que cada ordem usa 5% da banca total,
- quais chaves serao cadastradas,
- se a conta esta em modo teste ou real,
- quais sao as regras atuais de TP e SL,
- que existe limite de ate 5 posicoes simultaneas,
- como o painel deve ser interpretado.

## 14.3 Sugestao de texto comercial/responsavel

> O Motor Sniper e uma plataforma de apoio e automacao operacional para trading. Ele utiliza analise tecnica, regras de risco e consenso de IA para qualificar sinais. Apesar de possuir controles operacionais, toda operacao em mercado envolve risco e nao ha garantia de rentabilidade.

---

## 15. Checklist de onboarding de cliente

Antes de ativar um cliente:

1. confirmar nome e identificacao interna,
2. validar se sera modo teste ou real,
3. validar saldo base,
4. validar chaves e segredos,
5. validar Telegram/chat id,
6. informar regras de TP/SL,
7. informar limite de posicoes simultaneas,
8. registrar aceite de risco,
9. testar leitura do painel,
10. iniciar com banca pequena.

---

## 16. Guia de operacao interna

### Inicio de ambiente

1. configurar `.env`,
2. instalar dependencias Python,
3. instalar dependencias Node,
4. subir backend,
5. subir/buildar frontend,
6. validar endpoints,
7. validar painel.

### Rotina de operacao

1. acompanhar status do motor,
2. acompanhar slots ativos,
3. acompanhar oportunidades ranqueadas,
4. validar se a nuvem esta online ou em fallback local,
5. validar clientes ativos,
6. revisar trades fechados e P&L.

### Rotina de contingencia

Se houver erro:

- revisar log,
- revisar conectividade de APIs,
- revisar cooldown/rate limit,
- revisar Supabase,
- revisar banco local,
- pausar migracao para conta real se necessario.

---

## 17. Estrutura de pastas relevante

```text
main_web.py
main.jsx
src/
  ai_brain/
    validator.py
    learning.py
  broker/
    bybit_client.py
  database/
    manager.py
    supabase_manager.py
  engine/
    indicators.py
tools/
  supabase_schema.sql
tests/
```

---

## 18. Variaveis de ambiente esperadas

Principais variaveis:

- `USE_TESTNET`
- `BYBIT_API_KEY`
- `BYBIT_API_SECRET`
- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GEMINI_API_KEY`
- `GROQ_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_CLIENTS_SECRET`
- `VITE_API_BASE`

---

## 19. Estado recomendado para entrega a cliente

Para entregar com mais seguranca, recomenda-se:

1. manter documentacao e versao alinhadas,
2. isolar ambiente de homologacao,
3. iniciar clientes em modo teste,
4. ativar conta real apenas apos validacao,
5. manter backup dos dados de clientes,
6. publicar politica de risco e privacidade,
7. manter rotina de revisao tecnica.

---

## 20. Conclusao executiva

O Motor Sniper v60.7 e uma base funcional de trading automatizado com boa visibilidade operacional, integracao multi-camada e estrutura pronta para crescer. O sistema ja possui:

- painel operacional,
- logica tecnica,
- consenso de IA,
- cadastro de clientes,
- fallback local/cloud,
- protecao basica de credenciais,
- monitoramento multiativo.

Ao mesmo tempo, ele deve ser tratado com postura profissional:

- sem promessas irreais,
- com gestao de risco,
- com homologacao antes da conta real,
- com documentacao clara para equipe e clientes,
- com evolucao continua de seguranca e escalabilidade.
