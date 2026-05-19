# -*- coding: utf-8 -*-
"""
Streamlit Web Interface - AI Sniper Bybit V5
Interface web separada para monitoramento e testes de API
NÃO executa o bot principal - apenas visualização e testes
"""

import streamlit as st
import time
import os
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Configuração da página
st.set_page_config(
    page_title="AI Sniper Bybit V5 - Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado para melhorar a aparência
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1E88E5;
    }
    .success-box {
        background-color: #d4edda;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #28a745;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #f8d7da;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #dc3545;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #ffc107;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Título principal
st.markdown('<div class="main-header">🎯 AI Sniper Bybit V5 - Dashboard</div>', unsafe_allow_html=True)

# Inicializa session state
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()
if 'api_tested' not in st.session_state:
    st.session_state.api_tested = False
if 'api_status' not in st.session_state:
    st.session_state.api_status = None
if 'balance_data' not in st.session_state:
    st.session_state.balance_data = None
if 'latency' not in st.session_state:
    st.session_state.latency = None

# Sidebar com informações
with st.sidebar:
    st.image("https://via.placeholder.com/150x50/1E88E5/FFFFFF?text=AI+Sniper", use_container_width=True)
    st.markdown("---")
    st.markdown("### ⚙️ Configurações")

    # Auto-refresh
    auto_refresh = st.checkbox("Auto-refresh (30s)", value=False)
    if auto_refresh:
        time.sleep(30)
        st.rerun()

    st.markdown("---")
    st.markdown("### ℹ️ Informações")
    st.info("Esta interface é apenas para monitoramento. O bot principal deve ser executado separadamente.")

    st.markdown("---")
    st.markdown(f"**Última atualização:** {st.session_state.last_refresh.strftime('%H:%M:%S')}")

    if st.button("🔄 Atualizar agora"):
        st.session_state.last_refresh = datetime.now()
        st.rerun()

# Função para testar API Bybit
def test_bybit_api(api_key, api_secret):
    """
    Testa conexão com Bybit V5 usando pybit.unified_trading
    Retorna: (success, balance, latency, error_message)
    """
    try:
        from pybit.unified_trading import HTTP

        # Cria sessão com as credenciais
        session = HTTP(
            testnet=False,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=10000
        )

        # Sincroniza tempo do servidor (OBRIGATÓRIO antes de qualquer chamada)
        start_time = time.time()
        server_time = session.get_server_time()

        if not server_time or 'result' not in server_time:
            return False, None, None, "Erro ao sincronizar tempo do servidor"

        # Obtém saldo da carteira
        balance_response = session.get_wallet_balance(accountType="UNIFIED")
        latency = round((time.time() - start_time) * 1000, 2)  # ms

        if balance_response['retCode'] == 0:
            # Sucesso - extrai saldo USDT
            balance = 0.0
            if 'result' in balance_response and 'list' in balance_response['result']:
                for account in balance_response['result']['list']:
                    if 'coin' in account:
                        for coin in account['coin']:
                            if coin['coin'] == 'USDT':
                                balance = float(coin['walletBalance'])
                                break

            return True, balance, latency, None
        else:
            error_msg = balance_response.get('retMsg', 'Erro desconhecido')
            return False, None, latency, f"Erro da API: {error_msg}"

    except Exception as e:
        error_msg = str(e)
        if "timeout" in error_msg.lower():
            return False, None, None, f"Timeout: {error_msg}"
        return False, None, None, f"Erro: {error_msg}"

# Função para carregar dados de investidores (mock - adaptar conforme necessário)
def load_investors_data():
    """
    Carrega dados dos investidores do banco de dados
    Esta é uma implementação mock - deve ser adaptada para ler do banco real
    """
    try:
        # Tentar importar e carregar dados reais do banco
        from src.database import manager as db

        # Mock data por enquanto
        return [
            {
                "nome": "Investidor 1",
                "saldo": 1000.00,
                "pnl": 150.50,
                "pnl_pct": 15.05,
                "status": "Ativo"
            },
            {
                "nome": "Investidor 2",
                "saldo": 2500.00,
                "pnl": -75.25,
                "pnl_pct": -3.01,
                "status": "Ativo"
            },
            {
                "nome": "Investidor 3",
                "saldo": 500.00,
                "pnl": 25.00,
                "pnl_pct": 5.00,
                "status": "Pausado"
            }
        ]
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return []

# Função para carregar ordens ativas (mock)
def load_active_orders():
    """
    Carrega ordens ativas dos investidores
    Esta é uma implementação mock - deve ser adaptada para ler dados reais
    """
    try:
        # Mock data por enquanto
        return [
            {
                "investidor": "Investidor 1",
                "symbol": "BTCUSDT",
                "side": "Long",
                "size": 0.05,
                "entry_price": 45000.00,
                "current_price": 45500.00,
                "pnl": 25.00,
                "pnl_pct": 1.11
            },
            {
                "investidor": "Investidor 2",
                "symbol": "ETHUSDT",
                "side": "Short",
                "size": 1.5,
                "entry_price": 3000.00,
                "current_price": 2980.00,
                "pnl": 30.00,
                "pnl_pct": 1.00
            }
        ]
    except Exception as e:
        st.error(f"Erro ao carregar ordens: {e}")
        return []

# Tabs principais
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🔑 Teste de API", "📈 Ordens Ativas"])

# ========== TAB 1: DASHBOARD ==========
with tab1:
    st.header("📊 Dashboard de Investidores")

    # Métricas gerais
    col1, col2, col3, col4 = st.columns(4)

    investors_data = load_investors_data()
    total_balance = sum([inv['saldo'] for inv in investors_data])
    total_pnl = sum([inv['pnl'] for inv in investors_data])
    active_count = sum([1 for inv in investors_data if inv['status'] == 'Ativo'])

    with col1:
        st.metric("💰 Saldo Total", f"${total_balance:,.2f}")
    with col2:
        st.metric("📈 PNL Total", f"${total_pnl:,.2f}", delta=f"{(total_pnl/total_balance*100):.2f}%")
    with col3:
        st.metric("👥 Investidores", len(investors_data))
    with col4:
        st.metric("✅ Ativos", active_count)

    st.markdown("---")

    # Tabela de investidores
    if investors_data:
        st.subheader("Detalhes dos Investidores")

        # Criar tabela formatada
        for investor in investors_data:
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])

                with col1:
                    st.markdown(f"**{investor['nome']}**")
                with col2:
                    st.markdown(f"💰 ${investor['saldo']:,.2f}")
                with col3:
                    pnl_color = "green" if investor['pnl'] >= 0 else "red"
                    st.markdown(f"<span style='color:{pnl_color}'>📈 ${investor['pnl']:,.2f}</span>", unsafe_allow_html=True)
                with col4:
                    pnl_pct_color = "green" if investor['pnl_pct'] >= 0 else "red"
                    st.markdown(f"<span style='color:{pnl_pct_color}'>📊 {investor['pnl_pct']:+.2f}%</span>", unsafe_allow_html=True)
                with col5:
                    status_emoji = "✅" if investor['status'] == "Ativo" else "⏸️"
                    st.markdown(f"{status_emoji} {investor['status']}")

                st.markdown("---")
    else:
        st.warning("Nenhum dado de investidor disponível")

