# ✅ Checklist de Deploy - Render.com
## AI Sniper V5 - PositionGuard + Trade Learning

---

## 📋 Pré-Deploy

- [ ] **Código commitado e pushado** para a branch `feature/abacus-analyst-agent`
- [ ] **PR #243 aberto** e revisado
- [ ] **Testes locais passando** (4/4 testes de PositionGuard + Trade Learning)

---

## 🔧 Configuração de Variáveis de Ambiente no Render

### **1. PositionGuard - Escada de Lucro (5 variáveis)**

- [ ] `POSITION_GUARD_LEVEL1_TRIGGER_PCT` = `1.8`
  - ✅ ROI% para ativar Nível 1 (saída parcial de 40%)
  
- [ ] `POSITION_GUARD_LEVEL1_PARTIAL_FRACTION` = `0.40`
  - ✅ Fração da posição a sair no Nível 1 (40%)
  
- [ ] `POSITION_GUARD_LEVEL2_TRIGGER_PCT` = `3.5`
  - ✅ ROI% para ativar Nível 2 (trailing stop dinâmico)
  
- [ ] `POSITION_GUARD_TRAIL_ATR_MULT` = `1.5`
  - ✅ Multiplicador do ATR para trailing stop (1.5x ATR)
  
- [ ] `POSITION_GUARD_FEE_BUFFER_PCT` = `0.12`
  - ✅ Buffer de taxa para evitar saídas prematuras (0.12%)

---

### **2. Trade Learning - Aprendizado Local (2 variáveis)**

- [ ] `TRADE_LEARNING_MIN_SAMPLE` = `8`
  - ✅ Mínimo de trades históricos necessários para aplicar learning
  
- [ ] `TRADE_LEARNING_LOW_WIN_MODE` = `reduce`
  - ✅ Modo de ação para baixa win-rate:
    - `reduce` → reduz lote para 0.5x
    - `discard` → bloqueia entrada completamente

---

### **3. Verificação Final no Render**

- [ ] **Todas as 7 variáveis adicionadas** no painel Environment
- [ ] **Clicou em "Save Changes"** (botão inferior direito)
- [ ] **Deploy automático iniciado** (aguardar conclusão ~3-5min)
- [ ] **Logs do deploy sem erros** (aba "Logs")

---

## 🧪 Validação Pós-Deploy

### **Método 1: Script de Validação Automática** (Recomendado)

Execute no **Shell do Render** (aba "Shell"):

```bash
cd /opt/render/project/src
python3 validate_env_position_guard.py
```

**Saída esperada:**
```
✅ Todas as 7 variáveis de ambiente estão configuradas!
✅ PositionGuard está pronto para uso.
✅ Trade Learning está pronto para uso.
```

---

### **Método 2: Verificação Manual via Logs**

Acesse a aba **"Logs"** no Render e procure por:

```
[INFO] PositionGuard: Level 1 trigger at 1.8% ROI, partial fraction 0.40
[INFO] PositionGuard: Level 2 trigger at 3.5% ROI, trailing ATR mult 1.5
[INFO] Trade Learning: Min sample 8, low win mode 'reduce'
```

---

### **Método 3: Testes Unitários no Servidor**

Execute no **Shell do Render**:

```bash
cd /opt/render/project/src
python3 -m pytest tests/test_position_guard.py tests/test_trade_learning_local.py -v
```

**Resultado esperado:**
```
tests/test_position_guard.py::test_level1_partial_and_breakeven PASSED
tests/test_position_guard.py::test_kill_switch_long PASSED
tests/test_position_guard.py::test_level3_exhaustion PASSED
tests/test_trade_learning_local.py::test_learning_stats_multiplier_up PASSED
tests/test_trade_learning_local.py::test_learning_stats_multiplier_down PASSED
tests/test_trade_learning_local.py::test_learning_discard_mode PASSED

===================== 6 passed in 2.34s ======================
```

---

## 📊 Monitoramento em Produção

### **Verificar PositionGuard em Ação**

