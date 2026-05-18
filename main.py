"""
╔══════════════════════════════════════════════════════════════════╗
║           MOTOR SNIPER V60.7 — GIVALDO SUPREME                  ║
║        Sistema de Entrada Ponto Zero (Triple Brain)              ║
╚══════════════════════════════════════════════════════════════════╝

Regras de Negócio:
  - API: pybit.unified_trading.HTTP com recv_window=20000
  - Timeframe de varredura: 30 minutos (30m) — exclusivo
  - Máximo de operações simultâneas: 1 (uma)
  - Entrada padrão: 15 % do saldo USDT (ou override via RISK_PER_TRADE_PCT)
  - Stop Loss: 50 % da entrada (≡ 5 % de preço com 10× alavancagem)
  - Take Profit: 100 % de lucro sobre a entrada (≡ 10 % de preço)
  - Alavancagem: 10× | Modo de Margem: Cross
  - Sinal autorizado somente quando:
      ① Confiança combinada ≥ 60 %
      ② 5 confluências simultâneas aprovadas
  - Erro 10003 (Chave de API inválida): log claro e encerramento seguro.
"""

import os
import time
import sys
import getpass
import math

from dotenv import load_dotenv

# ─── Carrega variáveis de ambiente ────────────────────────────────────────────
load_dotenv()

DEFAULT_RISK_PER_TRADE_PCT = 15.0


def _load_risk_per_trade_pct() -> float:
    """Lê o percentual de risco por ordem com fallback seguro."""
    try:
        return float(os.getenv('RISK_PER_TRADE_PCT', 15)) / 100
    except (TypeError, ValueError):
        print(f"⚠️ [RISK MANAGEMENT] RISK_PER_TRADE_PCT inválido. Usando fallback de {DEFAULT_RISK_PER_TRADE_PCT:.0f}%.")
        return DEFAULT_RISK_PER_TRADE_PCT / 100


RISK_PER_TRADE_PCT = _load_risk_per_trade_pct()


def _format_risk_per_trade_pct() -> str:
    pct_value = RISK_PER_TRADE_PCT * 100
    return f"{pct_value:.0f}%" if math.isclose(pct_value, round(pct_value), rel_tol=0, abs_tol=1e-9) else f"{pct_value:.2f}%"


def _log_risk_management_mode() -> None:
    if math.isclose(RISK_PER_TRADE_PCT, 0.15, rel_tol=0, abs_tol=1e-9):
        print("🔧 [RISK MANAGEMENT] Modo de entrada atualizado para: 15% do valor da banca real.")
    else:
        print(f"🔧 [RISK MANAGEMENT] Modo de entrada atualizado para: {_format_risk_per_trade_pct()} do valor da banca real.")

# ─── Configurações Globais ─────────────────────────────────────────────────────

# Define se usa testnet ou produção (USE_TESTNET=true → testnet)
USE_TESTNET: bool = str(os.getenv("USE_TESTNET", "true")).strip().lower() in {"1", "true", "yes", "on"}

# Par monitorado (pode ser sobrescrito via variável de ambiente)
SYMBOL: str = os.getenv("SYMBOL", "ETHUSDT")

# Intervalo de tempo dos candles — fixado em 30 minutos
TIMEFRAME: str = "30m"

# Parâmetros de risco
ENTRY_PCT_DEFAULT: float = RISK_PER_TRADE_PCT
ENTRY_PCT_AFTER_STOP: float = RISK_PER_TRADE_PCT  # Mantido para compatibilidade com o fluxo do RiskManager
# Com 10× de alavancagem, 5 % de preço = 50 % de perda sobre margem (Stop Loss)
# Com 10× de alavancagem, 10 % de preço = 100 % de lucro sobre margem (Take Profit)
STOP_LOSS_PCT: float = 0.05    # 5 % de preço → 50 % da margem (entrada)
TAKE_PROFIT_PCT: float = 0.10  # 10 % de preço → 100 % de lucro sobre margem
LEVERAGE: int = 10             # 10× alavancagem
MARGIN_MODE: str = "CROSSED"   # Cross Margin

# Confiança mínima exigida pelo Tribunal dos 3 Cérebros
MIN_CONFIDENCE: int = 60       # 60 % combinado

# Pausa entre ciclos de varredura (segundos)
SCAN_INTERVAL: int = int(os.getenv("SCAN_INTERVAL", "30"))


