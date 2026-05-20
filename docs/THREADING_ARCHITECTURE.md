# Arquitetura de Threading do Robô de Trading

## 🎯 Visão Geral

O robô está estruturado para rodar em **servidores web WSGI (Gunicorn/Render)** com a lógica de trading executando em **threads separadas** para não bloquear as requisições HTTP.

## 🏗️ Estrutura de Threads

### 1. Thread Principal (Main Thread)
- **Responsabilidade**: Servidor Flask/Gunicorn
- **Função**: Responder às requisições HTTP (`/api/status`, `/api/trades`, etc.)
- **Status**: NUNCA bloqueia

### 2. Thread do Motor Sniper (`sniper_worker_loop`)
- **Responsabilidade**: Varredura do mercado e geração de sinais
- **Função**: Loop contínuo (`while True`) que:
  - Busca os ativos com maior volume na Bybit
  - Calcula indicadores técnicos (RSI, MACD, SMA, etc.)
  - Consulta os 3 cérebros de IA (Groq, Gemini, Local Brain)
  - Executa ordens quando há confluência >= 60%
- **Intervalo**: 60 segundos entre ciclos completos
- **Tipo**: `daemon=True` (encerra automaticamente ao fechar o servidor)
- **Inicialização**: Linha 360 de `main_web.py`

### 3. Thread de Monitor SL/TP (`_monitor_sl_tp_automatico`)
- **Responsabilidade**: Monitoramento de Stop Loss e Take Profit
- **Função**: Loop contínuo que fecha posições automaticamente quando:
  - Perda atinge -5% (Stop Loss)
  - Lucro atinge +100% (Take Profit)
- **Intervalo**: 10 segundos entre verificações
- **Tipo**: `daemon=True`
- **Inicialização**: Linha 362 de `main_web.py`

### 4. Thread de Cache de Saldo (Background)
- **Responsabilidade**: Aquecimento do cache de saldos
- **Função**: Busca os saldos de todos os clientes ativos ao iniciar
- **Execução**: Uma vez no startup
- **Tipo**: `daemon=True`
- **Inicialização**: Linha 367 de `main_web.py`

## 🚀 Inicialização

### Função: `start_runtime_services()` (linha 352)

```python
def start_runtime_services():
    """Inicia as threads do robô uma única vez, inclusive sob gunicorn/wsgi."""
    global RUNTIME_STARTED

    with RUNTIME_START_LOCK:
        if RUNTIME_STARTED:
            return False

        # Inicia Motor Sniper
        threading.Thread(target=sniper_worker_loop, daemon=True).start()
        print("🔄 [THREADING] Motor Sniper inicializado em thread daemon", flush=True)

        # Inicia Monitor SL/TP
        threading.Thread(target=_monitor_sl_tp_automatico, daemon=True).start()
        print("   Monitor SL/TP: ATIVO (-5% SL / +100% TP)", flush=True)

        # Aquece cache de saldo
        threading.Thread(target=_fetch_active_client_balances, kwargs={'force': True}, daemon=True).start()
        print("⚡ Cache de saldo: aquecendo em background...", flush=True)

        RUNTIME_STARTED = True
        return True
```

### Proteção contra inicialização múltipla

- **Lock**: `RUNTIME_START_LOCK` (threading.Lock)
- **Flag**: `RUNTIME_STARTED` (boolean global)
- **Motivo**: Gunicorn pode criar múltiplos workers; apenas o primeiro inicializa as threads

## 📊 Loop Principal do Motor Sniper

### Estrutura do Loop (linha 1784)

```python
while True:
    try:
        # 1. Log de heartbeat (confirmação de que está rodando)
        print(f"🔄 [MOTOR] Varrendo o mercado em busca de sinais... [{datetime.now().strftime('%H:%M:%S')}]", flush=True)

        # 2. Reparo de trades órfãos no banco
        _repair_open_trades()
        _close_stale_open_trades(max_age_minutes=180)

        # 3. Verificar se já atingiu MAX_MOEDAS_ATIVAS
        if len(central_state['active_trades']) >= MAX_MOEDAS_ATIVAS:
            time.sleep(5)
            continue

        # 4. Buscar top 8 moedas por volume
        tickers = master_broker.exchange.fetch_tickers(params={'category': 'linear'})
        top_coins = sorted([...], key=lambda x: x.get('quoteVolume', 0), reverse=True)[:8]

        # 5. Analisar cada moeda
        for t in top_coins:
            df = master_broker.fetch_ohlcv(sym, timeframe='15m')
            signals = IndicatorEngine(df).get_signals()

            # 6. Consultar IA
            res = validator.consensus_predict(signals, sym)

            if prob >= 60 and decisao in ['COMPRAR', 'VENDER']:
                # 7. Executar ordem via broadcast
                broadcast_ordem_global(...)

            time.sleep(5)  # Anti rate-limit entre moedas

        time.sleep(60)  # Aguardar 60s antes do próximo ciclo
    except Exception as e:
        print(f"⚠️ [LOOP ERRO] {e}", flush=True)
        time.sleep(15)
```

