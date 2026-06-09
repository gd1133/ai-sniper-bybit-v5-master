# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║             AI SNIPER BYBIT V5 - MAIN WEB APPLICATION            ║
║                  MAESTRO CORE FULL EDITION v61.5                 ║
╚══════════════════════════════════════════════════════════════════╝

gunicorn -w 1 -k gthread main_web:app
"""
import os
import time
import threading
import sqlite3
import requests
import re
import sys
import math
import gc
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta

if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from src.config import get_bybit_base_url, get_environment_config, resolve_use_testnet

try:
    from src.database import manager as db
except Exception as e:
    print(f"❌ Erro Crítico ao importar Database Manager: {e}")
    db = None

BybitClient = None
BybitV5HTTP = None
IndicatorEngine = None
GroqValidator = None
public_price_broker = None
public_radar_broker = None
public_price_brokers = {}

RUNTIME_START_LOCK = threading.Lock()
RUNTIME_STARTED = False
AI_RATE_LIMIT_STATUS_MESSAGE = '⚠️ Limite das IAs atingido. Aguardando cooldown de 60s...'
AI_COOLDOWN_ACTIVE = False
AI_COOLDOWN_LOCK = threading.Lock()

# Runtime-only: bloqueio temporário de clientes com erro de autenticação (ex.: chaves MAINNET em modo TESTNET)
_CLIENT_AUTH_RUNTIME = {}  # client_id -> {authenticated: bool, disabled_until: float, reason: str}
_CLIENT_AUTH_LOCK = threading.Lock()
_CLIENT_AUTH_COOLDOWN_SECONDS = 10 * 60  # 10 min

def _extract_bybit_ret_code_from_error(error):
    """Extrai retCode (ex.: 10003) de exceções CCXT/Pybit ou mensagens logadas."""
    try:
        for attr in ('error_code', 'code', 'retCode'):
            code = getattr(error, attr, None)
            if code is not None:
                return str(code)
    except Exception:
        pass
    text = str(error or '')
    match = re.search(r'retCode\\s*["\\\']?\\s*[:=]\\s*(\\d+)', text)
    if match:
        return match.group(1)
    match = re.search(r'retCode=(\\d+)', text)
    if match:
        return match.group(1)
    return None

def _is_client_temporarily_disabled(client_id):
    if not client_id:
        return False
    now = time.time()
    with _CLIENT_AUTH_LOCK:
        entry = _CLIENT_AUTH_RUNTIME.get(int(client_id))
        if not entry:
            return False
        disabled_until = float(entry.get('disabled_until') or 0.0)
        if disabled_until and now >= disabled_until:
            _CLIENT_AUTH_RUNTIME.pop(int(client_id), None)
            return False
        return entry.get('authenticated') is False

def _get_client_disable_reason(client_id):
    with _CLIENT_AUTH_LOCK:
        entry = _CLIENT_AUTH_RUNTIME.get(int(client_id or 0)) or {}
        return str(entry.get('reason') or '').strip() or None

def _disable_client_temporarily(client, reason, cooldown_seconds=_CLIENT_AUTH_COOLDOWN_SECONDS):
    client_id = int((client or {}).get('id') or 0)
    if not client_id:
        return False
    now = time.time()
    with _CLIENT_AUTH_LOCK:
        entry = _CLIENT_AUTH_RUNTIME.get(client_id)
        if entry:
            disabled_until = float(entry.get('disabled_until') or 0.0)
            if disabled_until and now < disabled_until:
                return False
        _CLIENT_AUTH_RUNTIME[client_id] = {
            'authenticated': False,
            'disabled_until': now + float(cooldown_seconds or 0),
            'reason': str(reason or '').strip(),
        }
        return True

def _handle_invalid_api_key_10003_for_client(client, source_label='bybit'):
    nome = (client or {}).get('nome') or 'Unknown'
    client_id = int((client or {}).get('id') or 0)
    if _is_client_temporarily_disabled(client_id):
        return

    # Mensagem explícita por cliente (sem depender do USE_TESTNET global)
    if _resolve_request_is_testnet(client, fallback=False):
        print(
            f"❌ [CONFIGURAÇÃO] O cliente {nome} está configurado como TESTNET, mas as chaves parecem ser de MAINNET. "
            f"Altere as chaves no banco de dados para chaves geradas em testnet.bybit.com.",
            flush=True,
        )

    _disable_client_temporarily(
        client,
        reason=f"bybit retCode=10003 (API key is invalid) detectado em {source_label}",
    )

# 🔧 CONFIGURAÇÃO DE GERENCIAMENTO DE RISCO MOTOR SNIPER V60.7
# Altere estes valores conforme necessário para diferentes estratégias de trading
ALAVANCAGEM = 20  # Alavancagem fixa (pode ser alterado para 30 ou 50 no futuro)
MARGEM_INPUT = 5.0  # Margem de entrada fixa em USDT (anteriormente era 5% da banca)
LIMITE_PERDA_STOP = -2.50  # Stop loss financeiro: -50% da margem de entrada ($5.0)
ALVO_LUCRO_USDT = 2.50  # Take Profit absoluto em USDT (editável: 2.50, 3.00, 5.00, etc.)
STOP_PERDA_USDT = -2.50  # Stop Loss absoluto em USDT (valor bruto negativo)

def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = str(raw).strip()
    if not raw:
        return default
    try:
        return float(raw.replace(',', '.'))
    except Exception:
        return default

def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = str(raw).strip().lower()
    if not raw:
        return default
    if raw in ('1', 'true', 'yes', 'y', 'on'):
        return True
    if raw in ('0', 'false', 'no', 'n', 'off'):
        return False
    return default

def _coerce_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in ('1', 'true', 'yes', 'y', 'on', 'test', 'teste', 'testnet', 'simulacao', 'simulação', 'demo', 'sandbox'):
        return True
    if raw in ('0', 'false', 'no', 'n', 'off', 'real', 'mainnet', 'prod', 'producao', 'produção'):
        return False
    return default

def _resolve_request_is_testnet(payload, *, fallback: bool = False) -> bool:
    """
    Resolve is_testnet exclusivamente do payload/registro do cliente.
    Não depende de USE_TESTNET global.
    """
    data = payload or {}
    for key in ('is_testnet', 'testnet', 'use_testnet', 'isTestnet', 'modo_teste', 'environment', 'ambiente'):
        if key not in data:
            continue
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return _coerce_bool(value, default=fallback)
    # Fallback semântico para payloads de UI antigos.
    for key in ('account_mode', 'modo_conta', 'operation_mode'):
        if key not in data:
            continue
        value = data.get(key)
        if value is None:
            continue
        raw = str(value).strip().lower()
        if not raw:
            continue
        if raw in ('test', 'teste', 'testnet', 'simulacao', 'simulação', 'sandbox'):
            return True
        if raw in ('real', 'mainnet', 'prod', 'producao', 'produção'):
            return False
    return bool(fallback)

def _is_training_fake_balance_enabled() -> bool:
    # Default: enabled on TESTNET to allow UI/training without valid API keys.
    try:
        default_enabled = bool(USE_TESTNET)
    except Exception:
        default_enabled = False
    return _env_bool('ENABLE_TRAINING_FAKE_BALANCE', default_enabled)

def _get_training_fake_balance_usd() -> float | None:
    if not _is_training_fake_balance_enabled():
        return None
    value = float(_env_float('TRAINING_FAKE_BALANCE_USD', 500.0))
    return value if value > 0 else None

_VALID_BALANCE_SOURCES = {'broker_real_balance', 'training_fake_balance'}

def _normalize_balance_source(value) -> str:
    raw = str(value or '').strip().lower()
    if not raw or raw in {'broker_testnet_balance', 'real', 'broker'}:
        return 'broker_real_balance'
    if raw in {'training_fake_balance', 'fake', 'training', 'teste', 'test'}:
        return 'training_fake_balance'
    return raw if raw in _VALID_BALANCE_SOURCES else 'broker_real_balance'

def _is_training_fake_balance_client(client) -> bool:
    # Regra mandatória: is_testnet=1 roda como simulação local pura (sem rede/exchange).
    if _resolve_request_is_testnet(client or {}, fallback=False):
        return True
    return _normalize_balance_source((client or {}).get('balance_source')) == 'training_fake_balance'

def _get_forced_training_fake_balance_usd() -> float:
    value = float(_env_float('TRAINING_FAKE_BALANCE_USD', 500.0))
    return value if value > 0 else 500.0


class BrokerManager:
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
        if self._initialized: return
        self._broker_cache = {}
        self._broker_classes = {}
        self._max_cached_brokers = max(1, int(_env_float('BROKER_MANAGER_MAX_CACHE', 6)))
        self._stale_seconds = max(30, int(_env_float('BROKER_MANAGER_STALE_SECONDS', 600)))
        self._cache_lock = threading.Lock()
        self._initialized = True
        print(f"🔄 [BROKER MANAGER] Singleton inicializado | max_cache={self._max_cached_brokers} | stale={self._stale_seconds}s")

    def _generate_cache_key(self, client_id, exchange, testnet):
        return f"{exchange}_{client_id}_{testnet}"

    def _get_broker_class(self, exchange):
        normalized_exchange = 'bybit'
        broker_cls = self._broker_classes.get(normalized_exchange)
        if broker_cls is not None:
            return broker_cls

        from src.broker.bybit_client import BybitClient as _BybitClient
        broker_cls = _BybitClient
        normalized_exchange = 'bybit'

        self._broker_classes[normalized_exchange] = broker_cls
        return broker_cls

    def _prune_cache_unlocked(self, *, active_client_ids=None, active_exchanges=None):
        now = time.time()
        removed = []
        for key, entry in list(self._broker_cache.items()):
            if not isinstance(entry, dict):
                removed.append(key)
                continue
            last_used = float(entry.get('last_used') or 0.0)
            client_id = entry.get('client_id')
            exchange = str(entry.get('exchange') or 'bybit').strip().lower()
            if now - last_used > self._stale_seconds:
                removed.append(key)
                continue
            if active_client_ids is not None and client_id not in active_client_ids:
                removed.append(key)
                continue
            if active_exchanges is not None and exchange not in active_exchanges:
                removed.append(key)
                continue

        for key in removed:
            self._broker_cache.pop(key, None)

        while len(self._broker_cache) > self._max_cached_brokers:
            oldest_key = min(
                self._broker_cache,
                key=lambda k: float((self._broker_cache.get(k) or {}).get('last_used') or 0.0),
            )
            self._broker_cache.pop(oldest_key, None)
            removed.append(oldest_key)

        if removed:
            gc.collect()

    def get_broker(self, client, testnet):
        client_id = client.get('id')
        exchange = 'bybit'
        cache_key = self._generate_cache_key(client_id, exchange, testnet)

        with self._cache_lock:
            self._prune_cache_unlocked()
            cached_entry = self._broker_cache.get(cache_key)
            if cached_entry:
                cached_broker = cached_entry.get('broker')
                api_key = str(client.get('bybit_key') or '').strip()
                if hasattr(cached_broker, 'exchange') and hasattr(cached_broker.exchange, 'apiKey'):
                    if cached_broker.exchange.apiKey == api_key:
                        cached_entry['last_used'] = time.time()
                        return cached_broker
                self._broker_cache.pop(cache_key, None)

            api_key = str(client.get('bybit_key') or '').strip()
            api_secret = str(client.get('bybit_secret') or '').strip()
            if not api_key or not api_secret: raise RuntimeError(f"Cliente sem credenciais (id={client_id})")

            broker_cls = self._get_broker_class(exchange)
            broker_instance = broker_cls(api_key, api_secret, testnet=testnet)
            self._broker_cache[cache_key] = {
                'broker': broker_instance,
                'last_used': time.time(),
                'client_id': int(client_id or 0),
                'exchange': exchange,
            }
            self._prune_cache_unlocked()
            return broker_instance

    def invalidate_client(self, client_id):
        with self._cache_lock:
            keys_to_remove = [key for key, entry in self._broker_cache.items() if int((entry or {}).get('client_id') or 0) == int(client_id or 0)]
            for key in keys_to_remove:
                self._broker_cache.pop(key, None)
            if keys_to_remove:
                gc.collect()

    def prune_unused(self, *, active_client_ids=None, active_exchanges=None):
        with self._cache_lock:
            self._prune_cache_unlocked(active_client_ids=active_client_ids, active_exchanges=active_exchanges)

_broker_manager = None
_broker_manager_lock = threading.Lock()
def _get_broker_manager():
    global _broker_manager
    if _broker_manager is not None: return _broker_manager
    with _broker_manager_lock:
        if _broker_manager is None: _broker_manager = BrokerManager()
    return _broker_manager

load_dotenv()
ENV_CONFIG = get_environment_config()

# ==============================================================================
# 🚀 INICIALIZAÇÃO DO APP FLASK & BANCO DE DADOS (CORE RECONSTRUIDO)
# ==============================================================================
app = Flask(__name__, static_folder='dist', static_url_path='')
CORS(app)

if db is not None:
    db.init_db()

# ==============================================================================
# 🎨 FUNÇÕES DE VALIDAÇÃO DO BUILD DO FRONTEND VITE (REACT)
# ==============================================================================
def _frontend_index_path():
    """Retorna o caminho completo do index.html do build do React"""
    return os.path.join(app.static_folder or "", 'index.html')

def _frontend_is_built():
    """Verifica se o frontend foi compilado e está disponível"""
    return bool(app.static_folder) and os.path.isfile(_frontend_index_path())

def _frontend_asset_exists(path):
    """Verifica se um asset específico do frontend existe"""
    return bool(path) and bool(app.static_folder) and os.path.isfile(os.path.join(app.static_folder, path))

APP_MODE = 'real'
ALLOW_ORDER_EXECUTION = ENV_CONFIG.allow_order_execution
ALLOW_REAL_TRADING = ENV_CONFIG.allow_real_trading
USE_TESTNET = ENV_CONFIG.use_testnet
RISK_MODE = 'conservative'
MAX_MOEDAS_ATIVAS = 1
LEVERAGE = 10  # Alavancagem padrão (deve coincidir com main.py)

# Constantes do Sniper Worker
SCAN_TOP_COINS = 50
THRESHOLD_ENTRADA = 70.0
COOLDOWN_INSTITUCIONAL_SECS = 5
SCAN_INTER_SYMBOL_DELAY_SECS = 0.5
SNIPER_SIGNAL_LOCK = threading.Lock()
SNIPER_SIGNAL_RESERVATIONS = set()            

# ==============================================================================
# 🧪 MODO DE TESTE RÁPIDO (TEMPORÁRIO)
# ==============================================================================
# Quando True:
#  - Mantém o "bypass" de teste sempre habilitado (debug).
# Por padrão (False), o bypass só é aplicado quando:
#  - USE_TESTNET=True e não há posições abertas (positions == 0).
FORCAR_SINAL_TESTE = False
_FORCED_SIGNAL_FIRED = False

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
    "operation_mode": "real",
    "operation_mode_label": "CONTA REAL",
    "execution_enabled": True,
    "execution_label": "Ordens reais ativas",
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
LAST_TICKER_CACHE = {}
LAST_TICKER_LOCK = threading.Lock()


def _remember_last_price(symbol, price):
    try:
        normalized = _canonicalize_symbol(symbol)
        value = float(price or 0.0)
        if not normalized or value <= 0:
            return
        with LAST_TICKER_LOCK:
            LAST_TICKER_CACHE[normalized] = {
                "price": value,
                "updated_at": time.time(),
            }
    except Exception:
        pass


def _get_cached_last_price(symbol):
    try:
        normalized = _canonicalize_symbol(symbol)
        if not normalized:
            return 0.0
        with LAST_TICKER_LOCK:
            entry = LAST_TICKER_CACHE.get(normalized) or {}
        return float(entry.get("price") or 0.0)
    except Exception:
        return 0.0


def _get_live_market_price(symbol, *, preferred_price=0.0):
    """
    Busca preço vivo com fallback para último preço conhecido em memória.
    """
    normalized = _canonicalize_symbol(symbol)
    if not normalized:
        return 0.0
    live_price = float(preferred_price or 0.0)
    if live_price > 0:
        _remember_last_price(normalized, live_price)
        return live_price

    # Prioriza broker público sem credenciais (mainnet) para evitar retCode 10003
    # em ambiente com clientes inválidos misturados no cache.
    try:
        radar_broker = _get_public_radar_broker_mainnet()
        if radar_broker is not None:
            live_price = float(radar_broker.get_last_price(normalized) or 0.0)
            if live_price > 0:
                _remember_last_price(normalized, live_price)
                return live_price
    except Exception:
        pass

    try:
        pub_broker = _get_public_price_broker()
        live_price = float(pub_broker.get_last_price(normalized) or 0.0)
        if live_price > 0:
            _remember_last_price(normalized, live_price)
            return live_price
    except Exception:
        pass

    return _get_cached_last_price(normalized)

def _is_rate_limit_error(err: Exception) -> bool:
    msg = str(err or "").lower()
    return ("429" in msg) or ("rate limit" in msg) or ("too many requests" in msg)

def _apply_ai_rate_limit_cooldown(err: Exception, cooldown_seconds: int = 60) -> bool:
    if not _is_rate_limit_error(err):
        return False
    print(f"⏸️  [IA RATE LIMIT] AGUARDANDO COOLDOWN de {cooldown_seconds} segundos...", flush=True)
    time.sleep(int(cooldown_seconds))
    return True

def _handle_ai_rate_limit(err: Exception, cooldown_seconds: int = 60) -> bool:
    if not _is_rate_limit_error(err):
        return False
    central_state["status"] = AI_RATE_LIMIT_STATUS_MESSAGE
    return _apply_ai_rate_limit_cooldown(err, cooldown_seconds=cooldown_seconds)

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

client_balance_cache = CachedValue(ttl_seconds=10)  
_status_cache = CachedValue(ttl_seconds=3)  
_balance_refresh_lock = threading.Lock()
_balance_refresh_in_progress = False

if db is not None:
    _saved_risk_mode = db.get_config('RISK_MODE')
    if _saved_risk_mode in ('conservative', 'aggressive'):
        RISK_MODE = _saved_risk_mode
        MAX_MOEDAS_ATIVAS = 1 if RISK_MODE == 'conservative' else 5
        central_state['risk_mode'] = RISK_MODE
        central_state['max_moedas_ativas'] = MAX_MOEDAS_ATIVAS
    _saved_leverage = db.get_config('LEVERAGE')
    if _saved_leverage:
        try:
            _lev = int(_saved_leverage)
            if _lev > 0:
                LEVERAGE = _lev
        except (ValueError, TypeError):
            pass

def start_runtime_services():
    global RUNTIME_STARTED
    with RUNTIME_START_LOCK:
        if RUNTIME_STARTED: return False
        threading.Thread(target=sniper_worker_loop, daemon=True).start()
        threading.Thread(target=_monitor_sl_tp_automatico, daemon=True).start()
        threading.Thread(target=_monitor_financial_stop_loss, daemon=True).start()
        threading.Thread(target=_fetch_active_client_balances, kwargs={'force': True}, daemon=True).start()
        threading.Thread(target=_monitor_dashboard_positions, daemon=True).start()
        RUNTIME_STARTED = True
        return True

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
    if compact.endswith("USDT") and len(compact) > 4: return f"{compact[:-4]}/USDT:USDT"
    return compact

def _coerce_float(*values, default=0.0):
    for v in values:
        try:
            numeric = float(v)
            if numeric == numeric: return numeric
        except Exception: continue
    return float(default)

# ==============================================================================
# 📊 FUNÇÃO DE CÁLCULO DE MÉTRICAS DE PREÇO LIVE (PNL OSCILANTE)
# ==============================================================================
def _calculate_live_trade_metrics(entry_price, current_price, side):
    """
    Calcula métricas de PnL em tempo real para ordens ativas.
    Alimenta os cards visuais da Dashboard com dados oscilantes.
    """
    entry = float(entry_price or 0)
    current = float(current_price or 0)

    if entry <= 0 or current <= 0:
        return {
            "current_price": current,
            "price_change_pct": 0.0,
            "pnl_pct": 0.0,
            "trend": "flat",
            "is_favorable": False
        }

    # Calcula a movimentação do mercado em %
    market_move = ((current - entry) / entry) * 100

    # Inverte o PnL se for posição SHORT/VENDER
    price_pct = -market_move if str(side).upper() in ('VENDER', 'SELL', 'SHORT') else market_move

    # Aplica alavancagem para obter PnL % sobre a margem (igual ao exibido na Bybit)
    pnl_pct = price_pct * LEVERAGE

    return {
        "current_price": round(current, 8),
        "price_change_pct": round(market_move, 4),
        "pnl_pct": round(pnl_pct, 4),
        "trend": "up" if current > entry else "down",
        "is_favorable": pnl_pct >= 0
    }

def _get_symbol_trade_edge(symbol, side, limit=300):
    try:
        normalized_symbol = _normalize_symbol_key(_canonicalize_symbol(symbol) or symbol)
        normalized_side = str(side or '').upper()
        trades = db.get_recent_trades(limit)
        matching = [t for t in trades if str(t.get('status', 'closed')).lower() == 'closed' and _normalize_symbol_key(_canonicalize_symbol(t.get('pair')) or t.get('pair')) == normalized_symbol and str(t.get('side') or '').upper() == normalized_side]
        if not matching: return {"sample_size": 0, "win_rate": 0.0, "profit_total": 0.0, "edge_score": 0.0}
        wins = sum(1 for t in matching if _coerce_float(t.get('profit'), default=0.0) > 0)
        win_rate = (wins / len(matching)) * 100
        profit_total = sum(_coerce_float(t.get('profit'), default=0.0) for t in matching)
        return {"sample_size": len(matching), "win_rate": round(win_rate, 2), "profit_total": round(profit_total, 2), "edge_score": round(max(-10.0, min(20.0, ((win_rate - 50.0) * 0.30) + (profit_total * 0.05))), 2)}
    except Exception: return {"sample_size": 0, "win_rate": 0.0, "profit_total": 0.0, "edge_score": 0.0}

def _build_money_flow_metrics(signals, ticker, decision):
    volume_ratio = _coerce_float(signals.get('volume_ratio'), default=0.0)
    recent_return_pct = abs(_coerce_float(signals.get('recent_return_pct'), default=0.0))
    quote_volume = _coerce_float(ticker.get('quoteVolume'), default=0.0) / 1_000_000
    score = max(0.0, min(100.0, (volume_ratio * 20) + (recent_return_pct * 10) + (quote_volume * 0.1)))
    return {"money_flow_score": round(score, 2), "institutional_pressure": round(max(0.0, volume_ratio - 1.0) * 35.0, 2), "volume_ratio": round(volume_ratio, 2), "quote_volume_millions": round(quote_volume, 2), "recent_return_pct": round(recent_return_pct, 2), "money_flow_side": str(signals.get('money_flow_side') or 'WAIT').upper()}

def _sanitize_signal_payload(raw_data):
    data = dict(raw_data or {})
    symbol = _canonicalize_symbol(data.get('symbol') or data.get('pair'))
    side_raw = str(data.get('side') or data.get('decision') or '').strip().upper()
    side = 'COMPRAR' if side_raw in ('BUY', 'LONG', 'COMPRAR') else 'VENDER'
    entry_price = _coerce_float(data.get('entry_price'), data.get('price'), default=0.0)
    if entry_price <= 0:
        radar_broker = _get_public_radar_broker_mainnet()
        if radar_broker is not None:
            entry_price = _coerce_float(radar_broker.get_last_price(symbol), default=0.0)
        if entry_price <= 0:
            entry_price = _coerce_float(_get_public_price_broker().get_last_price(symbol), default=0.0)
    return {'symbol': symbol, 'side': side, 'entry_price': round(entry_price, 8), 'confidence': max(0.0, min(100.0, _coerce_float(data.get('confidence'), default=70.0))), 'reason': str(data.get('reason') or 'Sinal').strip()}

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

_public_price_broker_lock = threading.Lock()
_public_radar_broker_lock = threading.Lock()

class _NullPublicBroker:
    def get_last_price(self, symbol):
        return 0.0

    def fetch_ohlcv(self, symbol, timeframe='15m'):
        return None

def _get_active_exchange_names() -> set:
    for client in _get_registered_clients(active_only=True):
        client_id = int(client.get('id') or 0)
        if _is_training_fake_balance_client(client) or _is_client_temporarily_disabled(client_id):
            continue
        api_key = str(client.get('bybit_key') or '').strip()
        api_secret = str(client.get('bybit_secret') or '').strip()
        if api_key and api_secret:
            return {'bybit'}
    return set()

def _get_active_investor_credentials(exchange='bybit'):
    exchange_name = 'bybit'
    for client in _get_registered_clients(active_only=True):
        client_id = int(client.get('id') or 0)
        if _is_training_fake_balance_client(client) or _is_client_temporarily_disabled(client_id):
            continue
        if str(client.get('exchange') or 'bybit').strip().lower() != exchange_name:
            continue
        persisted = _get_registered_client_by_id(client.get('id'))
        if persisted:
            k = str(persisted.get('bybit_key') or '').strip()
            s = str(persisted.get('bybit_secret') or '').strip()
            if k and s:
                return persisted.get('id'), k, s
    return None, '', ''

def _get_public_price_broker():
    global BybitClient, public_price_broker, public_price_brokers
    active_exchanges = _get_active_exchange_names()
    if not active_exchanges:
        return _NullPublicBroker()

    preferred_exchange = 'bybit'
    cached_public = public_price_brokers.get(preferred_exchange)
    if cached_public is not None:
        return cached_public

    with _public_price_broker_lock:
        cached_public = public_price_brokers.get(preferred_exchange)
        if cached_public is not None:
            return cached_public

        client_id, api_key, api_secret = _get_active_investor_credentials(preferred_exchange)
        if not api_key or not api_secret:
            return _NullPublicBroker()

        if BybitClient is None:
            from src.broker.bybit_client import BybitClient as _BybitClient
            BybitClient = _BybitClient
        public_price_broker = BybitClient(api_key, api_secret, testnet=ENV_CONFIG.use_testnet)

        public_price_brokers[preferred_exchange] = public_price_broker
        _get_broker_manager().prune_unused(
            active_client_ids={int(c.get('id') or 0) for c in _get_registered_clients(active_only=True)},
            active_exchanges=active_exchanges,
        )
        gc.collect()
    return public_price_broker

def _get_public_radar_broker_mainnet():
    """
    Broker dedicado para leitura pública de dados de mercado do RADAR.
    Requisito: deve usar SEMPRE Mainnet (testnet=False), independentemente de USE_TESTNET.
    """
    global BybitClient, public_radar_broker
    if public_radar_broker is not None:
        return public_radar_broker
    with _public_radar_broker_lock:
        if public_radar_broker is not None:
            return public_radar_broker
        if BybitClient is None:
            from src.broker.bybit_client import BybitClient as _BybitClient
            BybitClient = _BybitClient
        # Passa placeholders "truthy" para impedir fallback para chaves do .env.
        public_radar_broker = BybitClient(" ", " ", testnet=False)
        gc.collect()
    return public_radar_broker

def _ensure_broker_class(exchange='bybit'):
    return _get_broker_manager()._get_broker_class(exchange)

def _make_broker(client):
    if _is_training_fake_balance_client(client):
        raise RuntimeError("Cliente em modo TESTE local não deve instanciar exchange")
    exchange = 'bybit'
    use_testnet = _resolve_request_is_testnet(client, fallback=False)
    _ensure_broker_class(exchange)
    return _get_broker_manager().get_broker(client, use_testnet)

def _get_registered_clients(active_only=False):
    try: return [{**dict(c), "storage_source": "local"} for c in (db.get_active_clients() if active_only else db.get_all_clients())]
    except Exception: return []

def _get_registered_client_by_id(client_id):
    local_client = db.get_client_by_id(client_id)
    return {**dict(local_client), "storage_source": "local"} if local_client else None

def _get_active_investor_bybit_credentials():
    return _get_active_investor_credentials('bybit')

def _save_client_everywhere(client_data):
    payload = dict(client_data or {})
    payload['account_mode'] = 'real'
    payload['is_testnet'] = _resolve_request_is_testnet(payload, fallback=False)
    payload['balance_source'] = _normalize_balance_source(payload.get('balance_source'))
    payload['exchange'] = 'bybit'
    res = db.upsert_client_local(payload) if payload.get('id') is not None else db.add_client(payload)
    client_balance_cache.clear()
    return _get_registered_client_by_id(payload.get('id') or res), False, bool(res)

def _delete_client_everywhere(client_id):
    global public_price_broker, public_radar_broker, public_price_brokers
    _get_broker_manager().invalidate_client(client_id)
    public_price_broker = None
    public_radar_broker = None
    public_price_brokers.clear()
    gc.collect()
    return True, db.delete_client(client_id)


def _delete_client_sqlite_fast(client_id: int) -> bool:
    """
    DELETE blindado com conexão curta e timeout de 30s.
    """
    try:
        db_path = getattr(db, 'DB_PATH', '/data/database.db')
        with sqlite3.connect(db_path, timeout=30.0, check_same_thread=False) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM trades WHERE client_id = ?", (int(client_id),))
            cur.execute("DELETE FROM clientes_sniper WHERE id = ?", (int(client_id),))
            conn.commit()
        return True
    except Exception as del_err:
        print(f"⚠️ [DELETE INVESTIDOR] Falha ao remover ID {client_id}: {del_err}", flush=True)
        return False

def _fetch_active_client_balances(force=False):
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

    items, total = [], 0.0
    active_clients = _get_registered_clients(active_only=True)
    active_client_ids = {int(c.get('id') or 0) for c in active_clients}
    active_exchanges = _get_active_exchange_names()
    try:
        _get_broker_manager().prune_unused(
            active_client_ids=active_client_ids,
            active_exchanges=active_exchanges,
        )
        for client in active_clients:
            balance = None
            error = None
            is_fake_balance = False
            try:
                client_id = int(client.get('id') or 0)
                if _is_training_fake_balance_client(client):
                    balance = _get_forced_training_fake_balance_usd()
                    is_fake_balance = True
                elif _is_client_temporarily_disabled(client_id):
                    error = _get_client_disable_reason(client_id) or 'Cliente temporariamente desativado por erro de autenticação'
                    fake = _get_training_fake_balance_usd()
                    if fake is not None:
                        balance = fake
                        is_fake_balance = True
                else:
                    broker = _make_broker(client)
                    balance = broker.get_balance()
                    code = str(getattr(broker, 'last_auth_error_code', '') or '')
                    if code == '10003' and balance is None:
                        _handle_invalid_api_key_10003_for_client(client, source_label='fetch_balance')
                        fake = _get_training_fake_balance_usd()
                        if fake is not None:
                            balance = fake
                            is_fake_balance = True
                if balance is not None:
                    balance = round(float(balance), 2)
                    total += balance
            except Exception as e: error = str(e)
            items.append({
                "id": client.get('id'), "nome": client.get('nome'), "saldo_real": balance,
                "saldo_base": float(client.get('saldo_base', 0) or 0), "is_testnet": _resolve_request_is_testnet(client, fallback=False),
                "account_mode": "real", "exchange": str(client.get('exchange') or 'bybit').lower(),
                "status": client.get('status'), "error": error, "is_fake_balance": is_fake_balance,
            })
    except Exception:
        pass
    finally:
        gc.collect()
    
    res = {"items": items, "total": round(total, 2)}
    client_balance_cache.set(res)
    
    # ⚡ CORE FIX: Força sincronização em tempo real do card para o React
    valid_items = [item for item in items if item.get("saldo_real") is not None]
    fake_items = [item for item in valid_items if item.get("is_fake_balance")]
    real_items = [item for item in valid_items if not item.get("is_fake_balance")]
    central_state['real_client_balances'] = items
    if valid_items:
        # Unificação obrigatória: o saldo total do dashboard sempre soma TODOS os investidores ativos
        # (incluindo clientes com saldo fictício / training_fake_balance).
        central_state['balance'] = round(sum(float(i["saldo_real"]) for i in valid_items), 2)
    else:
        central_state['balance'] = 0.0

    if real_items:
        msg = f"💼 CONTA REAL: saldo sincronizado para {len(real_items)} investidores"
        if fake_items:
            msg += f" ( +{len(fake_items)} com saldo fictício TESTNET )"
        central_state['status'] = msg
    elif fake_items:
        central_state['status'] = f"🧪 TESTNET: saldo fictício ativo para {len(fake_items)} investidores"
    else:
        central_state['status'] = "💼 CONTA REAL: aguardando pareamento de chaves..."
        
    return res

def _build_api_status_payload():
    """
    Garante estrutura estável de chaves no retorno do `/api/status`,
    independente de modo REAL/TESTE, para não quebrar o frontend.
    """
    payload = dict(central_state or {})
    balance = round(_coerce_float(payload.get('balance'), default=0.0), 2)

    active_trades = payload.get('active_trades')
    if not isinstance(active_trades, list):
        active_trades = []

    normalized_trades = []
    for t in active_trades:
        if not isinstance(t, dict):
            continue
        row = dict(t)
        row['preco_atual'] = _coerce_float(row.get('current_price'), row.get('preco_atual'), default=0.0)
        row['pnl_flutuante'] = round(_coerce_float(row.get('open_pnl_value'), row.get('pnl_flutuante'), default=0.0), 2)
        normalized_trades.append(row)

    active_trades = normalized_trades
    payload['active_trades'] = active_trades

    payload['saldo_real'] = balance
    payload['saldo'] = balance
    payload['saldo_atual'] = balance
    payload['posicoes'] = active_trades
    payload['radar'] = payload.get('symbol') or '---'
    payload['confianca_ia'] = _coerce_float(payload.get('confidence'), default=0.0)
    payload['pnl_total_realizado'] = round(_coerce_float(payload.get('pnl_total'), default=0.0), 2)
    return payload

def _refresh_real_balance_state(force=False):
    _fetch_active_client_balances(force=force)

def _get_live_price_snapshot(symbol, entry_price, side):
    try:
        current_price = _get_live_market_price(symbol)
        return _calculate_live_trade_metrics(entry_price, current_price, side)
    except Exception:
        return _calculate_live_trade_metrics(entry_price, _get_cached_last_price(symbol), side)

def _refresh_last_sniper_signal():
    s = central_state.get('last_sniper_signal')
    if s: s.update(_get_live_price_snapshot(s.get('raw_symbol') or s.get('symbol'), s.get('entry_price'), s.get('side')))

def _repair_open_trades():
    try:
        open_trades = db.get_open_trades(100)
        if not open_trades: return
        conn = None
        try:
            conn = db._connect()
            cur = conn.cursor()
            for t in open_trades:
                canonical = _canonicalize_symbol(t.get('pair'))
                if not canonical or _extract_entry_price(t) <= 0:
                    cur.execute("UPDATE trades SET status='closed', pnl_pct=0, closed_at=? WHERE id=?", (time.strftime("%d/%m %H:%M"), t.get('id')))
            conn.commit()
        finally:
            if conn is not None:
                conn.close()
    except Exception: pass

def _can_open_new_signal(symbol):
    _repair_open_trades()
    open_symbols = {_normalize_symbol_key(t.get('pair')) for t in db.get_open_trades(100) if t.get('pair')}
    if _normalize_symbol_key(_canonicalize_symbol(symbol)) in open_symbols: return False, "Moeda já ativa."
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
        pnl, w, l = 0.0, 0, 0
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
    """
    Monitor percentual legado desativado.
    A saída oficial é feita somente pelo _monitor_financial_stop_loss em USDT bruto.
    """
    print("⏸️ [MONITOR SL/TP LEGADO] Desativado — usando apenas alvo fixo em USDT.", flush=True)
    while True:
        time.sleep(60)

def _normalize_position_side(raw_side: str) -> str:
    side = str(raw_side or '').strip().lower()
    if side in ('buy', 'long', 'comprar'):
        return 'buy'
    if side in ('sell', 'short', 'vender'):
        return 'sell'
    return side

def _detect_flow_reversal_1m(broker, symbol: str, side: str):
    """
    CÉREBRO 3: detecta quebra estrutural (ChoCh/MSS) em 1m com volume forte.
    Retorna: (reversal_detected, reason)
    """
    try:
        df = broker.fetch_ohlcv(symbol, timeframe='1m')
        if df is None or len(df) < 35:
            return False, "insufficient_1m_data"

        if not isinstance(df, pd.DataFrame):
            return False, "invalid_1m_frame"

        frame = df.tail(30).copy()
        for col in ('close', 'high', 'low', 'vol'):
            frame[col] = pd.to_numeric(frame[col], errors='coerce')
        frame = frame.dropna(subset=['close', 'high', 'low', 'vol'])
        if len(frame) < 20:
            return False, "insufficient_numeric_1m_data"

        last_closed = frame.iloc[-2]
        history = frame.iloc[:-2]
        if len(history) < 10:
            return False, "insufficient_history_1m"

        vol_ma = float(history['vol'].tail(20).mean() or 0.0)
        vol_ratio = (float(last_closed['vol']) / vol_ma) if vol_ma > 0 else 0.0
        strong_volume = vol_ratio >= 1.6
        normalized_side = _normalize_position_side(side)

        if normalized_side == 'buy':
            last_higher_low = float(history['low'].tail(12).min())
            broke_structure = float(last_closed['close']) < last_higher_low
            if broke_structure and strong_volume:
                return True, f"ChoCh bearish (close<{last_higher_low:.6f}) vol={vol_ratio:.2f}x"
        elif normalized_side == 'sell':
            last_lower_high = float(history['high'].tail(12).max())
            broke_structure = float(last_closed['close']) > last_lower_high
            if broke_structure and strong_volume:
                return True, f"ChoCh bullish (close>{last_lower_high:.6f}) vol={vol_ratio:.2f}x"
        return False, "no_flow_break"
    except Exception as exc:
        return False, f"flow_check_error: {exc}"

def _monitor_financial_stop_loss():
    """
    🎯 MONITOR FINANCEIRO V60.7 — ESCALONAMENTO RÁPIDO EM USDT (BINÁRIO)

    Monitora o unrealisedPnl em tempo real de todas as posições abertas.
    Regra estritamente em PnL bruto (USDT):
    - Take Profit: fecha quando unrealisedPnl >= ALVO_LUCRO_USDT
    - Stop Loss:  fecha quando unrealisedPnl <= STOP_PERDA_USDT
    - Zona neutra: não faz nada.

    Contingência:
    - Se falhar leitura de preço/ticker, não executa fechamento.
    """
    time.sleep(5)  # Aguarda inicialização do sistema
    alvo_lucro = float(ALVO_LUCRO_USDT)
    alvo_perda = float(STOP_PERDA_USDT)
    print(
        f"🎯 [MONITOR FINANCEIRO] Iniciado — TP: +${alvo_lucro:.2f} | SL: ${alvo_perda:.2f}",
        flush=True
    )

    while True:
        try:
            clientes = _get_registered_clients(active_only=True)

            for cliente in clientes:
                try:
                    client_id = int(cliente.get('id') or 0)
                    if _is_training_fake_balance_client(cliente):
                        try:
                            open_trades = [
                                t for t in db.get_open_trades(limit=200)
                                if int(t.get('client_id') or 0) == client_id
                            ]
                            for trade in open_trades:
                                symbol = _canonicalize_symbol(trade.get('pair') or '')
                                if not symbol:
                                    continue
                                entry_price = _coerce_float(trade.get('entry_price'), default=0.0)
                                qty = _coerce_float(trade.get('quantity'), default=0.0)
                                if entry_price <= 0 or qty <= 0:
                                    continue
                                side = _normalize_position_side(trade.get('side') or '')
                                current_price = _coerce_float(_get_live_market_price(symbol, preferred_price=entry_price), default=0.0)
                                if current_price <= 0:
                                    continue
                                if side == 'sell':
                                    unrealised_pnl = (entry_price - current_price) * qty
                                else:
                                    unrealised_pnl = (current_price - entry_price) * qty

                                print(
                                    f"   📊 [MONITOR PAPER] {symbol} | Qty: {qty} | unrealisedPnl: ${unrealised_pnl:.2f} | "
                                    f"TP: +${alvo_lucro:.2f} | SL: ${alvo_perda:.2f}",
                                    flush=True
                                )

                                motivo_fechamento = None
                                if unrealised_pnl >= alvo_lucro:
                                    motivo_fechamento = "TAKE_PROFIT_PAPER"
                                elif unrealised_pnl <= alvo_perda:
                                    motivo_fechamento = "STOP_LOSS_PAPER"

                                if motivo_fechamento:
                                    db.close_trade(
                                        trade_id=int(trade.get('id') or 0),
                                        pnl_pct=0.0,
                                        profit=round(unrealised_pnl, 2),
                                        exit_price=current_price,
                                        closed_at=time.strftime("%d/%m %H:%M"),
                                        notes=f"PAPER_AUTO_CLOSE | {motivo_fechamento}",
                                        entry_price=entry_price,
                                        quantity=qty,
                                        side=str(trade.get('side') or ''),
                                    )
                                    print(
                                        f"   ✅ [PAPER CLOSE] {symbol} encerrada ({motivo_fechamento}) com PnL ${unrealised_pnl:.2f}",
                                        flush=True
                                    )
                                    _sync_active_trades_from_db()
                        except Exception as paper_err:
                            print(f"   ⚠️ [MONITOR PAPER] Erro ao processar posições simuladas: {paper_err}", flush=True)
                        continue
                    if _is_client_temporarily_disabled(client_id):
                        continue

                    broker = _make_broker(cliente)
                    exchange_name = str(cliente.get('exchange') or 'bybit').strip().lower()
                    if exchange_name != 'bybit':
                        continue
                    positions_list = []

                    try:
                        if exchange_name == 'bybit':
                            if not broker.pybit_session or not broker.authenticated:
                                continue

                            positions_response = broker.pybit_session.get_positions(category='linear', settleCoin='USDT')
                            ok, err = broker._handle_v5_ret_code(positions_response, 'get_positions')

                            if not ok:
                                if str(_extract_bybit_ret_code_from_error(err)) == '10003' or 'retCode=10003' in str(err):
                                    _handle_invalid_api_key_10003_for_client(cliente, source_label='MONITOR FINANCEIRO:get_positions')
                                continue

                            positions_list = (positions_response.get('result') or {}).get('list', [])
                        else:
                            continue

                        for pos in positions_list:
                            try:
                                symbol = pos.get('symbol', '')
                                size = float(pos.get('size') or 0)
                                side = _normalize_position_side(pos.get('side', ''))
                                unrealised_pnl = float(pos.get('unrealisedPnl') or 0)
                                entry_price = float(pos.get('avgPrice') or pos.get('entryPrice') or 0)
                                mark_price = float(pos.get('markPrice') or pos.get('lastPrice') or entry_price or 0)
                                leverage = float(pos.get('leverage') or ALAVANCAGEM or 1.0)

                                if size <= 0:
                                    continue

                                # Contingência: se preço não puder ser lido com confiança, não fecha posição.
                                current_price = 0.0
                                try:
                                    current_price = float(broker.get_last_price(symbol) or 0.0)
                                except Exception as ticker_err:
                                    print(f"   ⚠️ [MONITOR] Falha no ticker de {symbol}: {ticker_err} — saída bloqueada", flush=True)
                                if current_price <= 0 and mark_price <= 0:
                                    print(f"   ⚠️ [MONITOR] Preço indisponível para {symbol} — saída bloqueada até reestabelecer conexão", flush=True)
                                    continue

                                print(
                                    f"   📊 [MONITOR] {symbol} | Size: {size} | "
                                    f"unrealisedPnl: ${unrealised_pnl:.2f} | "
                                    f"TP: +${alvo_lucro:.2f} | SL: ${alvo_perda:.2f}",
                                    flush=True
                                )

                                # CÉREBRO 3: proteção antirreversão por quebra estrutural.
                                reversal_detected, reversal_reason = _detect_flow_reversal_1m(broker, symbol, side)
                                if reversal_detected:
                                    motivo_fechamento = "REVERSAO_FLUXO"
                                    print(
                                        f"[CÉREBRO 3] Alerta: Estrutura quebrou contra a operação em {symbol} "
                                        f"({reversal_reason}). Abortando trade com PnL ${unrealised_pnl:.2f}.",
                                        flush=True
                                    )
                                elif unrealised_pnl >= alvo_lucro:
                                    motivo_fechamento = "TAKE_PROFIT"
                                elif unrealised_pnl <= alvo_perda:
                                    motivo_fechamento = "STOP_LOSS"
                                else:
                                    # Zona neutra — não faz nada
                                    continue
                                # ───────────────────────────────────────────────────────

                                if motivo_fechamento == "TAKE_PROFIT":
                                    print(f"🏆 [TAKE PROFIT] {symbol} atingiu alvo de lucro!", flush=True)
                                    print(f"   💰 unrealisedPnl: ${unrealised_pnl:.2f} >= Alvo: +${alvo_lucro:.2f}", flush=True)
                                elif motivo_fechamento == "STOP_LOSS":
                                    print(f"🚨 [STOP LOSS] {symbol} atingiu limite de perda!", flush=True)
                                    print(f"   💔 unrealisedPnl: ${unrealised_pnl:.2f} <= Limite: ${alvo_perda:.2f}", flush=True)
                                else:
                                    print(f"🧠 [REVERSÃO] {symbol} fechamento defensivo por fluxo contrário", flush=True)

                                print(f"   🔒 Disparando fechamento forçado...", flush=True)

                                try:
                                    success = broker.close_position_with_sl(symbol, side)

                                    if success:
                                        print(f"   ✅ [{motivo_fechamento}] Posição {symbol} fechada com sucesso!", flush=True)

                                        try:
                                            conn = None
                                            conn = db._connect()
                                            cur = conn.cursor()
                                            profit = unrealised_pnl
                                            note_tag = (
                                                f" | TAKE_PROFIT_AUTO unrealisedPnl=${unrealised_pnl:.2f}"
                                                if motivo_fechamento == "TAKE_PROFIT"
                                                else f" | STOP_LOSS_AUTO unrealisedPnl=${unrealised_pnl:.2f}"
                                            )
                                            cur.execute(
                                                "UPDATE trades SET status='closed', pnl_pct=?, profit=?, notes=COALESCE(notes,'') || ? WHERE pair=? AND client_id=? AND status='open'",
                                                (
                                                    0.0,
                                                    round(profit, 2),
                                                    note_tag,
                                                    symbol,
                                                    cliente.get('id')
                                                )
                                            )
                                            conn.commit()
                                            print(f"   💾 [BANCO] Trade atualizado — P&L: ${profit:.2f}", flush=True)
                                        except Exception as db_err:
                                            print(f"   ⚠️ [BANCO] Erro ao atualizar trade: {db_err}", flush=True)
                                        finally:
                                            try:
                                                if conn is not None:
                                                    conn.close()
                                            except Exception:
                                                pass

                                        try:
                                            from src.trade_history import record_closed_trade_sync
                                            _auto_direction = 'BUY' if side in ('long', 'buy') else 'SELL'
                                            record_closed_trade_sync(
                                                pybit_session=broker.pybit_session,
                                                asset=symbol,
                                                direction=_auto_direction,
                                                entry_price=entry_price,
                                                stop_loss=0.0,
                                                take_profit=0.0,
                                                exit_price=mark_price,
                                                exit_reason=motivo_fechamento,
                                                gross_pnl=round(unrealised_pnl, 4),
                                                market_context={
                                                    'unrealised_pnl': unrealised_pnl,
                                                    'target_tp_usdt': round(alvo_lucro, 2),
                                                    'target_sl_usdt': round(alvo_perda, 2),
                                                    'leverage': leverage,
                                                    'mark_price': mark_price,
                                                    'close_reason': motivo_fechamento,
                                                },
                                                client_id=int(cliente.get('id') or 0),
                                            )
                                        except Exception as th_err:
                                            print(f"   ⚠️ [TRADE HISTORY] Erro ao salvar histórico: {th_err}", flush=True)

                                        _sync_active_trades_from_db()
                                    else:
                                        print(f"   ❌ [{motivo_fechamento}] Falha ao fechar posição {symbol}", flush=True)

                                except Exception as close_err:
                                    print(f"   ❌ [{motivo_fechamento}] Erro ao fechar posição: {close_err}", flush=True)

                            except Exception as pos_err:
                                print(f"   ⚠️ [MONITOR] Erro ao processar posição: {pos_err}", flush=True)
                                continue

                    except Exception as fetch_err:
                        code = _extract_bybit_ret_code_from_error(fetch_err)
                        if str(code) == '10003' or 'API key is invalid' in str(fetch_err):
                            _handle_invalid_api_key_10003_for_client(cliente, source_label='MONITOR FINANCEIRO:exception')
                            continue
                        print(f"   ⚠️ [MONITOR] Erro ao buscar posições do cliente {cliente.get('nome')}: {fetch_err}", flush=True)
                        continue

                except Exception as client_err:
                    print(f"   ⚠️ [MONITOR] Erro ao processar cliente {cliente.get('nome', 'Unknown')}: {client_err}", flush=True)
                    continue

        except Exception as general_err:
            print(f"❌ [MONITOR FINANCEIRO] Erro geral: {general_err}", flush=True)

        time.sleep(5)

def _sync_active_trades_from_db():
    """ ⚡ ESTRUTURADOR DOS CARDS EM TEMPO REAL PARA ACENDER O PAINEL REACT """
    try:
        _repair_open_trades()
        open_trades = db.get_open_trades(50)
        grouped = {}

        for t in open_trades:
            if str(t.get('status')).lower() != 'open': continue
            raw_symbol = _canonicalize_symbol(t.get('pair'))
            if not raw_symbol: continue

            key = _normalize_symbol_key(raw_symbol)
            qty = _coerce_float(t.get('quantity'), default=0.0)
            entry_price = _extract_entry_price(t)
            if entry_price <= 0: continue
            margin = _coerce_float(t.get('margin'), default=0.0)
            if margin <= 0 and qty > 0:
                margin = abs((qty * entry_price) / float(ALAVANCAGEM or 1))

            if key not in grouped:
                grouped[key] = {
                    'id': t.get('id'),
                    'symbol': _limpar_simbolo(raw_symbol),
                    'raw_symbol': raw_symbol,
                    'side': t.get('side'),
                    'entry': 0.0,
                    'entry_price': entry_price,
                    'current_price': 0.0,
                    'price_change_pct': 0.0,
                    'pnl_pct': 0.0,
                    'trend': 'flat',
                    'is_favorable': False,
                    'notes': t.get('notes', ''),
                    'client_count': 0,
                    'trade_count': 0,
                    'quantity': 0.0,
                    'latest_trade_id': int(t.get('id') or 0),
                }

            trade_group = grouped[key]
            trade_group['entry'] = round(float(trade_group.get('entry', 0) or 0) + margin, 2)
            trade_group['quantity'] = float(trade_group.get('quantity', 0.0) or 0.0) + qty
            trade_group['client_count'] += 1
            trade_group['trade_count'] += 1

        central_state['active_trades'] = sorted(grouped.values(), key=lambda x: x.get('latest_trade_id', 0), reverse=True)

        for trade in central_state['active_trades']:
            live = _get_live_price_snapshot(trade.get('raw_symbol') or trade.get('symbol'), trade.get('entry_price'), trade.get('side'))
            trade.update(live)
            qty = _coerce_float(trade.get('quantity'), default=0.0)
            entry_price = _coerce_float(trade.get('entry_price'), default=0.0)
            current_price = _coerce_float(trade.get('current_price'), default=0.0)
            side_raw = str(trade.get('side') or '').upper()
            if qty > 0 and entry_price > 0 and current_price > 0:
                if side_raw in ('VENDER', 'SELL', 'SHORT'):
                    open_pnl = (entry_price - current_price) * qty
                else:
                    open_pnl = (current_price - entry_price) * qty
                trade['open_pnl_value'] = round(open_pnl, 2)
            else:
                trade['open_pnl_value'] = 0.0
            trade['pnl_flutuante'] = trade['open_pnl_value']
    except Exception:
        central_state['active_trades'] = []

def _monitor_dashboard_positions():
    """
    🔄 MONITOR DE SINCRONIZAÇÃO DO DASHBOARD EM TEMPO REAL

    Busca posições abertas e saldo diretamente da API da Bybit para alimentar
    o frontend do painel, garantindo que os dados exibidos reflitam a realidade da conta.

    Esta função corrige o problema de dashboard travado em "Iniciando sistema..."
    e exibindo $0 quando há posições abertas na Bybit.

    Parâmetros obrigatórios da API Bybit V5:
    - category='linear' (para contratos perpétuos USDT)
    - settleCoin='USDT' (para evitar erro 10001)
    """
    time.sleep(8)  # Aguarda inicialização completa do sistema
    print(f"🔄 [DASHBOARD MONITOR] Iniciado - Sincronização de posições Bybit → Frontend", flush=True)

    while True:
        try:
            # Busca todos os clientes ativos
            clientes = _get_registered_clients(active_only=True)

            if not clientes:
                central_state['status'] = "💼 Aguardando registro de investidores..."
                central_state['balance'] = 0.0
                central_state['active_trades'] = []
                time.sleep(10)
                continue

            total_wallet_balance = 0.0
            all_positions = []
            open_trades_snapshot = db.get_open_trades(limit=300)
            simulated_trades_by_client = {}
            for _t in open_trades_snapshot:
                try:
                    _cid = int(_t.get('client_id') or 0)
                except Exception:
                    _cid = 0
                if _cid <= 0:
                    continue
                simulated_trades_by_client.setdefault(_cid, []).append(_t)

            for cliente in clientes:
                try:
                    client_id = int(cliente.get('id') or 0)
                    exchange_name = str(cliente.get('exchange') or 'bybit').strip().lower()
                    if exchange_name != 'bybit':
                        continue
                    if _is_training_fake_balance_client(cliente):
                        fake = _get_forced_training_fake_balance_usd()
                        total_wallet_balance += float(fake)
                        client_open_trades = simulated_trades_by_client.get(client_id, [])
                        for trade in client_open_trades:
                            try:
                                symbol = _canonicalize_symbol(trade.get('pair') or '')
                                if not symbol:
                                    continue
                                qty = _coerce_float(trade.get('quantity'), default=0.0)
                                entry_price = _coerce_float(trade.get('entry_price'), default=0.0)
                                if qty <= 0 or entry_price <= 0:
                                    continue
                                side = _normalize_position_side(trade.get('side') or '')
                                side_normalized = 'COMPRAR' if side in ('buy', 'long') else 'VENDER'
                                current_price = _get_live_market_price(symbol, preferred_price=entry_price)
                                if current_price <= 0:
                                    continue
                                if side_normalized == 'VENDER':
                                    unrealised_pnl = (entry_price - current_price) * qty
                                else:
                                    unrealised_pnl = (current_price - entry_price) * qty
                                all_positions.append({
                                    'client_id': client_id,
                                    'client_nome': cliente.get('nome'),
                                    'symbol': symbol,
                                    'side': side_normalized,
                                    'size': qty,
                                    'entry_price': entry_price,
                                    'unrealised_pnl': round(unrealised_pnl, 8),
                                    'leverage': float(ALAVANCAGEM or 1),
                                    'mark_price': current_price,
                                })
                            except Exception as sim_err:
                                print(f"   ⚠️ [DASHBOARD] Erro ao processar posição simulada: {sim_err}", flush=True)
                                continue
                        print(
                            f"   🧪 [DASHBOARD] Cliente {cliente.get('nome')} em modo TESTE — usando saldo fictício: ${float(fake):.2f} USDT",
                            flush=True,
                        )
                        continue

                    if _is_client_temporarily_disabled(client_id):
                        fake = _get_training_fake_balance_usd()
                        if fake is not None:
                            total_wallet_balance += float(fake)
                            print(
                                f"   🧪 [DASHBOARD] Cliente {cliente.get('nome')} desativado por autenticação — usando saldo fictício: ${float(fake):.2f} USDT",
                                flush=True,
                            )
                        else:
                            print(
                                f"   ⚠️ [DASHBOARD] Cliente {cliente.get('nome')} desativado por autenticação: {_get_client_disable_reason(client_id) or 'motivo indisponível'}",
                                flush=True,
                            )
                        continue

                    broker = _make_broker(cliente)

                    # Verifica autenticação mínima de forma agnóstica de corretora
                    if not getattr(broker, 'authenticated', False):
                        fake = _get_training_fake_balance_usd()
                        if fake is not None:
                            total_wallet_balance += float(fake)
                            print(
                                f"   🧪 [DASHBOARD] Cliente {cliente.get('nome')} sem autenticação ativa — usando saldo fictício: ${float(fake):.2f} USDT",
                                flush=True,
                            )
                        else:
                            print(f"   ⚠️ [DASHBOARD] Cliente {cliente.get('nome')} sem autenticação ativa", flush=True)
                        continue

                    # 1️⃣/2️⃣ PROCESSAMENTO ESTRITAMENTE BYBIT
                    if not getattr(broker, 'pybit_session', None):
                        fake = _get_training_fake_balance_usd()
                        if fake is not None:
                            total_wallet_balance += float(fake)
                        print(f"   ⚠️ [DASHBOARD] {cliente.get('nome')}: sessão Bybit indisponível", flush=True)
                        continue

                    # BYBIT - saldo
                    try:
                        client_balance_added = False
                        wallet_response = broker.pybit_session.get_wallet_balance(accountType='UNIFIED')
                        ok, err = broker._handle_v5_ret_code(wallet_response, 'get_wallet_balance')

                        if ok:
                            result = wallet_response.get('result', {})
                            wallet_list = result.get('list', [])
                            if wallet_list:
                                wallet_data = wallet_list[0]
                                for coin in wallet_data.get('coin', []):
                                    if coin.get('coin') == 'USDT':
                                        wallet_balance = float(coin.get('walletBalance') or coin.get('equity') or 0)
                                        total_wallet_balance += wallet_balance
                                        client_balance_added = True
                                        print(f"   💰 [DASHBOARD] {cliente.get('nome')}: ${wallet_balance:.2f} USDT", flush=True)
                                        break
                        else:
                            print(f"   ⚠️ [DASHBOARD] Erro ao buscar saldo de {cliente.get('nome')}: {err}", flush=True)
                            code = _extract_bybit_ret_code_from_error(err)
                            if not client_balance_added and str(code or '') == '10003':
                                _handle_invalid_api_key_10003_for_client(cliente, source_label='DASHBOARD:get_wallet_balance')
                                fake = _get_training_fake_balance_usd()
                                if fake is not None:
                                    total_wallet_balance += float(fake)
                                    print(
                                        f"   🧪 [DASHBOARD] {cliente.get('nome')}: saldo fictício aplicado após erro 10003 (${float(fake):.2f} USDT)",
                                        flush=True,
                                    )
                    except Exception as wallet_err:
                        print(f"   ⚠️ [DASHBOARD] Exceção ao buscar saldo Bybit: {wallet_err}", flush=True)
                        code = _extract_bybit_ret_code_from_error(wallet_err)
                        if str(code or '') == '10003':
                            _handle_invalid_api_key_10003_for_client(cliente, source_label='DASHBOARD:get_wallet_balance:exception')
                            fake = _get_training_fake_balance_usd()
                            if fake is not None:
                                total_wallet_balance += float(fake)
                                print(
                                    f"   🧪 [DASHBOARD] {cliente.get('nome')}: saldo fictício aplicado após exceção 10003 (${float(fake):.2f} USDT)",
                                    flush=True,
                                )

                    # BYBIT - posições
                    try:
                        positions_response = broker.pybit_session.get_positions(
                            category='linear',
                            settleCoin='USDT'
                        )
                        ok, err = broker._handle_v5_ret_code(positions_response, 'get_positions')
                        if not ok:
                            print(f"   ⚠️ [DASHBOARD] Erro ao buscar posições de {cliente.get('nome')}: {err}", flush=True)
                            continue

                        positions_list = (positions_response.get('result') or {}).get('list', [])
                        for pos in positions_list:
                            try:
                                symbol = pos.get('symbol', '')
                                size = float(pos.get('size') or 0)
                                side = str(pos.get('side', '')).lower()
                                entry_price = float(pos.get('avgPrice') or 0)
                                unrealised_pnl = float(pos.get('unrealisedPnl') or 0)
                                leverage = float(pos.get('leverage') or ALAVANCAGEM)
                                if size <= 0:
                                    continue
                                side_normalized = 'COMPRAR' if side in ('buy', 'long') else 'VENDER'
                                all_positions.append({
                                    'client_id': cliente.get('id'),
                                    'client_nome': cliente.get('nome'),
                                    'symbol': symbol,
                                    'side': side_normalized,
                                    'size': size,
                                    'entry_price': entry_price,
                                    'unrealised_pnl': unrealised_pnl,
                                    'leverage': leverage
                                })
                                print(f"   📊 [DASHBOARD] {symbol}: {side_normalized} | Size: {size} | Entry: ${entry_price:.4f} | PnL: ${unrealised_pnl:.2f}", flush=True)
                            except Exception as pos_parse_err:
                                print(f"   ⚠️ [DASHBOARD] Erro ao processar posição Bybit: {pos_parse_err}", flush=True)
                                continue
                    except Exception as fetch_pos_err:
                        print(f"   ⚠️ [DASHBOARD] Erro ao buscar posições Bybit: {fetch_pos_err}", flush=True)
                        continue

                except Exception as client_err:
                    print(f"   ⚠️ [DASHBOARD] Erro ao processar cliente {cliente.get('nome', 'Unknown')}: {client_err}", flush=True)
                    continue

            # 🔄 SINCRONIZAÇÃO REVERSA: DETECTAR E LIMPAR POSIÇÕES ENCERRADAS NA BYBIT
            # Verifica se posições marcadas como 'open' no banco foram fechadas na corretora
            try:
                # Normaliza símbolos antes de comparar (ex: 'TON/USDT:USDT' -> 'TONUSDT')
                def normalize_pair(pair_str):
                    """
                    Normaliza formato de par/símbolo para comparação entre banco e Bybit API.
                    Ex.: 'TON/USDT:USDT' -> 'TONUSDT' | 'BILL-USDT' -> 'BILLUSDT'
                    """
                    text = str(pair_str or '').strip().upper()
                    text = text.split(':', 1)[0]  # remove sufixos como ':USDT'
                    return (
                        text
                        .replace('/', '')
                        .replace('-', '')
                        .replace(' ', '')
                    )

                # Constrói mapa de posições ativas normalizadas da Bybit: (normalized_symbol, client_id) → True
                bybit_active_positions = set()
                for pos in all_positions:
                    symbol = normalize_pair(pos.get('symbol'))
                    client_id = pos.get('client_id')
                    if symbol and client_id is not None:
                        bybit_active_positions.add((symbol, client_id))

                # Obtém todas as posições marcadas como 'open' no banco de dados
                open_trades = db.get_open_trades(limit=100)

                # Itera sobre posições abertas no banco
                stale_trades_count = 0
                for trade in open_trades:
                    trade_symbol = trade.get('pair', '')
                    client_id = trade.get('client_id')

                    if not trade_symbol or client_id is None:
                        continue

                    # Normaliza para comparação com Bybit
                    normalized_trade_pair = normalize_pair(trade_symbol)
                    if not normalized_trade_pair:
                        continue

                    # Verifica se esta posição existe nos ativos normalizados da Bybit
                    position_exists = (normalized_trade_pair, client_id) in bybit_active_positions

                    # Se posição está 'open' no banco mas NÃO existe na Bybit → foi fechada externamente
                    if not position_exists:
                        # Marca como 'closed' no banco de dados
                        conn = db._connect()
                        cur = conn.cursor()
                        try:
                            timestamp = datetime.now().strftime("%d/%m %H:%M")
                            note = f"Position closed on exchange (Bybit API sync)"
                            cur.execute(
                                "UPDATE trades SET status='closed', closed_at=?, notes=COALESCE(notes,'') || ' | ' || ? WHERE id=?",
                                (timestamp, note, trade.get('id'))
                            )
                            conn.commit()
                            stale_trades_count += 1
                            print(f"   🧹 [SYNC REVERSA] Posição {trade_symbol} (ID: {trade.get('id')}) marcada como fechada (detectada ausência na API Bybit)", flush=True)
                        except Exception as update_err:
                            print(f"   ⚠️ [SYNC REVERSA] Erro ao atualizar trade ID {trade.get('id')}: {update_err}", flush=True)
                        finally:
                            conn.close()

                        # 🧠 Registra na trade_history com PnL líquido real da API V5
                        try:
                            from src.trade_history import record_closed_trade_sync
                            # Recupera o broker do cliente para buscar PnL real
                            _sync_client = next(
                                (c for c in clientes if c.get('id') == client_id), None
                            )
                            _sync_pybit = None
                            if _sync_client:
                                try:
                                    _sync_pybit = _make_broker(_sync_client).pybit_session
                                except Exception:
                                    pass
                            _sync_side = str(trade.get('side') or '').upper()
                            _sync_direction = 'SELL' if _sync_side in ('VENDER', 'SELL', 'SHORT') else 'BUY'
                            _sync_entry = float(trade.get('entry_price') or 0)
                            _sync_qty = float(trade.get('quantity') or 0)
                            _sync_exit = float(trade.get('exit_price') or 0)
                            _sync_gross = float(trade.get('profit') or 0)
                            record_closed_trade_sync(
                                pybit_session=_sync_pybit,
                                asset=trade_symbol,
                                direction=_sync_direction,
                                entry_price=_sync_entry,
                                stop_loss=0.0,
                                take_profit=0.0,
                                exit_price=_sync_exit,
                                exit_reason='MANUAL',
                                gross_pnl=_sync_gross,
                                market_context={
                                    'quantity': _sync_qty,
                                    'close_source': 'bybit_reverse_sync',
                                },
                                client_id=int(client_id or 0),
                                trade_db_id=int(trade.get('id') or 0),
                            )
                        except Exception as th_err:
                            print(f"   ⚠️ [TRADE HISTORY] Erro ao salvar histórico (sync reversa): {th_err}", flush=True)

                if stale_trades_count > 0:
                    print(f"   ✅ [SYNC REVERSA] {stale_trades_count} posição(ões) sincronizada(s) como encerrada(s)", flush=True)

            except Exception as sync_err:
                print(f"   ⚠️ [SYNC REVERSA] Erro durante sincronização reversa: {sync_err}", flush=True)
                import traceback
                traceback.print_exc()

            # 3️⃣ ATUALIZA O ESTADO CENTRAL DO DASHBOARD
            central_state['balance'] = round(total_wallet_balance, 2)

            if all_positions:
                central_state['status'] = f"✅ ONLINE | {len(all_positions)} posição(ões) ativa(s)"
                print(f"🔄 [SINCRONIZAÇÃO] Atualizando Tickers e P&L para {len(all_positions)} posições ativas.", flush=True)

                # Agrupa posições por símbolo para o painel
                grouped_positions = {}
                for pos in all_positions:
                    symbol = pos['symbol']
                    key = _normalize_symbol_key(symbol)

                    if key not in grouped_positions:
                        grouped_positions[key] = {
                            'symbol': _limpar_simbolo(symbol),
                            'raw_symbol': symbol,
                            'side': pos['side'],
                            'entry_price': pos['entry_price'],
                            'mark_price': _coerce_float(pos.get('mark_price'), default=0.0),
                            'unrealised_pnl': 0.0,
                            'size': 0.0,
                            'leverage': pos['leverage'],
                            'client_count': 0
                        }

                    grouped_positions[key]['unrealised_pnl'] += pos['unrealised_pnl']
                    grouped_positions[key]['size'] += pos['size']
                    grouped_positions[key]['client_count'] += 1
                    grouped_positions[key]['mark_price'] = _coerce_float(pos.get('mark_price'), grouped_positions[key].get('mark_price'), default=grouped_positions[key].get('mark_price', 0.0))

                # Atualiza os trades ativos com preços em tempo real
                active_trades_list = []
                for key, pos_data in grouped_positions.items():
                    try:
                        # Busca preço atual para calcular PnL% com fallback em memória.
                        current_price = _get_live_market_price(
                            pos_data['raw_symbol'],
                            preferred_price=pos_data.get('mark_price', 0.0),
                        )

                        # Calcula métricas em tempo real
                        live_metrics = _calculate_live_trade_metrics(
                            pos_data['entry_price'],
                            current_price,
                            pos_data['side']
                        )

                        # Calcula margem total usada (notional value / leverage)
                        leverage = grouped_positions[key].get('leverage', ALAVANCAGEM)
                        notional_value = pos_data['size'] * pos_data['entry_price']
                        margin_used = notional_value / leverage if leverage > 0 else notional_value

                        active_trades_list.append({
                            'symbol': pos_data['symbol'],
                            'raw_symbol': pos_data['raw_symbol'],
                            'side': pos_data['side'],
                            'entry_price': pos_data['entry_price'],
                            'current_price': live_metrics['current_price'],
                            'preco_atual': live_metrics['current_price'],
                            'price_change_pct': live_metrics['price_change_pct'],
                            'pnl_pct': live_metrics['pnl_pct'],
                            'trend': live_metrics['trend'],
                            'is_favorable': live_metrics['is_favorable'],
                            'open_pnl_value': round(pos_data['unrealised_pnl'], 2),
                            'pnl_flutuante': round(pos_data['unrealised_pnl'], 2),
                            'entry': round(margin_used, 2),
                            'size': pos_data['size'],
                            'client_count': pos_data['client_count']
                        })
                    except Exception as calc_err:
                        print(f"   ⚠️ [DASHBOARD] Erro ao calcular métricas para {pos_data['symbol']}: {calc_err}", flush=True)
                        continue

                central_state['active_trades'] = active_trades_list

            else:
                central_state['status'] = f"✅ ONLINE | Saldo: ${total_wallet_balance:.2f} USDT | Sem posições abertas"
                central_state['active_trades'] = []

            print(f"🔄 [DASHBOARD] Estado atualizado: Saldo=${total_wallet_balance:.2f} | Posições={len(all_positions)}", flush=True)

        except Exception as general_err:
            print(f"❌ [DASHBOARD MONITOR] Erro geral: {general_err}", flush=True)
            import traceback
            traceback.print_exc()
        finally:
            gc.collect()

        # Aguarda 10 segundos antes da próxima sincronização
        time.sleep(10)

def _close_stale_open_trades(max_age_minutes=180):
    try:
        conn = None
        conn = db._connect()
        cur = conn.cursor()
        for t in db.get_open_trades(100):
            dt = datetime.fromisoformat(str(t.get('created_at')).replace('Z', ''))
            if (datetime.now() - dt) > timedelta(minutes=max_age_minutes):
                cur.execute("UPDATE trades SET status='closed', notes=COALESCE(notes,'') || ' | STALE' WHERE id=?", (t.get('id'),))
        conn.commit()
    except Exception: pass
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

def _calculate_dynamic_order_quantity(broker, symbol, banca=None):
    """
    🎯 GESTÃO ESTRITAMENTE FINANCEIRA V60.7 - COM MARGEM FIXA
    
    Utiliza margem de entrada fixa: MARGEM_INPUT = 5.0 USDT
    Alavancagem fixa: ALAVANCAGEM = 20x
    
    Calcula quantidade baseada em:
    - Margem de entrada: 5.0 USDT (MARGEM_INPUT, fixo)
    - Alavancagem: 20x fixo (ALAVANCAGEM)
    - Fórmula: Qty = (5.0 × 20) / Preço Atual
    
    Retorna (margem_separada, quantidade_normalizada, saldo_atualizado)
    """
    try:
        # 🔥 CONFIGURAÇÃO FIXA: Usa as variáveis de módulo definidas
        risk_margin = MARGEM_INPUT  # 5.0 USDT
        leverage_value = ALAVANCAGEM  # 20x

        # Busca saldo atual para referência (não mais usado para cálculo de margem)
        saldo_atual = broker.get_balance()
        if saldo_atual is None or saldo_atual <= 0:
            print(f"⚠️ [CALC QTY] Falha ao buscar saldo da Bybit, usando padrão: ${banca:.2f}", flush=True)
            saldo_atual = banca if banca and banca > 0 else 1000.0
        
        saldo_atual = float(saldo_atual)
        
        # 🔧 MARGEM FIXA: Sempre 5.0 USDT independente do saldo
        margem = risk_margin

        # Busca o preço atual do símbolo
        last_price = float(broker.get_last_price(symbol) or 0)
        if last_price <= 0:
            print(f"❌ [CALC QTY] Preço inválido para {symbol}", flush=True)
            return 0.0, 0.0, saldo_atual

        # 🔧 FÓRMULA FIXA COM MARGEM E ALAVANCAGEM
        # Qty = (Margem Fixa × Alavancagem) / Preço Atual
        # Qty = (5.0 × 20) / Preço Atual = 100 / Preço Atual
        qty = (margem * leverage_value) / last_price

        print(f"   💰 [CALC QTY] Saldo Atual (BYBIT V5): ${saldo_atual:.2f} USDT", flush=True)
        print(f"   💰 [CALC QTY] Margem Fixa: ${margem:.2f} USDT (conforme MARGEM_INPUT)", flush=True)
        print(f"   📊 [CALC QTY] Preço: ${last_price:.4f} | Alavancagem: {leverage_value}x", flush=True)
        print(f"   🔢 [CALC QTY] Qty calculada: {qty:.6f} (Fórmula: {margem:.2f} × {leverage_value} / {last_price:.4f})", flush=True)

        # Normaliza com as precisões da exchange
        try:
            qty = float(broker.exchange.amount_to_precision(symbol, qty))
            print(f"   ✅ [CALC QTY] Qty normalizada: {qty}", flush=True)
        except Exception as precision_err:
            print(f"   ⚠️ [CALC QTY] Erro na precisão, usando arredondamento simples: {precision_err}", flush=True)
            qty = round(qty, 3)

        return round(margem, 2), qty, saldo_atual
    except Exception as calc_err:
        print(f"❌ [CALC QTY] Erro no cálculo: {calc_err}", flush=True)
        return 0.0, 0.0, banca if banca and banca > 0 else 1000.0


def _calculate_paper_order_quantity(symbol, entry_price, banca=None):
    """
    Calcula quantidade para PAPER TRADE local (sem API externa).
    Fórmula fixa: Qty = (MARGEM_INPUT × ALAVANCAGEM) / entry_price.
    """
    try:
        entry = float(entry_price or 0.0)
        if entry <= 0:
            return 0.0, 0.0, float(banca or _get_forced_training_fake_balance_usd())
        margem = float(MARGEM_INPUT)
        qty = (margem * float(ALAVANCAGEM)) / entry
        qty = round(float(qty), 6)
        saldo_ref = float(banca or _get_forced_training_fake_balance_usd())
        return round(margem, 2), qty, saldo_ref
    except Exception:
        return 0.0, 0.0, float(banca or _get_forced_training_fake_balance_usd())

def _is_order_execution_enabled(client_context):
    """
    Verifica se a execução de ordens está habilitada no sistema.
    """
    return ALLOW_ORDER_EXECUTION and ALLOW_REAL_TRADING

def broadcast_ordem_global(symbol, side, entry_price, res_ia):
    slot_reserved = False
    try:
        if not _reserve_signal_slot(symbol): return
        slot_reserved = True
        signal_snapshot = _build_last_sniper_signal(symbol, side, entry_price, res_ia.get('probabilidade', 70), res_ia.get('motivo', ''))
        central_state['last_sniper_signal'] = signal_snapshot
        central_state['symbol'] = signal_snapshot.get('symbol', central_state.get('symbol', '---'))
        central_state['confidence'] = signal_snapshot.get('confidence', central_state.get('confidence', 0))
        _push_recent_sniper_signal(signal_snapshot)
        
        threading.Thread(
            target=_process_client_orders_background,
            args=(symbol, side, entry_price, res_ia.get('probabilidade', 70), res_ia.get('motivo', '')),
            daemon=True
        ).start()
    finally:
        if slot_reserved: _release_signal_slot(symbol)

def sniper_worker_loop():
    time.sleep(1)
    from src.engine.indicators import IndicatorEngine
    from src.ai_brain.validator import GroqValidator
    global _FORCED_SIGNAL_FIRED

    while True:
        try:
            _repair_open_trades()
            _calcular_pnl_trades()
            _refresh_real_balance_state()
            _sync_active_trades_from_db()

            if len(central_state['active_trades']) >= MAX_MOEDAS_ATIVAS:
                time.sleep(15)
                continue

            active_clients = _get_registered_clients(active_only=True)
            if not active_clients:
                time.sleep(10)
                continue

            has_paper_clients = any(
                _is_training_fake_balance_client(c)
                for c in active_clients
            )
            _, key, sec = _get_active_investor_bybit_credentials()
            has_real_credentials = bool(key and sec)

            # Permite varredura também no modo PAPER (TESTE local),
            # sem exigir cliente real autenticado.
            if not has_real_credentials and not has_paper_clients:
                time.sleep(10)
                continue
            # RADAR/ANÁLISE: usa sempre Mainnet (dados reais), mesmo quando USE_TESTNET=True
            # para execução de ordens (Testnet).
            radar_broker = _get_public_radar_broker_mainnet()
            if radar_broker is None:
                central_state['status'] = "💼 Sem investidores Bybit ativos para varredura."
                time.sleep(10)
                continue
            try:
                tickers = radar_broker.exchange.fetch_tickers(params={'category': 'linear'}) or {}
            except Exception:
                tickers = {}

            radar_candidates = []
            for t in (tickers.values() if isinstance(tickers, dict) else []):
                sym = str((t or {}).get('symbol') or '').strip()
                if not sym:
                    continue
                if 'USDT' not in sym:
                    continue
                radar_candidates.append(t)

            top_coins = sorted(
                radar_candidates,
                key=lambda x: _coerce_float((x or {}).get('quoteVolume'), (x or {}).get('baseVolume'), default=0.0),
                reverse=True,
            )[:SCAN_TOP_COINS]

            validator = GroqValidator()

            # Alimenta o card RADAR LIVE imediatamente com a primeira moeda do radar.
            positions_empty = len(central_state.get('active_trades') or []) == 0
            force_testnet_bypass = bool((USE_TESTNET or has_paper_clients) and positions_empty)
            if top_coins:
                central_state['symbol'] = _limpar_simbolo((top_coins[0] or {}).get('symbol'))
                if not central_state.get('last_sniper_signal'):
                    central_state['confidence'] = 0
            else:
                central_state['symbol'] = '---'
                if not central_state.get('last_sniper_signal'):
                    central_state['confidence'] = 0

            # BYPASS (MECANISMO DE DEBUG):
            # Em Testnet, sem posições abertas, não espera "sinal institucional perfeito".
            # Força 1 ordem imediata na Testnet para validar TP(+100%)/SL(-50%) e o pipeline de execução.
            if (USE_TESTNET or has_paper_clients) and top_coins and (not _FORCED_SIGNAL_FIRED) and (FORCAR_SINAL_TESTE or force_testnet_bypass):
                t = top_coins[0]
                sym = (t or {}).get('symbol')
                if sym:
                    side = 'buy' if int(time.time()) % 2 == 0 else 'sell'
                    decisao = 'COMPRAR' if side == 'buy' else 'VENDER'
                    entry_price = 0.0
                    try:
                        df = radar_broker.fetch_ohlcv(sym, timeframe='15m')
                        if df is not None and len(df) > 0:
                            signals = IndicatorEngine(df).get_signals()
                            entry_price = float(signals.get('price') or 0.0)
                    except Exception:
                        entry_price = 0.0
                    if entry_price <= 0:
                        try:
                            entry_price = float((radar_broker.exchange.fetch_ticker(sym) or {}).get('last') or 0.0)
                        except Exception:
                            entry_price = 0.0

                    if entry_price > 0:
                        central_state['symbol'] = _limpar_simbolo(sym)
                        central_state['confidence'] = 98
                        res = {
                            "probabilidade": 98,
                            "decisao": decisao,
                            "motivo": "TESTNET BYPASS: ordem de debug (ignora filtros SMC/Volume/IA) para validar execução/TP/SL",
                        }
                        broadcast_ordem_global(sym, side, entry_price, res)
                        _FORCED_SIGNAL_FIRED = True
                        time.sleep(COOLDOWN_INSTITUCIONAL_SECS)
                        continue

            for t in top_coins:
                sym = t['symbol']
                df = radar_broker.fetch_ohlcv(sym, timeframe='15m')
                if df is None or len(df) < 200: continue
                
                signals = IndicatorEngine(df).get_signals()
                if signals['trend'] == 'NEUTRO' or validator.local_signal(signals) < 25: continue
                
                res = validator.consensus_predict(signals, sym, force_local_only=True)
                prob = float(res.get('probabilidade', 0))
                decisao = str(res.get('decisao', 'ABORTAR')).upper()
                brain_logs = res.get('brain_logs') or {}
                brain1_log = str(brain_logs.get('brain1') or (
                    f"[CÉREBRO 1] Tendência Macro identificada: {signals.get('trend')}."
                ))
                brain2_log = str(brain_logs.get('brain2') or (
                    "[CÉREBRO 2] Aguardando validação de volume/sweep institucional."
                ))
                print(brain1_log, flush=True)
                print(brain2_log, flush=True)

                if decisao in ('BUY', 'COMPRAR'):
                    print(
                        f"[CÉREBRO 1] Price={float(signals.get('price') or 0.0):.6f} | "
                        f"OrderBlockBull={bool(signals.get('bullish_order_block'))}",
                        flush=True
                    )
                elif decisao in ('SELL', 'VENDER'):
                    print(
                        f"[CÉREBRO 1] Price={float(signals.get('price') or 0.0):.6f} | "
                        f"OrderBlockBear={bool(signals.get('bearish_order_block'))}",
                        flush=True
                    )
                central_state['symbol'] = _limpar_simbolo(sym)
                central_state['confidence'] = round(prob, 2)

                if prob >= THRESHOLD_ENTRADA and decisao in ['COMPRAR', 'VENDER', 'BUY', 'SELL']:
                    broadcast_ordem_global(sym, 'buy' if decisao in ('BUY', 'COMPRAR') else 'sell', float(signals['price']), res)
                    time.sleep(COOLDOWN_INSTITUCIONAL_SECS)
                    break
                time.sleep(SCAN_INTER_SYMBOL_DELAY_SECS)
        except Exception:
            pass
        finally:
            gc.collect()
        time.sleep(15)

def _process_client_orders_background(symbol, side, entry_price, confidence, reason):
    """ Loop assíncrono com salvamento local e disparo protegido anti-400 do Telegram """
    try:
        # 1. DUALIDADE DE CONFIGURAÇÃO (FALLBACK DO BANCO)
        # Primeiro tenta ler do .env, depois fallback para variáveis do banco
        tk = f"{os.getenv('TELEGRAM_TOKEN') or ''}".strip()
        chat = f"{os.getenv('TELEGRAM_CHAT_ID') or ''}".strip()

        clientes = _get_registered_clients(active_only=True)

        for c in clientes:
            try:
                client_id = int(c.get('id') or 0)
                if _is_training_fake_balance_client(c):
                    symbol_norm = _canonicalize_symbol(symbol)
                    sim_entry_price = float(_get_live_market_price(symbol_norm, preferred_price=entry_price) or 0.0)
                    margem, qty, saldo_atualizado = _calculate_paper_order_quantity(
                        symbol_norm,
                        sim_entry_price,
                        banca=float(c.get('saldo_base', _get_forced_training_fake_balance_usd()) or _get_forced_training_fake_balance_usd()),
                    )
                    if qty <= 0 or sim_entry_price <= 0:
                        print(
                            f"   ⚠️ [PAPER] Cliente {c.get('nome')} sem preço válido para simular ordem em {symbol_norm}",
                            flush=True,
                        )
                        continue

                    side_label = 'COMPRAR' if side.lower() in ('buy', 'comprar') else 'VENDER'
                    db.record_trade(
                        client_id=client_id,
                        pair=symbol_norm,
                        side=side_label,
                        pnl_pct=0.0,
                        profit=0.0,
                        closed_at=time.strftime("%d/%m %H:%M"),
                        notes="PAPER_TRADE_LOCAL",
                        status="open",
                        entry_price=sim_entry_price,
                        exit_price=0.0,
                        quantity=qty,
                        margin=margem,
                    )
                    print(
                        f"   🧪 [PAPER] Ordem virtual aberta para {c.get('nome')} | {symbol_norm} | {side_label} | "
                        f"entry=${sim_entry_price:.4f} | qty={qty} | margem=${margem:.2f}",
                        flush=True,
                    )
                    _sync_active_trades_from_db()
                    continue
                if _is_client_temporarily_disabled(client_id):
                    print(f"   ⚠️ [EXEC] Cliente {c.get('nome')} desativado por autenticação — ignorando execução de ordens", flush=True)
                    continue

                # Fallback dinâmico: se .env estiver vazio, busca do dicionário do cliente
                # CORREÇÃO: campos corretos do banco são 'tg_token', 'tg_api_key' e 'chat_id'
                client_tk = tk or f"{c.get('tg_token') or c.get('tg_api_key') or c.get('telegram_token') or c.get('token_telegram') or ''}".strip()
                client_chat = chat or f"{c.get('chat_id') or c.get('telegram_chat_id') or ''}".strip()

                broker = _make_broker(c)
                banca = float(c.get('saldo_base', 1000.0))

                # 🔒 CORREÇÃO MODO CONSERVADOR: Bloqueia nova entrada se já houver posição aberta
                if RISK_MODE == 'conservative':
                    try:
                        # Verifica quantas posições reais o cliente tem abertas na Bybit
                        if broker.pybit_session and broker.authenticated:
                            positions_response = broker.pybit_session.get_positions(
                                category='linear',
                                settleCoin='USDT'
                            )
                            ok, err = broker._handle_v5_ret_code(positions_response, 'get_positions')

                            if ok:
                                positions_list = (positions_response.get('result') or {}).get('list', [])
                                open_positions_count = sum(1 for pos in positions_list if float(pos.get('size') or 0) > 0)

                                if open_positions_count >= 1:
                                    print(f"   🔒 [CONSERVADOR] Cliente {c.get('nome')} já tem {open_positions_count} posição(ões) aberta(s). Bloqueando nova entrada.", flush=True)
                                    continue  # Pula para o próximo cliente
                            else:
                                print(f"   ⚠️ [CONSERVADOR] Erro ao verificar posições para {c.get('nome')}: {err}", flush=True)
                    except Exception as pos_check_err:
                        print(f"   ⚠️ [CONSERVADOR] Exceção ao verificar posições: {pos_check_err}", flush=True)

                # 🔥 CORREÇÃO 1: Busca saldo atual da Bybit e calcula margem dinamicamente
                margem, qty, saldo_atualizado = _calculate_dynamic_order_quantity(broker, symbol, banca)

                if qty > 0 and _is_order_execution_enabled(None):
                    # 🔧 CONFIGURAÇÃO AUTOMÁTICA DE ALAVANCAGEM (VARIÁVEL)
                    # Define alavancagem conforme ALAVANCAGEM global antes de enviar ordem
                    if broker.pybit_session:
                        try:
                            v5_symbol = broker._normalize_v5_symbol(symbol)
                            leverage_str = str(ALAVANCAGEM)
                            rsp_leverage = broker.pybit_session.set_leverage(
                                category='linear',
                                symbol=v5_symbol,
                                buyLeverage=leverage_str,
                                sellLeverage=leverage_str
                            )
                            ok, err = broker._handle_v5_ret_code(rsp_leverage, 'set_leverage')
                            if ok or 'leverage not modified' in err.lower():
                                print(f"   ✅ [LEVERAGE] {v5_symbol} configurado para {ALAVANCAGEM}x", flush=True)
                            else:
                                print(f"   ⚠️ [LEVERAGE] Aviso ao definir alavancagem: {err}", flush=True)
                        except Exception as lev_err:
                            # Ignora erros se moeda já estiver na alavancagem desejada
                            print(f"   ⚠️ [LEVERAGE] Erro ao configurar para {ALAVANCAGEM}x (pode já estar neste valor): {lev_err}", flush=True)

                    order_result = broker.execute_market_order(symbol, side.lower(), qty, raise_on_error=True)
                    if order_result:
                        order_id = order_result.get('id', order_result.get('orderId', 'N/A'))
                        side_label = 'COMPRAR' if side.lower() in ('buy', 'comprar') else 'VENDER'

                        # 🔥 CORREÇÃO 2: Armazena margem, quantidade e saldo para cálculo posterior de P&L
                        db.record_trade(
                            client_id=c.get('id', 1), 
                            pair=symbol, 
                            side=side_label, 
                            pnl_pct=0,
                            profit=0.0,  # Será calculado ao fechar
                            closed_at=time.strftime("%d/%m %H:%M"),
                            notes=f"AUTO SNIPER | ID: {order_id}", 
                            status="open", 
                            entry_price=entry_price,
                            exit_price=0.0,
                            quantity=qty,
                            margin=margem
                        )

                        broker.set_tp_sl_sniper(symbol, side.lower(), entry_price, qty)

                        # 2. DEPURAÇÃO ATIVA + 3. HIGIENIZAÇÃO DE ENVIO
                        if client_tk and client_chat:
                            msg_tg = (
                                f"🔥 OPERACAO REAL EXECUTADA\n\n"
                                f"👤 Investidor: {c.get('nome')}\n"
                                f"📦 Ativo: {symbol}\n"
                                f"📈 Direcao: {side_label}\n"
                                f"📊 Lote: {qty}\n"
                                f"💰 Margem Separada: ${margem:.2f} USDT\n"
                                f"💼 Saldo Atualizado: ${saldo_atualizado:.2f} USDT\n"
                                f"🆔 Hash ID: {order_id}"
                            )
                            try:
                                # Higienização: limpa espaços e converte chat_id numérico para int
                                clean_chat = str(client_chat).strip()
                                if clean_chat.isdigit():
                                    clean_chat = int(clean_chat)

                                requests.post(
                                    f"https://api.telegram.org/bot{client_tk}/sendMessage",
                                    json={"chat_id": clean_chat, "text": msg_tg},
                                    timeout=5
                                )
                                print(f"✅ [TELEGRAM] Notificação enviada com sucesso para {c.get('nome')} (chat_id: {clean_chat})", flush=True)
                            except Exception as tg_err:
                                print(f"❌ [TELEGRAM ERROR] Falha ao enviar notificação para {c.get('nome')}: {tg_err}", flush=True)
            except Exception as client_err:
                print(f"⚠️ [CLIENT ERROR] Falha ao processar ordem para cliente {c.get('nome', 'Unknown')}: {client_err}", flush=True)
    except Exception as general_err:
        print(f"❌ [PROCESS ERROR] Erro geral no processamento de ordens: {general_err}", flush=True)

# ==============================================================================
# 🎛️ ENDPOINTS DA API REST (FLASK)
# ==============================================================================

def _safe_fetch_active_client_balances(timeout_seconds: float = 6.0):
    """
    Evita travar a API de investidores quando monitor/corretora estiver lento.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_fetch_active_client_balances)
        try:
            return future.result(timeout=float(timeout_seconds)) or {'items': []}
        except FutureTimeoutError:
            future.cancel()
            cached = central_state.get('real_client_balances') or []
            return {'items': cached if isinstance(cached, list) else []}
        except Exception:
            return {'items': []}