# ─── Imports internos ─────────────────────────────────────────────────────────
from src.broker.bybit_client import BybitClient
from src.engine.indicators import IndicatorEngine
from src.ai_brain.validator import GroqValidator
from src.ai_brain.learning import TradeLearner


# ─── Gestão de Risco Dinâmica ─────────────────────────────────────────────────

class RiskManager:
    """
    Controla o percentual de entrada de forma dinâmica:

      - Padrão  : 15 % do saldo (ENTRY_PCT_DEFAULT)
      - Após SL : mantém o mesmo percentual configurado
      - Após Gain: mantém o mesmo percentual configurado

    Uso:
        rm = RiskManager()
        pct = rm.current_entry_pct   # percentual ativo
        rm.register_stop()           # chamado quando trade fecha no SL
        rm.register_gain()           # chamado quando trade fecha no TP
    """

    def __init__(self) -> None:
        self._last_result: str = "NONE"  # "NONE" | "STOP" | "GAIN"

    @property
    def current_entry_pct(self) -> float:
        """Retorna o percentual de entrada do próximo trade."""
        return ENTRY_PCT_AFTER_STOP if self._last_result == "STOP" else ENTRY_PCT_DEFAULT

    def register_stop(self) -> None:
        """Registra que o último trade encerrou em Stop Loss."""
        self._last_result = "STOP"
        print(
            f"⚠️  [RISCO] Último trade: STOP LOSS. "
            f"Próxima entrada mantida em {ENTRY_PCT_AFTER_STOP * 100:.0f}% do saldo."
        )

    def register_gain(self) -> None:
        """Registra que o último trade encerrou em lucro (Take Profit)."""
        self._last_result = "GAIN"
        print(
            f"✅ [RISCO] Último trade: GAIN. "
            f"Entrada mantida em {ENTRY_PCT_DEFAULT * 100:.0f}% do saldo."
        )

    def status(self) -> str:
        return (
            f"Último resultado={self._last_result} | "
            f"Próxima entrada={self.current_entry_pct * 100:.0f}%"
        )


# ─── Consulta de Posições Abertas ────────────────────────────────────────────

def get_active_position(client: BybitClient, symbol: str) -> "dict | None":
    """
    Retorna o dict da posição aberta na Bybit V5 para *symbol*, ou None se não
    houver posição ativa.

    Garante a regra de no máximo 1 operação simultânea: o loop principal só
    autoriza nova entrada quando esta função retorna None.
    """
    if client.pybit_session is None or not client.authenticated:
        return None

    v5_symbol = client._normalize_v5_symbol(symbol)
    try:
        rsp = client.pybit_session.get_positions(category="linear", symbol=v5_symbol)
        ok, _ = client._handle_v5_ret_code(rsp, "get_positions")
        if not ok:
            return None
        for item in (rsp.get("result") or {}).get("list", []):
            if float(item.get("size", 0) or 0) > 0:
                return item
        return None
    except Exception as e:
        print(f"⚠️  [POSIÇÃO] Erro ao consultar posição aberta: {e}")
        return None


def get_last_closed_pnl(client: BybitClient, symbol: str) -> "float | None":
    """
    Retorna o PnL realizado do último trade fechado para *symbol*.

    Valor positivo  → trade encerrado com lucro  (Take Profit / GAIN)
    Valor negativo  → trade encerrado com perda   (Stop Loss)
    None            → sem histórico ou API indisponível
    """
    if client.pybit_session is None or not client.authenticated:
        return None

    v5_symbol = client._normalize_v5_symbol(symbol)
    try:
        rsp = client.pybit_session.get_closed_pnl(
            category="linear", symbol=v5_symbol, limit=1
        )
        ok, _ = client._handle_v5_ret_code(rsp, "get_closed_pnl")
        if not ok:
            return None
        items = (rsp.get("result") or {}).get("list", [])
        if items:
            return float(items[0].get("closedPnl", 0) or 0)
        return None
    except Exception as e:
        print(f"⚠️  [PNL] Erro ao consultar PnL fechado: {e}")
        return None


# ─── Conexão Centralizada com a Bybit (UTA / pybit V5) ────────────────────────

