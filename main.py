"""
╔══════════════════════════════════════════════════════════════════╗
║           MOTOR SNIPER V60.7 — GIVALDO SUPREME                  ║
║        Sistema de Entrada Ponto Zero (Triple Brain)              ║
╚══════════════════════════════════════════════════════════════════╝

Regras de Negócio:
  - API: pybit.unified_trading.HTTP com recv_window=20000
  - Timeframe de varredura: 30 minutos (30m) — exclusivo
  - Máximo de operações simultâneas: 1 (uma)
  - Entrada padrão: 5 % do saldo USDT
  - Entrada reduzida (após Stop Loss): 3 % do saldo USDT
  - Retorno ao padrão: na primeira operação com Gain
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

from dotenv import load_dotenv

# ─── Carrega variáveis de ambiente ────────────────────────────────────────────
load_dotenv()

# ─── Configurações Globais ─────────────────────────────────────────────────────

# Define se usa testnet ou produção (USE_TESTNET=true → testnet)
USE_TESTNET: bool = str(os.getenv("USE_TESTNET", "true")).strip().lower() in {"1", "true", "yes", "on"}

# Par monitorado (pode ser sobrescrito via variável de ambiente)
SYMBOL: str = os.getenv("SYMBOL", "ETHUSDT")

# Intervalo de tempo dos candles — fixado em 30 minutos
TIMEFRAME: str = "30m"

# Parâmetros de risco
ENTRY_PCT_DEFAULT: float = 0.05        # 5 % do saldo — entrada padrão
ENTRY_PCT_AFTER_STOP: float = 0.03     # 3 % do saldo — após Stop Loss
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

      - Padrão  : 5 % do saldo (ENTRY_PCT_DEFAULT)
      - Após SL : 3 % do saldo (ENTRY_PCT_AFTER_STOP)
      - Após Gain: retorna ao padrão de 5 %

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
            f"Próxima entrada reduzida para {ENTRY_PCT_AFTER_STOP * 100:.0f}% do saldo."
        )

    def register_gain(self) -> None:
        """Registra que o último trade encerrou em lucro (Take Profit)."""
        self._last_result = "GAIN"
        print(
            f"✅ [RISCO] Último trade: GAIN. "
            f"Entrada retorna ao padrão de {ENTRY_PCT_DEFAULT * 100:.0f}% do saldo."
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
      - Valor de entrada = entry_pct do saldo USDT (5 % padrão ou 3 % após SL)
      - Quantidade = valor_entrada / preço_atual
      - Se saldo ≤ 0 → operação abortada (retorna 0.0)
    """
    balance = client.get_balance()

    # Segurança: saldo nulo ou não positivo → aborta
    if balance is None or balance <= 0:
        print("🚫 [SEGURANÇA] Saldo USDT inválido ou zero. Operação ABORTADA.")
        return 0.0

    entry_value = balance * entry_pct
    qty = entry_value / price if price > 0 else 0.0

    print(f"💰 [RISCO] Saldo={balance:.2f} USDT | Entrada={entry_value:.2f} USDT ({entry_pct*100:.0f}%) | Qty≈{qty:.4f}")
    return round(qty, 4)


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
        # Coloca ordem a mercado com TP/SL embutidos (V5 suporta na mesma chamada)
        payload = {
            "category": "linear",
            "symbol": v5_symbol,
            "side": v5_side,
            "orderType": "Market",
            "qty": str(qty),
            "takeProfit": str(tp_price),
            "stopLoss": str(sl_price),
            "tpTriggerBy": "MarkPrice",
            "slTriggerBy": "MarkPrice",
        }

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


# ─── Loop Principal de Varredura ──────────────────────────────────────────────

def run_sniper(symbol: str = SYMBOL):
    """
    Loop principal do Motor Sniper V60.7.

    Regras de execução:
      - Varredura exclusiva no timeframe de 30 minutos (30m)
      - Máximo de 1 operação ativa simultaneamente
      - Gestão de risco dinâmica via RiskManager (5% padrão → 3% após SL → 5% após Gain)

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
    print(f"  Regras: 1 trade ativo | SL=50% entrada | TP=100% lucro | Entrada=5%/3%")
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

def verify_2fa() -> bool:
    """
    Verificação de autenticação em dois fatores (2FA) via Google Authenticator.

    Lê o segredo TOTP de TOTP_2FA_SECRET no .env.
    - Se a variável não estiver configurada → exibe aviso e ignora 2FA
      (adequado para ambientes automatizados como Railway / CI).
    - Se configurada → solicita o código de 6 dígitos do app Google Authenticator
      e valida via pyotp.TOTP. O operador tem 3 tentativas antes do bloqueio.

    Retorna True se autenticado (ou 2FA não configurado), False caso contrário.

    Como gerar o segredo:
        python -c "import pyotp; print(pyotp.random_base32())"
    Adicione o segredo ao .env e escaneie o QR Code com o Google Authenticator:
        python -c "import pyotp; print(pyotp.totp.TOTP('SEU_SEGREDO').provisioning_uri('MotorSniper','Bybit'))"
    """
    totp_secret = str(os.getenv("TOTP_2FA_SECRET", "")).strip()

    if not totp_secret:
        print(
            "⚠️  [2FA] TOTP_2FA_SECRET não configurado no .env. "
            "Verificação 2FA IGNORADA (modo automatizado)."
        )
        return True

    try:
        import pyotp  # noqa: PLC0415 (pylint: disable=import-outside-toplevel)
    except ImportError:
        print("❌ [2FA] pyotp não instalado. Execute: pip install pyotp")
        return False

    totp = pyotp.TOTP(totp_secret)
    max_attempts = 3

    print("\n🔐 [2FA] Autenticação de dois fatores requerida.")
    print("   Abra o Google Authenticator e insira o código de 6 dígitos para 'MotorSniper'.\n")

    for attempt in range(1, max_attempts + 1):
        try:
            code = getpass.getpass(f"   Código 2FA (tentativa {attempt}/{max_attempts}): ").strip()
        except (EOFError, KeyboardInterrupt):
            # Ambiente não-interativo (CI/cron) — cancela silenciosamente
            print("\n⚠️  [2FA] Entrada interativa indisponível; 2FA ignorado (ambiente não-interativo).")
            return True

        if totp.verify(code, valid_window=1):
            print("✅ [2FA] Autenticado com sucesso!\n")
            return True

        remaining = max_attempts - attempt
        if remaining > 0:
            print(f"   ❌ Código inválido. {remaining} tentativa(s) restante(s).")
        else:
            print("❌ [2FA] Número máximo de tentativas atingido. Acesso BLOQUEADO.")

    return False


if __name__ == "__main__":
    # ── Verificação 2FA antes de qualquer inicialização da API ────────────────
    if not verify_2fa():
        sys.exit(1)

    target_symbol = sys.argv[1] if len(sys.argv) > 1 else SYMBOL
    run_sniper(symbol=target_symbol)
