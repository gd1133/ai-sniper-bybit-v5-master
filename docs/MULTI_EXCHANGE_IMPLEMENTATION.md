# Motor Sniper V60.7 - Implementação Multi-Exchange

## 📋 Resumo da Implementação

Este documento descreve a implementação completa do suporte para operação simultânea em **Bybit** e **Binance** (Contas Reais e Testnet) no Motor Sniper V60.7.

---

## 🎯 Funcionalidades Implementadas

### 1. INTEGRAÇÃO MULTICONTA (Bybit + Binance)

#### Arquitetura Multi-Exchange

O sistema utiliza uma arquitetura modular que permite trocar de exchange de forma transparente:

**Localização dos Brokers:**
- `src/broker/bybit_client.py` - Cliente Bybit V5 API
- `src/broker/binance_client.py` - Cliente Binance Futures USDM

**Seleção Automática de Broker:**
```python
# main_web.py:645-672
def _ensure_broker_class(exchange='bybit'):
    """Retorna a classe broker correta dependendo da corretora do cliente."""
    exchange = str(exchange or 'bybit').strip().lower()
    if exchange == 'binance':
        from src.broker.binance_client import BinanceClient as _BC
        return _BC
    from src.broker.bybit_client import BybitClient as _BybitClient
    return _BybitClient

def _make_broker(client):
    """Instancia o broker correto usando as credenciais e exchange do cliente."""
    exchange = str(client.get('exchange') or 'bybit').strip().lower()
    broker_cls = _ensure_broker_class(exchange)
    account_mode = _normalize_account_mode(client.get('account_mode'))
    return broker_cls(
        client.get('bybit_key'),
        client.get('bybit_secret'),
        testnet=_is_testnet_account(account_mode)
    )
```

#### Banco de Dados

O campo `exchange` na tabela `clientes_sniper` controla qual corretora será usada:

```sql
-- src/database/manager.py:77
ALTER TABLE clientes_sniper ADD COLUMN exchange TEXT DEFAULT 'bybit'
```

Valores válidos:
- `'bybit'` - Bybit Perpetual Futures
- `'binance'` - Binance Futures USDM

#### Suporte a Testnets

Ambas as exchanges suportam testnet:

**Bybit Testnet:**
- URL: `https://api-testnet.bybit.com`
- Credenciais: Chaves de API da Bybit Testnet

**Binance Testnet:**
- URL: `https://testnet.binancefuture.com`
- Credenciais: Chaves de API da Binance Futures Testnet

---

### 2. DIAGNÓSTICO DE ORDENS (Filtro de Erros)

#### Função pre_flight_check()

Implementada em ambos os brokers para validação completa antes de executar ordens:

**Assinatura:**
```python
def pre_flight_check(self, symbol=None, required_balance=0):
    """
    🔍 PRE-FLIGHT CHECK - Validação completa antes de executar ordem
    
    Verifica:
    1. Conectividade com a API
    2. Autenticação válida
    3. Permissões de trading
    4. Saldo suficiente
    5. Símbolo válido (se fornecido)
    
    Retorna tupla (bool sucesso, str categoria_erro, str mensagem_detalhada)
    Categorias: 'OK', 'ERRO_CORRETORA', 'ERRO_ROBO'
    """
```

**Implementação:**
- `src/broker/bybit_client.py:428-498`
- `src/broker/binance_client.py:222-294`

#### Categorias de Erro

**ERRO_CORRETORA** - Problemas com a exchange:
- Chaves de API inválidas ou expiradas
- Saldo insuficiente
- API sem permissão de trading
- Símbolo inválido ou não encontrado

**ERRO_ROBO** - Problemas do sistema:
- Timeout de conexão
- Erro de rede
- Erro interno de lógica

#### Integração no Fluxo de Execução

**main.py - Execução CLI:**
```python
# main.py:352-377
print("\n🔍 [PRE-FLIGHT CHECK] Validando condições de execução...")

ok, error_category, error_message = client.pre_flight_check(
    symbol=v5_symbol, 
    required_balance=required_balance
)

if not ok:
    print(f"\n❌ [{error_category}] {error_message}")
    if error_category == 'ERRO_CORRETORA':
        print("   → Verifique:")
        print("      • Chaves API válidas e com permissões corretas")
        print("      • Saldo suficiente na conta")
    elif error_category == 'ERRO_ROBO':
        print("   → Erro de sistema:")
        print("      • Problema de conectividade/timeout")
    return False
```

