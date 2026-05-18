# 🔧 Correção InvalidNonce Error (retCode 10002)

## 📋 Problema Identificado

**Data:** 2026-05-18
**Versão:** v60.9
**Status:** ✅ CORRIGIDO

### Erro Original

```
! InvalidNonce : bybit {"retCode":10002,"retMsg":"solicitação inválida, verifique o timestamp do seu servidor ou o parâmetro recv_window: req_timestamp[1779123899105],server_timestamp[1779123908029],recv_window[5000]","result":{},"retExtInfo":{},"time":1779123908029}
```

### Análise do Erro

- **retCode**: 10002 (Invalid Request)
- **req_timestamp**: 1779123899105 (timestamp da requisição)
- **server_timestamp**: 1779123908029 (timestamp do servidor Bybit)
- **Diferença**: ~9 segundos (8924ms)
- **recv_window**: 5000ms (5 segundos)

**Causa raiz:** A diferença de tempo entre o cliente e o servidor (9 segundos) excede a janela de recepção configurada (5 segundos), causando rejeição da requisição pela API da Bybit.

---

## ✅ Solução Implementada

### 1. Aumento do recvWindow

**Arquivo modificado:** `src/broker/bybit_client.py`

#### CCXT Configuration (linha 74)
```python
# ANTES
'recvWindow': 5000,  # Janela de 5s conforme documentação oficial

# DEPOIS
'recvWindow': 20000,  # Janela de 20s para ambientes com dessincronização de relógio
```

#### Pybit Session (linha 147)
```python
# ANTES
recv_window=5000,  # Janela de 5s conforme documentação oficial

# DEPOIS
recv_window=20000,  # Janela de 20s para ambientes com dessincronização de relógio
```

### 2. Detecção Melhorada de Erros

**Arquivo modificado:** `src/broker/bybit_client.py`

#### Método _is_auth_error (linha 184)
```python
def _is_auth_error(self, msg):
    return (
        '10003' in msg          # Invalid API Key
        or '10004' in msg       # Invalid sign / timestamp mismatch
        or '10002' in msg       # Invalid request / timestamp issue / InvalidNonce ✅ NOVO
        or 'API key is invalid' in msg
        or '403' in msg
        or 'Forbidden' in msg
        or 'CloudFront' in msg
        or 'timestamp' in msg.lower()
        or 'nonce' in msg.lower()  # ✅ NOVO
    )
```

#### Método execute_market_order - Tratamento CCXT (linha 463)
```python
elif "10002" in error_details or "InvalidNonce" in error_details or "timestamp" in error_details.lower():
    print(f"   ⏰ ERRO DE TIMESTAMP/NONCE: Dessincronização entre relógio local e servidor")
    print(f"   💡 SOLUÇÃO: Sincronize o relógio do sistema ou use NTP. recvWindow aumentado para 20000ms")
    print(f"   ℹ️  Este erro ocorre quando a diferença de tempo excede a janela de recepção permitida")
```

#### Método execute_market_order - Tratamento Genérico (linha 487)
```python
elif "10002" in error_details or "InvalidNonce" in error_details or "timestamp" in error_details.lower():
    print(f"   ⏰ ERRO DE TIMESTAMP/NONCE: Dessincronização entre relógio local e servidor")
    print(f"   💡 SOLUÇÃO: Sincronize o relógio do sistema ou use NTP. recvWindow aumentado para 20000ms")
    print(f"   ℹ️  Este erro ocorre quando a diferença de tempo excede a janela de recepção permitida")
```

### 3. Log Atualizado

```python
print(f"🔌 [PYBIT V5] módulo={self.pybit_sdk_module} endpoint={self.active_endpoint} recv_window=20000ms")
```

---

## 📊 Comparação Antes vs Depois

