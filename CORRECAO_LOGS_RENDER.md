# Correção: Logs em Tempo Real no Render/Gunicorn

## 🎯 Problema Identificado

O robô de trading já estava corretamente estruturado com threads separadas para o motor de trading, MAS os logs não apareciam em tempo real no Render devido à **falta do parâmetro `flush=True`** nos comandos `print()`.

### Sintomas

- ✅ API HTTP respondia normalmente (`/api/status` funcionando)
- ❌ Logs do motor de trading não apareciam ou demoravam muito
- ❌ Impossível verificar se o loop estava executando
- ❌ Debugging em produção era impossível

## ✅ Solução Implementada

### 1. Adicionado `flush=True` em todos os prints críticos

#### Inicialização das threads (linha 361-368)
```python
threading.Thread(target=sniper_worker_loop, daemon=True).start()
print("🔄 [THREADING] Motor Sniper inicializado em thread daemon", flush=True)
threading.Thread(target=_monitor_sl_tp_automatico, daemon=True).start()
print("   Monitor SL/TP: ATIVO (-5% SL / +100% TP)", flush=True)
```

#### Loop principal do motor (linha 1787)
```python
while True:
    try:
        # Log de heartbeat para confirmar execução
        print(f"🔄 [MOTOR] Varrendo o mercado em busca de sinais... [{datetime.now().strftime('%H:%M:%S')}]", flush=True)
        # ...
```

#### Logs de análise (linha 1826)
```python
print(f"DEBUG {clean_sym}: Trend {signals['trend']} | Price {signals['price']} | SMA {signals['sma_200']}", flush=True)
```

#### Logs de erro (linha 1970-1974)
```python
except Exception as e:
    print(f"⚠️ [LOOP SCAN] Erro durante varredura: {e}", flush=True)
    time.sleep(15)
```

#### Broadcast de ordens (linha 2440-2443)
```python
print(f"\n🔍 [BROADCAST] Iniciando execução para {len(clientes)} cliente(s) ativo(s)", flush=True)
print(f"   💼 ALLOW_ORDER_EXECUTION: {ALLOW_ORDER_EXECUTION}", flush=True)
print(f"   🔐 ALLOW_REAL_TRADING: {ALLOW_REAL_TRADING}", flush=True)
```

#### Diagnóstico de startup (linha 2676-2707)
```python
print("\n" + "="*70, flush=True)
print("🔍 DIAGNÓSTICO DE CONFIGURAÇÃO DO SISTEMA", flush=True)
print("="*70, flush=True)
print(f"📌 ENVIRONMENT: {ENV_CONFIG.name}", flush=True)
# ... todos os prints do diagnóstico
```

### 2. Log de heartbeat com timestamp

Adicionado log explícito no início de cada iteração do loop principal:

```python
print(f"🔄 [MOTOR] Varrendo o mercado em busca de sinais... [{datetime.now().strftime('%H:%M:%S')}]", flush=True)
```

Este log aparece a cada 60 segundos e confirma que:
- ✅ O motor está executando
- ✅ O timestamp mostra quando aconteceu
- ✅ Permite rastrear se há travamentos

### 3. Melhorias nos logs de erro

Agora os erros mostram mais detalhes:

```python
except Exception as e:
    print(f"⚠️ [LOOP SCAN] Erro durante varredura: {e}", flush=True)
```

Antes era apenas `except Exception:` (silencioso).

## 📊 Arquitetura Confirmada

O código JÁ tinha a arquitetura correta de threading:

### ✅ Thread separada para o motor
```python
# Linha 360
threading.Thread(target=sniper_worker_loop, daemon=True).start()
```

### ✅ Loop infinito com sleep adequado
```python
# Linha 1784
while True:
    try:
        # Lógica de trading...
        time.sleep(60)  # 60s entre ciclos
    except Exception as e:
        time.sleep(15)  # 15s em caso de erro
```

### ✅ Broker Manager compartilhado
```python
# Linha 1761 - instância única criada dentro da thread
master_broker = BybitClient(*get_bybit_credentials(), testnet=False)
```

### ✅ Proteção contra inicialização múltipla
```python
# Linha 356
with RUNTIME_START_LOCK:
    if RUNTIME_STARTED:
        return False
    # ... inicializa threads
    RUNTIME_STARTED = True
```

## 🔍 Como Verificar no Render

### 1. Acesse os logs do Render

```
Dashboard > Seu serviço > Logs
```

### 2. Procure pelos seguintes logs na ordem:

