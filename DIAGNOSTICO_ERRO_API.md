# 🔍 Diagnóstico de Erros de API - IA Sniper Bot

## Problema Identificado

Você está vendo a mensagem:
```
❌ [ERRO API] Ambos APIs falharam. Abortando operação para expor erro real.
```

## Causa Raiz

O sistema usa **3 cérebros de IA** para análise de trading:
1. **Cérebro Local** (matemático - sempre funciona)
2. **Groq API** (análise tática - pode falhar)
3. **Gemini API** (análise estratégica - pode falhar)

Quando **ambos Groq e Gemini falham**, o sistema aborta a operação para evitar decisões baseadas apenas em análise local.

## Possíveis Causas

### 1. Chaves API Não Configuradas ❌
**Sintoma:**
```
Groq: Cliente Groq não inicializado
Gemini: Erro de conexão
```

**Solução:**
```bash
# Verifique se as chaves estão configuradas no .env
echo $GEMINI_API_KEY
echo $GROQ_API_KEY
```

Se estiverem vazias, configure:
```bash
# .env ou variáveis de ambiente Railway
GEMINI_API_KEY=YOUR_ACTUAL_GEMINI_KEY
GROQ_API_KEY=YOUR_ACTUAL_GROQ_KEY
```

**Como obter as chaves:**
- Gemini: https://makersuite.google.com/app/apikey
- Groq: https://console.groq.com/keys

---

### 2. Rate Limit Excedido ⏱️
**Sintoma:**
```
Groq: Rate limit: Error 429
Gemini: Rate limit 429 - muitas requisições
```

**Solução:**
- O sistema agora entra automaticamente em **cooldown**:
  - Groq: 90 segundos
  - Gemini: 120 segundos
- Aguarde o cooldown terminar
- Considere reduzir a frequência de análise (se estiver em loop muito rápido)

**Para APIs gratuitas:**
- Gemini: ~60 requisições/minuto
- Groq: ~30 requisições/minuto

---

### 3. Timeout de Conexão 🌐
**Sintoma:**
```
Gemini: Timeout após 5s - API não respondeu
Groq: Falha após 2 tentativas: timeout
```

**Solução:**
- Verifique sua conexão com a internet
- APIs podem estar temporariamente indisponíveis
- O sistema já possui retry automático (2 tentativas)
- Se persistir, pode ser problema de firewall ou proxy

---

### 4. Erro de Autenticação 🔑
**Sintoma:**
```
Gemini: HTTP 401: Unauthorized
Gemini: HTTP 403: Forbidden
```

**Solução:**
- Chave API inválida ou expirada
- Regenere a chave no console da API
- Verifique se copiou a chave completa (sem espaços)

---

## Melhorias Implementadas ✅

### Antes:
```
❌ [ERRO API] Ambos APIs falharam. Abortando operação para expor erro real.
```

### Agora:
```
❌ [ERRO API] Groq: Rate limit: Error 429 | Gemini: Timeout após 5s - API não respondeu
💡 Dica: Verifique se as chaves GEMINI_API_KEY e GROQ_API_KEY estão configuradas corretamente
💡 Dica: Verifique se você não atingiu o limite de requisições das APIs
```

**Novos recursos:**
1. ✅ Mensagens de erro **específicas** para cada API
2. ✅ Exibição de **tempo restante** em cooldown
3. ✅ **Retry automático** com backoff exponencial
4. ✅ Dicas contextuais de diagnóstico
5. ✅ Informações de erro retornadas no resultado JSON

---

## Como Testar as Melhorias

```bash
# Execute o teste para ver os erros detalhados
python3 -c "
from src.ai_brain.validator import GroqValidator
import os

validator = GroqValidator(
    os.getenv('GEMINI_API_KEY'),
    os.getenv('GROQ_API_KEY')
)

tech_data = {
    'trend': 'ALTA',
    'price': 100.0,
    'sma': 95.0,
    'fib_618': 98.0,
    'fib_distance_pct': 2.0,
    'volume_ratio': 1.8,
    'rsi': 55
}

result = validator.consensus_predict(tech_data, 'BTC/USDT')
print(f'Decisão: {result[\"decisao\"]}')
if result['brain_used'] == 'ERROR':
    print(f'Erro Groq: {result.get(\"groq_error\", \"N/A\")}')
    print(f'Erro Gemini: {result.get(\"gemini_error\", \"N/A\")}')
"
```

---

## Logs Esperados (Funcionamento Normal)

Quando as APIs estão funcionando:
```
DEBUG SOL/USDT: Trend BAIXA | Price 86.15 | SMA 87.34475
✅ [CONSENSUS ALERT] 75% - VENDER
🔥 [ORDEM SNIPER BYBIT] SELL 0.5 em SOL/USDT
```

Quando há erro (agora com diagnóstico):
```
DEBUG HYPE/USDT: Trend ALTA | Price 43.529 | SMA 42.538615
⚠️ [GROQ] Rate limit detectado: Error 429
⏸️ [GEMINI] Em cooldown (restam 87s)
❌ [ERRO API] Groq: Rate limit: Error 429 | Gemini: Rate limit cooldown (87s restantes)
💡 Dica: Verifique se você não atingiu o limite de requisições das APIs
```

---

## Verificação Rápida

Execute este checklist:

```bash
# 1. Verificar se as chaves estão definidas
echo "GEMINI_API_KEY: ${GEMINI_API_KEY:0:10}..."
echo "GROQ_API_KEY: ${GROQ_API_KEY:0:10}..."

# 2. Testar conexão com Gemini
curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY" | head -n 1

# 3. Verificar logs do bot
tail -f logs/*.log  # ou docker logs se estiver em container
```

---

## Próximos Passos

Se o erro persistir após verificar as chaves:

1. ⚡ **Railway/Produção**: Verifique as variáveis de ambiente no painel Railway
2. 🔄 **Reinicie o serviço** após atualizar as chaves
3. 📊 **Monitor de Rate Limit**: O sistema agora mostra cooldown automático
4. 🧪 **Modo Local Only**: Em caso de falha persistente, considere implementar modo `force_local_only=True`

---

## Contato e Suporte

Se precisar de ajuda adicional:
- Verifique os logs detalhados no console
- Revise as mensagens de diagnóstico aprimoradas
- Todos os erros agora incluem informações específicas sobre a causa

**Arquivo modificado:** `src/ai_brain/validator.py`
**Data da correção:** 2026-05-17