def build_client() -> BybitClient:
    """
    Instancia o BybitClient garantindo:
      - pybit.unified_trading.HTTP (V5)
      - recv_window=20000
      - Endpoint correto conforme USE_TESTNET
    """
    api_key = str(os.getenv("BYBIT_API_KEY", "")).strip()
    api_secret = str(os.getenv("BYBIT_API_SECRET", "")).strip()

    if not api_key or not api_secret:
        print("⚠️  [CONFIGURAÇÃO] BYBIT_API_KEY / BYBIT_API_SECRET não definidas no .env")
        print("    O robô rodará em modo leitura (sem execução de ordens).")

    client = BybitClient(api_key=api_key, api_secret=api_secret, testnet=USE_TESTNET)
    return client


# ─── Gestão de Margem e Alavancagem ───────────────────────────────────────────

def configure_leverage_and_margin(client: BybitClient, symbol: str) -> bool:
    """
    Define:
      - Modo de Margem: Cross (CROSSED)
      - Alavancagem: 10×

    Retorna True se bem-sucedido, False caso contrário.
    """
    if client.pybit_session is None:
        print("⚠️  [LEVERAGE] pybit_session indisponível; configuração de margem ignorada.")
        return False

    v5_symbol = client._normalize_v5_symbol(symbol)

    try:
        # Configura modo de margem para Cross (buyLeverage = sellLeverage = 10)
        rsp_margin = client.pybit_session.set_leverage(
            category="linear",
            symbol=v5_symbol,
            buyLeverage=str(LEVERAGE),
            sellLeverage=str(LEVERAGE),
        )
        ok, err = client._handle_v5_ret_code(rsp_margin, "set_leverage")
        if not ok and "leverage not modified" not in err.lower():
            print("⚠️  [LEVERAGE] Falha ao configurar alavancagem (verifique permissões da chave API).")
            return False

        # Ativa modo Cross Margin
        rsp_mode = client.pybit_session.switch_margin_mode(
            category="linear",
            symbol=v5_symbol,
            tradeMode=0,          # 0 = Cross, 1 = Isolated
            buyLeverage=str(LEVERAGE),
            sellLeverage=str(LEVERAGE),
        )
        ok, err = client._handle_v5_ret_code(rsp_mode, "switch_margin_mode")
        if not ok and "margin mode is not modified" not in err.lower():
            print("⚠️  [MARGIN MODE] Falha ao configurar Cross Margin (verifique permissões da chave API).")
            return False

        print(f"✅ [CONFIGURAÇÃO] {v5_symbol} → {LEVERAGE}× alavancagem | Cross Margin")
        return True

    except Exception as e:
        # Erro 10003 — chave inválida: loga e encerra o fluxo
        if "10003" in str(e):
            print("❌ [ERRO 10003] Chave de API inválida ou sem permissão.")
            print("   → Verifique BYBIT_API_KEY e BYBIT_API_SECRET no arquivo .env")
            print("   → Certifique-se de que a chave tem permissão de 'Futuros' ativada na Bybit.")
            return False
        print(f"⚠️  [LEVERAGE] Exceção inesperada ao configurar alavancagem/margem.")
        return False


# ─── Gestão de Risco: Tamanho da Entrada ──────────────────────────────────────

def calculate_entry_qty(client: BybitClient, price: float, entry_pct: float) -> float:
    """
    Calcula a quantidade de contratos para a entrada.

    Regras:
      - Valor de entrada = entry_pct do saldo USDT (15 % por padrão)
      - Quantidade = valor_entrada / preço_atual
      - Se saldo ≤ 0 → operação abortada (retorna 0.0)
      - Piso mínimo de $3 USD de margem (mínimo aceito pela Bybit V5)
    """
    balance = client.get_balance()

    # Segurança: saldo nulo ou não positivo → aborta
    if balance is None or balance <= 0:
        print("🚫 [SEGURANÇA] Saldo USDT inválido ou zero. Operação ABORTADA.")
        return 0.0

    entry_value = balance * entry_pct

    # 🛡️ TRAVA DE SEGURANÇA: Valida tamanho mínimo de ordem
    # Se margem calculada for muito baixa, força mínimo operacional
    MIN_MARGIN_USD = 3.0  # Piso mínimo de $3 USD de margem (mínimo aceito pela Bybit V5)
    if 0 < entry_value < MIN_MARGIN_USD:
        print(f"⚠️  [RISK MANAGEMENT] Margem calculada (${entry_value:.2f}) abaixo do mínimo. Ajustando para ${MIN_MARGIN_USD:.2f}")
        entry_value = MIN_MARGIN_USD

    qty = entry_value / price if price > 0 else 0.0

    print(f"💰 [RISCO] Saldo={balance:.2f} USDT | Entrada={entry_value:.2f} USDT ({entry_pct*100:.0f}%) | Qty≈{qty:.4f}")
    return qty