```
======================================================================
🔍 DIAGNÓSTICO DE CONFIGURAÇÃO DO SISTEMA
======================================================================
📌 ENVIRONMENT: production
📌 ALLOW_ORDER_EXECUTION: True
📌 ALLOW_REAL_TRADING: True
📌 USE_TESTNET: False
📌 APP_MODE: real
📌 Execução de ordens: ✅ HABILITADA
📌 Clientes ativos: X
======================================================================

🔄 [THREADING] Motor Sniper inicializado em thread daemon
   Monitor SL/TP: ATIVO (-5% SL / +100% TP)
⚡ Cache de saldo: aquecendo em background...
✅ DuoIA Maestro v60.1 Online na Porta 10000
🧭 Modo operacional: REAL MODE
⚡ Execução: Ordens reais ativas
📊 Dashboard: http://0.0.0.0:10000
🧠 Cérebro Triplo: ATIVO (Rigor 50%)

⏳ Carregando dependências pesadas (primeira vez)...
✅ Dependências carregadas com sucesso
🔧 [MASTER BROKER] Modo: REAL (testnet=False)
🚀 Motor Sniper v60.1 Operante. Rigor: 60%
💼 REAL MODE - Saldo inicial sincronizado dos clientes

🔄 [MOTOR] Varrendo o mercado em busca de sinais... [14:32:15]
DEBUG BTCUSDT: Trend bullish | Price above_sma | SMA bullish
DEBUG ETHUSDT: Trend bearish | Price below_sma | SMA bearish
...

🔄 [MOTOR] Varrendo o mercado em busca de sinais... [14:33:15]
...
```

### 3. Sinais de que está funcionando

- ✅ Você vê `🔄 [MOTOR] Varrendo o mercado...` a cada ~60 segundos
- ✅ Você vê análises de moedas (`DEBUG BTCUSDT: ...`)
- ✅ Os timestamps são recentes (não atrasados)
- ✅ Não há erros repetidos

### 4. Sinais de problema

- ❌ Não vê `🔄 [THREADING] Motor Sniper inicializado`
- ❌ Não vê logs de varredura (`🔄 [MOTOR]`)
- ❌ Vê `❌ Erro ao carregar dependências`
- ❌ Vê `⚠️ [LOOP ERRO]` repetidamente

## 🐛 Troubleshooting

### Problema: "Motor não inicia"

**Sintomas**: Não aparece `🔄 [THREADING] Motor Sniper inicializado`

**Causas possíveis**:
1. `start_runtime_services()` não foi chamado
2. Erro antes da inicialização das threads

**Solução**:
- Verificar logs ANTES da linha de inicialização
- Procurar por exceções Python

### Problema: "Motor inicia mas não varre"

**Sintomas**: Aparece log de inicialização mas não vê `🔄 [MOTOR] Varrendo o mercado...`

**Causas possíveis**:
1. Exceção dentro do loop principal
2. Travamento em alguma operação (fetch_tickers, etc.)

**Solução**:
- Procurar por `⚠️ [LOOP ERRO]` ou `⚠️ [LOOP SCAN]`
- Verificar conectividade com Bybit API

### Problema: "Logs aparecem mas com atraso"

**Sintomas**: Logs aparecem mas com 1-2 minutos de atraso

**Causas possíveis**:
1. Ainda há prints sem `flush=True`
2. Problema no Render (raro)

**Solução**:
- Verificar se TODOS os prints têm `flush=True`
- Redeployar o serviço

## 📦 Arquivos Modificados

### `main_web.py`
- ✅ Linha 361-368: Inicialização das threads com flush
- ✅ Linha 1747-1756: Carregamento de dependências com flush
- ✅ Linha 1766-1773: Inicialização do broker com flush
- ✅ Linha 1787: Heartbeat do loop com timestamp
- ✅ Linha 1826: Logs de análise com flush
- ✅ Linha 1970-1974: Logs de erro com flush
- ✅ Linha 2440-2443: Logs de broadcast com flush
- ✅ Linha 2676-2707: Diagnóstico de startup com flush

### Documentação criada
- ✅ `docs/THREADING_ARCHITECTURE.md`: Documentação completa da arquitetura
- ✅ `CORRECAO_LOGS_RENDER.md`: Este documento

## ✅ Resultado Final

Agora você consegue:

1. ✅ Ver logs do motor de trading em tempo real
2. ✅ Confirmar que o loop está executando (heartbeat a cada 60s)
3. ✅ Debugar problemas em produção
4. ✅ Verificar análises de moedas em tempo real
5. ✅ Confirmar execução de ordens
6. ✅ Rastrear erros imediatamente

## 🚀 Próximos Passos

1. **Deploy no Render**:
   ```bash
   git push origin main
   ```

2. **Verificar logs**:
   - Acesse o painel do Render
   - Vá em Logs > Live Logs
   - Procure por `🔄 [THREADING] Motor Sniper inicializado`

3. **Monitorar execução**:
   - Procure por `🔄 [MOTOR] Varrendo o mercado...` a cada ~60s
   - Verifique timestamps recentes

4. **Testar API**:
   ```bash
   curl https://seu-app.onrender.com/api/status
   ```

## 📚 Referências

- **Documentação completa**: `docs/THREADING_ARCHITECTURE.md`
- **Código principal**: `main_web.py`
- **Deploy no Render**: `docs/RENDER_DEPLOYMENT.md`

---

**Data da correção**: 2026-05-20
**Commit**: `Add flush=True to all critical logs for real-time visibility on Render/Gunicorn`
**Status**: ✅ Resolvido