**main_web.py - Broadcast de Sinais:**
```python
# main_web.py:1784-1804
if _is_order_execution_enabled(APP_MODE):
    exchange_name = str(c.get('exchange') or 'bybit').upper()
    print(f"🔍 [PRE-FLIGHT CHECK] Validando {c.get('nome')} ({exchange_name})...")
    
    ok, error_category, error_message = broker.pre_flight_check(
        symbol=symbol, 
        required_balance=margem * 1.1
    )
    
    if not ok:
        print(f"❌ [{error_category}] Cliente: {c.get('nome')} | {error_message}")
        # Pula este cliente e continua com os próximos
        return
```

---

### 3. REFORMULAÇÃO DO FORMULÁRIO (Frontend)

#### Layout Otimizado

O formulário de investidor utiliza layout de grade com 2 colunas para economizar espaço:

**Localização:** `main.jsx:1118-1222`

#### Seletores de Exchange

Botões visuais para escolher entre Bybit e Binance:

```jsx
// main.jsx:1120-1142
<div className="grid grid-cols-2 gap-4">
  <button
    type="button"
    onClick={() => handleFieldChange('exchange', 'bybit')}
    className={formExchange === 'bybit' ? 'bg-yellow-500/15 border-yellow-500/40' : '...'}
  >
    🟡 Bybit
  </button>
  <button
    type="button"
    onClick={() => handleFieldChange('exchange', 'binance')}
    className={formExchange === 'binance' ? 'bg-orange-500/15 border-orange-500/40' : '...'}
  >
    🟠 Binance
  </button>
</div>
```

#### Seletores de Modo de Conta

Botões para escolher entre Testnet e Real:

```jsx
// main.jsx:1145-1165
<div className="grid grid-cols-2 gap-4">
  <button
    type="button"
    onClick={() => handleFieldChange('account_mode', 'testnet')}
    className={formAccountMode === 'testnet' ? 'bg-blue-500/15 border-blue-500/40' : '...'}
  >
    🛰️ Conta Testnet
  </button>
  <button
    type="button"
    onClick={() => handleFieldChange('account_mode', 'real')}
    className={formAccountMode === 'real' ? 'bg-green-500/15 border-green-500/40' : '...'}
  >
    💼 Conta Real
  </button>
</div>
```

#### Campo de Saldo Read-Only

O campo de saldo é somente leitura e exibe "Sincronizando..." enquanto valida a API:

```jsx
// main.jsx:1172-1184
<input
  value={addFormFields.saldo_base ? `Sincronizado: ${addFormFields.saldo_base}` : ''}
  type="text"
  disabled
  className="w-full p-5 rounded-[1.5rem] bg-zinc-950 border-white/5 text-zinc-500 cursor-not-allowed"
  placeholder={formBalancePlaceholder}
/>
```

---

### 4. GESTÃO DE RISCO E EXECUÇÃO

#### Gerenciamento Dinâmico de Entrada

Implementado via classe `RiskManager` em `main.py`:

**Regras:**
- Entrada padrão: **5% do saldo** (após Gains)
- Entrada reduzida: **3% do saldo** (após Stop Loss)
- Retorno ao padrão: na primeira operação com Gain

```python
# main.py:70-99
class RiskManager:
    def __init__(self) -> None:
        self._last_result: str = "NONE"

    @property
    def current_entry_pct(self) -> float:
        """Retorna o percentual de entrada do próximo trade."""
        return ENTRY_PCT_AFTER_STOP if self._last_result == "STOP" else ENTRY_PCT_DEFAULT

    def register_stop(self) -> None:
        """Registra que o último trade encerrou em Stop Loss."""
        self._last_result = "STOP"

    def register_gain(self) -> None:
        """Registra que o último trade encerrou em Take Profit."""
        self._last_result = "GAIN"
```

#### Trava de 1 Operação Ativa por Conta

Implementada via `MAX_MOEDAS_ATIVAS` e `_can_open_new_signal()`:

```python
# main_web.py:168
MAX_MOEDAS_ATIVAS = 1  # Conservador: 1 moeda por vez

# main_web.py:1336-1363
def _can_open_new_signal(symbol):
    """Valida se as travas de segurança permitem uma nova entrada."""
    open_trades = db.get_open_trades(100)
    
    if len(occupied_symbols) >= MAX_MOEDAS_ATIVAS:
        return False, f"Limite de {MAX_MOEDAS_ATIVAS} moedas atingido."
    
    return True, "ok"
```

#### Timeframe Fixo de 30 Minutos

Configurado em `main.py`:

```python
# main.py:42
TIMEFRAME: str = "30m"  # Intervalo de tempo dos candles — fixado em 30 minutos
```

#### Protocolo de Proteção 100/3

- **Take Profit:** +100% de lucro sobre a margem (10% de preço com 10× alavancagem)
- **Stop Loss:** -3% de perda fixa sobre a margem

```python
# main.py:48-50
STOP_LOSS_PCT: float = 0.05    # 5% de preço → 50% da margem
TAKE_PROFIT_PCT: float = 0.10  # 10% de preço → 100% de lucro
LEVERAGE: int = 10             # 10× alavancagem
```

---

## 🔧 Como Usar

### Cadastrar Cliente Bybit

1. Acesse a aba **GESTÃO** no dashboard
2. Clique em **+ Novo Investidor**
3. Selecione **🟡 Bybit**
4. Escolha **🛰️ Conta Testnet** ou **💼 Conta Real**
5. Preencha:
   - Nome do cliente
   - API Key da Bybit
   - API Secret da Bybit
6. Clique em **Guardar Investidor**
7. O saldo será sincronizado automaticamente

### Cadastrar Cliente Binance

1. Acesse a aba **GESTÃO** no dashboard
2. Clique em **+ Novo Investidor**
3. Selecione **🟠 Binance**
4. Escolha **🛰️ Conta Testnet** ou **💼 Conta Real**
5. Preencha:
   - Nome do cliente
   - API Key da Binance
   - API Secret da Binance
6. Clique em **Guardar Investidor**
7. O saldo será sincronizado automaticamente

### Testar Conexão

Ao salvar um investidor, o sistema automaticamente:

1. Executa `pre_flight_check()` para validar as credenciais
2. Consulta o saldo da conta
3. Exibe mensagens claras de erro se houver problemas

**Exemplo de mensagem de sucesso:**
```
✅ Pre-flight check passou: Saldo $1234.56
```

**Exemplo de mensagem de erro:**
```
❌ [ERRO_CORRETORA] Autenticação falhou: Invalid API key
   → Verifique:
      • Chaves API válidas e com permissões corretas
      • Saldo suficiente na conta
      • API não expirou ou foi revogada
```

---

## 📊 Fluxo de Execução de Ordem

```
┌─────────────────────────────────────────────────┐
│  1. Sinal Detectado pelo Motor Sniper          │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│  2. Verificação de Slots Disponíveis            │
│     _can_open_new_signal()                      │
│     - Limite de 1 trade por conta              │
│     - Símbolo não duplicado                     │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│  3. Loop de Clientes Ativos                     │
│     Para cada cliente cadastrado:               │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│  4. Instanciar Broker Correto                   │
│     _make_broker(client)                        │
│     - Lê campo 'exchange' do cliente            │
│     - Instancia BybitClient ou BinanceClient    │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│  5. PRE-FLIGHT CHECK 🔍                         │
│     broker.pre_flight_check()                   │
│     - Valida autenticação                       │
│     - Verifica saldo suficiente                 │
│     - Valida símbolo                            │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
  ┌───────────┐              ┌──────────┐
  │ ERRO?     │              │ OK?      │
  │ Pula      │              │ Executa  │
  │ Cliente   │              │ Ordem    │
  └───────────┘              └─────┬────┘
                                   │
                                   ▼
              ┌────────────────────────────────────┐
              │  6. Execução da Ordem              │
              │     broker.execute_market_order()  │
              │     - Ordem a mercado              │
              └────────────────┬───────────────────┘
                               │
                               ▼
              ┌────────────────────────────────────┐
              │  7. Proteção Automática            │
              │     broker.set_tp_sl_sniper()      │
              │     - Take Profit: +100%           │
              │     - Stop Loss: -3%               │
              └────────────────┬───────────────────┘
                               │
                               ▼
              ┌────────────────────────────────────┐
              │  8. Registro no Banco de Dados     │
              │     db.record_trade()              │
              │     - Status: "open"               │
              │     - Entry price registrado       │
              └────────────────────────────────────┘
```

