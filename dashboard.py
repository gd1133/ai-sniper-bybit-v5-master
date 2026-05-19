"""
🧠 DASHBOARD PREMIUM DARK v61.0 - 3º CÉREBRO EXECUTOR PRINCIPAL
Visualização em tempo real do sistema de trading com aprendizado local.
Interface Streamlit com tema dark elegante e sem termos de "Inteligência Artificial".
"""

import streamlit as st
import sqlite3
import pandas as pd
import json
from datetime import datetime, timedelta
import sys
import os

# Adiciona src ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ai_brain.learning import TradeLearner
from src.ai_brain.local_ml_engine import LocalMLEngine


def inject_dark_theme_css():
    """Injeta CSS com tema Premium Dark elegante."""
    dark_css = """
    <style>
        /* ═══════════════════════════════════════════════════════════ */
        /* 🎨 TEMA PREMIUM DARK v61.0 */
        /* ═══════════════════════════════════════════════════════════ */
        
        /* Fundo Principal - Preto Sólido */
        html, body, [data-testid="stAppViewContainer"] {
            background-color: #0a0a0a !important;
            color: #ffffff !important;
        }
        
        /* Sidebar */
        [data-testid="stSidebar"] {
            background-color: #0f0f0f !important;
            border-right: 1px solid #1a1a1a !important;
        }
        
        /* Headers e Títulos */
        h1, h2, h3, h4, h5, h6 {
            color: #ffffff !important;
            font-weight: 600 !important;
        }
        
        /* Texto Principal */
        p, span, label {
            color: #e0e0e0 !important;
        }
        
        /* Boxes de Métrica */
        [data-testid="stMetric"] {
            background-color: #1a1a1a !important;
            border: 1px solid #2a2a2a !important;
            border-radius: 6px !important;
            padding: 16px !important;
        }
        
        [data-testid="stMetricDelta"] {
            color: #4ade80 !important;
        }
        
        /* Cards e Containers */
        [data-testid="stVerticalBlock"], [data-testid="stHorizontalBlock"] {
            background-color: transparent !important;
        }
        
        .metric-card {
            background-color: #1a1a1a !important;
            border: 1px solid #2a2a2a !important;
            border-radius: 8px !important;
            padding: 20px !important;
            margin-bottom: 12px !important;
        }
        
        .metric-card h3 {
            color: #ffffff !important;
            font-size: 18px !important;
            margin-bottom: 8px !important;
        }
        
        .metric-card p {
            color: #a0a0a0 !important;
            font-size: 14px !important;
        }
        
        /* Buttons */
        button {
            background-color: #1a1a1a !important;
            color: #ffffff !important;
            border: 1px solid #2a2a2a !important;
            border-radius: 6px !important;
        }
        
        button:hover {
            background-color: #252525 !important;
            border-color: #3a3a3a !important;
        }
        
        /* Tabelas */
        [data-testid="dataTable"] {
            background-color: #1a1a1a !important;
        }
        
        [data-testid="dataTable"] tbody tr {
            background-color: #0f0f0f !important;
            border-color: #1a1a1a !important;
        }
        
        [data-testid="dataTable"] tbody tr:hover {
            background-color: #1a1a1a !important;
        }
        
        [data-testid="dataTable"] thead tr {
            background-color: #0a0a0a !important;
            border-color: #1a1a1a !important;
        }
        
        [data-testid="dataTable"] th {
            color: #ffffff !important;
            font-weight: 600 !important;
        }
        
        [data-testid="dataTable"] td {
            color: #e0e0e0 !important;
        }
        
        /* Inputs e Selects */
        input, select, textarea {
            background-color: #1a1a1a !important;
            color: #ffffff !important;
            border: 1px solid #2a2a2a !important;
            border-radius: 4px !important;
        }
        
        input:focus, select:focus, textarea:focus {
            background-color: #252525 !important;
            border-color: #4a4a4a !important;
            outline: none !important;
        }
        
        /* Linha Horizontal */
        hr {
            border-color: #1a1a1a !important;
        }
        
        /* Status Badges */
        .status-active {
            background-color: #1a4d2e !important;
            color: #4ade80 !important;
            padding: 4px 12px !important;
            border-radius: 12px !important;
            font-size: 12px !important;
            font-weight: 600 !important;
        }
        
        .status-inactive {
            background-color: #4d1a1a !important;
            color: #f87171 !important;
            padding: 4px 12px !important;
            border-radius: 12px !important;
            font-size: 12px !important;
            font-weight: 600 !important;
        }
        
        .status-warning {
            background-color: #4d3a1a !important;
            color: #fbbf24 !important;
            padding: 4px 12px !important;
            border-radius: 12px !important;
            font-size: 12px !important;
            font-weight: 600 !important;
        }
        
        /* Destaque Principal */
        .highlight-box {
            background: linear-gradient(135deg, #1a1a1a 0%, #252525 100%) !important;
            border: 1px solid #3a3a3a !important;
            border-radius: 8px !important;
            padding: 24px !important;
            margin: 16px 0 !important;
        }
        
        .highlight-box h2 {
            color: #4ade80 !important;
            margin-top: 0 !important;
        }
        
        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 8px !important;
            height: 8px !important;
        }
        
        ::-webkit-scrollbar-track {
            background: #0a0a0a !important;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #2a2a2a !important;
            border-radius: 4px !important;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: #3a3a3a !important;
        }
        
        /* Expander */
        [data-testid="stExpander"] {
            background-color: transparent !important;
            border: 1px solid #2a2a2a !important;
            border-radius: 6px !important;
        }
        
        [data-testid="stExpanderDetails"] {
            background-color: #1a1a1a !important;
        }
        
        /* Tabs */
        [data-testid="stTabs"] [role="tablist"] {
            border-bottom: 1px solid #2a2a2a !important;
        }
        
        [data-testid="stTabs"] button {
            color: #a0a0a0 !important;
        }
        
        [data-testid="stTabs"] button[aria-selected="true"] {
            color: #4ade80 !important;
            border-bottom: 2px solid #4ade80 !important;
        }
        
        /* Info Box */
        [data-testid="stInfo"], [data-testid="stSuccess"], 
        [data-testid="stWarning"], [data-testid="stError"] {
            background-color: #1a1a1a !important;
            border-radius: 6px !important;
        }
    </style>
    """
    st.markdown(dark_css, unsafe_allow_html=True)