# ─── Verificação das 5 Confluências ───────────────────────────────────────────

def check_five_confluences(tech_data: dict, consensus: dict) -> tuple[bool, list[str]]:
    """
    Valida 5 confluências obrigatórias antes de autorizar o Ponto Zero:

      1. Tendência Macro (SMA 200) — ALTA ou BAIXA definida
      2. Fibonacci 0.618 — preço dentro da Golden Zone (≤ 1,5 % de distância)
      3. Volume Institucional — volume_ratio ≥ 1.5×
      4. RSI em zona segura — 20 < RSI < 80 (sem exaustão)
      5. SuperTrend confirmando a direção

    Retorna (aprovado: bool, detalhes: list[str]).
    """
    checks = consensus.get("local_checks", {})
    trend = tech_data.get("trend", "NEUTRO")
    rsi = float(tech_data.get("rsi", 50) or 50)
    st_signal = int(tech_data.get("supertrend_signal", 0) or 0)
    decisao = consensus.get("decisao", "SCANNER")

    # Confluência 5: SuperTrend alinhado com a decisão
    st_ok = (
        (decisao == "COMPRAR" and st_signal == 1 and trend == "ALTA")
        or (decisao == "VENDER" and st_signal == -1 and trend == "BAIXA")
    )

    confluences = {
        "1_macro_trend (SMA200)":       checks.get("macro_trend", False),
        "2_fibonacci_618":              checks.get("fib_zone", False),
        "3_volume_institucional":       checks.get("institutional_volume", False),
        "4_rsi_seguro (20<RSI<80)":     checks["rsi_safe"] if "rsi_safe" in checks else (20 < rsi < 80),
        "5_supertrend_alinhado":        st_ok,
    }

    passed = [name for name, ok in confluences.items() if ok]
    failed = [name for name, ok in confluences.items() if not ok]

    all_ok = len(passed) == 5

    # Log detalhado para auditoria
    status_lines = [f"   {'✅' if ok else '❌'} {name}" for name, ok in confluences.items()]
    print(f"\n📐 [5 CONFLUÊNCIAS] {len(passed)}/5 aprovadas:")
    for line in status_lines:
        print(line)

    return all_ok, failed


# ─── Colocação de Ordem com TP/SL ─────────────────────────────────────────────