@app.route('/api/investidores', methods=['GET'])
def get_investidores():
    try:
        rows = _get_registered_clients(active_only=False)
        balance_map = {item.get('id'): item for item in _safe_fetch_active_client_balances(timeout_seconds=6.0).get('items', [])}
        payload = []
        for r in rows:
            client_id = int(r.get('id') or 0)
            bm = balance_map.get(r.get('id')) or {}
            balance_source = _normalize_balance_source(r.get('balance_source'))
            payload.append({
                "id": r.get('id'),
                "nome": r.get('nome'),
                "banca": bm.get('saldo_real', r.get('saldo_base', 0)),
                "saldo_real": bm.get('saldo_real'),
                "saldo_configurado": r.get('saldo_base', 0),
                "status": r.get('status'),
                "mode": "REAL",
                "account_mode": "real",
                "is_testnet": _resolve_request_is_testnet(r, fallback=False),
                "balance_source": balance_source,
                "is_fake_balance": bool(bm.get('is_fake_balance')) or balance_source == 'training_fake_balance',
                "error": bm.get('error'),
                "auth_disabled": _is_client_temporarily_disabled(client_id),
                "auth_disabled_reason": _get_client_disable_reason(client_id),
                "storage_source": "local",
                "exchange": "bybit",
            })
        return jsonify(payload), 200
    except Exception: return jsonify([]), 200

