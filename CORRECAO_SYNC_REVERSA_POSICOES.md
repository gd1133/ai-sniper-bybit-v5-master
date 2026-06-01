# 🔄 Correção: Sincronização Reversa de Posições Encerradas

## 📋 Problema

O dashboard do Motor Sniper V60.7 apresentava um bug de sincronização onde:

1. **Posições eram encerradas na Bybit** - A corretora estava com 0 posições ativas
2. **Dashboard permanecia travado** - O card da moeda (ex: BILL/USDT) continuava exibindo a posição em execução
3. **Banco de dados não era atualizado** - O registro marcado como 'ATIVA' no SQLite não era limpo

**Causa:** O loop de monitoramento (`_monitor_dashboard_positions()`) buscava apenas as posições ativas na Bybit, mas não verificava se existiam posições marcadas como 'open' no banco de dados que não estavam mais presentes na API.

## ✅ Solução Implementada

### Lógica de Sincronização Reversa

A correção implementa uma **sincronização reversa** que:

1. **Obtém posições ativas da Bybit** via API (`category='linear', settleCoin='USDT'`)
2. **Constrói um mapa** das posições ativas: `(símbolo, client_id)`
3. **Consulta trades 'open'** no banco de dados SQLite
4. **Compara** - Para cada trade marcado como 'open':
   - Verifica se existe na lista de posições ativas da Bybit
   - **Se NÃO existe** → significa que foi fechado externamente
5. **Atualiza o banco de dados** - Marca como 'closed' com:
   - `status='closed'`
   - `closed_at=timestamp`
   - `notes='Position closed on exchange (Bybit API sync)'`
6. **Libera o slot do dashboard** - O card volta a exibir 'AGUARDANDO MOEDA'

### Código-Chave

O loop de sincronização reversa foi inserido em `main_web.py` na função `_monitor_dashboard_positions()`:

```python
# 🔄 SINCRONIZAÇÃO REVERSA: DETECTAR E LIMPAR POSIÇÕES ENCERRADAS NA BYBIT

# 1. Constrói mapa de posições ativas da Bybit
bybit_active_positions = set()
for pos in all_positions:
    bybit_active_positions.add((pos['symbol'], pos['client_id']))

# 2. Obtém todas as posições 'open' do banco
open_trades = db.get_open_trades(limit=100)

# 3. Para cada trade 'open', verifica se existe na Bybit
for trade in open_trades:
    normalized_trade_pair = normalize_pair(trade.get('pair', ''))
    
    # Procura a posição nos ativos da Bybit
    position_exists = False
    for bybit_symbol, bybit_client_id in bybit_active_positions:
        if bybit_client_id == trade.get('client_id'):
            if normalize_pair(bybit_symbol) == normalized_trade_pair:
                position_exists = True
                break
    
    # 4. Se não existe na Bybit → marca como fechada
    if not position_exists:
        cur.execute(
            "UPDATE trades SET status='closed', closed_at=?, notes=? WHERE id=?",
            (timestamp, note, trade.get('id'))
        )
```

### Normalização de Pares

Para garantir a comparação correta entre diferentes formatos de símbolos:

- **Bybit API**: `BILLУСDT` (símbolo puro)
- **Banco de dados**: `BILL-USDT` ou `BILL USDT` (possíveis variações)

A função `normalize_pair()` padroniza para `BILLУСDT`:

```python
def normalize_pair(pair_str):
    return str(pair_str or '').upper().replace('-', '').replace(' ', '')
```

## 📊 Fluxo de Execução

```
Cada 10 segundos:

1. _monitor_dashboard_positions() executa
   ↓
2. Busca posições ativas na Bybit API
   ↓
3. Busca todas as posições 'open' no SQLite
   ↓
4. [NOVO] Sincronização Reversa:
   - Compara Bybit vs Database
   - Marca como 'closed' se não encontrada na Bybit
   - Libera slot do dashboard
   ↓
5. Atualiza central_state['active_trades']
   ↓
6. Frontend renderiza apenas posições abertas
```

## 🧪 Testes Realizados

Um teste automatizado validou a lógica:

```
✅ 3 trades 'open' criados (BILL, DOGE, XRP)
✅ Apenas DOGE presente na Bybit
✅ Sincronização reversa detectou BILL e XRP como fechados
✅ 2 trades marcados como 'closed' com sucesso
✅ Dashboard agora mostra apenas DOGE/USDT ativa
```

## 📝 Logs de Debug

Durante a execução, o sistema agora imprime:

```
🔄 [DASHBOARD MONITOR] Iniciado - Sincronização de posições Bybit → Frontend

   🧹 [SYNC REVERSA] Posição BILL/USDT (ID: 1) marcada como fechada (detectada ausência na API Bybit)
   🧹 [SYNC REVERSA] Posição XRP/USDT (ID: 3) marcada como fechada (detectada ausência na API Bybit)
   ✅ [SYNC REVERSA] 2 posição(ões) sincronizada(s) como encerrada(s)
```

## 🎯 Benefícios

✅ **Dashboard sempre sincronizado** - Reflete a realidade da Bybit em tempo real
✅ **Slots liberados automaticamente** - Quando posição é fechada externamente
✅ **Rastreabilidade** - Notas registram quando e por que a posição foi fechada
✅ **Sem travamentos** - Cards não ficam mais presos em "EM LUCRO" indefinidamente
✅ **Robustez** - Funciona mesmo se a posição for fechada via API Bybit diretamente

## 🔧 Configuração

Nenhuma configuração adicional é necessária. O sistema funciona automaticamente:

- ✅ Executa a cada 10 segundos no loop `_monitor_dashboard_positions()`
- ✅ Compara até 100 trades 'open' por ciclo
- ✅ Busca apenas posições ativas na Bybit
- ✅ Suporta múltiplos clientes e moedas

## 📍 Arquivo Modificado

- `main_web.py` - Função `_monitor_dashboard_positions()` (linhas 915-978)

## 🚀 Resultado Final

Agora, quando uma posição é fechada na Bybit:

1. ✅ API Bybit retorna lista sem o símbolo
2. ✅ Sincronização reversa detecta a ausência
3. ✅ Database é atualizado (status='closed')
4. ✅ Central_state remove de active_trades
5. ✅ Dashboard renderiza slot como "AGUARDANDO MOEDA"
6. ✅ Novos sinais podem usar esse slot

**Problema resolvido!** 🎉
