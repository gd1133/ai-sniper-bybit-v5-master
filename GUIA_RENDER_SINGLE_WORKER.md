# 🚀 Guia de Configuração Render com Single Worker + Crash-Proof

## 📋 Problema Resolvido

Este guia documenta as correções implementadas para resolver 3 problemas críticos no deploy do bot Sniper na plataforma Render:

1. **Isolamento de Memória entre Workers**: Múltiplos workers do Gunicorn destruíam o padrão Singleton/Cache
2. **Thread Morrendo Silenciosamente**: O motor de trading parava sem logs ou avisos
3. **Falta de Visibilidade**: Impossível saber se o bot estava realmente operando

## ✅ Solução Implementada

### 1. 🔧 Comando de Inicialização com Single Worker

O arquivo `render.yaml` já está configurado corretamente com **apenas 1 worker**:

```yaml
startCommand: python -m gunicorn main_web:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
```

**Por que apenas 1 worker?**
- ✅ Preserva o padrão Singleton do `BrokerManager`
- ✅ Mantém cache de tickers em memória unificado
- ✅ Garante que a Thread de background funcione corretamente
- ✅ Elimina isolamento de processos que causava variação no tamanho da resposta HTTP

**IMPORTANTE**: Se você estiver configurando manualmente no painel do Render (não usando `render.yaml`), use o seguinte comando no campo "Start Command":

```bash
python -m gunicorn main_web:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
```

### 2. 🛡️ Crash-Proofing Total na Thread do Motor

O loop principal em `main_web.py` (função `sniper_worker_loop()`) agora possui:

#### **Proteção Robusta contra Crashes**

```python
while True:
    try:
        # ... todo o código do motor ...
    except Exception as e:
        # 🛡️ CRASH-PROOFING TOTAL
        error_type = type(e).__name__
        error_msg = str(e)

        print(f"❌ [MOTOR CHAVE - ERRO CAPTURADO] Tipo: {error_type}", flush=True)
        print(f"   Detalhes: {error_msg}", flush=True)
        print(f"   🔄 Recuperando em 10 segundos e continuando operação...", flush=True)

        # Pausa de 10 segundos antes de continuar
        time.sleep(10)

        # NUNCA deixa a Thread morrer - sempre continua o loop
        print(f"✅ [MOTOR CHAVE - RECUPERADO] Thread retomando operação normal", flush=True)
```

**Comportamento:**
- ✅ Captura **TODOS** os erros (rede, timeout, API, etc.)
- ✅ Loga tipo e detalhes do erro com `flush=True`
- ✅ Aguarda 10 segundos para recuperação
- ✅ **NUNCA** permite que a Thread morra
- ✅ Continua operando mesmo após erros críticos

### 3. 💓 Heartbeat Logging (Batimento Cardíaco)

Cada ciclo do loop agora inicia com um log explícito:

```python
while True:
    try:
        # 🔄 HEARTBEAT - Log de batimento cardíaco para monitoramento ativo
        print("🔄 [MOTOR CHAVE] Iniciando novo ciclo de varredura do mercado...", flush=True)

        # ... resto do código ...
```

**Benefícios:**
- ✅ Visibilidade em tempo real no terminal do Render
- ✅ Confirmação de que o motor está ativo
- ✅ Possibilita diagnóstico imediato de travamentos
- ✅ `flush=True` garante que o log aparece imediatamente (sem buffer)

## 🎯 Verificação no Render

### Como Monitorar o Bot no Render

1. **Acesse o Dashboard do Render** → Entre no seu serviço
2. **Vá para a aba "Logs"**
3. **Procure pelos seguintes indicadores:**

```
✅ Sinais Saudáveis:
🔄 [MOTOR CHAVE] Iniciando novo ciclo de varredura do mercado...
🔧 [MASTER BROKER] Modo REAL inicializado com investidor ativo do SQLite.
🚀 Motor Sniper v60.1 Operante. Rigor: 75%
🔍 Radar: BTCUSDT (1/50)

⚠️ Sinais de Problemas (agora com recuperação automática):
❌ [MOTOR CHAVE - ERRO CAPTURADO] Tipo: NetworkError
   Detalhes: Connection timeout
   🔄 Recuperando em 10 segundos e continuando operação...
✅ [MOTOR CHAVE - RECUPERADO] Thread retomando operação normal
```

### Frequência Esperada dos Logs

- **Heartbeat (`🔄 [MOTOR CHAVE]`)**: A cada 15-60 segundos (depende do ciclo)
- **Radar (`🔍 Radar`)**: Durante varredura de ativos
- **Erros Capturados**: Apenas quando ocorrem problemas (com recuperação automática)

## 🔍 Troubleshooting

### Problema: Não vejo logs de heartbeat

**Solução:**
1. Verifique se o serviço está rodando: olhe se há logs recentes
2. Confirme que há um investidor ativo com credenciais no SQLite
3. Reinicie o serviço no Render se necessário

### Problema: Vejo muitos erros capturados

**Comportamento Normal:**
- O sistema agora **captura e loga todos os erros**, mas continua funcionando
- Erros ocasionais de rede/timeout da Bybit são esperados
- O bot se recupera automaticamente após 10 segundos

**Quando Preocupar:**
- Se você vê **o mesmo erro continuamente** (mais de 10x seguidas)
- Se não há **nenhum ciclo bem-sucedido** entre os erros

### Problema: Resposta HTTP variando de tamanho

**Causa:** Múltiplos workers isolando memória (problema resolvido)

**Solução Aplicada:**
- `render.yaml` configurado com `--workers 1`
- Apenas um processo mantém o estado global

**Verificação:**
```bash
# No terminal local, teste a API várias vezes:
curl https://seu-app.onrender.com/api/status

# O tamanho da resposta deve ser CONSISTENTE agora
```

## 📊 Arquitetura Singleton Protegida

```
┌─────────────────────────────────────────┐
│  GUNICORN (--workers 1)                 │
│  ├─ Processo Único do Python            │
│     ├─ Flask App (HTTP Server)          │
│     ├─ BrokerManager (Singleton) ✅     │
│     ├─ central_state (Cache Global) ✅  │
│     └─ Thread Background                │
│        └─ sniper_worker_loop()          │
│           ├─ 🔄 Heartbeat Logging       │
│           ├─ 🛡️ Try-Except Robusto     │
│           └─ ⏰ Sleep(10) + Retry       │
└─────────────────────────────────────────┘
```

## 📝 Checklist de Deploy no Render

- [x] `render.yaml` com `--workers 1` configurado
- [x] Heartbeat logging implementado no loop principal
- [x] Try-except robusto capturando todos os erros
- [x] Sleep de 10 segundos em caso de erro
- [x] Logs com `flush=True` para visibilidade imediata
- [x] Thread nunca morre (continua após erros)

## 🎓 Lições Aprendidas

1. **Gunicorn Multi-Worker** ≠ Ideal para apps com estado local
2. **Threads de Background** precisam de proteção robusta contra crashes
3. **Heartbeat Logging** é essencial para diagnóstico remoto
4. **flush=True** garante que logs apareçam imediatamente no Render
5. **Recuperação Automática** > Deixar a aplicação morrer silenciosamente

## 🔗 Referências

- Arquivo modificado: `main_web.py` (linhas 2065-2310)
- Configuração: `render.yaml` (linha 10)
- Função principal: `sniper_worker_loop()`

---

**Desenvolvido por:** Time de Desenvolvimento Sniper
**Versão do Sistema:** v60.1+
**Data de Implementação:** 2026-05-20