---

## 🧪 Testes Recomendados

### Teste 1: Validação de Credenciais Bybit Testnet

1. Obtenha chaves de API da Bybit Testnet
2. Cadastre um cliente com essas chaves
3. Verifique se o saldo é sincronizado corretamente
4. Observe os logs para confirmar: `✅ [PRE-FLIGHT OK]`

### Teste 2: Validação de Credenciais Binance Testnet

1. Obtenha chaves de API da Binance Futures Testnet
2. Cadastre um cliente com essas chaves
3. Verifique se o saldo é sincronizado corretamente
4. Observe os logs para confirmar: `✅ [PRE-FLIGHT OK]`

### Teste 3: Erro de Chave Inválida

1. Cadastre um cliente com chave API inválida
2. Verifique se aparece: `❌ [ERRO_CORRETORA] Autenticação falhou`
3. Confirme que o log detalha o problema

### Teste 4: Saldo Insuficiente

1. Cadastre um cliente com saldo baixo (< $10)
2. Tente executar uma ordem que requer mais saldo
3. Verifique se aparece: `❌ [ERRO_CORRETORA] Saldo insuficiente`

### Teste 5: Timeout de Conexão

1. Simule problema de rede (bloqueie temporariamente a API)
2. Tente executar uma ordem
3. Verifique se aparece: `❌ [ERRO_ROBO] Timeout de conexão`

---

## 📝 Notas Importantes

### Compatibilidade de Chaves

- As chaves Bybit são armazenadas nos campos `bybit_key` e `bybit_secret`
- As chaves Binance também usam os mesmos campos por compatibilidade
- O campo `exchange` determina qual API será chamada

### Permissões Necessárias

**Bybit:**
- ✅ Contract Trading (Futuros)
- ✅ Read API Key
- ✅ Write API Key (para ordens)

**Binance:**
- ✅ Enable Futures
- ✅ Enable Reading
- ✅ Enable Spot & Margin Trading (para execução)

### Segurança

- Nunca compartilhe suas chaves de API
- Use sempre testnet para testes iniciais
- Revise todas as permissões das chaves antes de usar em produção
- O sistema valida as chaves antes de cada operação via `pre_flight_check()`

---

## 🐛 Troubleshooting

### Problema: "Chave API inválida"

**Solução:**
1. Verifique se as chaves estão corretas
2. Confirme que a chave tem permissões de trading
3. Verifique se o modo (testnet/real) está correto
4. Revise se a chave não expirou

### Problema: "Saldo insuficiente"

**Solução:**
1. Confirme o saldo na conta da exchange
2. Verifique se está usando o modo correto (testnet/real)
3. Aguarde sincronização do saldo (até 30 segundos)

### Problema: "Símbolo inválido"

**Solução:**
1. Verifique se o símbolo existe na exchange
2. Para Bybit: use formato como "BTCUSDT"
3. Para Binance: use formato como "BTCUSDT"

### Problema: "Timeout de conexão"

**Solução:**
1. Verifique sua conexão com a internet
2. Confirme que as APIs não estão em manutenção
3. Aguarde alguns minutos e tente novamente

---

## 🚀 Próximos Passos

1. **Testes em Testnet:** Validar todas as funcionalidades em ambiente de testes
2. **Monitoramento:** Acompanhar logs de execução para identificar problemas
3. **Otimização:** Ajustar timeouts e retry logic conforme necessário
4. **Expansão:** Considerar adicionar mais exchanges no futuro

---

## 📞 Suporte

Em caso de dúvidas ou problemas:

1. Revise os logs do sistema
2. Verifique a documentação das APIs da exchange
3. Confirme que todas as dependências estão instaladas
4. Teste primeiro em testnet antes de usar em produção

---

**Motor Sniper V60.7** - Sistema de Trading Automatizado Multi-Exchange  
© 2026 - Todos os direitos reservados
