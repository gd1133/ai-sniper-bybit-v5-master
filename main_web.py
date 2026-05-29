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
import io
import math
from datetime import datetime, timedelta

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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

RUNTIME_START_LOCK = threading.Lock()
RUNTIME_STARTED = False
AI_RATE_LIMIT_STATUS_MESSAGE = '⚠️ Limite das IAs atingido. Aguardando cooldown de 60s...'
AI_COOLDOWN_ACTIVE = False
AI_COOLDOWN_LOCK = threading.Lock()

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
                    if cached_broker.exchange.apiKey == api_key: return cached_broker
                del self._broker_cache[cache_key]

            api_key = str(client.get('bybit_key') or '').strip()
            api_secret = str(client.get('bybit_secret') or '').strip()
            if not api_key or not api_secret: raise RuntimeError(f"Cliente sem credenciais (id={client_id})")

            broker_instance = broker_cls(api_key, api_secret, testnet=testnet)
            self._broker_cache[cache_key] = broker_instance
            return broker_instance

    def invalidate_client(self, client_id):
        with self._cache_lock:
            keys_to_remove = [key for key in self._broker_cache.keys() if f"_{client_id}_" in f"_{key}_"]
            for key in keys_to_remove: del self._broker_cache[key]

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
USE_TESTNET = False
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
    if entry_price <= 0: entry_price = _coerce_float(_get_public_price_broker().get_last_price(symbol), default=0.0)
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

