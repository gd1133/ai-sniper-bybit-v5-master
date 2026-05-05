"""
╔══════════════════════════════════════════════════════════════════╗
║           MOTOR SNIPER V60.7 — GIVALDO SUPREME                  ║
║        Sistema de Entrada Ponto Zero (Triple Brain)              ║
╚══════════════════════════════════════════════════════════════════╝

Regras de Negócio:
  - API: pybit.unified_trading.HTTP com recv_window=20000
  - Entrada:  5 % do saldo USDT disponível
  - Stop Loss: 3 % sobre o preço de entrada  (trava institucional)
  - Take Profit: +10 % de preço = +100 % de margem (10× alavancagem)
  - Alavancagem: 10× | Modo de Margem: Cross
  - Sinal autorizado somente quando:
      ① Confiança combinada ≥ 60 %
      ② 5 confluências simultâneas aprovadas
  - Erro 10003 (Chave de API inválida): log claro e encerramento seguro.
"""

import os
import time
import sys

from dotenv import load_dotenv

# ─── Carrega variáveis de ambiente ────────────────────────────────────────────
load_dotenv()

# ─── Configurações Globais ─────────────────────────────────────────────────────

# Define se usa testnet ou produção (USE_TESTNET=true → testnet)
USE_TESTNET: bool = str(os.getenv("USE_TESTNET", "true")).strip().lower() in {"1", "true", "yes", "on"}

# Par monitorado (pode ser sobrescrito via variável de ambiente)
SYMBOL: str = os.getenv("SYMBOL", "ETHUSDT")

# Intervalo de tempo dos candles
TIMEFRAME: str = os.getenv("TIMEFRAME", "15m")

# Parâmetros de risco
ENTRY_PCT: float = 0.05        # 5 % do saldo por entrada
STOP_LOSS_PCT: float = 0.03    # 3 % de stop loss
# Com 10× de alavancagem, +10 % de preço = +100 % de margem
TAKE_PROFIT_PCT: float = 0.10  # +10 % = 100 % de lucro sobre margem
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
            print(f"⚠️  [LEVERAGE] {err}")
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
            print(f"⚠️  [MARGIN MODE] {err}")
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
        print(f"⚠️  [LEVERAGE] Exceção: {e}")
        return False


# ─── Gestão de Risco: Tamanho da Entrada ──────────────────────────────────────