## 🔧 Importância do `flush=True`

### Problema

Em ambientes de produção (Render, Railway, Gunicorn), os logs são **bufferizados** por padrão. Isso significa:

- ❌ Logs podem demorar minutos para aparecer
- ❌ Logs podem ser perdidos se o processo morrer
- ❌ Impossível debugar em tempo real

### Solução

Adicionar `flush=True` em **todos os prints críticos**:

```python
print("🔄 [MOTOR] Varrendo o mercado...", flush=True)  # ✅ Aparece imediatamente
print("✅ Ordem executada", flush=True)                 # ✅ Aparece imediatamente
print("❌ Erro ao conectar")                            # ❌ Pode demorar minutos
```

### Locais onde `flush=True` foi adicionado

1. ✅ Inicialização das threads (linha 361-368)
2. ✅ Início do loop do motor (linha 1787)
3. ✅ Logs de debug de análise (linha 1826)
4. ✅ Logs de erro do loop (linha 1970-1974)
5. ✅ Broadcast de ordens (linha 2440-2443)
6. ✅ Diagnóstico de startup (linha 2676-2707)

## 🐛 Debugging

### Ver logs em tempo real no Render

```bash
# No painel do Render
Logs > Live Logs

# Procure por:
🔄 [THREADING] Motor Sniper inicializado em thread daemon
🚀 Motor Sniper v60.1 Operante. Rigor: 60%
🔄 [MOTOR] Varrendo o mercado em busca de sinais... [HH:MM:SS]
```

### Verificar se o motor está rodando

1. **Via Logs**: Procure por `🔄 [MOTOR] Varrendo o mercado...` aparecendo a cada 60s
2. **Via API**: `GET /api/status` - campo `status` deve mostrar atividade
3. **Via Dashboard**: Painel deve atualizar automaticamente

### Problemas comuns

| Sintoma | Causa | Solução |
|---------|-------|---------|
| Logs não aparecem | Falta `flush=True` | ✅ Já corrigido |
| Motor não inicia | Erro na importação de libs | Verificar logs de `❌ Erro ao carregar dependências` |
| API responde mas motor parado | Thread não inicializada | Verificar se `start_runtime_services()` foi chamado |
| Logs aparecem mas sem varredura | Exceção silenciosa no loop | Adicionar try/except com log |

## 🔒 Compartilhamento de Estado

### `central_state` (dict global)

Todas as threads compartilham o mesmo dicionário `central_state`:

```python
central_state = {
    'status': 'Inicializando...',
    'symbol': '---',
    'confidence': 0,
    'balance': 0.0,
    'active_trades': [],
    'opportunities': [],
    'trades': [],
    # ...
}
```

- **Motor Sniper**: Escreve `status`, `symbol`, `confidence`, `opportunities`
- **API Routes**: Leem todos os campos
- **Monitor SL/TP**: Lê `active_trades`, escreve resultados

### Thread Safety

- ✅ Leitura: Thread-safe (Python GIL)
- ⚠️ Escrita: Geralmente segura para dicts em CPython
- 🔒 Sincronização crítica: `SNIPER_SIGNAL_LOCK` para reserva de sinais

## 📦 Broker Manager Global

### Instância única do broker

```python
master_broker = BybitClient(*get_bybit_credentials(), testnet=False)
```

- **Criado em**: `sniper_worker_loop` (linha 1761)
- **Usado por**: Apenas a thread do motor sniper
- **Clientes individuais**: Cada cliente tem sua própria instância em `broadcast_ordem_global`

## ✅ Checklist de Verificação

Antes de fazer deploy no Render/Gunicorn, verifique:

- [x] `start_runtime_services()` é chamado no `__main__` (linha 2701)
- [x] Threads criadas com `daemon=True`
- [x] Todos os prints críticos têm `flush=True`
- [x] Loop principal tem try/except com log de erro
- [x] `use_reloader=False` no `app.run()` (evita duplicar threads)
- [x] Lock para evitar inicialização múltipla

## 🚀 Deploy no Render

### Configuração recomendada

```bash
# Comando de start
gunicorn main_web:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120

# Ou simplesmente
python main_web.py
```

**Importante**: Use `--workers 1` para evitar múltiplas instâncias do motor de trading.

### Variáveis de ambiente essenciais

```bash
ENVIRONMENT=production
BYBIT_API_KEY=sua_key
BYBIT_API_SECRET=seu_secret
GEMINI_API_KEY=sua_key
GROQ_API_KEY=sua_key
TELEGRAM_TOKEN=seu_token
TELEGRAM_CHAT_ID=seu_chat_id
```

## 📚 Referências

- **Arquivo principal**: `main_web.py`
- **Função de inicialização**: `start_runtime_services()` (linha 352)
- **Loop do motor**: `sniper_worker_loop()` (linha 1742)
- **Monitor SL/TP**: `_monitor_sl_tp_automatico()` (linha 1447)
- **Broadcast de ordens**: `broadcast_ordem_global()` (linha 2377)

---

**Última atualização**: 2026-05-20
**Versão do sistema**: v60.1