def _get_public_price_broker():
    global BybitClient, public_price_broker
    if public_price_broker is not None: return public_price_broker
    with _public_price_broker_lock:
        if public_price_broker is not None: return public_price_broker
        if BybitClient is None:
            from src.broker.bybit_client import BybitClient as _BybitClient
            BybitClient = _BybitClient
        _, bybit_api_key, bybit_api_secret = _get_active_investor_bybit_credentials()
        if not bybit_api_key or not bybit_api_secret:
            from src.broker.bybit_client import _get_ccxt as _get_ccxt_cached
            class CCXTPublicPriceFallback:
                def __init__(self):
                    self._ccxt_exchange = _get_ccxt_cached().bybit()
                def get_last_price(self, symbol):
                    try: return float(self._ccxt_exchange.fetch_ticker(symbol)['last'])
                    except Exception: return 0.0
                def fetch_ohlcv(self, symbol, timeframe='15m'):
                    try:
                        from src.broker.bybit_client import _get_pd as _get_pd_cached
                        pd = _get_pd_cached()
                        return pd.DataFrame(self._ccxt_exchange.fetch_ohlcv(symbol, timeframe, limit=200), columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
                    except Exception: return None
            return CCXTPublicPriceFallback()
        public_price_broker = BybitClient(bybit_api_key, bybit_api_secret, testnet=False)
    return public_price_broker

def _ensure_broker_class(exchange='bybit'):
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

def _get_registered_clients(active_only=False):
    try: return [{**dict(c), "storage_source": "local"} for c in (db.get_active_clients() if active_only else db.get_all_clients())]
    except Exception: return []

def _get_registered_client_by_id(client_id):
    local_client = db.get_client_by_id(client_id)
    return {**dict(local_client), "storage_source": "local"} if local_client else None

def _get_active_investor_bybit_credentials():
    for client in _get_registered_clients(active_only=True):
        persisted = _get_registered_client_by_id(client.get('id'))
        if persisted:
            k = str(persisted.get('bybit_key') or '').strip()
            s = str(persisted.get('bybit_secret') or '').strip()
            if k and s: return persisted.get('id'), k, s
    return None, '', ''

def _save_client_everywhere(client_data):
    payload = dict(client_data or {})
    payload['account_mode'], payload['is_testnet'], payload['balance_source'] = 'real', False, 'broker_real_balance'
    res = db.upsert_client_local(payload) if payload.get('id') is not None else db.add_client(payload)
    client_balance_cache.clear()
    return _get_registered_client_by_id(payload.get('id') or res), False, bool(res)

def _delete_client_everywhere(client_id):
    _get_broker_manager().invalidate_client(client_id)
    return True, db.delete_client(client_id)

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
    try:
        _ensure_broker_class('bybit')
        _ensure_broker_class('binance')
        for client in _get_registered_clients(active_only=True):
            balance = None
            error = None
            try:
                balance = _make_broker(client).get_balance()
                if balance is not None:
                    balance = round(float(balance), 2)
                    total += balance
            except Exception as e: error = str(e)
            items.append({
                "id": client.get('id'), "nome": client.get('nome'), "saldo_real": balance,
                "saldo_base": float(client.get('saldo_base', 0) or 0), "is_testnet": False,
                "account_mode": "real", "exchange": str(client.get('exchange') or 'bybit').lower(),
                "status": client.get('status'), "error": error,
            })
    except Exception: pass
    
    res = {"items": items, "total": round(total, 2)}
    client_balance_cache.set(res)
    
    # ⚡ CORE FIX: Força sincronização em tempo real do card para o React
    valid_items = [item for item in items if item.get("saldo_real") is not None]
    central_state['real_client_balances'] = items
    if valid_items:
        central_state['balance'] = round(sum(float(i["saldo_real"]) for i in valid_items), 2)
        central_state['status'] = f"💼 CONTA REAL: saldo sincronizado para {len(valid_items)} investidores"
    else:
        central_state['balance'] = 0.0
        central_state['status'] = "💼 CONTA REAL: aguardando pareamento de chaves..."
        
    return res

def _refresh_real_balance_state(force=False):
    _fetch_active_client_balances(force=force)

def _get_live_price_snapshot(symbol, entry_price, side):
    try: return _calculate_live_trade_metrics(entry_price, _get_public_price_broker().get_last_price(symbol), side)
    except Exception: return _calculate_live_trade_metrics(entry_price, 0.0, side)

def _refresh_last_sniper_signal():
    s = central_state.get('last_sniper_signal')
    if s: s.update(_get_live_price_snapshot(s.get('raw_symbol') or s.get('symbol'), s.get('entry_price'), s.get('side')))

def _repair_open_trades():
    try:
        open_trades = db.get_open_trades(100)
        if not open_trades: return
        conn = db._connect(); cur = conn.cursor()
        for t in open_trades:
            canonical = _canonicalize_symbol(t.get('pair'))
            if not canonical or _extract_entry_price(t) <= 0:
                cur.execute("UPDATE trades SET status='closed', pnl_pct=0, closed_at=? WHERE id=?", (time.strftime("%d/%m %H:%M"), t.get('id')))
        conn.commit(); conn.close()
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
    time.sleep(1)
    while True:
        try:
            for t in db.get_open_trades(100):
                live = _get_live_price_snapshot(t.get('pair'), _extract_entry_price(t), t.get('side'))
                pnl_pct = live.get('pnl_pct', 0.0)
                motivo = "SL_AUTO -50%" if pnl_pct <= -50.0 else "TP_AUTO +100%" if pnl_pct >= 100.0 else None
                if motivo:
                    conn = db._connect(); cur = conn.cursor()
                    cur.execute("UPDATE trades SET status='closed', pnl_pct=?, notes=COALESCE(notes,'') || ? WHERE id=?", (round(pnl_pct, 4), f" | {motivo}", t.get('id')))
                    conn.commit(); conn.close()
                    _sync_active_trades_from_db()
        except Exception: pass
        time.sleep(10)

def _monitor_financial_stop_loss():
    """
    🛡️ MONITOR DE STOP LOSS FINANCEIRO V60.7

    Monitora o unrealisedPnl em tempo real de todas as posições abertas.
    Se o prejuízo atingir -50% da margem utilizada, fecha a posição imediatamente
    via ordem a mercado (reduceOnly=True).

    Exemplo:
    - Margem usada: $2.40 USDT
    - Limite de perda: -$1.20 USDT (50% da margem)
    - Quando unrealisedPnl <= -$1.20, dispara fechamento forçado
    """
    time.sleep(5)  # Aguarda inicialização do sistema
    print("🛡️ [MONITOR FINANCEIRO] Iniciado - Stop Loss financeiro ativo (-50% da margem)", flush=True)

    while True:
        try:
            # Busca todos os clientes ativos
            clientes = _get_registered_clients(active_only=True)

            for cliente in clientes:
                try:
                    broker = _make_broker(cliente)

                    # Verifica se tem sessão pybit ativa
                    if not broker.pybit_session or not broker.authenticated:
                        continue

                    # Busca posições abertas do cliente
                    try:
                        positions_response = broker.pybit_session.get_positions(category='linear')
                        ok, err = broker._handle_v5_ret_code(positions_response, 'get_positions')

                        if not ok:
                            continue

                        positions_list = (positions_response.get('result') or {}).get('list', [])

                        for pos in positions_list:
                            try:
                                # Extrai dados da posição
                                symbol = pos.get('symbol', '')
                                size = float(pos.get('size') or 0)
                                side = str(pos.get('side', '')).lower()
                                unrealised_pnl = float(pos.get('unrealisedPnl') or 0)
                                position_value = float(pos.get('positionValue') or 0)
                                leverage = float(pos.get('leverage') or 20)

                                # Pula se não houver posição aberta
                                if size <= 0:
                                    continue

                                # 🔧 CÁLCULO DA MARGEM UTILIZADA
                                # Margem = Valor da Posição / Alavancagem
                                margem_utilizada = position_value / leverage if leverage > 0 else position_value

                                # 🚨 LIMITE DE PERDA: -50% da margem
                                limite_perda = -0.50 * margem_utilizada

                                print(f"   📊 [MONITOR] {symbol} | Size: {size} | unrealisedPnl: ${unrealised_pnl:.2f} | Margem: ${margem_utilizada:.2f} | Limite: ${limite_perda:.2f}", flush=True)

                                # 🔥 CONDIÇÃO DE FECHAMENTO FORÇADO
                                if unrealised_pnl <= limite_perda:
                                    print(f"🚨 [STOP FINANCEIRO] {symbol} atingiu limite de perda!", flush=True)
                                    print(f"   💔 unrealisedPnl: ${unrealised_pnl:.2f} <= Limite: ${limite_perda:.2f}", flush=True)
                                    print(f"   🔒 Disparando fechamento forçado...", flush=True)

                                    # Determina o lado da ordem de fechamento
                                    close_side = 'sell' if side in ('long', 'buy') else 'buy'

                                    # Fecha a posição via ordem a mercado
                                    try:
                                        success = broker.close_position_with_sl(symbol, side)

                                        if success:
                                            print(f"   ✅ [STOP FINANCEIRO] Posição {symbol} fechada com sucesso!", flush=True)

                                            # Atualiza registro no banco de dados
                                            try:
                                                conn = db._connect()
                                                cur = conn.cursor()

                                                # Calcula PnL percentual
                                                pnl_pct = (unrealised_pnl / margem_utilizada * 100) if margem_utilizada > 0 else 0

                                                cur.execute(
                                                    "UPDATE trades SET status='closed', pnl_pct=?, notes=COALESCE(notes,'') || ? WHERE pair=? AND client_id=? AND status='open'",
                                                    (
                                                        round(pnl_pct, 2),
                                                        f" | STOP_FINANCEIRO_AUTO unrealisedPnl=${unrealised_pnl:.2f}",
                                                        symbol,
                                                        cliente.get('id')
                                                    )
                                                )
                                                conn.commit()
                                                conn.close()
                                                print(f"   💾 [BANCO] Trade atualizado no banco de dados", flush=True)
                                            except Exception as db_err:
                                                print(f"   ⚠️ [BANCO] Erro ao atualizar trade: {db_err}", flush=True)

                                            # Sincroniza estado central
                                            _sync_active_trades_from_db()
                                        else:
                                            print(f"   ❌ [STOP FINANCEIRO] Falha ao fechar posição {symbol}", flush=True)

                                    except Exception as close_err:
                                        print(f"   ❌ [STOP FINANCEIRO] Erro ao fechar posição: {close_err}", flush=True)

                            except Exception as pos_err:
                                print(f"   ⚠️ [MONITOR] Erro ao processar posição: {pos_err}", flush=True)
                                continue

                    except Exception as fetch_err:
                        print(f"   ⚠️ [MONITOR] Erro ao buscar posições do cliente {cliente.get('nome')}: {fetch_err}", flush=True)
                        continue

                except Exception as client_err:
                    print(f"   ⚠️ [MONITOR] Erro ao processar cliente {cliente.get('nome', 'Unknown')}: {client_err}", flush=True)
                    continue

        except Exception as general_err:
            print(f"❌ [MONITOR FINANCEIRO] Erro geral: {general_err}", flush=True)

        # Aguarda 5 segundos antes da próxima verificação
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
            margin = float(t.get('profit', 0) or 0)
            entry_price = _extract_entry_price(t)
            if margin <= 0 or entry_price <= 0: continue

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
                    'latest_trade_id': int(t.get('id') or 0),
                }

            trade_group = grouped[key]
            trade_group['entry'] = round(float(trade_group.get('entry', 0) or 0) + margin, 2)
            trade_group['client_count'] += 1
            trade_group['trade_count'] += 1

        central_state['active_trades'] = sorted(grouped.values(), key=lambda x: x.get('latest_trade_id', 0), reverse=True)

        for trade in central_state['active_trades']:
            live = _get_live_price_snapshot(trade.get('raw_symbol') or trade.get('symbol'), trade.get('entry_price'), trade.get('side'))
            trade.update(live)
            entry_margin = float(trade.get('entry', 0) or 0)
            pnl_pct = float(trade.get('pnl_pct', 0) or 0)
            trade['open_pnl_value'] = round((entry_margin * pnl_pct) / 100, 2) if entry_margin else 0.0
    except Exception:
        central_state['active_trades'] = []