No dashboard do bot, procure por:

1. **Logs de Posição Aberta:**
   ```
   [PositionGuard] Level 1 triggered: ROI=1.85%, executing partial TP (40%)
   [PositionGuard] Breakeven SL applied at 50000.0
   ```

2. **Logs de Kill-Switch:**
   ```
   [PositionGuard] Kill-switch LONG: price closed below EMA20 with high volume
   [PositionGuard] Early exit recommended
   ```

3. **Logs de Trailing Stop:**
   ```
   [PositionGuard] Level 2 triggered: ROI=3.6%, dynamic trailing stop active
   [PositionGuard] Stop extended to EMA8-1.5*ATR
   ```

---

### **Verificar Trade Learning em Ação**

No dashboard ou logs, procure por:

1. **Consulta de Learning antes da Entrada:**
   ```
   [TradeLearn] Setup: trend_long_5m, Pair: BTCUSDT
   [TradeLearn] Last 20 trades: 13W/7L, Win Rate: 65.0%
   [TradeLearn] Multiplier: 1.15x (high win rate bonus)
   ```

2. **Ajuste de Lote:**
   ```
   [TradeLearn] Original qty: 0.100, Adjusted qty: 0.115 (bonus +15%)
   ```

3. **Bloqueio de Entrada (se discard mode):**
   ```
   [TradeLearn] Setup: trend_short_15m, Win Rate: 35.0% (< 40%)
   [TradeLearn] Entry discarded (low win rate, discard mode active)
   ```

4. **Gravação de Learning após Fechamento:**
   ```
   [TradeLearn] Recording: setup=trend_long_5m, win=True, pnl=+2.3%
   [TradeLearn] Learning record saved to database
   ```

---

## 🔍 Troubleshooting

### ❌ **Deploy falhou com erro de sintaxe**
- **Causa:** Código Python com erro de sintaxe
- **Solução:** Revisar logs do deploy, corrigir e re-push

### ❌ **Variáveis não aparecem nos logs**
- **Causa:** Variáveis não foram salvas ou deploy não reiniciou
- **Solução:** 
  1. Voltar ao painel Environment
  2. Verificar se as 7 variáveis estão lá
  3. Clicar em "Manual Deploy" → "Clear build cache & deploy"

### ❌ **Script de validação retorna "Variável X não encontrada"**
- **Causa:** Variável não foi adicionada ou nome digitado errado
- **Solução:** 
  1. Comparar nome exato da variável com este checklist
  2. Re-adicionar com o nome correto (copiar/colar recomendado)

### ❌ **Testes falhando no servidor**
- **Causa:** Dependências não instaladas ou versão Python incompatível
- **Solução:** 
  1. Verificar `requirements.txt` inclui `pytest`
  2. Verificar Python 3.10+ no Render
  3. Rodar `pip install -r requirements.txt` manualmente no Shell

---

## 🎯 Checklist Final

- [ ] ✅ Deploy concluído sem erros
- [ ] ✅ Script de validação passou (7/7 variáveis OK)
- [ ] ✅ Logs mostram inicialização do PositionGuard
- [ ] ✅ Logs mostram inicialização do Trade Learning
- [ ] ✅ Testes unitários passaram no servidor (6/6)
- [ ] ✅ Dashboard acessível e responsivo
- [ ] ✅ Monitoramento ativo para primeira posição

---

## 📞 Suporte

Se todos os itens acima estão ✅ mas ainda há problemas:

1. **Exportar logs completos** do Render (últimas 500 linhas)
2. **Capturar screenshot** do painel Environment
3. **Rodar script de diagnóstico:**
   ```bash
   cd /opt/render/project/src
   python3 validate_env_position_guard.py --verbose
   ```

---

**✨ Última atualização:** 15/09/2026  
**📦 Versão:** AI Sniper V5 - Feature Branch `feature/abacus-analyst-agent`  
**🔗 PR:** [#243](https://github.com/gd1133/ai-sniper-bybit-v5-master/pull/243)