| Aspecto | Antes (v60.8) | Depois (v60.9) | Melhoria |
|---------|---------------|----------------|----------|
| recvWindow CCXT | 5000ms | 20000ms | 4x maior |
| recv_window pybit | 5000ms | 20000ms | 4x maior |
| Detecção retCode 10002 | ❌ Não específica | ✅ Específica | Diagnóstico claro |
| Mensagem de erro | Genérica | Específica com solução | UX melhorada |
| Suporte a clock skew | Até 5 segundos | Até 20 segundos | Mais robusto |

---

## 🎯 Cenários Cobertos

Esta correção resolve problemas em:

1. **Sistemas locais sem NTP**
   - Windows com sincronização de tempo desabilitada
   - Linux sem serviço NTP ativo
   - WSL com clock drift

2. **Ambientes cloud com latência**
   - Railway com latência de rede
   - VPS com relógio dessincronizado
   - Containers Docker sem time sync

3. **Primeira requisição CCXT**
   - `adjustForTimeDifference` precisa calibrar offset
   - Primeira chamada pode falhar antes da calibração
   - recvWindow maior previne falha inicial

---

## 🧪 Testes Realizados

### test_bybit_client_v5_order_flow.py
```bash
$ python tests/test_bybit_client_v5_order_flow.py
🔌 [PYBIT V5] módulo=pybit.unified_trading endpoint=https://api.bybit.com recv_window=20000ms
✅ [BYBIT] Ordem criada com sucesso - ID: oid-123
✅ Fluxo V5 de ordem, insurance e retCode 10003 OK
```

### test_bybit_client_endpoint_config.py
```bash
$ python tests/test_bybit_client_endpoint_config.py
🔌 [PYBIT V5] módulo=pybit.unified_trading endpoint=https://api-testnet.bybit.com recv_window=20000ms
🔌 [PYBIT V5] módulo=pybit.unified_trading endpoint=https://api.bybit.com recv_window=20000ms
✅ Endpoint Bybit segue USE_TESTNET sem redundância
```

---

## 💡 Recomendações Adicionais

### Para Usuários

1. **Sincronize o relógio do sistema:**
   ```bash
   # Linux
   sudo apt-get install ntp
   sudo systemctl enable ntp
   sudo systemctl start ntp

   # Windows
   # Settings > Time & Language > Date & Time > "Set time automatically" ON
   ```

2. **Verifique a diferença de tempo:**
   ```python
   import time
   import requests

   local_time = int(time.time() * 1000)
   server_time = requests.get('https://api.bybit.com/v5/market/time').json()['result']['timeSecond'] * 1000
   diff = abs(server_time - local_time)
   print(f"Diferença de tempo: {diff}ms")
   ```

3. **Use NTP servers confiáveis:**
   - `time.google.com`
   - `time.cloudflare.com`
   - `pool.ntp.org`

### Para Desenvolvedores

1. **Monitore erros 10002:**
   - Log quando ocorrer InvalidNonce
   - Track clock drift ao longo do tempo
   - Alerta se drift > 10 segundos

2. **Considere implementar:**
   - Time sync check na inicialização
   - Auto-ajuste de recvWindow baseado em histórico
   - Fallback para timestamp do servidor

---

## 📚 Referências

- [Bybit V5 API - Authentication](https://bybit-exchange.github.io/docs/v5/guide#authentication)
- [Bybit Error Codes](https://bybit-exchange.github.io/docs/v5/error)
- CORRECOES_API_OFICIAL.md - Seção 2: AJUSTE DE TIMESTAMP E RECVWINDOW

---

## 📝 Changelog

### v60.9 (2026-05-18)
- ✅ Aumentado recvWindow de 5000ms para 20000ms em BybitClient
- ✅ Adicionada detecção específica de retCode 10002 (InvalidNonce)
- ✅ Mensagens de erro melhoradas com diagnóstico e solução
- ✅ Log atualizado para mostrar recv_window=20000ms
- ✅ Documentação atualizada em CORRECOES_API_OFICIAL.md
- ✅ Testes validados e passando

### v60.8 (Anterior)
- recvWindow: 5000ms
- Detecção genérica de erros de autenticação