def _close_stale_open_trades(max_age_minutes=180):
    try:
        conn = db._connect(); cur = conn.cursor()
        for t in db.get_open_trades(100):
            dt = datetime.fromisoformat(str(t.get('created_at')).replace('Z', ''))
            if (datetime.now() - dt) > timedelta(minutes=max_age_minutes):
                cur.execute("UPDATE trades SET status='closed', notes=COALESCE(notes,'') || ' | STALE' WHERE id=?", (t.get('id'),))
        conn.commit(); conn.close()
    except Exception: pass

def _calculate_dynamic_order_quantity(broker, symbol, banca):
    """
    🎯 GESTÃO ESTRITAMENTE FINANCEIRA V60.7
    Calcula quantidade baseada em:
    - Margem de entrada: 5% da banca atual (ex: $48 → $2.40 USDT)
    - Alavancagem: 20x fixo
    - Fórmula: Qty = (Margem × 20) / Preço Atual

    Retorna (margem_separada, quantidade_normalizada)
    """
    try:
        RISK_PER_TRADE_PCT = 5.0  # 5% da banca por operação
        LEVERAGE = 20  # Alavancagem fixa em 20x

        margem = (banca * RISK_PER_TRADE_PCT) / 100.0

        # Busca o preço atual do símbolo
        last_price = float(broker.get_last_price(symbol) or 0)
        if last_price <= 0:
            print(f"❌ [CALC QTY] Preço inválido para {symbol}", flush=True)
            return 0.0, 0.0

        # 🔧 FÓRMULA CORRETA COM ALAVANCAGEM 20X
        # Qty = (Margem Calculada × 20) / Preço Atual da Moeda
        qty = (margem * LEVERAGE) / last_price

        print(f"   💰 [CALC QTY] Banca: ${banca:.2f} → Margem (5%): ${margem:.2f} USDT", flush=True)
        print(f"   📊 [CALC QTY] Preço: ${last_price:.4f} | Alavancagem: {LEVERAGE}x", flush=True)
        print(f"   🔢 [CALC QTY] Qty calculada: {qty:.6f}", flush=True)

        # Normaliza com as precisões da exchange
        try:
            markets = broker.exchange.load_markets()
            market = markets.get(symbol, {})
            amount_precision = market.get('precision', {}).get('amount', 3)
            qty = broker.exchange.amount_to_precision(symbol, qty)
            qty = float(qty)
            print(f"   ✅ [CALC QTY] Qty normalizada: {qty}", flush=True)
        except Exception as precision_err:
            print(f"   ⚠️ [CALC QTY] Erro na precisão, usando arredondamento simples: {precision_err}", flush=True)
            qty = round(qty, 3)

        return round(margem, 2), qty
    except Exception as calc_err:
        print(f"❌ [CALC QTY] Erro no cálculo: {calc_err}", flush=True)
        return 0.0, 0.0

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
    from src.broker.bybit_client import BybitClient
    from src.engine.indicators import IndicatorEngine
    from src.ai_brain.validator import GroqValidator

    while True:
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

            # Reutiliza broker via BrokerManager (singleton cacheado) em vez de instanciar novo BybitClient
            active_clients = _get_registered_clients(active_only=True)
            if not active_clients:
                time.sleep(10)
                continue
            ex_master = _make_broker(active_clients[0])
            tickers = ex_master.exchange.fetch_tickers(params={'category': 'linear'})
            top_coins = sorted([t for t in tickers.values() if 'USDT' in t.get('symbol', '') and ':' in t['symbol']], key=lambda x: x.get('quoteVolume', 0), reverse=True)[:SCAN_TOP_COINS]
            
            validator = GroqValidator()
            for t in top_coins:
                sym = t['symbol']
                df = ex_master.fetch_ohlcv(sym, timeframe='15m')
                if df is None or len(df) < 200: continue
                
                signals = IndicatorEngine(df).get_signals()
                if signals['trend'] == 'NEUTRO' or validator.local_signal(signals) < 25: continue
                
                res = validator.consensus_predict(signals, sym, force_local_only=True)
                prob = float(res.get('probabilidade', 0))
                decisao = str(res.get('decisao', 'ABORTAR')).upper()

                if prob >= THRESHOLD_ENTRADA and decisao in ['COMPRAR', 'VENDER', 'BUY', 'SELL']:
                    broadcast_ordem_global(sym, 'buy' if decisao in ('BUY', 'COMPRAR') else 'sell', float(signals['price']), res)
                    time.sleep(COOLDOWN_INSTITUCIONAL_SECS)
                    break
                time.sleep(SCAN_INTER_SYMBOL_DELAY_SECS)
        except Exception: pass
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
                # Fallback dinâmico: se .env estiver vazio, busca do dicionário do cliente
                # CORREÇÃO: campos corretos do banco são 'tg_token', 'tg_api_key' e 'chat_id'
                client_tk = tk or f"{c.get('tg_token') or c.get('tg_api_key') or c.get('telegram_token') or c.get('token_telegram') or ''}".strip()
                client_chat = chat or f"{c.get('chat_id') or c.get('telegram_chat_id') or ''}".strip()

                broker = _make_broker(c)
                banca = float(c.get('saldo_base', 1000.0))
                margem, qty = _calculate_dynamic_order_quantity(broker, symbol, banca)

                if qty > 0 and _is_order_execution_enabled(None):
                    # 🔧 CONFIGURAÇÃO AUTOMÁTICA DE ALAVANCAGEM 20X
                    # Define alavancagem para 20x antes de enviar ordem
                    if broker.pybit_session:
                        try:
                            v5_symbol = broker._normalize_v5_symbol(symbol)
                            rsp_leverage = broker.pybit_session.set_leverage(
                                category='linear',
                                symbol=v5_symbol,
                                buyLeverage='20',
                                sellLeverage='20'
                            )
                            ok, err = broker._handle_v5_ret_code(rsp_leverage, 'set_leverage')
                            if ok or 'leverage not modified' in err.lower():
                                print(f"   ✅ [LEVERAGE] {v5_symbol} configurado para 20x", flush=True)
                            else:
                                print(f"   ⚠️ [LEVERAGE] Aviso ao definir alavancagem: {err}", flush=True)
                        except Exception as lev_err:
                            # Ignora erros se moeda já estiver em 20x
                            print(f"   ⚠️ [LEVERAGE] Erro ao configurar (pode já estar em 20x): {lev_err}", flush=True)

                    order_result = broker.execute_market_order(symbol, side.lower(), qty, raise_on_error=True)
                    if order_result:
                        order_id = order_result.get('id', order_result.get('orderId', 'N/A'))
                        side_label = 'COMPRAR' if side.lower() in ('buy', 'comprar') else 'VENDER'

                        db.record_trade(
                            client_id=c.get('id', 1), pair=symbol, side=side_label, pnl_pct=0,
                            profit=round(margem, 2), closed_at=time.strftime("%d/%m %H:%M"),
                            notes=f"AUTO SNIPER | ID: {order_id}", status="open", entry_price=entry_price
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

@app.route('/api/investidores', methods=['GET'])
def get_investidores():
    try:
        rows = _get_registered_clients(active_only=False)
        balance_map = {item.get('id'): item for item in _fetch_active_client_balances().get('items', [])}
        return jsonify([{
            "id": r.get('id'), "nome": r.get('nome'),
            "banca": (balance_map.get(r.get('id')) or {}).get('saldo_real', r.get('saldo_base', 0)),
            "saldo_real": (balance_map.get(r.get('id')) or {}).get('saldo_real'),
            "saldo_configurado": r.get('saldo_base', 0), "status": r.get('status'),
            "mode": "REAL", "account_mode": "real", "balance_source": r.get('balance_source'),
            "storage_source": "local", "exchange": str(r.get('exchange') or 'bybit').lower(),
        } for r in rows]), 200
    except Exception: return jsonify([]), 200

@app.route('/api/vincular_cliente', methods=['POST'])
def add_cliente():
    data = request.json or {}
    try:
        validation = validar_e_salvar_cliente(data.get('bybit_key'), data.get('bybit_secret'), False, client_payload=data)
        if validation.get('record'): return jsonify({"status": "sucesso", "msg": "Investidor conectado!", "valid": True, "client": validation.get('record')}), 200
        return jsonify({"status": "erro", "msg": "Falha ao salvar investidor"}), 500
    except Exception as e: return jsonify({"status": "erro", "msg": str(e)}), 400

@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        _repair_open_trades()
        _refresh_real_balance_state()
        _sync_active_trades_from_db()
        _refresh_last_sniper_signal()
        central_state['trades'] = db.get_recent_trades(20)
        return jsonify(central_state), 200
    except Exception: return jsonify(central_state), 200

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
            v = validar_e_salvar_cliente(data.get('bybit_key'), data.get('bybit_secret'), False, client_payload=data, client_id=client_id, existing_client=_get_registered_client_by_id(client_id))
            return jsonify({"success": True, "client": v.get('record')})
        elif request.method == 'DELETE':
            return jsonify({"success": _delete_client_everywhere(client_id)[1]})
    except Exception as e: return jsonify({"error": str(e)}), 400

@app.route('/api/trade/manual-entry', methods=['POST'])
def api_manual_entry_trade():
    try:
        data = request.json or {}
        symbol, side, force_execute = data.get('symbol', '').strip(), data.get('side', '').strip().upper(), data.get('force_execute', False)
        if not symbol or side not in ['BUY', 'SELL', 'COMPRAR', 'VENDER']: return jsonify({"success": False, "error": "Parâmetros inválidos"}), 400
        side_normalized = 'COMPRAR' if side in ['BUY', 'COMPRAR'] else 'VENDER'
        pub_broker = _get_public_price_broker()
        entry_price = float(pub_broker.get_last_price(symbol))
        
        global IndicatorEngine, GroqValidator
        from src.engine.indicators import IndicatorEngine
        from src.ai_brain.validator import GroqValidator

        if force_execute:
            if not _reserve_signal_slot(symbol): return jsonify({"success": False, "error": "Limite atingido"}), 409
            try:
                db.record_trade(1, symbol, side_normalized, 0, 10, time.strftime("%d/%m %H:%M"), "ENTRADA MANUAL", "open", entry_price)
                _sync_active_trades_from_db()
                threading.Thread(target=_process_client_orders_background, args=(symbol, side_normalized, entry_price, 70, "Manual"), daemon=True).start()
                return jsonify({"success": True, "message": "Ordem manual enviada"}), 200
            finally: _release_signal_slot(symbol)
        
        df = pub_broker.fetch_ohlcv(symbol, timeframe='15m')
        tech_data = IndicatorEngine(df).get_signals() if df is not None and len(df) >= 200 else {'trend': 'ALTA', 'price': entry_price, 'sma_200': entry_price}
        ai_result = GroqValidator().consensus_predict(tech_data, symbol, force_local_only=True)
        return jsonify({"success": True, "analysis_only": True, "symbol": symbol, "side": side_normalized, "entry_price": entry_price, "ai_analysis": {"confidence": ai_result.get('probabilidade', 70), "reason": ai_result.get('motivo', 'Aprovado')}}), 200
    except Exception as e: return jsonify({"success": False, "error": str(e)}), 400

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
                            # Fecha o trade com PnL zerado (fechamento manual)
                            db.close_trade(
                                trade_id=trade.get('id'),
                                pnl_pct=0.0,
                                profit=0.0,
                                closed_at=time.strftime("%d/%m %H:%M"),
                                notes="FECHAMENTO MANUAL"
                            )
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

def validar_e_salvar_cliente(api_key, api_secret, is_testnet, *, client_payload=None, client_id=None, existing_client=None):
    payload = dict(client_payload or {})
    payload['account_mode'], payload['is_testnet'], payload['balance_source'] = 'real', False, 'broker_real_balance'
    payload['exchange'] = str(payload.get('exchange') or 'bybit').strip().lower()
    if client_id is not None: payload['id'] = client_id
    if api_key: payload['bybit_key'] = api_key
    if api_secret: payload['bybit_secret'] = api_secret
    if existing_client is not None and 'nome' not in payload: payload['nome'] = existing_client.get('nome')

    try:
        broker = _make_broker(payload)
        balance = broker.get_balance()
        payload['saldo_base'] = round(float(balance or 0.0), 2)
        payload['status'] = 'ativo'
        record, _, local_synced = _save_client_everywhere(payload)
        return {'valid': True, 'msg': 'Validado OK', 'record': record, 'synced_to_local': local_synced, 'balance': payload['saldo_base'], 'account_mode': 'real', 'exchange': payload['exchange']}
    except Exception as e:
        payload['status'] = 'erro_api'
        payload['saldo_base'] = round(float((existing_client or {}).get('saldo_base') or 0.0), 2)
        record, _, local_synced = _save_client_everywhere(payload)
        return {'valid': False, 'msg': str(e), 'record': record, 'synced_to_local': local_synced, 'balance': payload['saldo_base'], 'account_mode': 'real', 'exchange': payload['exchange']}

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