def place_order_with_protection(
    client: BybitClient,
    learner: TradeLearner,
    symbol: str,
    side: str,
    qty: float,
    price: float,
    consensus: dict,
) -> bool:
    """
    Executa a ordem a mercado e imediatamente define TP/SL via pybit V5.

    TP/SL Sniper:
      - Take Profit: +10 % sobre o preço de entrada (= +100 % de margem com 10× alavancagem)
      - Stop Loss:    -5 % sobre o preço de entrada (=  -50 % de margem com 10× alavancagem)
    """
    v5_symbol = client._normalize_v5_symbol(symbol)
    v5_side = "Buy" if side.upper() == "BUY" else "Sell"
    close_side = "Sell" if v5_side == "Buy" else "Buy"

    tp_price = round(price * (1 + TAKE_PROFIT_PCT), 2) if v5_side == "Buy" else round(price * (1 - TAKE_PROFIT_PCT), 2)
    sl_price = round(price * (1 - STOP_LOSS_PCT), 2) if v5_side == "Buy" else round(price * (1 + STOP_LOSS_PCT), 2)

    print(f"\n🚀 [PONTO ZERO] {v5_symbol} | {v5_side} | Qty={qty}")
    print(f"   📍 Entrada : ${price:.4f}")
    print(f"   🎯 TP       : ${tp_price:.4f}  (+{TAKE_PROFIT_PCT*100:.0f}% preço = +100% margem)")
    print(f"   🛡️  SL       : ${sl_price:.4f}  (-{STOP_LOSS_PCT*100:.0f}% preço = -50% margem)")
    print(f"   🧠 Motivo   : {consensus.get('motivo', '')[:120]}")

    if client.pybit_session is None:
        print("⚠️  [ORDEM] pybit_session indisponível. Ordem NÃO executada.")
        return False

    try:
        normalized_qty = client._normalize_order_qty(symbol, qty)
        qty_value = float(normalized_qty)

        # Coloca ordem a mercado com TP/SL embutidos (V5 suporta na mesma chamada)
        payload = {
            "category": "linear",
            "symbol": v5_symbol,
            "side": v5_side,
            "orderType": "Market",
            "qty": normalized_qty,
            "takeProfit": str(tp_price),
            "stopLoss": str(sl_price),
            "tpTriggerBy": "MarkPrice",
            "slTriggerBy": "MarkPrice",
        }

        print(f"   📦 Adjusted qty: {qty_value}")
        rsp = client.pybit_session.place_order(**payload)
        ok, err = client._handle_v5_ret_code(rsp, "place_order (Sniper)")

        if not ok:
            # Erro 10003: chave inválida — alerta claro e encerramento
            if "10003" in err:
                print("❌ [ERRO 10003] Chave de API inválida detectada na execução da ordem.")
                print("   → Verifique BYBIT_API_KEY / BYBIT_API_SECRET no .env")
                print("   → A chave precisa ter permissão 'Contratos' (Futuros) habilitada.")
                client.authenticated = False
            else:
                print("❌ [ORDEM FALHOU] Bybit retornou erro na execução. Verifique os logs do broker.")
            return False

        result = (rsp or {}).get("result", {})
        order_id = result.get("orderId") or result.get("orderLinkId", "N/A")
        print(f"✅ [ORDEM CONFIRMADA] orderId={order_id} | TP/SL setados na mesma chamada")

        # Registra na memória neural
        learner.record_entry(
            symbol=v5_symbol,
            side=v5_side.upper(),
            ia_mode="TRIPLE_BRAIN",
            reason=consensus.get("motivo", ""),
        )
        return True

    except Exception as e:
        err_str = str(e)
        if "10003" in err_str:
            print("❌ [ERRO 10003] Chave de API inválida ou expirada.")
            print("   → Verifique BYBIT_API_KEY / BYBIT_API_SECRET no .env")
            print("   → Certifique-se de que a chave não está expirada e tem permissão Futuros.")
            client.authenticated = False
        else:
            print("❌ [ORDEM EXCEÇÃO] Exceção inesperada na execução da ordem de mercado.")
        return False


# ─── Autenticação 2FA (Google Authenticator / TOTP) ──────────────────────────

def verify_2fa() -> None:
    """
    Valida o código TOTP do Google Authenticator antes de inicializar a sessão.

    Lógica de verificação (em ordem de prioridade):
      1. Se a variável de ambiente TOTP_SECRET não estiver definida, o 2FA é
         considerado opcional e a função retorna sem bloquear (compatibilidade
         com ambientes sem 2FA configurado).
      2. Se TOTP_CODE estiver definida (deploy em nuvem / CI), usa esse valor
         diretamente, sem interação com o terminal — evita bloqueio em Railway.
      3. Se houver TTY interativo (execução local), solicita o código ao operador.
      4. Se nenhum dos casos acima fornecer um código, o arranque é interrompido
         com mensagem clara.

    Variáveis de ambiente relevantes:
      TOTP_SECRET  — segredo Base32 gerado pelo Google Authenticator (obrigatório
                     para ativar 2FA).
      TOTP_CODE    — código de 6 dígitos fornecido pelo app; use em ambientes sem
                     TTY (ex.: Railway, Docker) para evitar bloqueio de input.
    """
    try:
        import pyotp  # noqa: PLC0415
    except ImportError:
        print("⚠️  [2FA] pyotp não instalado — execute 'pip install pyotp==2.9.0'.")
        print("         O 2FA será ignorado nesta inicialização.")
        return

    totp_secret = str(os.getenv("TOTP_SECRET", "")).strip()
    if not totp_secret:
        # 2FA não configurado: avança sem bloqueio
        print("ℹ️  [2FA] TOTP_SECRET não definida. Autenticação 2FA desativada.")
        return

    totp = pyotp.TOTP(totp_secret)

    # ── Origem do código: variável de ambiente (cloud) ────────────────────────
    env_code = str(os.getenv("TOTP_CODE", "")).strip()
    if env_code:
        code = env_code
        source = "variável de ambiente TOTP_CODE"
    elif sys.stdin.isatty():
        # ── Origem do código: input interativo (terminal local) ───────────────
        print("\n🔐 [2FA] Google Authenticator — insira o código de 6 dígitos:")
        code = getpass.getpass("   Código: ").strip()
        source = "input interativo"
    else:
        # ── Sem TTY e sem TOTP_CODE: não pode prosseguir ──────────────────────
        print("❌ [2FA] TOTP_SECRET definida, mas não há TTY nem TOTP_CODE disponível.")
        print("   → Em ambientes cloud (Railway/Docker), defina TOTP_CODE nas variáveis")
        print("     de ambiente com o código atual do Google Authenticator.")
        sys.exit(1)

    if totp.verify(code, valid_window=1):
        print(f"✅ [2FA] Código válido (fonte: {source}). Autenticação concluída.")
    else:
        print(f"❌ [2FA] Código INVÁLIDO (fonte: {source}).")
        print("   → Verifique se o horário do dispositivo está sincronizado (NTP).")
        print("   → O código expira a cada 30 segundos — tente novamente.")
        sys.exit(1)


