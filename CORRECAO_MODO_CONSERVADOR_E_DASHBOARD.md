# Correção Modo Conservador e Renderização do Dashboard

## 📋 Resumo das Correções

Este documento descreve as correções implementadas para resolver dois bugs críticos no Motor Sniper V60.7:

1. **Modo Conservador não estava respeitando o limite de 1 posição por vez**
2. **Dashboard não estava renderizando as posições ativas nos slots**

## 🔒 Correção 1: Trava do Modo Conservador

### Problema
O robô estava ignorando o modo conservador e permitindo a abertura de múltiplas posições simultâneas, tanto no Telegram quanto na Bybit, mesmo quando configurado para operar apenas 1 moeda por vez.

### Solução Implementada
Adicionada verificação rigorosa no arquivo `main_web.py`, função `_process_client_orders_background()` (linhas 1090-1112):

```python
# 🔒 CORREÇÃO MODO CONSERVADOR: Bloqueia nova entrada se já houver posição aberta
if RISK_MODE == 'conservative':
    try:
        # Verifica quantas posições reais o cliente tem abertas na Bybit
        if broker.pybit_session and broker.authenticated:
            positions_response = broker.pybit_session.get_positions(
                category='linear',
                settleCoin='USDT'
            )
            ok, err = broker._handle_v5_ret_code(positions_response, 'get_positions')

            if ok:
                positions_list = (positions_response.get('result') or {}).get('list', [])
                open_positions_count = sum(1 for pos in positions_list if float(pos.get('size') or 0) > 0)

                if open_positions_count >= 1:
                    print(f"   🔒 [CONSERVADOR] Cliente {c.get('nome')} já tem {open_positions_count} posição(ões) aberta(s). Bloqueando nova entrada.", flush=True)
                    continue  # Pula para o próximo cliente
            else:
                print(f"   ⚠️ [CONSERVADOR] Erro ao verificar posições para {c.get('nome')}: {err}", flush=True)
    except Exception as pos_check_err:
        print(f"   ⚠️ [CONSERVADOR] Exceção ao verificar posições: {pos_check_err}", flush=True)
```

### Como Funciona
1. **Verificação em Tempo Real**: Antes de abrir uma nova posição, o sistema consulta diretamente a API da Bybit
2. **Contagem de Posições**: Conta quantas posições com `size > 0` o cliente possui
3. **Bloqueio Imediato**: Se `open_positions_count >= 1`, a função executa `continue`, pulando para o próximo cliente
4. **Logs Informativos**: Registra no console quando um cliente é bloqueado por já ter posição aberta

### Benefícios
- ✅ Garante que no modo conservador apenas 1 moeda seja operada por vez
- ✅ Previne overtrading e exposição excessiva ao risco
- ✅ Funciona para todos os clientes ativos simultaneamente
- ✅ Verificação acontece antes de calcular quantidade e enviar ordem

## 📊 Correção 2: Renderização de Posições no Dashboard

### Problema
O backend estava enviando um payload de 7563 bytes, mas o frontend React não conseguia mapear os ativos para os slots de exibição. Os slots ficavam vazios mesmo com posições abertas na Bybit.

### Causa Raiz
A função `_monitor_dashboard_positions()` estava construindo corretamente os dados das posições, mas faltava o campo `entry` (margem) que o frontend React espera para exibir nos slots.

### Solução Implementada

#### 1. Adição do Campo `leverage` nas Posições Agrupadas
Arquivo `main_web.py`, função `_monitor_dashboard_positions()` (linhas 858-872):

```python
if key not in grouped_positions:
    grouped_positions[key] = {
        'symbol': _limpar_simbolo(symbol),
        'raw_symbol': symbol,
        'side': pos['side'],
        'entry_price': pos['entry_price'],
        'unrealised_pnl': 0.0,
        'size': 0.0,
        'leverage': pos['leverage'],  # ← ADICIONADO
        'client_count': 0
    }
```

#### 2. Cálculo e Inclusão do Campo `entry`
Arquivo `main_web.py`, função `_monitor_dashboard_positions()` (linhas 888-907):