@app.route('/api/investidores/alternar_modo', methods=['POST'])
def api_investidores_alternar_modo():
    try:
        data = request.json or {}
        investor_id = int(data.get('investidor_id') or data.get('investor_id') or data.get('id') or 0)
        novo_modo = str(data.get('novo_modo') or data.get('mode') or '').strip().lower()
        if investor_id <= 0:
            return jsonify({"success": False, "error": "investidor_id inválido"}), 400
        if novo_modo not in ('real', 'teste'):
            return jsonify({"success": False, "error": "novo_modo deve ser 'real' ou 'teste'"}), 400

        existing = _get_registered_client_by_id(investor_id)
        if not existing:
            return jsonify({"success": False, "error": "Investidor não encontrado"}), 404

        updated = dict(existing)
        is_teste = (novo_modo == 'teste')
        updated['is_testnet'] = 1 if is_teste else 0
        updated['account_mode'] = 'real'
        updated['status'] = 'ativo'
        updated['exchange'] = 'bybit'
        updated['balance_source'] = 'training_fake_balance' if is_teste else 'broker_real_balance'
        if is_teste:
            updated['saldo_base'] = round(float(_get_forced_training_fake_balance_usd()), 2)

        ok = db.update_client(investor_id, updated)
        if not ok:
            return jsonify({"success": False, "error": "Falha ao atualizar modo do investidor"}), 500

        # Limpa cache/runtime deste cliente para sincronizar monitor na próxima varredura.
        client_balance_cache.clear()
        _get_broker_manager().invalidate_client(investor_id)
        with _CLIENT_AUTH_LOCK:
            _CLIENT_AUTH_RUNTIME.pop(int(investor_id), None)

        return jsonify({
            "success": True,
            "status": "ok",
            "investidor_id": investor_id,
            "novo_modo": novo_modo,
            "is_testnet": bool(updated.get('is_testnet')),
            "client": _get_registered_client_by_id(investor_id),
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/vincular_cliente', methods=['POST'])
def add_cliente():
    data = request.json or {}
    try:
        requested_is_testnet = _resolve_request_is_testnet(data, fallback=False)
        validation = validar_e_salvar_cliente(data.get('bybit_key'), data.get('bybit_secret'), requested_is_testnet, client_payload=data)
        if validation.get('record'):
            is_valid = bool(validation.get("valid"))
            return jsonify({
                "status": "sucesso" if is_valid else "erro",
                "msg": validation.get("msg") or "Investidor conectado!",
                "valid": is_valid,
                "api_error": validation.get("api_error"),
                "client": validation.get('record'),
            }), (200 if is_valid else 400)
        return jsonify({"status": "erro", "msg": "Falha ao salvar investidor"}), 500
    except Exception as e:
        return jsonify({"status": "erro", "msg": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        _repair_open_trades()
        _refresh_real_balance_state()
        _sync_active_trades_from_db()
        _refresh_last_sniper_signal()
        central_state['trades'] = db.get_recent_trades(20)
        return jsonify(_build_api_status_payload()), 200
    except Exception:
        return jsonify(_build_api_status_payload()), 200

@app.route('/api/dashboard/balance', methods=['GET'])
def update_dashboard_balance():
    try:
        _refresh_real_balance_state(force=True)
        return jsonify({"balance": central_state['balance'], "status": central_state['status'], "real_client_balances": central_state.get('real_client_balances', [])}), 200
    except Exception as e: return jsonify({"balance": 0.0, "status": f"Erro: {e}"}), 200

@app.route('/api/cliente/<int:client_id>', methods=['GET', 'PUT', 'DELETE'])
def api_cliente_manage(client_id):
    try:
        if request.method == 'GET':
            c = _get_registered_client_by_id(client_id)
            return jsonify(c) if c else (jsonify({"error": "Não encontrado"}), 404)
        elif request.method == 'PUT':
            data = request.json or {}
            existing = _get_registered_client_by_id(client_id)
            requested_is_testnet = _resolve_request_is_testnet(
                data,
                fallback=_resolve_request_is_testnet(existing or {}, fallback=False),
            )
            v = validar_e_salvar_cliente(data.get('bybit_key'), data.get('bybit_secret'), requested_is_testnet, client_payload=data, client_id=client_id, existing_client=existing)
            is_valid = bool(v.get('valid'))
            return jsonify({
                "success": is_valid,
                "valid": is_valid,
                "api_error": v.get('api_error'),
                "msg": v.get('msg'),
                "client": v.get('record')
            }), (200 if is_valid else 400)
        elif request.method == 'DELETE':
            # Remoção local blindada para evitar deadlock e travamento do frontend.
            _get_broker_manager().invalidate_client(client_id)
            with _CLIENT_AUTH_LOCK:
                _CLIENT_AUTH_RUNTIME.pop(int(client_id), None)
            client_balance_cache.clear()
            public_price_brokers.clear()
            success = _delete_client_sqlite_fast(client_id)
            return jsonify({
                "success": bool(success),
                "status": "ok" if success else "error",
                "client_id": int(client_id),
            }), 200
    except Exception as e:
        return jsonify({"success": False, "status": "error", "error": str(e), "client_id": int(client_id)}), 200

@app.route('/api/cliente/<int:client_id>/balance-source', methods=['POST'])
def api_cliente_balance_source(client_id):
    try:
        data = request.json or {}
        balance_source = _normalize_balance_source(data.get('balance_source'))
        existing = _get_registered_client_by_id(client_id)
        if not existing:
            return jsonify({"success": False, "error": "Não encontrado"}), 404

        existing['balance_source'] = balance_source
        ok = db.update_client(int(client_id), existing)
        client_balance_cache.clear()
        if ok:
            with _CLIENT_AUTH_LOCK:
                _CLIENT_AUTH_RUNTIME.pop(int(client_id), None)
            return jsonify({"success": True, "client": _get_registered_client_by_id(client_id)}), 200
        return jsonify({"success": False, "error": "Falha ao atualizar"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/trade/manual-entry', methods=['POST'])
def api_manual_entry_trade():
    return jsonify({
        "success": False,
        "error": "Entrada manual desativada nesta versão (Bybit-only sem teste manual)."
    }), 410

@app.route('/api/trade/manual-close', methods=['POST'])
def api_manual_close_trade():
    """Endpoint para fechar posições manualmente via interface web"""
    try:
        data = request.json or {}
        symbol = _canonicalize_symbol(data.get('symbol', '').strip())
        side = data.get('side', '').strip().upper()
        client_id = data.get('client_id')

        if not symbol:
            return jsonify({"success": False, "error": "Símbolo é obrigatório"}), 400

        if side and side not in ['BUY', 'SELL', 'COMPRAR', 'VENDER', 'LONG', 'SHORT']:
            return jsonify({"success": False, "error": "Lado inválido. Use: BUY, SELL, LONG ou SHORT"}), 400

        # Normaliza o lado da posição (quando ausente, tenta ambos os lados)
        if not side:
            position_sides = ['buy', 'sell']
        elif side in ['BUY', 'COMPRAR', 'LONG']:
            position_sides = ['buy']
        else:
            position_sides = ['sell']

        # Se client_id foi especificado, fecha apenas para esse cliente
        if client_id:
            client = _get_registered_client_by_id(client_id)
            if not client:
                return jsonify({"success": False, "error": f"Cliente ID {client_id} não encontrado"}), 404
            clients_to_close = [client]
        else:
            # Senão, fecha para todos os clientes ativos
            clients_to_close = _get_registered_clients(active_only=True)

        if not clients_to_close:
            return jsonify({"success": False, "error": "Nenhum cliente ativo encontrado"}), 404

        results = []
        normalized_symbol = _normalize_symbol_key(symbol)
        for c in clients_to_close:
            try:
                broker = _make_broker(c)
                success = False
                used_symbol = symbol
                for position_side in position_sides:
                    for symbol_candidate in [symbol, _limpar_simbolo(symbol)]:
                        if not symbol_candidate:
                            continue
                        success = broker.close_position_with_sl(symbol_candidate, position_side)
                        if success:
                            used_symbol = symbol_candidate
                            print(f"✅ [MANUAL CLOSE] Fechamento confirmado no lado {position_side.upper()} para {symbol_candidate}", flush=True)
                            break
                    if success:
                        break

                if success:
                    # Busca o trade aberto correspondente no banco e fecha
                    open_trades = db.get_open_trades(limit=100)
                    for trade in open_trades:
                        trade_canonical = _canonicalize_symbol(trade.get('pair'))
                        if not trade_canonical:
                            continue
                        trade_symbol = _normalize_symbol_key(trade_canonical)
                        if (trade.get('client_id') == c.get('id') and
                            trade_symbol == normalized_symbol and
                            trade.get('status') == 'open'):
                            
                            # 🔥 CORREÇÃO 2: Busca o preço de fechamento e calcula P&L correto
                            current_price = broker.get_last_price(used_symbol) or 0
                            entry_price = float(trade.get('entry_price', 0))
                            qty = float(trade.get('quantity', 0))
                            side = str(trade.get('side', '')).upper()
                            
                            # Calcula P&L baseado no tipo de posição
                            if qty > 0 and entry_price > 0 and current_price > 0:
                                if side in ('VENDER', 'SELL', 'SHORT'):
                                    # SHORT: Lucro = (Preço de Entrada - Preço de Saída) * Quantidade
                                    profit = (entry_price - current_price) * qty
                                else:
                                    # LONG: Lucro = (Preço de Saída - Preço de Entrada) * Quantidade
                                    profit = (current_price - entry_price) * qty
                            else:
                                profit = 0.0
                            
                            # Fecha o trade com P&L calculado
                            db.close_trade(
                                trade_id=trade.get('id'),
                                pnl_pct=0.0,
                                profit=profit,
                                exit_price=current_price,
                                closed_at=time.strftime("%d/%m %H:%M"),
                                notes="FECHAMENTO MANUAL",
                                entry_price=entry_price,
                                quantity=qty,
                                side=side
                            )

                            # 🧠 Registra na trade_history com PnL líquido real da API V5
                            try:
                                from src.trade_history import record_closed_trade_sync
                                _manual_direction = 'SELL' if side in ('VENDER', 'SELL', 'SHORT') else 'BUY'
                                record_closed_trade_sync(
                                    pybit_session=broker.pybit_session,
                                    asset=used_symbol,
                                    direction=_manual_direction,
                                    entry_price=entry_price,
                                    stop_loss=0.0,
                                    take_profit=0.0,
                                    exit_price=current_price,
                                    exit_reason='MANUAL',
                                    gross_pnl=round(profit, 4),
                                    market_context={
                                        'quantity': qty,
                                        'close_source': 'manual_endpoint',
                                    },
                                    client_id=int(c.get('id') or 0),
                                    trade_db_id=int(trade.get('id') or 0),
                                )
                            except Exception as th_err:
                                print(f"   ⚠️ [TRADE HISTORY] Erro ao salvar histórico manual: {th_err}", flush=True)
                    _sync_active_trades_from_db()

                    results.append({
                        "client_id": c.get('id'),
                        "client_name": c.get('nome'),
                        "success": True,
                        "message": f"Posição fechada com sucesso ({used_symbol})"
                    })
                    print(f"✅ [MANUAL CLOSE] Posição {used_symbol} fechada para {c.get('nome')}", flush=True)
                else:
                    results.append({
                        "client_id": c.get('id'),
                        "client_name": c.get('nome'),
                        "success": False,
                        "message": f"Falha ao fechar posição {symbol} - verifique se existe posição aberta"
                    })
            except Exception as client_err:
                results.append({
                    "client_id": c.get('id'),
                    "client_name": c.get('nome'),
                    "success": False,
                    "error": str(client_err)
                })
                print(f"❌ [MANUAL CLOSE ERROR] Erro ao fechar para {c.get('nome')}: {client_err}", flush=True)

        success_count = sum(1 for r in results if r.get('success'))
        return jsonify({
            "success": success_count > 0,
            "message": f"{success_count}/{len(results)} posições fechadas com sucesso",
            "results": results
        }), 200

    except Exception as e:
        print(f"❌ [MANUAL CLOSE] Erro geral: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/config/risk-mode', methods=['GET', 'POST'])
def handle_risk_mode():
    global RISK_MODE, MAX_MOEDAS_ATIVAS
    if request.method == 'GET': return jsonify({"risk_mode": RISK_MODE, "max_moedas_ativas": MAX_MOEDAS_ATIVAS})
    data = request.json or {}
    mode = str(data.get('mode', 'conservative')).strip().lower()
    RISK_MODE = mode
    MAX_MOEDAS_ATIVAS = 1 if mode == 'conservative' else 5
    central_state['risk_mode'] = RISK_MODE; central_state['max_moedas_ativas'] = MAX_MOEDAS_ATIVAS
    db.set_config('RISK_MODE', RISK_MODE)
    return jsonify({"success": True, "risk_mode": RISK_MODE, "max_moedas_ativas": MAX_MOEDAS_ATIVAS})


@app.route('/api/market-intelligence', methods=['GET'])
def api_market_intelligence():
    """
    Endpoint do pipeline de exportação para o Cérebro (IA analista).

    Retorna um payload JSON estruturado com o histórico de operações encerradas,
    métricas agregadas e contexto de mercado para análise preditiva.

    Query params:
        limit (int): Quantidade máxima de trades a retornar (padrão: 100)
    """
    try:
        from src.trade_history import get_market_intelligence_data
        limit = int(request.args.get('limit', 100))
        limit = max(1, min(limit, 500))  # Clamp entre 1 e 500
        payload = get_market_intelligence_data(limit=limit)
        return jsonify({"success": True, "data": payload}), 200
    except Exception as e:
        print(f"❌ [MARKET INTELLIGENCE] Erro ao gerar payload: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500

def _validate_broker_balance_fast_fail(payload: dict, timeout_seconds: float = 5.0):
    """
    Valida credenciais com timeout rígido para evitar request pendente no frontend.
    """
    def _run_validation():
        broker = _make_broker(payload)
        try:
            if hasattr(broker, 'exchange') and getattr(broker, 'exchange') is not None:
                broker.exchange.enableRateLimit = True
                broker.exchange.timeout = int(timeout_seconds * 1000)
        except Exception:
            pass

        # Melhor esforço para limitar chamadas da sessão pybit.
        try:
            pybit = getattr(broker, 'pybit_session', None)
            if pybit is not None:
                if hasattr(pybit, 'timeout'):
                    pybit.timeout = int(timeout_seconds)
                if hasattr(pybit, 'recv_window'):
                    pybit.recv_window = min(int(getattr(pybit, 'recv_window', 5000) or 5000), 5000)
        except Exception:
            pass

        return broker, broker.get_balance()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_validation)
        try:
            broker, balance = future.result(timeout=float(timeout_seconds))
            return broker, balance
        except FutureTimeoutError:
            future.cancel()
            raise RuntimeError(
                f"Timeout ao validar credenciais ({int(timeout_seconds)}s). "
                "A corretora não respondeu a tempo, tente novamente."
            )

def validar_e_salvar_cliente(api_key, api_secret, is_testnet, *, client_payload=None, client_id=None, existing_client=None):
    payload = dict(client_payload or {})
    existing_is_testnet = _resolve_request_is_testnet(existing_client or {}, fallback=False)
    requested_is_testnet = _resolve_request_is_testnet(payload, fallback=_coerce_bool(is_testnet, default=existing_is_testnet))
    final_is_testnet = requested_is_testnet
    payload['account_mode'], payload['is_testnet'] = 'real', final_is_testnet
    payload['balance_source'] = _normalize_balance_source(payload.get('balance_source'))
    payload['exchange'] = 'bybit'
    if client_id is not None: payload['id'] = client_id
    if api_key: payload['bybit_key'] = api_key
    if api_secret: payload['bybit_secret'] = api_secret
    if existing_client is not None and 'nome' not in payload: payload['nome'] = existing_client.get('nome')

    try:
        # Versão de simulação local pura: TESTE não depende de API externa.
        if final_is_testnet:
            fake = float(payload.get('saldo_base') or 0) or _get_forced_training_fake_balance_usd()
            payload['saldo_base'] = round(float(fake), 2)
            payload['status'] = 'ativo'
            payload['balance_source'] = 'training_fake_balance'
            record, _, local_synced = _save_client_everywhere(payload)
            return {
                'valid': True,
                'msg': 'Modo TESTE local ativo (simulação sem conexão de exchange).',
                'record': record,
                'synced_to_local': local_synced,
                'balance': payload['saldo_base'],
                'account_mode': 'real',
                'exchange': payload['exchange'],
                'balance_source': payload.get('balance_source'),
                'is_testnet': final_is_testnet,
            }

        if payload.get('balance_source') == 'training_fake_balance':
            fake = float(payload.get('saldo_base') or 0) or _get_forced_training_fake_balance_usd()
            payload['saldo_base'] = round(float(fake), 2)
            payload['status'] = 'ativo'
            record, _, local_synced = _save_client_everywhere(payload)
            return {
                'valid': True,
                'msg': 'Modo teste de saldo fictício ativo',
                'record': record,
                'synced_to_local': local_synced,
                'balance': payload['saldo_base'],
                'account_mode': 'real',
                'exchange': payload['exchange'],
                'balance_source': payload.get('balance_source'),
                'is_testnet': final_is_testnet,
            }

        broker, balance = _validate_broker_balance_fast_fail(payload, timeout_seconds=5.0)
        if balance is None or not getattr(broker, 'authenticated', False):
            raw_msg = str(getattr(broker, 'last_auth_error_message', '') or '').strip()
            raw_code = str(getattr(broker, 'last_auth_error_code', '') or '').strip()
            if raw_code:
                raise RuntimeError(f"Falha na autenticação (retCode={raw_code}): {raw_msg or 'verifique as chaves'}")
            raise RuntimeError(raw_msg or 'Falha ao validar credenciais (saldo indisponível)')

        payload['saldo_base'] = round(float(balance), 2)
        payload['status'] = 'ativo'
        record, _, local_synced = _save_client_everywhere(payload)
        return {
            'valid': True,
            'msg': 'Validado OK',
            'record': record,
            'synced_to_local': local_synced,
            'balance': payload['saldo_base'],
            'account_mode': 'real',
            'exchange': payload['exchange'],
            'balance_source': payload.get('balance_source'),
            'is_testnet': final_is_testnet,
        }
    except Exception as e:
        # Auto-detecção de ambiente para chave Bybit quando usuário seleciona ambiente incorreto.
        err_text = str(e or '')
        if 'retCode=10003' in err_text and str(payload.get('exchange') or 'bybit').strip().lower() == 'bybit':
            flipped_is_testnet = not bool(final_is_testnet)
            probe_payload = dict(payload)
            probe_payload['is_testnet'] = flipped_is_testnet
            try:
                probe_broker, probe_balance = _validate_broker_balance_fast_fail(probe_payload, timeout_seconds=5.0)
                if probe_balance is not None and getattr(probe_broker, 'authenticated', False):
                    payload['is_testnet'] = flipped_is_testnet
                    payload['saldo_base'] = round(float(probe_balance), 2)
                    payload['status'] = 'ativo'
                    record, _, local_synced = _save_client_everywhere(payload)
                    detected_env = 'TESTNET' if flipped_is_testnet else 'MAINNET'
                    return {
                        'valid': True,
                        'msg': f'Chave validada no ambiente {detected_env}. Ambiente ajustado automaticamente.',
                        'record': record,
                        'synced_to_local': local_synced,
                        'balance': payload['saldo_base'],
                        'account_mode': 'real',
                        'exchange': payload['exchange'],
                        'balance_source': payload.get('balance_source'),
                        'is_testnet': flipped_is_testnet,
                    }
            except Exception:
                pass

        payload['status'] = 'erro_api'
        payload['saldo_base'] = round(float((existing_client or {}).get('saldo_base') or 0.0), 2)
        record, _, local_synced = _save_client_everywhere(payload)
        return {
            'valid': False,
            'msg': str(e),
            'api_error': str(e),
            'record': record,
            'synced_to_local': local_synced,
            'balance': payload['saldo_base'],
            'account_mode': 'real',
            'exchange': payload['exchange'],
            'balance_source': payload.get('balance_source'),
            'is_testnet': final_is_testnet,
        }

# ==============================================================================
# 🌍 ROTA PEGA-TUDO DO FRONTEND (OBRIGATORIAMENTE NO FINAL DO ARQUIVO)
# ==============================================================================
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if _frontend_asset_exists(path): return send_from_directory(app.static_folder, path)
    if _frontend_is_built(): return send_from_directory(app.static_folder, 'index.html')
    return jsonify({"status": "DuoIA Maestro API ativa. Painel React em compilação."}), 200

print("⚡ [MAESTRO CORE] Forçando inicialização dos serviços em background...", flush=True)
start_runtime_services()

if __name__ == "__main__":
    render_port = int(os.getenv("PORT", "5000"))
    start_runtime_services()
    app.run(host='0.0.0.0', port=render_port, debug=False, use_reloader=False)