# ─── Diagnóstico de Inicialização ─────────────────────────────────────────────

def run_diagnostics(client: BybitClient, symbol: str) -> None:
    """
    Executa a rotina de diagnóstico antes de entrar no loop de varredura.

    Verificações realizadas:
      1. Conectividade — acesso ao endpoint Bybit (público, sem credenciais)
      2. Ambiente — confirma se está operando em Testnet ou Produção
      3. Permissões da chave API:
           • Ordens   — tenta listar ordens abertas (confirma permissão "Trade")
           • Posições — consulta posições abertas (confirma permissão "Position")

    Nenhuma falha aqui interrompe o boot; o sistema apenas loga um alerta e
    continua — permitindo operação em modo leitura quando as credenciais não
    têm todas as permissões necessárias.
    """
    print("\n" + "═" * 60)
    print("  DIAGNÓSTICO DE INICIALIZAÇÃO")
    print("═" * 60)

    # ── 1. Ambiente ───────────────────────────────────────────────────────────
    env_label = "TESTNET ⚠️ (sandbox)" if USE_TESTNET else "PRODUÇÃO 🔴 (real)"
    print(f"🌐 Ambiente   : {env_label}")
    print(f"   Endpoint   : {client.active_endpoint}")

    # ── 2. Conectividade via pybit (V5 public endpoint) ───────────────────────
    ok_conn, msg_conn = client.test_connection()
    if ok_conn:
        print(f"🔌 Conexão    : OK — {msg_conn}")
    else:
        print(f"⚠️  Conexão    : FALHOU — {msg_conn}")
        if "10003" in msg_conn:
            print("   → Chave de API inválida (10003). Verifique BYBIT_API_KEY no .env")

    # ── 3. Permissões — apenas se autenticado ─────────────────────────────────
    if not client.authenticated or client.pybit_session is None:
        print("🔑 Permissões : chave API não configurada — modo leitura ativo.")
        print("═" * 60 + "\n")
        return

    v5_symbol = client._normalize_v5_symbol(symbol)

    # 3a. Permissão de Ordens (Trade)
    try:
        rsp_orders = client.pybit_session.get_open_orders(
            category="linear", symbol=v5_symbol
        )
        ok_orders, _ = client._handle_v5_ret_code(rsp_orders, "get_open_orders")
        status_orders = "✅ OK" if ok_orders else "❌ FALHOU (verifique permissão 'Trade')"
    except Exception as exc:
        status_orders = f"❌ EXCEÇÃO — {str(exc)[:80]}"

    # 3b. Permissão de Posições
    try:
        rsp_pos = client.pybit_session.get_positions(
            category="linear", symbol=v5_symbol
        )
        ok_pos, _ = client._handle_v5_ret_code(rsp_pos, "get_positions")
        status_pos = "✅ OK" if ok_pos else "❌ FALHOU (verifique permissão 'Position')"
    except Exception as exc:
        status_pos = f"❌ EXCEÇÃO — {str(exc)[:80]}"

    print(f"🔑 Ordens     : {status_orders}")
    print(f"🔑 Posições   : {status_pos}")
    print("═" * 60 + "\n")