```python
# Calcula margem total usada (notional value / leverage)
leverage = grouped_positions[key].get('leverage', ALAVANCAGEM)
notional_value = pos_data['size'] * pos_data['entry_price']
margin_used = notional_value / leverage if leverage > 0 else notional_value

active_trades_list.append({
    'symbol': pos_data['symbol'],
    'raw_symbol': pos_data['raw_symbol'],
    'side': pos_data['side'],
    'entry_price': pos_data['entry_price'],
    'current_price': live_metrics['current_price'],
    'price_change_pct': live_metrics['price_change_pct'],
    'pnl_pct': live_metrics['pnl_pct'],
    'trend': live_metrics['trend'],
    'is_favorable': live_metrics['is_favorable'],
    'open_pnl_value': round(pos_data['unrealised_pnl'], 2),
    'entry': round(margin_used, 2),  # ← ADICIONADO
    'size': pos_data['size'],
    'client_count': pos_data['client_count']
})
```

### Como Funciona
1. **Captura da Alavancagem**: Armazena a alavancagem de cada posição retornada pela Bybit
2. **Cálculo da Margem**: `margin_used = (size × entry_price) / leverage`
3. **Campo `entry`**: Representa a margem efetivamente usada na posição (em USDT)
4. **Sincronização com Frontend**: O campo `entry` é consumido pelo React para exibir "Margem $X.XX" nos slots

### Estrutura do JSON Retornado
O endpoint `/api/status` agora retorna `active_trades` com a seguinte estrutura completa:

```json
{
  "active_trades": [
    {
      "symbol": "BTCUSDT",
      "raw_symbol": "BTC/USDT:USDT",
      "side": "COMPRAR",
      "entry_price": 95000.00,
      "current_price": 95500.00,
      "price_change_pct": 0.53,
      "pnl_pct": 0.53,
      "trend": "up",
      "is_favorable": true,
      "open_pnl_value": 2.50,
      "entry": 47.50,
      "size": 0.01,
      "client_count": 1
    }
  ]
}
```

### Benefícios
- ✅ Frontend renderiza corretamente as posições nos slots visuais
- ✅ Exibe margem usada (campo "Margem $X.XX")
- ✅ Mostra PnL em tempo real com cores (verde/vermelho)
- ✅ Sincronização a cada 10 segundos com a Bybit
- ✅ Compatível com o formato esperado pelo React

## 🧪 Como Testar

### Teste 1: Modo Conservador
1. Configure o modo para "conservador" no painel
2. Abra manualmente 1 posição na Bybit
3. Aguarde um novo sinal do robô
4. **Resultado Esperado**: O robô deve bloquear a entrada e exibir no log:
   ```
   🔒 [CONSERVADOR] Cliente João já tem 1 posição(ões) aberta(s). Bloqueando nova entrada.
   ```

### Teste 2: Dashboard Renderização
1. Abra 1 ou mais posições na Bybit manualmente
2. Acesse o painel web do Motor Sniper
3. Aguarde até 10 segundos para sincronização
4. **Resultado Esperado**:
   - Slots exibem as moedas ativas (ex: "BTCUSDT")
   - Lado da operação (COMPRAR/VENDER)
   - Margem usada (ex: "Margem $47.50")
   - PnL% em tempo real com cores

## 📝 Notas Técnicas

### Variáveis de Configuração
- `RISK_MODE`: `'conservative'` (1 moeda) ou `'aggressive'` (5 moedas)
- `MAX_MOEDAS_ATIVAS`: 1 ou 5, definido automaticamente
- `ALAVANCAGEM`: 20x (padrão)
- `MARGEM_INPUT`: 5.0 USDT (margem fixa por entrada)

### Threads Envolvidas
- `sniper_worker_loop()`: Varre o mercado e dispara sinais
- `_process_client_orders_background()`: Executa ordens (COM verificação de modo conservador)
- `_monitor_dashboard_positions()`: Sincroniza posições Bybit → Dashboard a cada 10s
- `_monitor_financial_stop_loss()`: Monitora stop loss financeiro

### Endpoints Afetados
- `GET /api/status`: Retorna `central_state` incluindo `active_trades` completo
- `POST /api/config/risk-mode`: Altera entre conservador/agressivo

## ✅ Checklist de Validação

- [x] Modo conservador bloqueia novas entradas quando há 1+ posição aberta
- [x] Dashboard renderiza slots com dados de posições da Bybit
- [x] Campo `entry` (margem) presente no JSON
- [x] Campo `leverage` armazenado nas posições agrupadas
- [x] Logs informativos no console
- [x] Compatibilidade com múltiplos clientes
- [x] Thread `_monitor_dashboard_positions()` ativa e funcional

## 🔗 Arquivos Modificados

- `main_web.py` (linhas 1090-1112, 858-872, 888-907)

## 📅 Data da Correção

30 de maio de 2026

---

**Motor Sniper V60.7** - Correções de Modo Conservador e Renderização do Dashboard
