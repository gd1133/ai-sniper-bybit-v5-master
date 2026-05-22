# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║             AI SNIPER BYBIT V5 - MAIN WEB APPLICATION            ║
║                  MAESTRO CORE FULL EDITION v60.9                 ║
╚══════════════════════════════════════════════════════════════════╝

⚠️ CONFIGURAÇÃO CRÍTICA PARA O RENDER (GUNICORN):
---------------------------------------------------
Para garantir que a Thread do motor de trading e as rotas HTTP compartilhem
a MESMA memória e evitar inconsistências causadas por múltiplos workers isolados,
configure o "Start Command" no painel do Render com EXATAMENTE 1 worker:

    gunicorn -w 1 -k gthread main_web:app

Onde:
  -w 1        : Força apenas 1 worker process (essencial para Singletons e cache compartilhado)
  -k gthread  : Usa threads ao invés de processos para paralelização (compatível com threading.Thread)
  main_web:app: Aponta para a instância Flask neste arquivo

⚠️ NUNCA use -w 2 ou superior, pois isso criará processos isolados e quebrará
   a sincronização entre o motor de trading e as APIs HTTP!
"""
import os
import time
import threading
import sqlite3
import requests
import re
import sys
import io
import math
from datetime import datetime, timedelta

# Força UTF-8 no stdout do Windows para evitar quebras com emojis
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from src.config import get_bybit_base_url, get_environment_config, resolve_use_testnet

# --- IMPORTAÇÕES DAS PASTAS INTERNAS (SRC) ---
try:
    from src.database import manager as db
except Exception as e:
    print(f"❌ Erro Crítico ao importar Database Manager: {e}")
    db = None

# Módulos carregados sob demanda (Lazy Loading) para evitar importação circular
BybitClient = None
BybitV5HTTP = None
IndicatorEngine = None
GroqValidator = None
public_price_broker = None

RUNTIME_START_LOCK = threading.Lock()
RUNTIME_STARTED = False
AI_RATE_LIMIT_STATUS_MESSAGE = '⚠️ Limite das IAs atingido. Aguardando cooldown de 60s...'
AI_COOLDOWN_ACTIVE = False
AI_COOLDOWN_LOCK = threading.Lock()

# ==============================================================================
# 🔄 BROKER MANAGER SINGLETON - Previne rate limiting e vazamento de conexões
# ==============================================================================
class BrokerManager:
    """
    Singleton que gerencia instâncias de broker (Bybit/Binance) globalmente.
    Garante cache em memória por cliente prevenindo reconexões HTTP simultâneas.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(BrokerManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._broker_cache = {}  
        self._cache_lock = threading.Lock()
        self._initialized = True
        print("🔄 [BROKER MANAGER] Singleton inicializado")

    def _generate_cache_key(self, client_id, exchange, testnet):
        return f"{exchange}_{client_id}_{testnet}"

    def get_broker(self, client, broker_cls, testnet):
        client_id = client.get('id')
        exchange = str(client.get('exchange') or 'bybit').strip().lower()
        cache_key = self._generate_cache_key(client_id, exchange, testnet)

        with self._cache_lock:
            if cache_key in self._broker_cache:
                cached_broker = self._broker_cache[cache_key]
                api_key = str(client.get('bybit_key') or '').strip()
                if hasattr(cached_broker, 'exchange') and hasattr(cached_broker.exchange, 'apiKey'):
                    if cached_broker.exchange.apiKey == api_key:
                        return cached_broker
                print(f"🔄 [BROKER MANAGER] Credenciais alteradas para cliente {client_id}, recriando broker")
                del self._broker_cache[cache_key]

            api_key = str(client.get('bybit_key') or '').strip()
            api_secret = str(client.get('bybit_secret') or '').strip()

            if not api_key or not api_secret:
                raise RuntimeError(f"Cliente ativo sem credenciais no SQLite (id={client_id})")

            print(f"🔧 [BROKER INIT] Cliente: {client.get('nome')} | Exchange: {exchange} | Testnet: {testnet} | Cache Key: {cache_key}")

            broker_instance = broker_cls(
                api_key,
                api_secret,
                testnet=testnet,
            )

            self._broker_cache[cache_key] = broker_instance
            print(f"💾 [BROKER MANAGER] Broker cached para cliente {client_id} ({exchange})")
            return broker_instance

    def invalidate_client(self, client_id):
        with self._cache_lock:
            keys_to_remove = [key for key in self._broker_cache.keys() if f"_{client_id}_" in f"_{key}_"]
            for key in keys_to_remove:
                del self._broker_cache[key]
                print(f"🗑️ [BROKER MANAGER] Broker removido do cache: {key}")

    def clear_cache(self):
        with self._cache_lock:
            count = len(self._broker_cache)
            self._broker_cache.clear()
            print(f"🗑️ [BROKER MANAGER] Cache limpo ({count} brokers removidos)")

_broker_manager = None

def _get_broker_manager():
    global _broker_manager
    if _broker_manager is None:
        _broker_manager = BrokerManager()
    return _broker_manager


def _is_ai_cooldown_active():
    with AI_COOLDOWN_LOCK:
        return AI_COOLDOWN_ACTIVE


def _set_ai_cooldown_active(value: bool):
    global AI_COOLDOWN_ACTIVE
    with AI_COOLDOWN_LOCK:
        AI_COOLDOWN_ACTIVE = bool(value)


def _activate_global_ai_cooldown(symbol_label=''):
    _set_ai_cooldown_active(True)
    central_state['status'] = AI_RATE_LIMIT_STATUS_MESSAGE
    suffix = f" em {symbol_label}" if symbol_label else ""
    print(f"🔴 [COOLDOWN GLOBAL] 429 detectado{suffix}. Próximas moedas usarão somente o 3º Cérebro REAL.")

# ==============================================================================
# 🔘 GESTÃO DE RISCO E PARAMETRIZAÇÃO DE OPERAÇÃO
# ==============================================================================
load_dotenv()
ENV_CONFIG = get_environment_config()
ENVIRONMENT = ENV_CONFIG.name
print(f"[SISTEMA] Iniciando em modo: {ENVIRONMENT}")

DEFAULT_RISK_PER_TRADE_PCT = 15.0
WEBHOOK_ORDER_MARGIN_PCT = DEFAULT_RISK_PER_TRADE_PCT / 100


def _strict_env_bool(name, default):
    return str(os.getenv(name, default) or default).strip().lower() == 'true'


def _load_risk_per_trade_pct():
    try:
        return float(os.getenv('RISK_PER_TRADE_PCT', 15)) / 100
    except (TypeError, ValueError):
        print(f"⚠️ [RISK MANAGEMENT] RISK_PER_TRADE_PCT inválido. Usando fallback de {DEFAULT_RISK_PER_TRADE_PCT:.0f}%.")
        return DEFAULT_RISK_PER_TRADE_PCT / 100


RISK_PER_TRADE_PCT = _load_risk_per_trade_pct()


def _format_risk_per_trade_pct():
    pct_value = RISK_PER_TRADE_PCT * 100
    return f"{pct_value:.0f}%" if math.isclose(pct_value, round(pct_value), rel_tol=0, abs_tol=1e-9) else f"{pct_value:.2f}%"


def _calculate_order_margin(balance):
    """ DEPRECADO v2.0: Retorna o saldo completo para cálculo dinâmico baseado nos limites do par """
    return float(balance or 0.0)


def _calculate_order_quantity(balance, entry_price):
    print(f"⚠️ [DEPRECATION WARNING] _calculate_order_quantity() está obsoleto")
    return float(balance or 0.0), 0.0


def _calculate_webhook_order_quantity(balance, entry_price):
    print(f"⚠️ [DEPRECATION WARNING] _calculate_webhook_order_quantity() está obsoleto")
    return float(balance or 0.0), 0.0


def _calculate_dynamic_order_quantity(broker, symbol, balance):
    """
    🆕 v4.0: Executor focado ESTRITAMENTE no piso nocional mínimo da corretora.
    Lê dinamicamente os limites reais da exchange via CCXT e adiciona a margem de segurança.
    """
    try:
        current_price = broker.get_last_price(symbol)
        if current_price <= 0:
            print(f"❌ [EXECUTOR] Preço inválido para {symbol}: {current_price}")
            return 0.0, 0.0

        print(f"💰 [EXECUTOR MÍNIMO] Preço atual {symbol}: ${current_price:.8f}")
        exchange_name = broker.exchange.id.lower() if hasattr(broker, 'exchange') else 'bybit'

        min_amount = None
        min_notional_raw = None
        if hasattr(broker, 'exchange') and hasattr(broker.exchange, 'markets'):
            market_info = broker.exchange.markets.get(symbol)
            if market_info:
                limits = market_info.get('limits', {})
                min_amount = limits.get('amount', {}).get('min')
                min_notional_raw = limits.get('cost', {}).get('min')
                if min_amount: print(f"   📐 Limite dinâmico amount.min: {min_amount}")
                if min_notional_raw: print(f"   📐 Limite dinâmico cost.min: ${min_notional_raw}")

        SAFETY_MARGIN = 1.10  
        if min_notional_raw and min_notional_raw > 0:
            target_notional = min_notional_raw * SAFETY_MARGIN
        elif 'binance' in exchange_name:
            target_notional = 5.00 * SAFETY_MARGIN   
        else:
            target_notional = 2.00 * SAFETY_MARGIN   

        print(f"   衡量 Piso nocional alvo ({exchange_name}): ${target_notional:.2f} USDT")
        raw_qty = target_notional / current_price

        if min_amount and min_amount > 0:
            raw_qty = max(raw_qty, min_amount)

        final_qty = raw_qty
        if hasattr(broker, 'exchange') and hasattr(broker.exchange, 'amount_to_precision'):
            try:
                final_qty = float(broker.exchange.amount_to_precision(symbol, raw_qty))
                print(f"   ✅ amount_to_precision aplicado: {final_qty:.8f}")
            except Exception as precision_err:
                print(f"⚠️ [PRECISION] Falha no amount_to_precision: {precision_err} — usando fallback matemático")
                if min_amount and min_amount > 0:
                    decimals = max(0, -int(math.floor(math.log10(min_amount))))
                    final_qty = round(raw_qty, decimals)
                else:
                    final_qty = round(raw_qty, 4)
        elif hasattr(broker, '_normalize_order_qty'):
            try:
                final_qty = float(broker._normalize_order_qty(symbol, raw_qty))
            except Exception as norm_err:
                print(f"⚠️ [NORMALIZE QTY] Erro ao normalizar: {norm_err}")
                final_qty = round(raw_qty, 4)
        else:
            final_qty = round(raw_qty, 4)

        if min_amount and min_amount > 0 and final_qty < min_amount:
            final_qty = min_amount

        margin_used = final_qty * current_price
        print(f"   ✅ Quantidade calculada: {final_qty:.8f} | Nocional final: ${margin_used:.2f} USDT")
        return margin_used, final_qty

    except Exception as calc_err:
        print(f"❌ [ERRO EXECUTOR] Falha no cálculo: {calc_err}")
        return 0.0, 0.0


def _log_raw_broker_error(cliente_nome, error, context='ERRO ORDEM REAL'):
    error_type = type(error).__name__
    print(f"❌ [{context}] {cliente_nome}: {error_type}: {error}")


def _log_risk_management_mode():
    print(f"🔧 [RISK MANAGEMENT] Modo de entrada ativo: {_format_risk_per_trade_pct()} da banca em processamento dinâmico.")


def _is_rate_limit_error(error):
    error_message = str(error or "")
    lowered_message = error_message.lower()
    return "429" in error_message or "rate limit" in lowered_message or "rate_limit" in lowered_message


def _apply_ai_rate_limit_cooldown(error):
    if not _is_rate_limit_error(error):
        return False
    print("⚠️ [AGUARDANDO COOLDOWN] Limite atingido. Pausando robô por 60 segundos antes de tentar novamente...")
    time.sleep(60)
    return True


def _handle_ai_rate_limit(error):
    if not _apply_ai_rate_limit_cooldown(error):
        return False
    central_state['status'] = AI_RATE_LIMIT_STATUS_MESSAGE
    return True

VALID_OPERATION_MODES = {'real'}
VALID_ACCOUNT_MODES = {'real'}

def _normalize_operation_mode(value): return 'real'
def _normalize_account_mode(value): return 'real'
def _is_testnet_account(value): return False
def _mode_display_label(mode): return 'CONTA REAL'
def _mode_balance_source(mode): return 'broker_real_balance'
def _mode_uses_testnet(mode): return False
def _resolve_client_testnet_flag(value): return False
def _get_synced_account_mode_for_operation(mode): return 'real'

def _filter_balance_items_for_operation_mode(items, mode):
    filtered_items = []
    for item in items or []:
        filtered_items.append({**item, "account_mode": 'real'})
    return filtered_items

def _is_order_execution_enabled(mode):
    return bool(ALLOW_ORDER_EXECUTION and ALLOW_REAL_TRADING)

def _execution_status_label(mode):
    return 'Ordens reais ativas' if _is_order_execution_enabled(mode) else 'Ordens reais bloqueadas'


app = Flask(__name__, static_folder='dist', static_url_path='')
CORS(app)

db.init_db()

APP_MODE = _normalize_operation_mode(db.get_operation_mode())
ALLOW_ORDER_EXECUTION = ENV_CONFIG.allow_order_execution
ALLOW_REAL_TRADING = ENV_CONFIG.allow_real_trading
USE_TESTNET = ENV_CONFIG.use_testnet

if ALLOW_REAL_TRADING and not USE_TESTNET:
    print("=" * 80)
    print("✅ MODO PRODUÇÃO: Trading real HABILITADO nos servidores Bybit/Binance REAIS!")
    print("=" * 80)

RISK_MODE = 'conservative'       
MAX_MOEDAS_ATIVAS = 1            

central_state = {
    "balance": 0.0,  
    "status": "INICIANDO SISTEMA...",
    "symbol": "---",
    "confidence": 0,
    "opportunities": [],
    "active_trades": [],
    "trades": [],
    "last_sniper_signal": None,
    "recent_sniper_signals": [],
    "operation_mode": APP_MODE,
    "operation_mode_label": _mode_display_label(APP_MODE),
    "execution_enabled": _is_order_execution_enabled(APP_MODE),
    "execution_label": _execution_status_label(APP_MODE),
    "pnl_total": 0.0,  
    "pnl_percentage": 0.0,  
    "winning_trades": 0,  
    "losing_trades": 0,  
    "win_rate": 0.0,  
    "ia2_decision": {
        "motivo": "Varrendo o mercado com analise local, estatistica e historico...",
        "brains": {"local": "online", "analyst": "online", "learner": "online"}
    },
    "max_moedas_ativas": MAX_MOEDAS_ATIVAS,
    "risk_mode": RISK_MODE,
}

class CachedValue:
    def __init__(self, ttl_seconds=300):
        self.value = None
        self.timestamp = 0
        self.ttl = ttl_seconds

    def get(self):
        if time.time() - self.timestamp > self.ttl: return None
        return self.value

    def set(self, value):
        self.value = value
        self.timestamp = time.time()

    def is_expired(self): return time.time() - self.timestamp > self.ttl
    def clear(self): self.timestamp = 0; self.value = None


client_balance_cache = CachedValue(ttl_seconds=60)  
_status_cache = CachedValue(ttl_seconds=30)  

_balance_refresh_lock = threading.Lock()
_balance_refresh_in_progress = False


def _sync_runtime_mode_state(persist=False):
    global APP_MODE
    APP_MODE = _normalize_operation_mode(APP_MODE)
    central_state['operation_mode'] = APP_MODE
    central_state['operation_mode_label'] = _mode_display_label(APP_MODE)
    central_state['execution_enabled'] = _is_order_execution_enabled(APP_MODE)
    central_state['execution_label'] = _execution_status_label(APP_MODE)
    central_state['status'] = f"💼 {_mode_display_label(APP_MODE)}: sincronizando saldo dos clientes"
    if persist: db.set_operation_mode(APP_MODE)

_sync_runtime_mode_state()

_saved_risk_mode = db.get_config('RISK_MODE')
if _saved_risk_mode in ('conservative', 'aggressive'):
    RISK_MODE = _saved_risk_mode
    MAX_MOEDAS_ATIVAS = 1 if RISK_MODE == 'conservative' else 5
    central_state['risk_mode'] = RISK_MODE
    central_state['max_moedas_ativas'] = MAX_MOEDAS_ATIVAS


def start_runtime_services():
    """ 🚀 INICIALIZAÇÃO DE SERVIÇOS EM DAEMON WORKERS """
    global RUNTIME_STARTED
    with RUNTIME_START_LOCK:
        if RUNTIME_STARTED: return False
        threading.Thread(target=sniper_worker_loop, daemon=True).start()
        threading.Thread(target=_monitor_sl_tp_automatico, daemon=True).start()
        threading.Thread(target=_fetch_active_client_balances, kwargs={'force': True}, daemon=True).start()
        RUNTIME_STARTED = True
        return True

USE_LOCAL_BRAIN_ONLY = False
THRESHOLD_ENTRADA = 60           
COOLDOWN_INSTITUCIONAL_SECS = 15  
SNIPER_POSICAO_UNICA = False     

SNIPER_SIGNAL_LOCK = threading.Lock()
SNIPER_SIGNAL_RESERVATIONS = set()
ENABLE_RANDOM_TEST_TRADES = False

BLOQUEIO_REPETICAO_MOEDA_SECS = 60       
PENALIDADE_MOEDA_JA_ABERTA = 25           
PENALIDADE_STREAK_MESMA_MOEDA = 10      
SCAN_TOP_COINS = 8                       
SCAN_INTER_SYMBOL_DELAY_SECS = 5.0       

def _frontend_index_path(): return os.path.join(app.static_folder or "", 'index.html')
def _frontend_is_built(): return bool(app.static_folder) and os.path.isfile(_frontend_index_path())
def _frontend_asset_exists(path): return bool(path) and bool(app.static_folder) and os.path.isfile(os.path.join(app.static_folder, path))

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path.startswith('api/'): return jsonify({"error": "Endpoint não encontrado"}), 404
    if _frontend_asset_exists(path): return send_from_directory(app.static_folder, path)
    if _frontend_is_built(): return send_from_directory(app.static_folder, 'index.html')
    return jsonify({"status": "DuoIA Maestro API ativa. Painel React em compilação."}), 200

def _limpar_simbolo(sym):
    if not sym: return "---"
    return sym.split(':')[0] if ':' in sym else sym

def _normalize_symbol_key(sym): return re.sub(r'[^A-Z0-9]', '', str(sym or '').upper())

def _canonicalize_symbol(sym):
    raw = str(sym or '').strip().upper()
    if not raw: return ""
    compact = raw.replace(" ", "")
    if ":" in compact: return compact
    if "/" in compact:
        base, quote = compact.split("/", 1)
        return f"{base}/{quote}:{quote}"
    if compact.endswith("USDT") and len(compact) > 4:
        return f"{compact[:-4]}/USDT:USDT"
    return compact

def _coerce_float(*values, default=0.0):
    for v in values:
        try:
            numeric = float(v)
            if numeric == numeric: return numeric
        except Exception: continue
    return float(default)

def _clamp(value, minimum=0.0, maximum=100.0): return max(minimum, min(maximum, float(value)))

def _get_symbol_trade_edge(symbol, side, limit=300):
    try:
        normalized_symbol = _normalize_symbol_key(_canonicalize_symbol(symbol) or symbol)
        normalized_side = str(side or '').upper()
        trades = db.get_recent_trades(limit)
        matching = []
        for t in trades:
            if str(t.get('status', 'closed')).lower() != 'closed': continue
            if _normalize_symbol_key(_canonicalize_symbol(t.get('pair')) or t.get('pair')) == normalized_symbol and str(t.get('side') or '').upper() == normalized_side:
                matching.append(t)
        if not matching: return {"sample_size": 0, "win_rate": 0.0, "profit_total": 0.0, "edge_score": 0.0}
        wins = sum(1 for t in matching if _coerce_float(t.get('profit'), default=0.0) > 0)
        win_rate = (wins / len(matching)) * 100
        profit_total = sum(_coerce_float(t.get('profit'), default=0.0) for t in matching)
        edge_score = _clamp(((win_rate - 50.0) * 0.30) + min(12.0, profit_total * 0.05), -10.0, 20.0)
        return {"sample_size": len(matching), "win_rate": round(win_rate, 2), "profit_total": round(profit_total, 2), "edge_score": round(edge_score, 2)}
    except Exception:
        return {"sample_size": 0, "win_rate": 0.0, "profit_total": 0.0, "edge_score": 0.0}

def _build_money_flow_metrics(signals, ticker, decision):
    volume_ratio = _coerce_float(signals.get('volume_ratio'), default=0.0)
    recent_return_pct = abs(_coerce_float(signals.get('recent_return_pct'), default=0.0))
    quote_volume = _coerce_float(ticker.get('quoteVolume'), default=0.0) / 1_000_000
    money_flow_score = _clamp((volume_ratio * 20) + (recent_return_pct * 10) + (quote_volume * 0.1), 0.0, 100.0)
    return {"money_flow_score": round(money_flow_score, 2), "institutional_pressure": round(max(0.0, volume_ratio - 1.0) * 35.0, 2), "volume_ratio": round(volume_ratio, 2), "quote_volume_millions": round(quote_volume, 2), "recent_return_pct": round(recent_return_pct, 2), "money_flow_side": str(signals.get('money_flow_side') or 'WAIT').upper()}

def _sanitize_signal_payload(raw_data):
    data = dict(raw_data or {})
    symbol = _canonicalize_symbol(data.get('symbol') or data.get('pair') or data.get('asset'))
    if not symbol: raise ValueError("Sinal sem símbolo válido.")
    side_raw = str(data.get('side') or data.get('decision') or '').strip().upper()
    side = 'COMPRAR' if side_raw in ('BUY', 'LONG', 'COMPRAR') else 'VENDER' if side_raw in ('SELL', 'SHORT', 'VENDER') else None
    if not side: raise ValueError(f"Lado inválido para o sinal: {side_raw}")
    entry_price = _coerce_float(data.get('entry_price'), data.get('price'), default=0.0)
    if entry_price <= 0: entry_price = _coerce_float(_get_public_price_broker().get_last_price(symbol), default=0.0)
    return {'symbol': symbol, 'side': side, 'entry_price': round(entry_price, 8), 'confidence': max(0.0, min(100.0, _coerce_float(data.get('confidence'), default=70.0))), 'reason': str(data.get('reason') or 'Sinal Sniper Manual').strip()}

def _build_last_sniper_signal(symbol, side, entry_price, confidence, reason):
    canonical_symbol = _canonicalize_symbol(symbol) or str(symbol or '').strip()
    return {"signal_id": f"{_limpar_simbolo(canonical_symbol)}|{side.upper()}|{entry_price}|{int(time.time())}", "symbol": _limpar_simbolo(canonical_symbol), "raw_symbol": canonical_symbol, "side": side.upper(), "entry_price": round(float(entry_price), 8), "confidence": round(float(confidence), 2), "reason": str(reason).strip(), "received_at": datetime.now().isoformat(timespec='seconds')}

def _push_recent_sniper_signal(signal_data, max_items=10):
    if not signal_data: return
    recent = [signal_data.copy()]
    for s in central_state.get('recent_sniper_signals', []):
        if s.get('signal_id') != signal_data.get('signal_id'): recent.append(s)
    central_state['recent_sniper_signals'] = recent[:max_items]

def _extract_entry_price(trade):
    try:
        entry_price = float(trade.get('entry_price', 0) or 0)
        if entry_price > 0: return round(entry_price, 8)
    except Exception: pass
    return 0.0


def _get_public_price_broker():
    """ Instância pública de consulta de preços com Lazy Loading protegido anti-circular """
    global BybitClient, public_price_broker
    if public_price_broker is not None:
        return public_price_broker

    if BybitClient is None:
        from src.broker.bybit_client import BybitClient as _BybitClient
        BybitClient = _BybitClient

    _, bybit_api_key, bybit_api_secret = _get_active_investor_bybit_credentials()
    if not bybit_api_key or not bybit_api_secret:
        # Fallback público em CCXT puro caso o banco de dados esteja zerado no boot
        import ccxt
        class CCXTPublicPriceFallback:
            def get_last_price(self, symbol):
                try:
                    ex = ccxt.bybit({'enableRateLimit': True})
                    ticker = ex.fetch_ticker(symbol)
                    return float(ticker['last'])
                except Exception: return 0.0
            def fetch_ohlcv(self, symbol, timeframe='15m'):
                try:
                    ex = ccxt.bybit({'enableRateLimit': True})
                    import pandas as pd
                    data = ex.fetch_ohlcv(symbol, timeframe, limit=200)
                    return pd.DataFrame(data, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                except Exception: return None
        return CCXTPublicPriceFallback()

    public_price_broker = BybitClient(bybit_api_key, bybit_api_secret, testnet=False)
    return public_price_broker


def _ensure_broker_class(exchange='bybit'):
    """ Lazy loading absoluto que mata a importação circular estourada no background """
    exchange = str(exchange or 'bybit').strip().lower()
    if exchange == 'binance':
        global _BinanceClient
        if '_BinanceClient' not in globals() or _BinanceClient is None:
            from src.broker.binance_client import BinanceClient as _BC
            globals()['_BinanceClient'] = _BC
        return globals()['_BinanceClient']
    
    global BybitClient
    if BybitClient is None:
        from src.broker.bybit_client import BybitClient as _BybitClient
        BybitClient = _BybitClient
    return BybitClient


def _make_broker(client):
    exchange = str(client.get('exchange') or 'bybit').strip().lower()
    broker_cls = _ensure_broker_class(exchange)
    return _get_broker_manager().get_broker(client, broker_cls, False)

def _get_master_telegram_config():
    load_dotenv(override=True)
    return str(os.getenv('TELEGRAM_TOKEN') or '').strip(), str(os.getenv('TELEGRAM_CHAT_ID') or '').strip()

def _get_registered_clients(active_only=False):
    try:
        local_clients = db.get_active_clients() if active_only else db.get_all_clients()
        return [{**dict(client), "storage_source": "local"} for client in local_clients]
    except Exception: return []

def _get_registered_client_by_id(client_id):
    local_client = db.get_client_by_id(client_id)
    return {**dict(local_client), "storage_source": "local"} if local_client else None

def _get_active_investor_bybit_credentials():
    for client in _get_registered_clients(active_only=True):
        persisted = _get_registered_client_by_id(client.get('id'))
        if persisted:
            api_key = str(persisted.get('bybit_key') or '').strip()
            api_secret = str(persisted.get('bybit_secret') or '').strip()
            if api_key and api_secret: return persisted.get('id'), api_key, api_secret
    return None, '', ''

def _save_client_everywhere(client_data):
    payload = dict(client_data or {})
    payload['account_mode'] = 'real'
    payload['is_testnet'] = False
    payload['balance_source'] = 'broker_real_balance'
    local_result = db.upsert_client_local(payload) if payload.get('id') is not None else db.add_client(payload)
    final_id = payload.get('id') or local_result
    final_record = _get_registered_client_by_id(final_id)
    client_balance_cache.clear()
    return final_record, False, bool(local_result)

def _delete_client_everywhere(client_id):
    _get_broker_manager().invalidate_client(client_id)
    return True, db.delete_client(client_id)

def _fetch_active_client_balances(force=False):
    """ 
    🔄 LAZY LOADING PROTEGIDO CONTRA ERROS DE IMPORTAÇÃO CÍCLICA 
    Busca o saldo unificado linear perpétuo no banco SQLite e aloca nos caches.
    """
    global _balance_refresh_in_progress
    if not force and not client_balance_cache.is_expired(): return client_balance_cache.get()

    if not force:
        with _balance_refresh_lock:
            if not _balance_refresh_in_progress:
                _balance_refresh_in_progress = True
                def _bg_refresh():
                    global _balance_refresh_in_progress
                    try: _fetch_active_client_balances(force=True)
                    finally:
                        with _balance_refresh_lock: _balance_refresh_in_progress = False
                threading.Thread(target=_bg_refresh, daemon=True).start()
        return client_balance_cache.get() or {"items": [], "total": 0.0}

    items = []
    total = 0.0
    try:
        # Puxa as classes dentro do escopo da thread para quebrar qualquer nó circular
        _ensure_broker_class('bybit')
        _ensure_broker_class('binance')

        active_clients = _get_registered_clients(active_only=True)
        for client in active_clients:
            balance = None
            error = None
            try:
                broker = _make_broker(client)
                balance = broker.get_balance()
                if balance is not None:
                    balance = round(float(balance), 2)
                    total += balance
            except Exception as e:
                error = str(e)
            items.append({
                "id": client.get('id'), "nome": client.get('nome'), "saldo_real": balance,
                "saldo_base": float(client.get('saldo_base', 0) or 0), "is_testnet": False,
                "account_mode": "real", "exchange": str(client.get('exchange') or 'bybit').lower(),
                "status": client.get('status'), "error": error,
            })
    except Exception as e:
        print(f"⚠️ [_fetch_active_client_balances] Erro de alocação de saldo: {e}")
    
    res = {"items": items, "total": round(total, 2)}
    client_balance_cache.set(res)
    return res

def _refresh_real_balance_state(force=False):
    balances = _fetch_active_client_balances(force=force)
    mode_items = balances.get("items", [])
    for item in mode_items:
        if item.get("saldo_real") is None: item["saldo_real"] = item.get("saldo_base")
    valid_items = [item for item in mode_items if item.get("saldo_real") is not None]
    
    central_state['real_client_balances'] = mode_items
    if valid_items:
        central_state['balance'] = round(sum(float(item["saldo_real"]) for item in valid_items), 2)
        central_state['status'] = f"💼 CONTA REAL: saldo sincronizado para {len(valid_items)} investidores"
    else:
        central_state['balance'] = 0.0
        central_state['status'] = "💼 CONTA REAL: nenhum cliente real ativo vinculado"

def _calculate_live_trade_metrics(entry_price, current_price, side):
    entry = float(entry_price or 0)
    current = float(current_price or 0)
    if entry <= 0 or current <= 0: return {"current_price": current, "price_change_pct": 0.0, "pnl_pct": 0.0, "trend": "flat", "is_favorable": False}
    market_move = ((current - entry) / entry) * 100
    pnl_pct = -market_move if str(side).upper() in ('VENDER', 'SELL', 'SHORT') else market_move
    return {"current_price": round(current, 8), "price_change_pct": round(market_move, 4), "pnl_pct": round(pnl_pct, 4), "trend": "up" if current > entry else "down", "is_favorable": pnl_pct >= 0}

def _get_live_price_snapshot(symbol, entry_price, side):
    try:
        # Uso corrigido anti-NoneType da função de alocação de preço público
        pub_broker = _get_public_price_broker()
        return _calculate_live_trade_metrics(entry_price, pub_broker.get_last_price(symbol), side)
    except Exception:
        return _calculate_live_trade_metrics(entry_price, 0.0, side)

def _refresh_last_sniper_signal():
    s = central_state.get('last_sniper_signal')
    if s: s.update(_get_live_price_snapshot(s.get('raw_symbol') or s.get('symbol'), s.get('entry_price'), s.get('side')))

def _repair_open_trades():
    try:
        open_trades = db.get_open_trades(100)
        if not open_trades: return
        conn = db._connect()
        cur = conn.cursor()
        for t in open_trades:
            canonical = _canonicalize_symbol(t.get('pair'))
            price = _extract_entry_price(t)
            if not canonical or price <= 0:
                cur.execute("UPDATE trades SET status='closed', pnl_pct=0, closed_at=? WHERE id=?", (time.strftime("%d/%m %H:%M"), t.get('id')))
        conn.commit()
        conn.close()
    except Exception: pass

def _can_open_new_signal(symbol):
    _repair_open_trades()
    open_trades = db.get_open_trades(100)
    open_symbols = {_normalize_symbol_key(t.get('pair')) for t in open_trades if t.get('pair')}
    normalized = _normalize_symbol_key(_canonicalize_symbol(symbol))
    if normalized in open_symbols: return False, f"Moeda {symbol} já está em andamento."
    if len(open_symbols) >= MAX_MOEDAS_ATIVAS: return False, f"Limite de {MAX_MOEDAS_ATIVAS} ativos atingido."
    return True, "ok"

def _reserve_signal_slot(symbol):
    with SNIPER_SIGNAL_LOCK:
        ok, reason = _can_open_new_signal(symbol)
        if ok: SNIPER_SIGNAL_RESERVATIONS.add(_normalize_symbol_key(_canonicalize_symbol(symbol)))
        return ok, reason

def _release_signal_slot(symbol):
    with SNIPER_SIGNAL_LOCK: SNIPER_SIGNAL_RESERVATIONS.discard(_normalize_symbol_key(_canonicalize_symbol(symbol)))

def _calcular_pnl_trades():
    try:
        trades = db.get_recent_trades(500)
        pnl = 0.0; w = 0; l = 0
        for t in trades:
            if str(t.get('status')).lower() != 'closed': continue
            prof = float(t.get('profit', 0))
            pnl += prof
            if prof > 0: w += 1
            elif prof < 0: l += 1
        total = w + l or 1
        central_state['pnl_total'] = round(pnl, 2)
        central_state['winning_trades'] = w
        central_state['losing_trades'] = l
        central_state['win_rate'] = round((w / total) * 100, 2)
    except Exception: pass

def _monitor_sl_tp_automatico():
    """ 🛡️ MONITOR AUTOMÁTICO DE TRAVAS — ATUALIZADO PARA -50% STOP LOSS """
    time.sleep(1) # Delay estratégico de bootstrap
    SL_PCT = -50.0  # <-- Alinhado com a trava institucional de 50% de segurança
    TP_PCT = 100.0
    while True:
        try:
            open_trades = db.get_open_trades(100)
            for t in open_trades:
                live = _get_live_price_snapshot(t.get('pair'), _extract_entry_price(t), t.get('side'))
                pnl_pct = live.get('pnl_pct', 0.0)
                motivo = f"SL_AUTO -50%" if pnl_pct <= SL_PCT else f"TP_AUTO +100%" if pnl_pct >= TP_PCT else None
                if motivo:
                    conn = db._connect(); cur = conn.cursor()
                    cur.execute("UPDATE trades SET status='closed', pnl_pct=?, notes=COALESCE(notes,'') || ? WHERE id=?", (round(pnl_pct, 4), f" | {motivo}", t.get('id')))
                    conn.commit(); conn.close()
                    _sync_active_trades_from_db()
        except Exception: pass
        time.sleep(10)

def _sync_active_trades_from_db():
    try:
        trades = db.get_open_trades(50)
        res = []
        for t in trades:
            if str(t.get('status')).lower() != 'open': continue
            price = _extract_entry_price(t)
            live = _get_live_price_snapshot(t.get('pair'), price, t.get('side'))
            trade_payload = {
                'id': t.get('id'), 'symbol': _limpar_simbolo(t.get('pair')), 'raw_symbol': t.get('pair'),
                'side': t.get('side'), 'entry': round(float(t.get('profit', 0)), 2), 'entry_price': price,
                'client_count': 1, 'trade_count': 1,
            }
            trade_payload.update(live)
            res.append(trade_payload)
        central_state['active_trades'] = res
    except Exception: pass

def _close_stale_open_trades(max_age_minutes=180):
    try:
        trades = db.get_open_trades(100)
        conn = db._connect(); cur = conn.cursor()
        for t in trades:
            dt = datetime.fromisoformat(str(t.get('created_at')).replace('Z', ''))
            if (datetime.now() - dt) > timedelta(minutes=max_age_minutes):
                cur.execute("UPDATE trades SET status='closed', notes=COALESCE(notes,'') || ' | STALE' WHERE id=?", (t.get('id'),))
        conn.commit(); conn.close()
    except Exception: pass

def _manual_close_open_trades(symbol, requested_by="dashboard"):
    canonical = _canonicalize_symbol(symbol)
    trades = db.get_open_trades(200)
    norm = _normalize_symbol_key(canonical)
    count = 0
    for t in trades:
        if _normalize_symbol_key(t.get('pair')) == norm:
            live = _get_live_price_snapshot(canonical, _extract_entry_price(t), t.get('side'))
            db.close_trade(t.get('id'), live.get('pnl_pct', 0), 0, time.strftime("%d/%m %H:%M"), f"FECHAMENTO MANUAL {requested_by}")
            count += 1
    _sync_active_trades_from_db()
    return {"symbol": _limpar_simbolo(canonical), "closed_count": count}

def broadcast_ordem_global(symbol, side, entry_price, res_ia):
    slot_reserved = False
    try:
        if not _reserve_signal_slot(symbol): return
        slot_reserved = True
        signal_snapshot = _build_last_sniper_signal(symbol, side, entry_price, res_ia.get('probabilidade', 70), res_ia.get('motivo', ''))
        central_state['last_sniper_signal'] = signal_snapshot
        _push_recent_sniper_signal(signal_snapshot)
        
        threading.Thread(
            target=_process_client_orders_background,
            args=(symbol, side, entry_price, res_ia.get('probabilidade', 70), res_ia.get('motivo', '')),
            daemon=True
        ).start()
    finally:
        if slot_reserved: _release_signal_slot(symbol)

def sniper_worker_loop():
    """ 🔄 MOTOR SNIPER AUTÔNOMO — INTEGRADO COM 3º CÉREBRO LOCAL """
    time.sleep(1) # Delay de resiliência do compilador
    global BybitClient, IndicatorEngine, GroqValidator
    from src.broker.bybit_client import BybitClient
    from src.engine.indicators import IndicatorEngine
    from src.ai_brain.validator import GroqValidator

    while True:
        print("🔄 [MOTOR CHAVE] Iniciando novo ciclo de varredura do mercado...", flush=True)
        try:
            _repair_open_trades()
            _calcular_pnl_trades()
            _refresh_real_balance_state()
            _sync_active_trades_from_db()

            if len(central_state['active_trades']) >= MAX_MOEDAS_ATIVAS:
                time.sleep(15)
                continue

            _, key, sec = _get_active_investor_bybit_credentials()
            if not key or not sec:
                time.sleep(10)
                continue

            ex_master = BybitClient(key, sec, False)
            tickers = ex_master.exchange.fetch_tickers(params={'category': 'linear'})
            top_coins = sorted([t for t in tickers.values() if 'USDT' in t.get('symbol', '') and ':' in t['symbol']], key=lambda x: x.get('quoteVolume', 0), reverse=True)[:SCAN_TOP_COINS]
            
            validator = GroqValidator()
            for t in top_coins:
                sym = t['symbol']
                df = ex_master.fetch_ohlcv(sym, timeframe='15m')
                if df is None or len(df) < 200: continue
                
                signals = IndicatorEngine(df).get_signals()
                print(f"DEBUG {_limpar_simbolo(sym)}: Trend {signals['trend']} | Price {signals['price']} | SMA {signals['sma_200']}")
                
                if signals['trend'] == 'NEUTRO' or validator.local_signal(signals) < 25: continue
                
                res = validator.consensus_predict(signals, sym, force_local_only=True)
                prob = float(res.get('probabilidade', 0))
                decisao = str(res.get('decisao', 'ABORTAR')).upper()

                if prob >= THRESHOLD_ENTRADA and decisao in ['COMPRAR', 'VENDER', 'BUY', 'SELL']:
                    broadcast_ordem_global(sym, 'buy' if decisao in ('BUY', 'COMPRAR') else 'sell', float(signals['price']), res)
                    time.sleep(COOLDOWN_INSTITUCIONAL_SECS)
                    break
                time.sleep(SCAN_INTER_SYMBOL_DELAY_SECS)

        except Exception as e:
            print(f"❌ [MOTOR CORE - ERRO] {e}", flush=True)
        time.sleep(15)


def _process_client_orders_background(symbol, side, entry_price, confidence, reason):
    try:
        tk, chat = _get_master_telegram_config()
        clientes = _get_registered_clients(active_only=True)
        print(f"\n🔍 [BROADCAST] Iniciando execução para {len(clientes)} cliente(s) ativo(s)")

        for c in clientes:
            try:
                broker = _make_broker(c)
                banca = float(c.get('saldo_base', 1000.0))
                print(f"🆕 [CÁLCULO DINÂMICO] Cliente: {c.get('nome')}, Saldo: ${banca}")
                margem, qty = _calculate_dynamic_order_quantity(broker, symbol, banca)

                if qty > 0 and _is_order_execution_enabled(APP_MODE):
                    order_result = broker.execute_market_order(symbol, side.lower(), qty, raise_on_error=True)
                    if order_result:
                        order_id = order_result.get('id', order_result.get('orderId', 'N/A'))
                        print(f"✅ [ORDEM ENVIADA COM SUCESSO] ID: {order_id}")
                        broker.set_tp_sl_sniper(symbol, side.lower(), entry_price, qty)
            except Exception as order_err:
                print(f"❌ [ERRO DE EXECUÇÃO] {c.get('nome')} | Erro: {order_err}")
    except Exception as bg_err:
        print(f"❌ [ERRO BACKGROUND BROADCAST] {bg_err}")


@app.route('/api/trade/manual-entry', methods=['POST'])
def api_manual_entry_trade():
    """ 🎯 ROTA DE ENTRADA MANUAL CORRIGIDA ANTI-NONETYPE """
    try:
        data = request.json or {}
        symbol = data.get('symbol', '').strip()
        side = data.get('side', '').strip().upper()
        entry_price = data.get('entry_price')
        force_execute = data.get('force_execute', False)

        if not symbol or side not in ['BUY', 'SELL', 'COMPRAR', 'VENDER']:
            return jsonify({"success": False, "error": "Parâmetros inválidos"}), 400

        side_normalized = 'COMPRAR' if side in ['BUY', 'COMPRAR'] else 'VENDER'
        
        # Correção atômica: Aloca a instância de preço público com segurança
        pub_broker = _get_public_price_broker()
        if not entry_price:
            try:
                # Modificado para ler do broker público instanciado
                entry_price = float(pub_broker.get_last_price(symbol))
            except Exception as e:
                return jsonify({"success": False, "error": f"Erro de conexão com livro de ofertas: {str(e)}"}), 400

        entry_price = float(entry_price)
        df = pub_broker.fetch_ohlcv(symbol, timeframe='15m')
        
        global IndicatorEngine, GroqValidator
        from src.engine.indicators import IndicatorEngine
        from src.ai_brain.validator import GroqValidator

        tech_data = IndicatorEngine(df).get_signals() if df is not None and len(df) >= 200 else {'trend': 'ALTA', 'price': entry_price, 'sma_200': entry_price, 'rsi': 50}
        validator = GroqValidator()
        ai_result = validator.consensus_predict(tech_data, symbol, force_local_only=True)

        if force_execute:
            if not _reserve_signal_slot(symbol): return jsonify({"success": False, "error": "Moeda em uso ou limite estourado"}), 409
            try:
                db.record_trade(1, symbol, side_normalized, 0, 10, time.strftime("%d/%m %H:%M"), "ENTRADA MANUAL", "open", entry_price)
                _sync_active_trades_from_db()
                threading.Thread(target=_process_client_orders_background, args=(symbol, side_normalized, entry_price, 70, "Manual"), daemon=True).start()
                return jsonify({"success": True, "message": "Ordem manual enviada para as contas virtuais"}), 200
            finally: _release_signal_slot(symbol)
        
        return jsonify({"success": True, "analysis_only": True, "symbol": symbol, "side": side_normalized, "entry_price": entry_price, "ai_analysis": {"confidence": ai_result.get('probabilidade', 70), "reason": ai_result.get('motivo', 'Aprovado')}}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route('/api/investidores', methods=['POST'])
def add_investidor_legacy(): return add_cliente()

@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        _repair_open_trades()
        _refresh_real_balance_state()
        _sync_active_trades_from_db()
        _refresh_last_sniper_signal()
        central_state['trades'] = db.get_recent_trades(20)
        return jsonify(central_state)
    except Exception as e:
        return jsonify(central_state)

@app.route('/api/dashboard/balance', methods=['GET'])
def update_dashboard_balance():
    try:
        _refresh_real_balance_state(force=True)
        return jsonify({"balance": central_state['balance'], "status": central_state['status'], "real_client_balances": central_state.get('real_client_balances', [])})
    except Exception as e:
        return jsonify({"balance": 0.0, "status": f"Erro de comunicação: {e}"})

@app.route('/api/config/risk-mode', methods=['POST'])
def set_risk_mode():
    global RISK_MODE, MAX_MOEDAS_ATIVAS
    try:
        mode = str((request.json or {}).get('mode', 'conservative')).strip().lower()
        RISK_MODE = mode
        MAX_MOEDAS_ATIVAS = 1 if mode == 'conservative' else 5
        central_state['risk_mode'] = RISK_MODE
        central_state['max_moedas_ativas'] = MAX_MOEDAS_ATIVAS
        db.set_config('RISK_MODE', RISK_MODE)
        return jsonify({"success": True, "risk_mode": RISK_MODE, "max_moedas_ativas": MAX_MOEDAS_ATIVAS})
    except Exception: return jsonify({"error": "Erro ao alterar risco"}), 400

print("⚡ [MAESTRO CORE] Forçando inicialização dos serviços em background...", flush=True)
start_runtime_services()

if __name__ == "__main__":
    render_port = int(os.getenv("PORT", "5000"))
    start_runtime_services()
    app.run(host='0.0.0.0', port=render_port, debug=False, use_reloader=False)