def run_sniper(symbol: str = SYMBOL):
    """
    Loop principal do Motor Sniper V60.7.

    Regras de execução:
      - Varredura exclusiva no timeframe de 30 minutos (30m)
      - Máximo de 1 operação ativa simultaneamente
      - Gestão de risco via RiskManager com 15% padrão da banca (override opcional por ambiente)

    Fluxo por ciclo:
      1. Verifica posição ativa → bloqueia nova entrada se já houver 1 aberta
      2. Detecta fechamento de posição → atualiza RiskManager com resultado (SL/Gain)
      3. Busca OHLCV 30m e calcula indicadores (Cérebro 1 — Local/Matemático)
      4. Consulta Groq/LLaMA (Cérebro 2 — Tático)
      5. Consulta Gemini (Cérebro 3 — Estratégico / Histórico)
      6. Gera consenso ponderado (Gemini 40% | Groq 35% | Local 25%)
      7. Valida 5 confluências simultâneas
      8. Se confiança ≥ 60 % e todas as confluências OK → executa Ponto Zero
    """
    print("═" * 60)
    print(f"  MOTOR SNIPER V60.7 — iniciando em {'TESTNET' if USE_TESTNET else 'PRODUÇÃO'}")
    print(f"  Par: {symbol} | Timeframe: {TIMEFRAME} | Intervalo: {SCAN_INTERVAL}s")
    _log_risk_management_mode()
    print(f"  Regras: 1 trade ativo | SL=50% entrada | TP=100% lucro | Entrada={ENTRY_PCT_DEFAULT * 100:.0f}%")
    print("═" * 60)

    # ── Inicialização dos componentes ──────────────────────────────────────────
    client = build_client()
    learner = TradeLearner()
    risk_manager = RiskManager()

    gemini_key = str(os.getenv("GEMINI_API_KEY", "")).strip()
    groq_key = str(os.getenv("GROQ_API_KEY", "")).strip()
    validator = GroqValidator(api_key_gemini=gemini_key, api_key_groq=groq_key)

    # ── Teste de conexão inicial ───────────────────────────────────────────────
    ok, msg = client.test_connection()
    if not ok:
        if "10003" in msg:
            print("❌ [ERRO 10003] Chave de API inválida. Verifique BYBIT_API_KEY e BYBIT_API_SECRET.")
            print("   → O Motor Sniper não pode iniciar sem autenticação válida.")
            sys.exit(1)
        print(f"⚠️  [CONEXÃO] {msg} — rodando sem autenticação.")
    else:
        print(f"🔌 [CONEXÃO OK] {msg}")

    # ── Configura alavancagem e modo de margem ─────────────────────────────────
    if client.authenticated:
        configure_leverage_and_margin(client, symbol)

    # ── Diagnóstico de inicialização ───────────────────────────────────────────
    run_diagnostics(client, symbol)

    # ── Estado de controle do ciclo ────────────────────────────────────────────
    cycle = 0
    _had_position_last_cycle: bool = False

    # ── Loop de varredura ──────────────────────────────────────────────────────
    while True:
        cycle += 1
        ts = time.strftime("%H:%M:%S")
        print(f"\n{'─'*60}")
        print(f"[{ts}] Ciclo #{cycle} — {symbol} | Risco: {risk_manager.status()}")

        try:
            # ── ETAPA 1: Verificação de Posição Ativa (1 trade por vez) ────────
            active_pos = get_active_position(client, symbol)

            if active_pos is not None:
                unrealised = float(active_pos.get("unrealisedPnl", 0) or 0)
                side_open = active_pos.get("side", "?")
                size_open = active_pos.get("size", "?")
                print(
                    f"🔒 [1 TRADE] Posição ativa: {side_open} | Size={size_open} "
                    f"| P&L não realizado=${unrealised:.2f}. Aguardando fechamento."
                )
                _had_position_last_cycle = True
                time.sleep(SCAN_INTERVAL)
                continue

            # ── ETAPA 2: Detecção de Fechamento → Atualização do RiskManager ──
            if _had_position_last_cycle:
                pnl = get_last_closed_pnl(client, symbol)
                if pnl is not None:
                    print(f"📋 [RESULTADO] PnL do último trade: ${pnl:.4f}")
                    if pnl < 0:
                        risk_manager.register_stop()
                    else:
                        risk_manager.register_gain()
                _had_position_last_cycle = False

            # ── ETAPA 3: Dados de Mercado (30m) ───────────────────────────────
            df = client.fetch_ohlcv(symbol, TIMEFRAME)
            if df is None or df.empty:
                print("⚠️  Dados OHLCV indisponíveis; aguardando próximo ciclo.")
                time.sleep(SCAN_INTERVAL)
                continue

            # ── ETAPA 4: Cérebro 1 — Indicadores Locais/Matemáticos ───────────
            engine = IndicatorEngine(df)
            tech_data = engine.get_signals()

            price = tech_data.get("price", 0.0)
            if price <= 0:
                print("⚠️  Preço inválido; aguardando próximo ciclo.")
                time.sleep(SCAN_INTERVAL)
                continue

            print(
                f"📊 [MERCADO] Preço=${price:.4f} | Trend={tech_data['trend']} "
                f"| RSI={tech_data['rsi']:.1f} | Vol×={tech_data.get('volume_ratio', 0):.2f} "
                f"| SuperTrend={'▲' if tech_data['supertrend_signal'] == 1 else '▼'}"
            )

            # ── ETAPA 5: Cérebro 2 + 3 — Groq e Gemini → Consenso Triplo ─────
            consensus = validator.consensus_predict(tech_data, symbol)
            confidence = consensus.get("probabilidade", 0)
            decisao = consensus.get("decisao", "SCANNER")

            print(
                f"🧠 [TRIBUNAL] Confiança={confidence}% | Decisão={decisao} "
                f"| Local={consensus.get('breakdown',{}).get('local',0)}% "
                f"| Groq={consensus.get('breakdown',{}).get('groq',0)}% "
                f"| Gemini={consensus.get('breakdown',{}).get('gemini',0)}%"
            )

            # ── ETAPA 6: Filtro de Confiança Mínima ──────────────────────────
            if confidence < MIN_CONFIDENCE:
                print(f"⏸️  Confiança {confidence}% < {MIN_CONFIDENCE}%. Aguardando sinal mais forte.")
                time.sleep(SCAN_INTERVAL)
                continue

            if decisao not in ("COMPRAR", "VENDER"):
                print(f"⏸️  Decisão={decisao}. Nenhuma ação neste ciclo.")
                time.sleep(SCAN_INTERVAL)
                continue

            # ── ETAPA 7: Verificação das 5 Confluências Simultâneas ──────────
            all_confluences_ok, failed = check_five_confluences(tech_data, consensus)
            if not all_confluences_ok:
                print(f"🔒 [BLOQUEADO] {len(failed)} confluência(s) ausente(s): {failed}")
                time.sleep(SCAN_INTERVAL)
                continue

            # ── ETAPA 8: Autorização de Execução ─────────────────────────────
            if not client.authenticated:
                print("⚠️  Modo leitura: ordem NÃO executada (sem credenciais válidas).")
                time.sleep(SCAN_INTERVAL)
                continue

            # ── ETAPA 9: Cálculo de Tamanho da Entrada (Risco Dinâmico) ──────
            side = "BUY" if decisao == "COMPRAR" else "SELL"
            entry_pct = risk_manager.current_entry_pct
            qty = calculate_entry_qty(client, price, entry_pct)
            if qty <= 0:
                time.sleep(SCAN_INTERVAL)
                continue

            # ── ETAPA 10: Execução do Ponto Zero ─────────────────────────────
            executed = place_order_with_protection(
                client=client,
                learner=learner,
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                consensus=consensus,
            )

            if executed:
                _had_position_last_cycle = True
                # Pausa após execução para evitar entradas duplicadas
                print(f"✅ [PONTO ZERO ATIVADO] Aguardando 60s antes do próximo ciclo...")
                time.sleep(60)
            else:
                time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:
            print("\n🛑 Motor Sniper encerrado pelo usuário (Ctrl+C).")
            break
        except Exception as e:
            err_str = str(e)
            if "10003" in err_str:
                # ── Erro de Autenticação: log claro e encerramento seguro ─────
                print("❌ [ERRO 10003] Chave de API inválida capturada no loop principal.")
                print("   → Verifique BYBIT_API_KEY e BYBIT_API_SECRET no arquivo .env")
                print("   → A chave deve ter permissão 'Contratos (Derivativos)' ativada na Bybit.")
                print("   → Gerenciar chaves: Bybit → Conta → Segurança da conta → Chaves API")
                client.authenticated = False
                sys.exit(1)
            print(f"⚠️  [CICLO #{cycle}] Erro inesperado no ciclo de varredura.")
            time.sleep(SCAN_INTERVAL)


# ─── Ponto de entrada ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    # ── Etapa 0: Autenticação 2FA (Google Authenticator) ──────────────────────
    verify_2fa()

    target_symbol = sys.argv[1] if len(sys.argv) > 1 else SYMBOL
    run_sniper(symbol=target_symbol)
