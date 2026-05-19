# 🧠 DASHBOARD STREAMLIT - 3º CÉREBRO EXECUTOR PRINCIPAL

## Visão Geral

Este dashboard Streamlit fornece visualização em tempo real do sistema de trading autônomo com o 3º Cérebro operando como executor principal.

### Recursos

- ✅ **Status em Tempo Real**: Monitoramento de métricas e operações ativas
- 📊 **Decisões Recentes**: Histórico de operações e análises
- 📈 **Performance**: Estatísticas de ganho/perda por símbolo
- ⛔ **Bloqueios Ativos**: Símbolos temporariamente bloqueados por padrão de perda

## Tema Premium Dark

O dashboard usa tema dark elegante com:
- Fundo preto sólido (#0a0a0a)
- Textos brancos e cinza claro
- Bordas finas e refinadas
- Status badges coloridas

## Como Executar

### Instalação de Dependências

```bash
pip install streamlit>=1.28.0
```

### Iniciar o Dashboard

```bash
streamlit run dashboard.py
```

O dashboard abrirá em `http://localhost:8501`

### Configuração via Streamlit

Na sidebar, você pode:
- Ajustar intervalo de atualização (5-60 segundos)
- Filtrar por par específico
- Ver informações da versão

## Abas Principais

### 1️⃣ Status em Tempo Real
Exibe:
- Total de trades executados
- Taxa de acerto (Win Rate)
- PnL acumulado
- Status do sistema (ATIVO)
- Seção destacada do 3º Cérebro Executor Principal
- Trades abertos atualmente

### 2️⃣ Decisões Recentes
Mostra histórico das últimas 20 decisões:
- Par negociado
- Lado (BUY/SELL)
- Modo de IA utilizado
- Resultado (Lucro/Perda)
- PnL % obtido
- Data/hora
- Aprendizado registrado

### 3️⃣ Performance
Análises de performance:
- Estatísticas gerais (trades, wins, PnL)
- Indicadores de saúde do sistema
- Performance breakdown por símbolo
- Histórico expandível para cada par

### 4️⃣ Bloqueios Ativos
Gerenciamento de bloqueios:
- Lista de símbolos bloqueados
- Motivo do bloqueio (padrão de perda detectado)
- Tempo de desbloqueio
- Documentação da política de bloqueio

## Estrutura do Banco de Dados

O dashboard lê dados de `database.db` que contém:

### Tabelas Principais

1. **neural_memory** - Memória de decisões (compatível)
2. **local_ml_trades** - Novo: Trades do 3º Cérebro
   - Entrada/saída com indicadores
   - PnL resultado
   - Status (OPEN/CLOSED)
3. **symbol_blocks** - Novo: Bloqueios temporários
   - Símbolo bloqueado
   - Motivo
   - Quando desbloqueará

## Funcionalidades do 3º Cérebro Monitoradas

O dashboard exibe:

✅ **Execução Real Ativa**
- Quando APIs (Groq/Gemini) retornam erro 429
- 3º Cérebro opera com confiança mínima de 80%
- Ordens reais executadas no mercado

📊 **Aprendizado Adaptativo**
- Análise de últimas 50 operações
- Detecção de padrões de falha (3+ perdas)
- Bloqueio automático de símbolos problemáticos

💾 **Rastreamento Completo**
- Todos os indicadores no momento da entrada
- Preço de entrada/saída
- Resultado final (Gain/Loss)

## Refresh Automático

O Streamlit atualiza automaticamente:
- A cada 15 segundos por padrão (configurável)
- Sincroniza com database.db em tempo real
- Sem necessidade de refresh manual

## Performance

O dashboard:
- Usa SQLite com conexões thread-safe
- Suporta múltiplos usuários simultâneos
- Cache de componentes inicializados
- Leitura otimizada de últimos trades

## Troubleshooting

### Dashboard não atualiza
1. Verifique se `database.db` existe
2. Confirme permissões de leitura
3. Reinicie: `streamlit run dashboard.py`

### Erros de conexão
1. Verifique se o bot está rodando e escrevendo em `database.db`
2. Confira SQLite não está corrompido
3. Verifique espaço em disco

### Tema não aplica
1. Atualize Streamlit: `pip install --upgrade streamlit`
2. Limpe cache: `streamlit cache clear`
3. Reinicie o app

## Integração com Railway

Para deployar no Railway:

```yaml
# railway.json
{
  "build": {
    "builder": "nixpacks"
  },
  "deploy": {
    "startCommand": "streamlit run dashboard.py --server.port=$PORT"
  }
}
```

## Variáveis de Ambiente Suportadas

O dashboard usa:
- `DATABASE_PATH` - Caminho customizado do banco (default: `database.db`)

## Versão

Dashboard v61.0 - Compatível com 3º Cérebro Executor Principal v61.0

---

**Desenvolvido para operação autônoma em produção com aprendizado local adaptativo.**