def calculate_entry_qty(client: BybitClient, price: float) -> float:
    """
    Calcula a quantidade de contratos para a entrada.

    Regras:
      - Valor de entrada = 5 % do saldo USDT
      - Quantidade = valor_entrada / preço_atual
      - Se saldo ≤ 0 → operação abortada (retorna 0.0)
    """
    balance = client.get_balance()

    # Segurança: saldo nulo ou não positivo → aborta
    if balance is None or balance <= 0:
        print("🚫 [SEGURANÇA] Saldo USDT inválido ou zero. Operação ABORTADA.")
        return 0.0

    entry_value = balance * ENTRY_PCT
    qty = entry_value / price if price > 0 else 0.0

    print(f"💰 [RISCO] Saldo={balance:.2f} USDT | Entrada={entry_value:.2f} USDT ({ENTRY_PCT*100:.0f}%) | Qty≈{qty:.4f}")
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
        "4_rsi_seguro (20<RSI<80)":     checks.get("rsi_safe", 20 < rsi < 80),
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
      - Take Profit: +10 % sobre entrada (= +100 % de margem com 10× alavancagem)
      - Stop Loss:   -3 % sobre entrada  (trava institucional)
    """
    v5_symbol = client._normalize_v5_symbol(symbol)
    v5_side = "Buy" if side.upper() == "BUY" else "Sell"
    close_side = "Sell" if v5_side == "Buy" else "Buy"

    tp_price = round(price * (1 + TAKE_PROFIT_PCT), 2) if v5_side == "Buy" else round(price * (1 - TAKE_PROFIT_PCT), 2)
    sl_price = round(price * (1 - STOP_LOSS_PCT), 2) if v5_side == "Buy" else round(price * (1 + STOP_LOSS_PCT), 2)

    print(f"\n🚀 [PONTO ZERO] {v5_symbol} | {v5_side} | Qty={qty}")
    print(f"   📍 Entrada : ${price:.4f}")
    print(f"   🎯 TP       : ${tp_price:.4f}  (+{TAKE_PROFIT_PCT*100:.0f}% preço = +100% margem)")
    print(f"   🛡️  SL       : ${sl_price:.4f}  (-{STOP_LOSS_PCT*100:.0f}% trava)")
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
                print(f"❌ [ORDEM FALHOU] {err}")
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
            print(f"❌ [ORDEM EXCEÇÃO] {err_str}")
        return False


# ─── Loop Principal de Varredura ──────────────────────────────────────────────

def run_sniper(symbol: str = SYMBOL):
    """
    Loop principal do Motor Sniper V60.7.

    Fluxo por ciclo:
      1. Busca OHLCV e calcula indicadores (Cérebro 1 — Local/Matemático)
      2. Consulta Groq/LLaMA (Cérebro 2 — Tático)
      3. Consulta Gemini (Cérebro 3 — Estratégico / Histórico)
      4. Gera consenso ponderado (Gemini 40% | Groq 35% | Local 25%)
      5. Valida 5 confluências simultâneas
      6. Se confiança ≥ 60 % e todas as confluências OK → executa Ponto Zero
    """
    print("═" * 60)
    print(f"  MOTOR SNIPER V60.7 — iniciando em {'TESTNET' if USE_TESTNET else 'PRODUÇÃO'}")
    print(f"  Par: {symbol} | Timeframe: {TIMEFRAME} | Intervalo: {SCAN_INTERVAL}s")
    print("═" * 60)

    # ── Inicialização dos componentes ──────────────────────────────────────────
    client = build_client()
    learner = TradeLearner()

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

    # ── Loop de varredura ──────────────────────────────────────────────────────
    cycle = 0
    while True:
        cycle += 1
        ts = time.strftime("%H:%M:%S")
        print(f"\n{'─'*60}")
        print(f"[{ts}] Ciclo #{cycle} — {symbol}")

        try:
            # ── ETAPA 1: Dados de Mercado ──────────────────────────────────────
            df = client.fetch_ohlcv(symbol, TIMEFRAME)
            if df is None or df.empty:
                print("⚠️  Dados OHLCV indisponíveis; aguardando próximo ciclo.")
                time.sleep(SCAN_INTERVAL)
                continue

            # ── ETAPA 2: Cérebro 1 — Indicadores Locais/Matemáticos ───────────
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

            # ── ETAPA 3: Cérebro 2 + 3 — Groq e Gemini → Consenso Triplo ─────
            consensus = validator.consensus_predict(tech_data, symbol)
            confidence = consensus.get("probabilidade", 0)
            decisao = consensus.get("decisao", "SCANNER")

            print(
                f"🧠 [TRIBUNAL] Confiança={confidence}% | Decisão={decisao} "
                f"| Local={consensus.get('breakdown',{}).get('local',0)}% "
                f"| Groq={consensus.get('breakdown',{}).get('groq',0)}% "
                f"| Gemini={consensus.get('breakdown',{}).get('gemini',0)}%"
            )

            # ── ETAPA 4: Filtro de Confiança Mínima ──────────────────────────
            if confidence < MIN_CONFIDENCE:
                print(f"⏸️  Confiança {confidence}% < {MIN_CONFIDENCE}%. Aguardando sinal mais forte.")
                time.sleep(SCAN_INTERVAL)
                continue

            if decisao not in ("COMPRAR", "VENDER"):
                print(f"⏸️  Decisão={decisao}. Nenhuma ação neste ciclo.")
                time.sleep(SCAN_INTERVAL)
                continue

            # ── ETAPA 5: Verificação das 5 Confluências Simultâneas ──────────
            all_confluences_ok, failed = check_five_confluences(tech_data, consensus)
            if not all_confluences_ok:
                print(f"🔒 [BLOQUEADO] {len(failed)} confluência(s) ausente(s): {failed}")
                time.sleep(SCAN_INTERVAL)
                continue

            # ── ETAPA 6: Autorização de Execução ─────────────────────────────
            if not client.authenticated:
                print("⚠️  Modo leitura: ordem NÃO executada (sem credenciais válidas).")
                time.sleep(SCAN_INTERVAL)
                continue

            # ── ETAPA 7: Cálculo de Tamanho da Entrada (Gestão de Risco) ─────
            side = "BUY" if decisao == "COMPRAR" else "SELL"
            qty = calculate_entry_qty(client, price)
            if qty <= 0:
                time.sleep(SCAN_INTERVAL)
                continue

            # ── ETAPA 8: Execução do Ponto Zero ──────────────────────────────
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
            print(f"⚠️  [CICLO #{cycle}] Erro inesperado: {err_str[:200]}")
            time.sleep(SCAN_INTERVAL)


# ─── Ponto de entrada ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    target_symbol = sys.argv[1] if len(sys.argv) > 1 else SYMBOL
    run_sniper(symbol=target_symbol)