# ========== TAB 2: TESTE DE API ==========
with tab2:
    st.header("🔑 Teste de Conexão API Bybit V5")

    st.info("⚠️ Use esta aba para testar suas credenciais da API Bybit antes de operar.")

    # Formulário de teste
    with st.form("api_test_form"):
        st.subheader("Credenciais da API")

        # Campos de entrada
        api_key = st.text_input(
            "API Key",
            value=os.getenv("BYBIT_API_KEY", ""),
            type="default",
            help="Sua chave de API da Bybit"
        )

        api_secret = st.text_input(
            "API Secret",
            value=os.getenv("BYBIT_API_SECRET", ""),
            type="password",
            help="Seu secret da API da Bybit"
        )

        submit_button = st.form_submit_button("🧪 Testar Conexão", use_container_width=True)

        if submit_button:
            if not api_key or not api_secret:
                st.error("❌ Por favor, preencha API Key e API Secret")
            else:
                with st.spinner("Testando conexão com Bybit V5..."):
                    success, balance, latency, error = test_bybit_api(api_key, api_secret)

                    st.session_state.api_tested = True
                    st.session_state.api_status = success
                    st.session_state.balance_data = balance
                    st.session_state.latency = latency

                    if success:
                        st.success("✅ Conexão estabelecida com sucesso!")
                    else:
                        st.error(f"❌ Falha na conexão: {error}")

    # Exibir resultados do teste
    if st.session_state.api_tested:
        st.markdown("---")
        st.subheader("📋 Resultados do Teste")

        if st.session_state.api_status:
            # Sucesso
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric("🔐 Status de Autenticação", "Autenticado ✅")
                st.markdown('</div>', unsafe_allow_html=True)

            with col2:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.metric("💰 Saldo USDT", f"${st.session_state.balance_data:.2f}")
                st.markdown('</div>', unsafe_allow_html=True)

            with col3:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                latency_color = "green" if st.session_state.latency < 500 else "orange" if st.session_state.latency < 1000 else "red"
                st.metric("⚡ Latência", f"{st.session_state.latency} ms")
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="success-box">✅ Sua API está configurada corretamente e pronta para operar!</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="error-box">❌ Falha na autenticação. Verifique suas credenciais.</div>', unsafe_allow_html=True)

            # Dicas de troubleshooting
            with st.expander("💡 Dicas para resolver problemas"):
                st.markdown("""
                **Problemas comuns:**

                1. **API Key inválida**: Verifique se copiou a chave corretamente da Bybit
                2. **Permissões insuficientes**: Certifique-se que a API tem permissões de "Read Position" e "Trade Orders"
                3. **2FA ativo na API**: Desative o 2FA especificamente na API Key (não na conta)
                4. **IP Whitelist**: Se configurou whitelist de IPs na Bybit, adicione o IP deste servidor
                5. **Testnet vs Mainnet**: Esta interface usa MAINNET (testnet=False)
                6. **Timeout**: Verifique sua conexão com a internet

                **Como criar uma API Key na Bybit:**
                1. Acesse: https://www.bybit.com/app/user/api-management
                2. Crie uma nova API Key
                3. Selecione permissões: Read Position + Trade Orders
                4. **IMPORTANTE**: Desative 2FA na API Key
                5. Copie a Key e Secret imediatamente (o Secret não será exibido novamente)
                """)

