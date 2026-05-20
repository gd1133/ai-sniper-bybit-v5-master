# Funcionalidade de Entrada Manual - Motor Sniper v60.7+

## 📋 Resumo

Foi adicionada uma nova funcionalidade de **Entrada Manual** ao sistema, permitindo que o operador execute operações manuais enquanto mantém o sistema de entrada automática funcionando normalmente.

## ✨ Características Principais

### 1. Análise de IA Integrada
- Antes de executar uma entrada manual, o sistema consulta os **3 Cérebros de IA** (Groq, Gemini e Local Brain)
- Exibe análise técnica completa: tendência, RSI, SMA 200, Fibonacci
- Mostra recomendação com base na confiança da IA (≥60% = EXECUTAR, <60% = AGUARDAR)

### 2. Flexibilidade na Entrada
- **Símbolo**: Qualquer par disponível (ex: BTC/USDT, ETH/USDT)
- **Direção**: COMPRAR (BUY) ou VENDER (SELL)
- **Preço**: Opcional - usa preço de mercado se não informado

### 3. Duas Etapas de Operação
1. **Análise Prévia**: Obtenha análise de IA antes de executar
2. **Execução**: Execute a ordem após revisar a análise

## 🎯 Como Usar

### Passo 1: Acessar Entrada Manual
1. Acesse o dashboard principal
2. Clique no botão **"ENTRADA MANUAL"** no header (próximo aos indicadores de status)

### Passo 2: Configurar Operação
1. **Símbolo**: Digite o par (ex: BTC/USDT)
2. **Direção**: Escolha COMPRAR ou VENDER
3. **Preço** (opcional): Deixe vazio para usar preço de mercado

### Passo 3: Obter Análise
1. Clique em **"OBTER ANÁLISE IA"**
2. Sistema exibe:
   - Decisão dos 3 cérebros (Groq, Gemini, Local)
   - Confiança total (0-100%)
   - Recomendação (EXECUTAR ou AGUARDAR)
   - Indicadores técnicos (Tendência, RSI)
   - Motivo da decisão

### Passo 4: Executar ou Revisar
- Se aprovado, clique em **"EXECUTAR ENTRADA"**
- Se quiser nova análise, clique em **"NOVA ANÁLISE"**
- Para cancelar, clique em **"FECHAR"**

## 🔄 Integração com Sistema Automático

### Entrada Manual **NÃO** interfere com o sistema automático:
- ✅ Entradas automáticas via broadcast continuam funcionando
- ✅ Sinais do TradingView são processados normalmente
- ✅ Monitor de SL/TP permanece ativo
- ✅ Gestão de risco mantém os mesmos parâmetros

### Entrada Manual **USA** os mesmos recursos:
- ✅ Mesmos brokers configurados (Bybit, Binance)
- ✅ Mesma gestão de risco (% por operação)
- ✅ Mesmos clientes/investidores cadastrados
- ✅ Mesmo sistema de TP/SL automático
- ✅ Mesma integração com banco de dados SQLite

## 🔧 Arquivos Modificados

### Backend (Python)
- **`main_web.py`**:
  - Novo endpoint: `POST /api/trade/manual-entry`
  - Suporta dois modos: `force_execute=false` (análise) e `force_execute=true` (execução)
  - Integrado com IndicatorEngine e GroqValidator
  - Usa mesma lógica de processamento de ordens do broadcast

### Frontend (React)
- **`main.jsx`**:
  - Novos estados: `showManualEntryModal`, `manualEntryFields`, `manualEntryAnalysis`
  - Novas funções: `handleGetManualEntryAnalysis()`, `handleExecuteManualEntry()`
  - Novo botão no header com ícone de alvo (Target)
  - Modal completo com formulário e exibição de análise

## 📊 Fluxo de Dados

```
1. Usuário clica "ENTRADA MANUAL"
   ↓
2. Modal exibe formulário
   ↓
3. Usuário preenche símbolo/direção/preço
   ↓
4. Clica "OBTER ANÁLISE IA"
   ↓
5. Backend busca:
   - Preço atual (se não informado)
   - Indicadores técnicos (IndicatorEngine)
   - Análise de IA (GroqValidator)
   ↓
6. Frontend exibe:
   - Decisão dos 3 cérebros
   - Confiança total
   - Recomendação
   - Indicadores
   ↓
7. Se usuário confirma, clica "EXECUTAR ENTRADA"
   ↓
8. Backend:
   - Registra trade no banco
   - Atualiza central_state
   - Processa ordens para todos os clientes em background
   - Aplica TP/SL
   ↓
9. Frontend:
   - Exibe mensagem de sucesso
   - Atualiza dashboard
   - Fecha modal
```

