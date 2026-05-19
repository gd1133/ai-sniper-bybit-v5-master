# Streamlit Web Interface - Guia de Uso

## 📋 Arquivos Criados

1. **streamlit_app.py** - Interface web principal com Streamlit
2. **rodar_web.bat** - Script para Windows iniciar a interface
3. **Procfile** - Configuração atualizada para deploy no Railway
4. **.env.example** - Atualizado com variáveis do Streamlit

## 🚀 Como Executar Localmente

### Windows
```bash
rodar_web.bat
```

### Linux/Mac
```bash
pip install -r requirements.txt
python -m streamlit run streamlit_app.py --server.port 8501 --server.headless true
```

Acesse: http://localhost:8501

## 🌐 Deploy no Railway

O Procfile foi atualizado para executar automaticamente o Streamlit:
- A interface será executada na porta definida pela variável `$PORT`
- Modo headless ativado automaticamente

### Variáveis de Ambiente Necessárias

Adicione no Railway/Docker:
```
STREAMLIT_SERVER_HEADLESS=true
PORT=8501
BYBIT_API_KEY=sua_chave
BYBIT_API_SECRET=seu_secret
```

## 📱 Funcionalidades

### 1. Dashboard (Aba 1)
- **Métricas Gerais**: Saldo total, PNL, número de investidores
- **Tabela de Investidores**: Lista todos os investidores com saldo, PNL e status
- **Atualização em Tempo Real**: Auto-refresh opcional a cada 30 segundos

### 2. Teste de API (Aba 2)
- **Validação de Credenciais**: Testa conexão com Bybit V5
- **Exibe Resultados**:
  - Status de autenticação
  - Saldo USDT disponível
  - Latência da API em ms
- **Troubleshooting**: Dicas integradas para resolver problemas

### 3. Ordens Ativas (Aba 3)
- **Lista de Posições Abertas**: Mostra todas as posições de cada investidor
- **Detalhes por Ordem**:
  - Símbolo, lado (Long/Short)
  - Preço de entrada vs atual
  - PNL em dólares e percentual

## 🔧 Configuração da API Bybit

A interface usa o padrão correto conforme especificado:

```python
from pybit.unified_trading import HTTP

session = HTTP(
    testnet=False,
    api_key=api_key,
    api_secret=api_secret,
    recv_window=10000
)

# Sincroniza tempo ANTES de qualquer chamada
server_time = session.get_server_time()

# Depois obtém saldo
balance = session.get_wallet_balance(accountType="UNIFIED")
```

## ⚠️ Importante

- **Esta interface NÃO executa o bot principal**
- **NÃO inicia threads ou processos de trading**
- **Apenas visualização e testes de API**
- **O bot principal deve ser executado separadamente**

## 🎨 Features Visuais

- Design moderno com CSS customizado
- Cards coloridos para métricas
- Indicadores visuais de PNL (verde/vermelho)
- Progress bars para performance
- Expandable sections para detalhes
- Modo escuro disponível no Streamlit

## 🔄 Auto-Refresh

Para ativar auto-refresh:
1. Marque a checkbox "Auto-refresh (30s)" na sidebar
2. A página será atualizada automaticamente a cada 30 segundos

Ou clique em "🔄 Atualizar agora" para refresh manual.

## 📦 Dependências Adicionadas

```txt
streamlit>=1.45.0
python-dotenv>=1.0.1
```

Todas as outras dependências foram mantidas sem alterações.

## 🛠️ Troubleshooting

### Erro: "Module not found: streamlit"
```bash
pip install -r requirements.txt
```

### Porta 8501 já em uso
```bash
# Especifique outra porta
streamlit run streamlit_app.py --server.port 8502
```

### API timeout
- Verifique conexão com internet
- Confirme que as credenciais estão corretas
- O recv_window está configurado para 10000ms

### Dados não aparecem no Dashboard
- Os dados são mock por padrão
- Adapte as funções `load_investors_data()` e `load_active_orders()`
- Conecte ao banco de dados real do projeto

## 📝 Próximos Passos para Integração Completa

Para conectar com dados reais do bot:

1. **Dashboard**: Modificar `load_investors_data()` para ler do banco SQLite
2. **Ordens Ativas**: Modificar `load_active_orders()` para buscar posições reais
3. **Importar Broker**: Usar as classes existentes `BybitClient` e `BinanceClient`

```python
# Exemplo de integração
from src.broker.bybit_client import BybitClient
from src.database import manager as db

# Criar cliente
broker = BybitClient()

# Obter dados reais
positions = broker.get_positions()
balance = broker.get_balance()
```

## 📚 Referências

- [Documentação Streamlit](https://docs.streamlit.io/)
- [Bybit API V5](https://bybit-exchange.github.io/docs/v5/intro)
- [PyBit Unified Trading](https://github.com/bybit-exchange/pybit)

---

**Versão:** 1.0.0
**Última atualização:** 2026-05-19