@st.cache_resource
def init_learner():
    """Inicializa o TradeLearner com cache."""
    return TradeLearner()


@st.cache_resource
def init_ml_engine():
    """Inicializa o LocalMLEngine com cache."""
    return LocalMLEngine()


def format_status_badge(status):
    """Formata badge de status."""
    if status == "ACTIVE":
        return '<span class="status-active">🟢 ATIVO</span>'
    elif status == "OFFLINE":
        return '<span class="status-inactive">🔴 OFFLINE</span>'
    else:
        return '<span class="status-warning">🟡 AGUARDANDO</span>'


def main():
    """Interface principal do dashboard."""
    
    # Aplicar tema dark
    inject_dark_theme_css()
    
    # Configuração da página
    st.set_page_config(
        page_title="Sniper Trading - 3º Cérebro",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Título Principal
    st.markdown("""
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #4ade80; font-size: 36px; margin: 0;">🧠 3º CÉREBRO: EXECUTOR PRINCIPAL</h1>
        <p style="color: #a0a0a0; font-size: 16px; margin: 8px 0 0 0;">Sistema Autônomo de Negociação em Tempo Real</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Inicializar componentes
    learner = init_learner()
    ml_engine = init_ml_engine()
    
    # Sidebar
    with st.sidebar:
        st.markdown("### ⚙️ Configuração")
        
        refresh_interval = st.slider(
            "Intervalo de Atualização (s)",
            min_value=5,
            max_value=60,
            value=15,
            step=5
        )
        
        symbol_filter = st.text_input(
            "Filtrar por Par",
            placeholder="ex: ETHUSDT",
            value=""
        )
        
        st.markdown("---")
        st.markdown("### 📊 Sobre")
        st.markdown("""
        **Versão:** 61.0  
        **Modo:** Produção Real  
        **Execução:** Autônoma Local  
        **Status:** ✅ Online
        """)
    
    # Tabs principais
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Status em Tempo Real",
        "🤖 Decisões Recentes",
        "📊 Performance",
        "⛔ Bloqueios Ativos"
    ])
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 1: STATUS EM TEMPO REAL
    # ═══════════════════════════════════════════════════════════════════════════
    
    with tab1:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            stats = ml_engine.get_performance_stats()
            st.metric(
                "📈 Total Trades",
                stats['total_trades'],
                delta=f"✅ {stats['wins']} Wins"
            )
        
        with col2:
            st.metric(
                "🎯 Win Rate",
                f"{stats['win_rate']:.1f}%",
                delta_color="off"
            )
        
        with col3:
            st.metric(
                "💰 PnL Total",
                f"{stats['total_pnl']:.2f}%",
                delta_color="off"
            )
        
        with col4:
            st.metric(
                "🧠 Status",
                "ATIVO",
                delta="Real Execution"
            )
        
        st.markdown("---")
        
        # Destaque principal do 3º Cérebro
        st.markdown("""
        <div class="highlight-box">
            <h2>🧠 3º CÉREBRO: EXECUTOR PRINCIPAL (ATIVO REAL)</h2>
            <p>
                Sistema autônomo de análise matemática local em operação.
                Executa ordens reais de mercado quando APIs LLM falharem com status 429 (Rate Limit).
            </p>
            <ul style="color: #a0a0a0;">
                <li><strong>Modo Operação:</strong> Autônomo Local com Aprendizado Adaptativo</li>
                <li><strong>Mínimo Confiança:</strong> 80% para execução real</li>
                <li><strong>Bloqueio Automático:</strong> 3+ perdas consecutivas sob mesma condição</li>
                <li><strong>Notional Mínimo:</strong> $2.50 USDT (Bybit) | $5.50 USDT (Binance)</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
        # Trades abertos
        st.markdown("### 📂 Trades Abertos")
        open_trades = learner.get_open_trades()
        
        if open_trades:
            df_open = pd.DataFrame(open_trades)
            # Seleciona colunas relevantes
            display_cols = ['symbol', 'lado', 'ia_mode', 'timestamp', 'status']
            if all(col in df_open.columns for col in display_cols):
                st.dataframe(
                    df_open[display_cols],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.dataframe(df_open, use_container_width=True, hide_index=True)
        else:
            st.info("📭 Nenhum trade aberto no momento")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 2: DECISÕES RECENTES
    # ═══════════════════════════════════════════════════════════════════════════
    
    with tab2:
        st.markdown("### 🤖 Últimas Decisões do 3º Cérebro")
        
        recent_trades = learner.get_recent_trades(limit=20)
        
        if recent_trades:
            df_recent = pd.DataFrame(recent_trades)
            
            # Formatar para exibição
            display_data = []
            for _, row in df_recent.iterrows():
                pnl = row.get('pnl_pct', 0)
                result = "✅ LUCRO" if pnl > 0 else "❌ PERDA"
                display_data.append({
                    "Par": row.get('symbol', 'N/A'),
                    "Lado": row.get('lado', 'N/A'),
                    "Modo IA": row.get('ia_mode', 'LOCAL'),
                    "Resultado": result,
                    "PnL %": f"{pnl:.2f}%",
                    "Data": row.get('timestamp', 'N/A'),
                    "Aprendizado": row.get('licao_aprendida', '---')
                })
            
            df_display = pd.DataFrame(display_data)
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("📭 Sem histórico de decisões")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 3: PERFORMANCE
    # ═══════════════════════════════════════════════════════════════════════════
    
    with tab3:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📊 Estatísticas Gerais")
            stats = ml_engine.get_performance_stats()
            st.markdown(f"""
            **3º Cérebro Performance**
            - Total Trades: `{stats['total_trades']}`
            - Vitórias: `{stats['wins']}`
            - Taxa de Acerto: `{stats['win_rate']:.1f}%`
            - PnL Acumulado: `{stats['total_pnl']:.2f}%`
            """)
        
        with col2:
            st.markdown("### 🎯 Indicadores de Saúde")
            
            if stats['total_trades'] > 0:
                health_score = min(100, stats['win_rate'] + (stats['total_pnl'] / 10))
                health_color = "🟢" if health_score >= 70 else "🟡" if health_score >= 50 else "🔴"
                st.metric(
                    "Saúde do Sistema",
                    f"{health_score:.0f}%",
                    delta=health_color
                )
            else:
                st.info("Aguardando primeiro trade...")
        
        st.markdown("---")
        
        # Histórico por símbolo
        st.markdown("### 📈 Performance por Símbolo")
        
        # Listar todos os símbolos únicos
        conn = learner._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT symbol FROM local_ml_trades ORDER BY symbol")
            symbols = [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()
        
        if symbols:
            for symbol in symbols:
                with st.expander(f"📊 {symbol}"):
                    sym_stats = ml_engine.get_performance_stats(symbol)
                    st.markdown(f"""
                    - Trades: `{sym_stats['total_trades']}`
                    - Wins: `{sym_stats['wins']}`
                    - Win Rate: `{sym_stats['win_rate']:.1f}%`
                    - PnL: `{sym_stats['total_pnl']:.2f}%`
                    """)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TAB 4: BLOQUEIOS ATIVOS
    # ═══════════════════════════════════════════════════════════════════════════
    
    with tab4:
        st.markdown("### ⛔ Símbolos Bloqueados (Padrão de Perda Detectado)")
        
        blocked_symbols = ml_engine.get_blocked_symbols()
        
        if blocked_symbols:
            df_blocked = pd.DataFrame([
                {
                    "Par": b['symbol'],
                    "Desbloqueio": b.get('block_until', 'N/A'),
                    "Motivo": b.get('reason', 'Padrão de perda detectado')
                }
                for b in blocked_symbols
            ])
            st.dataframe(df_blocked, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Nenhum símbolo bloqueado. Sistema operando normalmente.")
        
        st.markdown("---")
        st.markdown("### ℹ️ Política de Bloqueio")
        st.markdown("""
        O 3º Cérebro implementa aprendizado adaptativo que detecta padrões de falha:
        
        - **Detecção:** 3+ perdas consecutivas sob mesmas condições técnicas (SMA 200, SuperTrend)
        - **Bloqueio:** Símbolo é bloqueado por 30 minutos automaticamente
        - **Razão:** Evitar repetição de erros reconhecidos pelo sistema
        - **Desbloqueio:** Automático após expiration timer ou reset manual
        """)


if __name__ == "__main__":
    main()