## 🔒 Validações de Segurança

1. **Símbolo obrigatório**: Sistema valida que um par foi informado
2. **Direção válida**: Aceita apenas BUY/SELL/COMPRAR/VENDER
3. **Preço opcional**: Usa preço de mercado automaticamente
4. **Confirmação dupla**: Modal + confirmação antes de executar
5. **Gestão de risco**: Mesmos limites do sistema automático

## 🎨 Interface Visual

### Botão no Header
- Cor: Verde brilhante (`bg-green-500`)
- Ícone: Alvo (Target)
- Texto: "ENTRADA MANUAL"
- Posicionamento: Entre navegação e indicadores de status

### Modal
- Design moderno com bordas arredondadas
- Fundo escuro com blur
- Cards informativos para análise
- Barra de progresso para confiança da IA
- Botões com estados de loading
- Cores temáticas:
  - Verde: Executar
  - Azul: Análise
  - Amarelo: Aguardar
  - Cinza: Fechar

## 📈 Casos de Uso

### 1. Operação Manual Planejada
Operador identifica oportunidade e quer validação da IA antes de entrar.

### 2. Entrada Rápida
Operador vê movimento no mercado e quer entrar rapidamente com análise.

### 3. Teste de Estratégia
Operador testa uma nova abordagem manualmente antes de automatizar.

### 4. Complemento ao Automático
Sistema automático está em cooldown, mas operador vê oportunidade clara.

## ⚙️ Configuração Necessária

### Variáveis de Ambiente (já existentes)
- `GROQ_API_KEY`: Chave da API Groq
- `GEMINI_API_KEY`: Chave da API Gemini
- `ALLOW_ORDER_EXECUTION`: true/false
- `ALLOW_REAL_TRADING`: true/false
- `RISK_PER_TRADE_PCT`: Percentual por operação (default: 15%)

### Dependências (já instaladas)
- Flask (backend)
- CCXT (conexão com exchanges)
- React (frontend)
- Lucide React (ícones)

## 🧪 Testando a Funcionalidade

### Teste Manual via Dashboard
1. Inicie o servidor: `python main_web.py`
2. Acesse: `http://localhost:5000`
3. Clique em "ENTRADA MANUAL"
4. Digite: BTC/USDT
5. Escolha: COMPRAR
6. Clique: "OBTER ANÁLISE IA"
7. Revise a análise
8. Clique: "EXECUTAR ENTRADA" (se satisfeito)

### Teste via API (cURL)
```bash
# 1. Obter análise apenas
curl -X POST http://localhost:5000/api/trade/manual-entry \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC/USDT",
    "side": "buy",
    "force_execute": false
  }'

# 2. Executar entrada manual
curl -X POST http://localhost:5000/api/trade/manual-entry \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC/USDT",
    "side": "buy",
    "entry_price": 74500,
    "force_execute": true
  }'
```

## 📝 Logs do Sistema

Ao executar entrada manual, você verá no console:

```
============================================================
🎯 ENTRADA MANUAL EXECUTADA
============================================================
   📦 Ativo: BTC/USDT
   📈 Lado: COMPRAR
   🎯 Entrada: $74486.10
   🧠 Confiança IA: 75%
   📝 Motivo: Confluência detectada - Tendência de alta confirmada
============================================================
```

## 🚀 Próximas Melhorias Sugeridas

1. **Histórico de Entradas Manuais**: Tab específica para ver histórico
2. **Templates de Entrada**: Salvar configurações favoritas
3. **Alertas Personalizados**: Notificação quando IA detecta oportunidade
4. **Análise em Tempo Real**: Atualizar análise automaticamente
5. **Gestão de Risco Customizada**: Permitir % diferente por entrada manual

## 🔗 Documentação Relacionada

- Sistema de Broadcast: Ver `main_web.py` linha 2794
- Gestão de Risco: Ver `RISK_PER_TRADE_PCT` configuração
- Análise de IA: Ver `src/ai_brain/validator.py`
- Indicadores Técnicos: Ver `src/indicators.py`

## 📞 Suporte

Se encontrar problemas:
1. Verifique logs do console Python
2. Verifique console do navegador (F12)
3. Confirme que APIs (Groq/Gemini) estão configuradas
4. Verifique conectividade com exchanges

---

**Versão**: 1.0
**Data**: 2026-05-20
**Autor**: Claude Code
**Sistema**: Motor Sniper v60.7+