# ========== TAB 3: ORDENS ATIVAS ==========
with tab3:
    st.header("📈 Ordens Ativas")

    orders = load_active_orders()

    if orders:
        st.subheader(f"Total de posições abertas: {len(orders)}")

        # Criar tabela de ordens
        for order in orders:
            with st.expander(f"🎯 {order['investidor']} - {order['symbol']} ({order['side']})"):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown(f"**Símbolo:** {order['symbol']}")
                    st.markdown(f"**Lado:** {order['side']}")
                    st.markdown(f"**Tamanho:** {order['size']}")
                    st.markdown(f"**Preço de Entrada:** ${order['entry_price']:,.2f}")

                with col2:
                    st.markdown(f"**Preço Atual:** ${order['current_price']:,.2f}")

                    pnl_color = "green" if order['pnl'] >= 0 else "red"
                    st.markdown(f"**PNL:** <span style='color:{pnl_color}'>${order['pnl']:,.2f}</span>", unsafe_allow_html=True)
                    st.markdown(f"**PNL %:** <span style='color:{pnl_color}'>{order['pnl_pct']:+.2f}%</span>", unsafe_allow_html=True)

                # Gráfico de progresso do PNL
                if order['pnl_pct'] >= 0:
                    st.progress(min(order['pnl_pct'] / 10, 1.0))  # Normaliza para 0-10%
    else:
        st.info("Nenhuma ordem ativa no momento")
        st.markdown("As ordens abertas aparecerão aqui automaticamente.")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 2rem 0;'>
    <p>🎯 <strong>AI Sniper Bybit V5</strong> - Interface Web de Monitoramento</p>
    <p style='font-size: 0.9rem;'>Esta interface não executa trades. Para iniciar o bot, use o comando principal.</p>
    <p style='font-size: 0.8rem; color: #999;'>v1.0.0 | Desenvolvido com ❤️ usando Streamlit</p>
</div>
""", unsafe_allow_html=True)
