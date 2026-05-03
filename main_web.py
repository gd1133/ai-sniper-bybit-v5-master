# -*- coding: utf-8 -*-
import os
import time
import random
import threading
import sqlite3
import requests
import re
import sys
import io
from datetime import datetime, timedelta

# Força UTF-8 no stdout do Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from src.config import get_bybit_base_url, get_bybit_credentials, get_environment_config, resolve_use_testnet

# --- IMPORTAÇÕES DAS PASTAS INTERNAS (SRC) - LAZY LOADING ---
try:
    from src.database import manager as db
    try:
        from src.database.supabase_manager import SupabaseManager
        cloud_db = SupabaseManager()
    except Exception as e:
        print(f"⚠️ Erro ao inicializar Supabase: {e}")
        cloud_db = None
except Exception as e:
    print(f"❌ Erro Crítico ao importar Database Manager: {e}")
    db = None
    cloud_db = None

# Importações pesadas (CCXT, TensorFlow, etc.) carregadas sob demanda
BybitClient = None
BybitV5HTTP = None
IndicatorEngine = None
GroqValidator = None
public_price_broker = None
RUNTIME_START_LOCK = threading.Lock()
RUNTIME_STARTED = False

# ==============================================================================
# 🔘 TACTICAL v60.1 PRO - MAESTRO SAAS (FULL EDITION)
# Orquestrador de Inteligência Híbrida, Multi-Contas e Sincronia Real-Time.
# ==============================================================================

load_dotenv()
ENV_CONFIG = get_environment_config()
ENVIRONMENT = ENV_CONFIG.name
print(f"[SISTEMA] Iniciando em modo: {ENVIRONMENT}")

VALID_OPERATION_MODES = {'paper', 'testnet', 'real'}
VALID_ACCOUNT_MODES = {'testnet', 'real'}


def _normalize_operation_mode(value):
    raw = str(value or '').strip().lower()
    if raw == 'test':
        return 'paper'
    if raw in VALID_OPERATION_MODES:
        return raw
    return 'paper'


def _normalize_account_mode(value):
    raw = str(value or '').strip().lower()
    if raw in VALID_ACCOUNT_MODES:
        return raw
    if value in [True, 1, '1', 'true', 'TRUE', 'True']:
        return 'testnet'
    if value in [False, 0, '0', 'false', 'FALSE', 'False']:
        return 'real'
    return 'testnet'


def _is_testnet_account(value):
    return _normalize_account_mode(value) == 'testnet'


def _mode_display_label(mode):
    labels = {
        'paper': 'PAPER TRADING',
        'testnet': 'BYBIT TESTNET',
        'real': 'CONTA REAL',
    }
    return labels.get(_normalize_operation_mode(mode), 'PAPER TRADING')


def _mode_balance_source(mode):
    return 'broker_testnet_balance' if _normalize_account_mode(mode) == 'testnet' else 'broker_real_balance'


def _mode_uses_testnet(mode):
    return _normalize_operation_mode(mode) == 'testnet'


def _resolve_client_testnet_flag(value):
    if value is None:
        return resolve_use_testnet(default=ENV_CONFIG.use_testnet)
    return _normalize_account_mode(value) == 'testnet'


def _get_synced_account_mode_for_operation(mode):
    normalized_mode = _normalize_operation_mode(mode)
    if normalized_mode == 'testnet':
        return 'testnet'
    if normalized_mode == 'real':
        return 'real'
    return None


def _filter_balance_items_for_operation_mode(items, mode):
    target_account_mode = _get_synced_account_mode_for_operation(mode)
    if target_account_mode is None:
        return []

    filtered_items = []
    for item in items or []:
        item_account_mode = _normalize_account_mode(item.get('account_mode', item.get('is_testnet')))
        if item_account_mode == target_account_mode:
            filtered_items.append({**item, "account_mode": item_account_mode})
    return filtered_items


def _is_order_execution_enabled(mode):
    mode = _normalize_operation_mode(mode)
    if mode == 'paper':
        return False
    if not ALLOW_ORDER_EXECUTION:
        return False
    if mode == 'real' and not ALLOW_REAL_TRADING:
        return False
    return True


def _execution_status_label(mode):
    mode = _normalize_operation_mode(mode)
    if mode == 'paper':
        return 'Sem ordens reais'
    if mode == 'testnet':
        return 'Ordens na testnet ativas' if _is_order_execution_enabled(mode) else 'Ordens na testnet bloqueadas'
    return 'Ordens reais ativas' if _is_order_execution_enabled(mode) else 'Ordens reais bloqueadas'


app = Flask(__name__, static_folder='dist', static_url_path='')
CORS(app)

# Inicializa o Banco de Dados Local (Cria tabelas se não existirem)
db.init_db()

# 🧪 CARREGA CONFIGURAÇÕES DE TESTE
INITIAL_PAPER_BALANCE = 1000.00  # Saldo inicial fixo do investidor
_stored_test_balance = db.get_test_balance()
TEST_BALANCE = _stored_test_balance if _stored_test_balance and _stored_test_balance > 0 else INITIAL_PAPER_BALANCE
APP_MODE = _normalize_operation_mode(db.get_operation_mode())
TEST_MODE_ENABLED = APP_MODE == 'paper'
ALLOW_ORDER_EXECUTION = ENV_CONFIG.allow_order_execution
ALLOW_REAL_TRADING = ENV_CONFIG.allow_real_trading

# Estado Global de Sincronização (O que o Dashboard React consome)
central_state = {
    "balance": TEST_BALANCE,  # Carregado do banco de dados
    "status": "INICIANDO SISTEMA...",
    "symbol": "---",
    "confidence": 0,
    "opportunities": [],
    "active_trades": [],
    "trades": [],
    "last_sniper_signal": None,
    "recent_sniper_signals": [],
    "test_balance": TEST_BALANCE,  # Novo campo para teste
    "test_mode": TEST_MODE_ENABLED,  # Novo campo para teste
    "operation_mode": APP_MODE,
    "operation_mode_label": _mode_display_label(APP_MODE),
    "execution_enabled": _is_order_execution_enabled(APP_MODE),
    "execution_label": _execution_status_label(APP_MODE),
    "pnl_total": 0.0,  # Lucro/Perda Total
    "pnl_percentage": 0.0,  # % de lucro/perda
    "winning_trades": 0,  # Número de trades vencedores
    "losing_trades": 0,  # Número de trades perdedores
    "win_rate": 0.0,  # % de trades vencedores
    "ia2_decision": {
        "motivo": "Varrendo o mercado em busca de confluência 60%...",
        "brains": {"local": "online", "groq": "online", "gemini": "online"}
    }
}

client_balance_cache = {
    "items": [],
    "total": 0.0,
    "timestamp": 0,
}


def _sync_runtime_mode_state(persist=False):
    global APP_MODE, TEST_MODE_ENABLED
    APP_MODE = _normalize_operation_mode(APP_MODE)
    TEST_MODE_ENABLED = APP_MODE == 'paper'
    central_state['test_mode'] = TEST_MODE_ENABLED
    central_state['operation_mode'] = APP_MODE
    central_state['operation_mode_label'] = _mode_display_label(APP_MODE)
    central_state['execution_enabled'] = _is_order_execution_enabled(APP_MODE)
    central_state['execution_label'] = _execution_status_label(APP_MODE)

    if TEST_MODE_ENABLED:
        central_state['balance'] = TEST_BALANCE
        central_state['test_balance'] = TEST_BALANCE
        central_state['status'] = f"🧪 {_mode_display_label(APP_MODE)}: {TEST_BALANCE} USDT (preço real, sem ordens)"
    else:
        central_state['status'] = f"💼 {_mode_display_label(APP_MODE)}: sincronizando saldo dos clientes"

    if persist:
        db.set_operation_mode(APP_MODE)
        db.set_config('TEST_MODE', 'true' if TEST_MODE_ENABLED else 'false')


_sync_runtime_mode_state()


def start_runtime_services():
    """Inicia as threads do robô uma única vez, inclusive sob gunicorn/wsgi."""
    global RUNTIME_STARTED

    with RUNTIME_START_LOCK:
        if RUNTIME_STARTED:
            return False

        threading.Thread(target=sniper_worker_loop, daemon=True).start()
        threading.Thread(target=_monitor_sl_tp_automatico, daemon=True).start()
        print("   Monitor SL/TP: ATIVO (-3% SL / +6% TP)")
        threading.Thread(target=_simulate_pnl_oscillation, daemon=True).start()
        print("   Simulação P&L: ATIVA (oscilação -2% a +4% a cada 3s)")

        if cloud_db:
            print("☁️ Iniciando Sincronização com Supabase Cloud em background...")
            threading.Thread(target=cloud_db.sync_clients, args=(db,), daemon=True).start()

        RUNTIME_STARTED = True
        return True

# Modo Fallback: Se True, usa APENAS o 3º Cérebro (Local Brain)
USE_LOCAL_BRAIN_ONLY = False

# --- PROTOCOLO SNIPER RIGOROSO v60.1 ---
THRESHOLD_ENTRADA = 60           # 🎯 Teste Provisório: 50% (Restaurar 60% depois)
COOLDOWN_INSTITUCIONAL_SECS = 15  # Reduzido para ver entradas rápido igual na foto 4
MAX_MOEDAS_ATIVAS = 5            # Paper trading com até 5 moedas diferentes
SNIPER_POSICAO_UNICA = False     # Multi-ativo: permite até 5 moedas simultâneas

# Trava atômica para bloquear corrida entre validação e gravação de sinal
SNIPER_SIGNAL_LOCK = threading.Lock()
SNIPER_SIGNAL_RESERVATIONS = set()
PAPER_TRADE_TP_PCT = 100.0       # Fecha somente quando dobrar a margem projetada
PAPER_TRADE_SL_PCT = -3.0        # Stop de perda em 3% da entrada
ENABLE_RANDOM_TEST_TRADES = False

# Anti-loop de ativo único (evita ficar preso na mesma moeda por muitos ciclos)
BLOQUEIO_REPETICAO_MOEDA_SECS = 60       # 1 min para girar moedas rápido
PENALIDADE_MOEDA_JA_ABERTA = 25           # Reduz score de ativo já aberto
PENALIDADE_STREAK_MESMA_MOEDA = 10      # Penalidade por repetição consecutiva
SCAN_TOP_COINS = 8                       # Menos ativos por ciclo para responder mais rápido
SCAN_INTER_SYMBOL_DELAY_SECS = 0.25      # Respiro curto sem travar o radar


def _frontend_index_path():
    return os.path.join(app.static_folder or "", 'index.html')


def _frontend_is_built():
    return bool(app.static_folder) and os.path.isfile(_frontend_index_path())


def _frontend_asset_exists(path):
    return bool(path) and bool(app.static_folder) and os.path.isfile(os.path.join(app.static_folder, path))


def _render_frontend_status_page():
    return (
        """<!DOCTYPE html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>DuoIA Maestro</title>
    <style>
      body {
        margin: 0;
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #020617;
        color: #e2e8f0;
        font-family: Inter, Arial, sans-serif;
      }
      main {
        max-width: 720px;
        margin: 24px;
        padding: 32px;
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 20px;
        background: rgba(15, 23, 42, 0.92);
        box-shadow: 0 20px 50px rgba(15, 23, 42, 0.45);
      }
      h1 {
        margin-top: 0;
        margin-bottom: 12px;
        font-size: 2rem;
      }
      p {
        margin: 0 0 12px;
        line-height: 1.6;
      }
      code {
        padding: 2px 8px;
        border-radius: 999px;
        background: rgba(30, 41, 59, 0.95);
      }
    </style>
  </head>
  <body>
    <main>
      <h1>DuoIA Maestro online</h1>
      <p>A API Flask esta respondendo normalmente.</p>
      <p>O bundle do frontend nao foi encontrado em <code>dist/index.html</code>, entao o dashboard React ainda nao foi publicado neste deploy.</p>
      <p>Assim que o build do Vite for gerado, esta rota passara a entregar o dashboard automaticamente.</p>
    </main>
  </body>
</html>""",
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    """Entrega o dashboard React no root sem interferir nas rotas da API."""
    if path.startswith('api/'):
        return jsonify({"error": "Endpoint não encontrado"}), 404

    if _frontend_asset_exists(path):
        return send_from_directory(app.static_folder, path)

    if _frontend_is_built():
        return send_from_directory(app.static_folder, 'index.html')

    return _render_frontend_status_page()

def _limpar_simbolo(sym):
    """Remove o sufixo da Bybit para limpeza visual no Dashboard."""
    if not sym: return "---"
    return sym.split(':')[0] if ':' in sym else sym


def _normalize_symbol_key(sym):
    """Normaliza símbolos para comparações robustas entre BTCUSDT e BTC/USDT:USDT."""
    return re.sub(r'[^A-Z0-9]', '', str(sym or '').upper())


def _canonicalize_symbol(sym):
    """Converte símbolos em formatos mistos para o padrão da Bybit."""
    raw = str(sym or '').strip().upper()
    if not raw:
        return ""

    compact = raw.replace(" ", "")
    if ":" in compact:
        return compact

    if "/" in compact:
        base, quote = compact.split("/", 1)
        if base and quote:
            return f"{base}/{quote}:{quote}"

    if compact.endswith("USDT") and len(compact) > 4:
        base = compact[:-4]
        return f"{base}/USDT:USDT"

    return compact


def _coerce_float(*values, default=0.0):
    for value in values:
        try:
            numeric = float(value)
            if numeric == numeric:
                return numeric
        except Exception:
            continue
    return float(default)


def _clamp(value, minimum=0.0, maximum=100.0):
    return max(minimum, min(maximum, float(value)))


def _get_symbol_trade_edge(symbol, side, limit=300):
    """
    Mede histórico recente da moeda/lado para priorizar setups com mais chance.
    """
    try:
        normalized_symbol = _normalize_symbol_key(_canonicalize_symbol(symbol) or symbol)
        normalized_side = str(side or '').upper()
        trades = db.get_recent_trades(limit)
        matching = []

        for trade in trades:
            if str(trade.get('status', 'closed')).lower() != 'closed':
                continue
            trade_symbol = _normalize_symbol_key(_canonicalize_symbol(trade.get('pair')) or trade.get('pair'))
            trade_side = str(trade.get('side') or '').upper()
            if trade_symbol != normalized_symbol or trade_side != normalized_side:
                continue
            matching.append(trade)

        if not matching:
            return {
                "sample_size": 0,
                "win_rate": 0.0,
                "profit_total": 0.0,
                "edge_score": 0.0,
            }

        wins = sum(1 for trade in matching if _coerce_float(trade.get('profit'), default=0.0) > 0)
        sample_size = len(matching)
        win_rate = (wins / sample_size) * 100 if sample_size else 0.0
        profit_total = sum(_coerce_float(trade.get('profit'), default=0.0) for trade in matching)
        edge_score = _clamp(((win_rate - 50.0) * 0.30) + min(12.0, profit_total * 0.05), -10.0, 20.0)

        return {
            "sample_size": sample_size,
            "win_rate": round(win_rate, 2),
            "profit_total": round(profit_total, 2),
            "edge_score": round(edge_score, 2),
        }
    except Exception:
        return {
            "sample_size": 0,
            "win_rate": 0.0,
            "profit_total": 0.0,
            "edge_score": 0.0,
        }


def _build_money_flow_metrics(signals, ticker, decision):
    """
    Estima onde o grande dinheiro está com base em volume, impulso e expansão.
    """
    volume_ratio = _coerce_float(signals.get('volume_ratio'), default=0.0)
    recent_return_pct = abs(_coerce_float(signals.get('recent_return_pct'), default=0.0))
    distance_from_sma_pct = _coerce_float(signals.get('distance_from_sma_pct'), default=0.0)
    candle_body_ratio = _coerce_float(signals.get('candle_body_ratio'), default=0.0)
    range_expansion = _coerce_float(signals.get('range_expansion'), default=0.0)
    quote_volume = _coerce_float(ticker.get('quoteVolume'), default=0.0)
    quote_volume_millions = quote_volume / 1_000_000
    money_flow_side = str(signals.get('money_flow_side') or 'WAIT').upper()
    normalized_decision = str(decision or '').upper()

    institutional_pressure = _clamp(max(0.0, volume_ratio - 1.0) * 35.0, 0.0, 35.0)
    momentum_score = _clamp(recent_return_pct * 10.0, 0.0, 20.0)
    trend_strength = _clamp(distance_from_sma_pct * 3.0, 0.0, 15.0)
    aggression_score = _clamp((candle_body_ratio * 0.12) + (range_expansion * 4.0), 0.0, 15.0)
    liquidity_score = _clamp(quote_volume_millions / 2.0, 0.0, 15.0)
    directional_bonus = 10.0 if money_flow_side and money_flow_side == normalized_decision.replace('COMPRAR', 'BUY').replace('VENDER', 'SELL') else 0.0

    money_flow_score = _clamp(
        institutional_pressure + momentum_score + trend_strength + aggression_score + liquidity_score + directional_bonus,
        0.0,
        100.0,
    )

    return {
        "money_flow_score": round(money_flow_score, 2),
        "institutional_pressure": round(institutional_pressure, 2),
        "volume_ratio": round(volume_ratio, 2),
        "quote_volume_millions": round(quote_volume_millions, 2),
        "recent_return_pct": round(_coerce_float(signals.get('recent_return_pct'), default=0.0), 2),
        "money_flow_side": money_flow_side,
    }


def _sanitize_signal_payload(raw_data):
    """Normaliza sinais externos e preenche preço de entrada quando possível."""
    data = dict(raw_data or {})
    symbol = _canonicalize_symbol(data.get('symbol') or data.get('pair') or data.get('asset'))
    if not symbol:
        raise ValueError("Sinal sem símbolo válido.")

    side_raw = str(data.get('side') or data.get('lado') or data.get('decision') or '').strip().upper()
    side_map = {
        'BUY': 'COMPRAR',
        'LONG': 'COMPRAR',
        'COMPRAR': 'COMPRAR',
        'SELL': 'VENDER',
        'SHORT': 'VENDER',
        'VENDER': 'VENDER',
    }
    side = side_map.get(side_raw, side_raw)
    if side not in {'COMPRAR', 'VENDER'}:
        raise ValueError(f"Lado inválido para o sinal: {side_raw or 'vazio'}.")

    entry_price = _coerce_float(data.get('entry_price'), data.get('entry'), data.get('price'), default=0.0)
    if entry_price <= 0:
        entry_price = _coerce_float(_get_public_price_broker().get_last_price(symbol), default=0.0)
    if entry_price <= 0:
        raise ValueError(f"Preço de entrada inválido para {symbol}.")

    confidence = max(0.0, min(100.0, _coerce_float(data.get('confidence'), data.get('probabilidade'), default=70.0)))
    reason = str(data.get('reason') or data.get('motivo') or 'Sinal Sniper Broadcast').strip()

    return {
        'symbol': symbol,
        'side': side,
        'entry_price': round(entry_price, 8),
        'confidence': round(confidence, 2),
        'reason': reason,
    }


def _build_last_sniper_signal(symbol, side, entry_price, confidence, reason):
    canonical_symbol = _canonicalize_symbol(symbol) or str(symbol or '').strip()
    return {
        "signal_id": f"{_limpar_simbolo(canonical_symbol)}|{str(side or '').upper()}|{round(float(entry_price or 0), 8)}|{datetime.now().isoformat(timespec='seconds')}",
        "symbol": _limpar_simbolo(canonical_symbol),
        "raw_symbol": canonical_symbol,
        "side": str(side or '').upper(),
        "entry_price": round(float(entry_price or 0), 8),
        "confidence": round(float(confidence or 0), 2),
        "reason": str(reason or '').strip(),
        "received_at": datetime.now().isoformat(timespec='seconds'),
    }


def _push_recent_sniper_signal(signal_data, max_items=10):
    if not signal_data:
        return

    signal_id = str(signal_data.get('signal_id') or '').strip()
    recent = []
    if signal_id:
        recent.append(signal_data.copy())

    for existing in central_state.get('recent_sniper_signals', []):
        if not isinstance(existing, dict):
            continue
        existing_id = str(existing.get('signal_id') or '').strip()
        if signal_id and existing_id == signal_id:
            continue
        recent.append(existing)

    central_state['recent_sniper_signals'] = recent[:max_items]


def _extract_entry_price(trade):
    """Prioriza o preço de entrada real e faz fallback para notas antigas."""
    try:
        entry_price = float(trade.get('entry_price', 0) or 0)
        if entry_price > 0:
            return round(entry_price, 8)
    except Exception:
        pass

    notes = str(trade.get('notes') or '')
    match = re.search(r'(?:ENTRADA:|@)\s*\$?\s*([0-9]+(?:\.[0-9]+)?)', notes, re.IGNORECASE)
    if match:
        try:
            return round(float(match.group(1)), 8)
        except Exception:
            pass

    return 0.0


def _get_public_price_broker():
    """Instância pública lazy para consultar preço ao vivo no dashboard."""
    global BybitClient, public_price_broker
    if public_price_broker is not None:
        return public_price_broker

    if BybitClient is None:
        from src.broker.bybit_client import BybitClient as _BybitClient
        BybitClient = _BybitClient

    bybit_api_key, bybit_api_secret = get_bybit_credentials()
    public_price_broker = BybitClient(
        bybit_api_key,
        bybit_api_secret,
        testnet=_mode_uses_testnet(APP_MODE),
    )
    return public_price_broker


def _ensure_broker_class():
    global BybitClient
    if BybitClient is None:
        from src.broker.bybit_client import BybitClient as _BybitClient
        BybitClient = _BybitClient
    return BybitClient


def _ensure_pybit_http_class():
    global BybitV5HTTP
    if BybitV5HTTP is None:
        from pybit.unified_trading import HTTP as _HTTP
        BybitV5HTTP = _HTTP
    return BybitV5HTTP


def _get_master_telegram_config():
    """Recarrega o .env para usar o token/chat mais recente do Telegram."""
    load_dotenv(override=True)
    token = str(os.getenv('TELEGRAM_TOKEN') or '').strip()
    chat_id = str(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
    return token, chat_id


def _is_supabase_ready():
    return bool(cloud_db and getattr(cloud_db, "is_available", lambda: False)())


def _get_registered_clients(active_only=False):
    """Fonte de verdade SaaS: Supabase quando disponível; SQLite como fallback."""
    if _is_supabase_ready():
        cloud_clients = cloud_db.get_clients(active_only=active_only)
        if cloud_clients is not None:
            normalized_cloud_clients = []
            for client in cloud_clients:
                client_with_source = dict(client)
                client_with_source['storage_source'] = 'supabase'
                try:
                    db.upsert_client_local(client_with_source)
                except Exception as e:
                    print(f"⚠️ [LOCAL MIRROR] cliente {client.get('id')}: {e}")
                normalized_cloud_clients.append(client_with_source)
            return normalized_cloud_clients

    local_clients = db.get_active_clients() if active_only else db.get_all_clients()
    return [{**dict(client), "storage_source": "local"} for client in local_clients]


def _get_registered_client_by_id(client_id):
    if _is_supabase_ready():
        cloud_client = cloud_db.get_client_by_id(client_id)
        if cloud_client is not None:
            cloud_client = dict(cloud_client)
            cloud_client['storage_source'] = 'supabase'
            try:
                db.upsert_client_local(cloud_client)
            except Exception as e:
                print(f"⚠️ [LOCAL MIRROR] cliente {client_id}: {e}")
            return cloud_client

    local_client = db.get_client_by_id(client_id)
    if local_client is None:
        return None
    return {**dict(local_client), "storage_source": "local"}


def _save_client_everywhere(client_data):
    """Persiste o cliente e devolve o registro final + status de sincronização."""
    payload = dict(client_data or {})
    payload['account_mode'] = _normalize_account_mode(payload.get('account_mode', payload.get('is_testnet')))
    payload['is_testnet'] = _is_testnet_account(payload.get('account_mode'))
    payload['balance_source'] = payload.get('balance_source') or _mode_balance_source(payload.get('account_mode'))
    remote_record = None
    cloud_synced = False

    if _is_supabase_ready():
        remote_record = cloud_db.save_client(payload)
        if remote_record is not None:
            payload.update(remote_record)
            cloud_synced = True

    local_result = db.upsert_client_local(payload) if payload.get('id') is not None else db.add_client(payload)
    local_synced = bool(local_result)

    final_id = payload.get('id')
    if final_id is None and local_result:
        try:
            final_id = int(local_result)
        except Exception:
            pass

    final_record = _get_registered_client_by_id(final_id) if final_id is not None else None
    if final_record is None and cloud_synced and remote_record is not None:
        final_record = {**dict(remote_record), "storage_source": "supabase"}
    if final_record is None and local_synced and final_id is not None:
        local_record = db.get_client_by_id(final_id)
        final_record = {**dict(local_record), "storage_source": "local"} if local_record is not None else None
    client_balance_cache["timestamp"] = 0
    return final_record, cloud_synced, local_synced


def _delete_client_everywhere(client_id):
    """Remove o cliente da nuvem e do fallback local."""
    cloud_deleted = (not _is_supabase_ready()) or cloud_db.delete_client(client_id)
    local_deleted = db.delete_client(client_id)
    client_balance_cache["timestamp"] = 0
    return cloud_deleted, local_deleted


def _resolve_client_balance_payload(raw_data, broker, account_mode, existing_client=None):
    """Sincroniza saldo do broker para testnet/real e preserva último valor conhecido como fallback."""
    payload = dict(raw_data or {})
    normalized_account_mode = _normalize_account_mode(account_mode)
    payload['account_mode'] = normalized_account_mode
    payload['is_testnet'] = _is_testnet_account(normalized_account_mode)

    real_balance = broker.get_balance() if broker is not None else None
    if real_balance is not None:
        payload['saldo_base'] = round(float(real_balance), 2)
    elif existing_client is not None:
        payload['saldo_base'] = round(float(existing_client.get('saldo_base') or 0.0), 2)
    else:
        try:
            payload['saldo_base'] = round(float(payload.get('saldo_base') or 0.0), 2)
        except Exception:
            payload['saldo_base'] = 0.0

    payload['balance_source'] = _mode_balance_source(normalized_account_mode)
    return payload


def _get_bybit_v5_base_url(is_testnet):
    return get_bybit_base_url(is_testnet)


def _get_bybit_server_time_ms(base_url, timeout=10):
    started_at = int(time.time() * 1000)
    response = requests.get(f'{base_url}/v5/market/time', timeout=timeout)
    finished_at = int(time.time() * 1000)

    if response.status_code == 403:
        raise RuntimeError(f'Bybit GET {base_url}/v5/market/time -> HTTP 403 Forbidden')
    response.raise_for_status()

    payload = response.json() or {}
    result = payload.get('result') or {}
    if str(payload.get('retCode', 0)) not in {'0', 'None'}:
        raise RuntimeError(f"Bybit GET {base_url}/v5/market/time -> {payload.get('retMsg') or 'erro desconhecido'}")

    time_nano = result.get('timeNano')
    if time_nano not in [None, '']:
        try:
            return int(int(time_nano) / 1_000_000), finished_at - started_at
        except Exception:
            pass

    time_second = result.get('timeSecond')
    if time_second not in [None, '']:
        return int(time_second) * 1000, finished_at - started_at

    raise RuntimeError('Bybit /v5/market/time sem timestamp válido')


def _compute_safe_recv_window(base_url):
    try:
        server_time_ms, round_trip_ms = _get_bybit_server_time_ms(base_url)
        local_time_ms = int(time.time() * 1000)
        offset_ms = abs(server_time_ms - local_time_ms)
        recv_window = 10000
        if round_trip_ms > 2500 or offset_ms > 2000:
            recv_window = 20000
        return min(recv_window, 30000)
    except Exception as e:
        print(f"⚠️ [recv_window] falha ao calcular janela de recepção ({e}). Usando padrão 20000ms")
        return 20000


def _extract_unified_usdt_balance(wallet_payload):
    ret_code = wallet_payload.get('retCode')
    if ret_code != 0:
        raise RuntimeError(
            f"Bybit get_wallet_balance falhou: retCode={ret_code} retMsg={wallet_payload.get('retMsg', 'desconhecido')}"
        )

    accounts = ((wallet_payload or {}).get('result') or {}).get('list') or []
    if not accounts:
        return 0.0

    account = accounts[0] or {}
    for field in ('totalWalletBalance', 'totalEquity'):
        raw_value = account.get(field)
        if raw_value not in [None, '']:
            try:
                return float(raw_value)
            except Exception:
                continue

    for coin in account.get('coin') or []:
        if str(coin.get('coin') or '').upper() != 'USDT':
            continue
        for field in ('walletBalance', 'equity', 'usdValue'):
            raw_value = coin.get(field)
            if raw_value not in [None, '']:
                try:
                    return float(raw_value)
                except Exception:
                    continue

    return 0.0


def validar_e_salvar_cliente(api_key, api_secret, is_testnet, *, client_payload=None, client_id=None, existing_client=None):
    """Valida credenciais Bybit V5 com pybit e persiste o cliente no fluxo atual do projeto."""
    payload = dict(client_payload or {})
    resolved_testnet = _resolve_client_testnet_flag(is_testnet)
    account_mode = 'testnet' if resolved_testnet else 'real'
    payload['account_mode'] = account_mode
    payload['is_testnet'] = resolved_testnet
    payload['balance_source'] = _mode_balance_source(account_mode)

    if client_id is not None:
        payload['id'] = client_id

    if api_key:
        payload['bybit_key'] = api_key
    if api_secret:
        payload['bybit_secret'] = api_secret

    if existing_client is not None and 'nome' not in payload:
        payload['nome'] = existing_client.get('nome')

    base_url = _get_bybit_v5_base_url(resolved_testnet)
    recv_window = None
    validation_message = None
    valid = False

    try:
        recv_window = _compute_safe_recv_window(base_url)
        session = _ensure_pybit_http_class()(
            testnet=resolved_testnet,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=recv_window,
        )
        wallet_payload = session.get_wallet_balance(accountType='UNIFIED', coin='USDT')
        balance = _extract_unified_usdt_balance(wallet_payload)
        payload['saldo_base'] = round(float(balance), 2)
        payload['status'] = 'ativo'
        valid = True
        validation_message = f'Conta {account_mode.upper()} validada via Bybit V5'
    except Exception as e:
        validation_message = str(e)
        payload['status'] = 'erro_api'
        if existing_client is not None:
            try:
                payload['saldo_base'] = round(float(existing_client.get('saldo_base') or 0.0), 2)
            except Exception:
                payload['saldo_base'] = 0.0
        else:
            try:
                payload['saldo_base'] = round(float(payload.get('saldo_base') or 0.0), 2)
            except Exception:
                payload['saldo_base'] = 0.0

    record = None
    cloud_synced = False
    local_synced = False
    if client_payload is not None:
        record, cloud_synced, local_synced = _save_client_everywhere(payload)

    return {
        'valid': valid,
        'msg': validation_message,
        'record': record,
        'synced_to_cloud': cloud_synced,
        'synced_to_local': local_synced,
        'recv_window': recv_window,
        'base_url': base_url,
        'balance': payload.get('saldo_base', 0.0),
        'account_mode': account_mode,
    }


def _validate_client_broker_credentials(client_data, account_mode):
    """Valida o broker no ambiente correto da Bybit."""
    normalized_account_mode = _normalize_account_mode(account_mode)
    broker = None
    try:
        broker = _ensure_broker_class()(
            client_data.get('bybit_key'),
            client_data.get('bybit_secret'),
            testnet=_is_testnet_account(normalized_account_mode),
        )
        ok, msg = broker.test_connection()
        return broker, ok, msg
    except Exception:
        return None, False, 'Broker test unavailable'


def _fetch_active_client_balances(force=False):
    """Busca o saldo real/testnet dos clientes ativos com cache curto."""
    global client_balance_cache

    now = time.time()
    if not force and (now - client_balance_cache["timestamp"]) < 10:
        return client_balance_cache

    broker_cls = _ensure_broker_class()

    items = []
    total = 0.0

    try:
        active_clients = _get_registered_clients(active_only=True)
        for client in active_clients:
            balance = None
            error = None
            account_mode = _normalize_account_mode(client.get('account_mode', client.get('is_testnet')))
            try:
                broker = broker_cls(
                    client.get('bybit_key'),
                    client.get('bybit_secret'),
                    testnet=_is_testnet_account(account_mode),
                )
                balance = broker.get_balance()
                if balance is not None:
                    balance = round(float(balance), 2)
                    total += balance
            except Exception as e:
                error = str(e)

            items.append({
                "id": client.get('id'),
                "nome": client.get('nome'),
                "saldo_real": balance,
                "saldo_base": float(client.get('saldo_base', 0) or 0),
                "is_testnet": _is_testnet_account(account_mode),
                "account_mode": account_mode,
                "status": client.get('status'),
                "error": error,
            })
    except Exception as e:
        print(f"⚠️ [_fetch_active_client_balances] erro: {e}")

    client_balance_cache = {
        "items": items,
        "total": round(total, 2),
        "timestamp": now,
    }
    return client_balance_cache


def _refresh_real_balance_state(force=False):
    """Atualiza o estado global com o saldo verdadeiro dos clientes."""
    if TEST_MODE_ENABLED:
        central_state['test_mode'] = True
        central_state['operation_mode'] = APP_MODE
        central_state['operation_mode_label'] = _mode_display_label(APP_MODE)
        central_state['execution_enabled'] = _is_order_execution_enabled(APP_MODE)
        central_state['execution_label'] = _execution_status_label(APP_MODE)
        return

    balances = _fetch_active_client_balances(force=force)
    mode_items = _filter_balance_items_for_operation_mode(balances.get("items", []), APP_MODE)
    valid_items = [item for item in mode_items if item.get("saldo_real") is not None]
    central_state['test_mode'] = False
    central_state['operation_mode'] = APP_MODE
    central_state['operation_mode_label'] = _mode_display_label(APP_MODE)
    central_state['execution_enabled'] = _is_order_execution_enabled(APP_MODE)
    central_state['execution_label'] = _execution_status_label(APP_MODE)
    central_state['real_client_balances'] = mode_items

    if valid_items:
        central_state['balance'] = round(sum(float(item.get("saldo_real") or 0.0) for item in valid_items), 2)
        central_state['status'] = f"💼 {_mode_display_label(APP_MODE)}: saldo sincronizado de {len(valid_items)} cliente(s)"
    elif mode_items:
        central_state['balance'] = 0.0
        central_state['status'] = f"💼 {_mode_display_label(APP_MODE)}: aguardando saldo válido dos clientes"
    else:
        account_label = 'REAL' if _get_synced_account_mode_for_operation(APP_MODE) == 'real' else 'TESTNET'
        central_state['balance'] = 0.0
        central_state['status'] = f"💼 {_mode_display_label(APP_MODE)}: nenhum cliente {account_label} ativo"


def _calculate_live_trade_metrics(entry_price, current_price, side):
    """Calcula direção do mercado e performance considerando o lado da operação."""
    try:
        entry = float(entry_price or 0)
        current = float(current_price or 0)
    except Exception:
        return {
            "current_price": 0.0,
            "price_change_pct": 0.0,
            "pnl_pct": 0.0,
            "trend": "flat",
            "is_favorable": False,
        }

    if entry <= 0 or current <= 0:
        return {
            "current_price": round(current, 8) if current > 0 else 0.0,
            "price_change_pct": 0.0,
            "pnl_pct": 0.0,
            "trend": "flat",
            "is_favorable": False,
        }

    market_move_pct = ((current - entry) / entry) * 100
    normalized_side = str(side or '').upper()
    is_sell = normalized_side in {'VENDER', 'SELL'}
    pnl_pct = ((entry - current) / entry) * 100 if is_sell else ((current - entry) / entry) * 100

    if current > entry:
        trend = "up"
    elif current < entry:
        trend = "down"
    else:
        trend = "flat"

    return {
        "current_price": round(current, 8),
        "price_change_pct": round(market_move_pct, 4),
        "pnl_pct": round(pnl_pct, 4),
        "trend": trend,
        "is_favorable": pnl_pct >= 0,
    }


def _get_live_price_snapshot(symbol, entry_price, side):
    """Consulta preço atual e devolve métricas para o dashboard."""
    try:
        broker = _get_public_price_broker()
        current_price = broker.get_last_price(symbol)
        return _calculate_live_trade_metrics(entry_price, current_price, side)
    except Exception as e:
        print(f"⚠️ [_get_live_price_snapshot] {symbol}: {e}")
        return _calculate_live_trade_metrics(entry_price, 0.0, side)


def _refresh_last_sniper_signal():
    signal_data = central_state.get('last_sniper_signal')
    if not signal_data:
        return

    entry_price = float(signal_data.get('entry_price', 0) or 0)
    symbol = signal_data.get('raw_symbol') or signal_data.get('symbol')
    live = _get_live_price_snapshot(symbol, entry_price, signal_data.get('side'))
    signal_data.update(live)
    central_state['last_sniper_signal'] = signal_data


def _get_initial_test_balance():
    """Base fixa do paper trading; não deve oscilar com P&L aberto."""
    configured = db.get_config('INITIAL_BALANCE')
    if configured is None:
        initial_balance = INITIAL_PAPER_BALANCE
        db.set_config('INITIAL_BALANCE', str(initial_balance))
        return initial_balance

    try:
        stored = round(float(configured), 2)
        return stored if stored > 0 else INITIAL_PAPER_BALANCE
    except Exception:
        db.set_config('INITIAL_BALANCE', str(INITIAL_PAPER_BALANCE))
        return INITIAL_PAPER_BALANCE


def _repair_open_trades():
    """
    Corrige símbolos/entradas de trades abertos e fecha registros inválidos
    que travariam o monitor com PnL congelado.
    """
    try:
        open_trades = db.get_open_trades(100)
        if not open_trades:
            return 0, 0

        conn = db._connect()
        cur = conn.cursor()
        repaired = 0
        closed = 0

        for trade in open_trades:
            trade_id = trade.get('id')
            raw_symbol = str(trade.get('pair') or '').strip()
            canonical_symbol = _canonicalize_symbol(raw_symbol)
            entry_price = _extract_entry_price(trade)
            current_entry = _coerce_float(trade.get('entry_price'), default=0.0)
            margin = _coerce_float(trade.get('profit'), default=0.0)

            if not canonical_symbol or entry_price <= 0 or margin <= 0:
                cur.execute(
                    """
                    UPDATE trades
                    SET status = 'closed',
                        pnl_pct = 0,
                        profit = 0,
                        closed_at = ?,
                        notes = COALESCE(notes, '') || ' | AUTO_CLOSE_INVALID_OPEN'
                    WHERE id = ?
                    """,
                    (time.strftime("%d/%m %H:%M", time.localtime()), trade_id),
                )
                closed += 1
                continue

            if canonical_symbol != raw_symbol or current_entry <= 0:
                cur.execute(
                    """
                    UPDATE trades
                    SET pair = ?, entry_price = ?,
                        notes = COALESCE(notes, '') ||
                            CASE
                                WHEN instr(COALESCE(notes, ''), 'AUTO_REPAIRED_OPEN') = 0
                                THEN ' | AUTO_REPAIRED_OPEN'
                                ELSE ''
                            END
                    WHERE id = ?
                    """,
                    (canonical_symbol, round(entry_price, 8), trade_id),
                )
                repaired += 1

        conn.commit()
        conn.close()
        return repaired, closed
    except Exception as e:
        print(f"⚠️ [_repair_open_trades] erro: {e}")
        return 0, 0



def _can_open_new_signal(symbol):
    """Valida se as travas de segurança permitem uma nova entrada."""
    _repair_open_trades()
    normalized_symbol = _normalize_symbol_key(_canonicalize_symbol(symbol) or symbol)
    open_trades = db.get_open_trades(100)
    open_symbols = {
        _normalize_symbol_key(_canonicalize_symbol(t.get('pair')) or t.get('pair'))
        for t in open_trades
        if t.get('pair')
    }
    reserved_symbols = set(SNIPER_SIGNAL_RESERVATIONS)
    occupied_symbols = open_symbols | reserved_symbols

    if SNIPER_POSICAO_UNICA and (open_trades or reserved_symbols):
        first_open_trade = next((t for t in open_trades if t.get('pair')), None)
        trade_label = _limpar_simbolo(first_open_trade.get('pair')) if first_open_trade else 'ativo já aberto'
        return False, f"Sniper Bloqueado: Posição Ativa em {trade_label}"

    if normalized_symbol in open_symbols:
        return False, f"Moeda {symbol} já está aberta. Diversificação obrigatória."

    if normalized_symbol in reserved_symbols:
        return False, f"Moeda {symbol} já está em processamento."

    if normalized_symbol not in occupied_symbols and len(occupied_symbols) >= MAX_MOEDAS_ATIVAS:
        return False, f"Limite de {MAX_MOEDAS_ATIVAS} moedas atingido."

    return True, "ok"


def _reserve_signal_slot(symbol):
    """Reserva o slot de sinal de forma atômica para evitar corrida entre threads/endpoints."""
    normalized_symbol = _normalize_symbol_key(_canonicalize_symbol(symbol) or symbol)
    with SNIPER_SIGNAL_LOCK:
        can_open, reason = _can_open_new_signal(symbol)
        if not can_open:
            return False, reason

        SNIPER_SIGNAL_RESERVATIONS.add(normalized_symbol)

    return True, "ok"


def _release_signal_slot(symbol):
    """Libera a reserva após concluir a gravação da operação."""
    normalized_symbol = _normalize_symbol_key(_canonicalize_symbol(symbol) or symbol)
    with SNIPER_SIGNAL_LOCK:
        SNIPER_SIGNAL_RESERVATIONS.discard(normalized_symbol)

def _calcular_pnl_trades():
    """Calcula o P&L total realizado, ignorando posições ainda abertas."""
    try:
        recent_trades = db.get_recent_trades(500)  # Pega últimos 500 trades
        pnl_total = 0.0
        winning = 0
        losing = 0
        initial_balance = _get_initial_test_balance()
        
        for trade in recent_trades:
            if str(trade.get('status', 'closed')).lower() != 'closed':
                continue
            profit = float(trade.get('profit', 0))
            pnl_total += profit
            if profit > 0:
                winning += 1
            elif profit < 0:
                losing += 1
        
        total_trades = winning + losing if (winning + losing) > 0 else 1
        win_rate = (winning / total_trades * 100) if total_trades > 0 else 0
        pnl_percentage = (pnl_total / initial_balance * 100) if initial_balance > 0 else 0
        
        central_state['pnl_total'] = round(pnl_total, 2)
        central_state['pnl_percentage'] = round(pnl_percentage, 2)
        central_state['winning_trades'] = winning
        central_state['losing_trades'] = losing
        central_state['win_rate'] = round(win_rate, 2)
        
        return pnl_total
    except Exception as e:
        print(f"❌ Erro ao calcular P&L: {e}")
        return 0.0

def _atualizar_saldo_com_pnl(pnl_lucro):
    """Atualiza o saldo realizado do paper trading."""
    global TEST_BALANCE
    try:
        saldo_inicial = _get_initial_test_balance()
        
        novo_saldo = saldo_inicial + pnl_lucro
        central_state['balance'] = round(novo_saldo, 2)
        central_state['test_balance'] = round(novo_saldo, 2)
        TEST_BALANCE = round(novo_saldo, 2)
        db.set_test_balance(novo_saldo)
        
    except Exception as e:
        print(f"❌ Erro ao atualizar saldo: {e}")


def _simulate_pnl_oscillation():
    """
    Simula variação de P&L em tempo real a cada 3 segundos.

    - Oscila entre -2.00% e +4.00% quando há pelo menos uma moeda ativa.
    - Atualiza pnl_percentage, pnl_total e o open_pnl_value de cada trade
      ativo para que o investidor veja o dinheiro subir ou descer na tela.
    - Não altera o saldo base realizado; apenas reflete o P&L não-realizado.
    """
    PNL_MIN_PCT = -2.00
    PNL_MAX_PCT =  4.00
    STEP_PCT    =  0.10  # variação máxima por tick
    INTERVAL    =  3     # segundos entre atualizações

    current_pct = 0.0  # ponto de partida neutro

    while True:
        try:
            active = central_state.get('active_trades', [])
            if active:
                # Movimento aleatório simétrico (random walk limitado à faixa)
                delta = random.uniform(-STEP_PCT, STEP_PCT)
                current_pct = max(PNL_MIN_PCT, min(PNL_MAX_PCT, current_pct + delta))

                initial_balance = _get_initial_test_balance()
                pnl_value = round(initial_balance * (current_pct / 100), 2)

                central_state['pnl_percentage'] = round(current_pct, 2)
                central_state['pnl_total'] = pnl_value

                # Distribui o P&L simulado entre os trades ativos
                for trade in active:
                    entry_margin = float(trade.get('entry', 0))
                    trade['pnl_pct'] = round(current_pct, 4)
                    trade['open_pnl_value'] = round((entry_margin * current_pct) / 100, 2) if entry_margin else 0.0
                    trade['is_favorable'] = current_pct >= 0
            else:
                # Nenhum ativo aberto: zera a oscilação
                current_pct = 0.0
                central_state['pnl_percentage'] = 0.0
                central_state['pnl_total'] = 0.0

        except Exception as exc:
            print(f"⚠️ [_simulate_pnl_oscillation] {exc}")

        time.sleep(INTERVAL)


def _monitor_sl_tp_automatico():
    """
    Monitora trades abertos e fecha automaticamente quando atingem:
    - Stop Loss: -3% (perda maxima institucional)
    - Take Profit: +6% (lucro alvo)
    Executa em background a cada 10 segundos.
    """
    SL_PCT = -3.0
    TP_PCT =  6.0

    while True:
        try:
            trades_abertos = list(central_state.get('active_trades', []))
            for trade in trades_abertos:
                trade_id = trade.get('id')
                symbol = trade.get('raw_symbol') or trade.get('symbol')
                entry_price = trade.get('entry_price', 0)
                side = trade.get('side', 'buy')

                if not trade_id or not entry_price or entry_price == 0:
                    continue

                live = _get_live_price_snapshot(symbol, entry_price, side)
                pnl_pct = live.get('pnl_pct', 0.0)

                motivo = None
                if pnl_pct <= SL_PCT:
                    motivo = f"SL_AUTO -3% (real: {pnl_pct:.2f}%)"
                elif pnl_pct >= TP_PCT:
                    motivo = f"TP_AUTO +6% (real: {pnl_pct:.2f}%)"

                if motivo:
                    try:
                        conn = db._connect()
                        cur = conn.cursor()
                        cur.execute(
                            "UPDATE trades SET status='closed', pnl_pct=?, notes=COALESCE(notes,'') || ? WHERE id=?",
                            (round(pnl_pct, 4), f" | {motivo}", trade_id)
                        )
                        conn.commit()
                        conn.close()
                        print(f"   [SL/TP AUTO] trade_id={trade_id} {symbol} fechado: {motivo}")

                        tg_token = os.getenv("TELEGRAM_TOKEN")
                        tg_chat  = os.getenv("TELEGRAM_CHAT_ID")
                        if tg_token and tg_chat:
                            emoji = "OK" if pnl_pct >= TP_PCT else "STOP"
                            msg = (f"[{emoji}] FECHAMENTO AUTOMATICO\nAtivo: {symbol}\nPnL: {pnl_pct:.2f}%\nMotivo: {motivo}")
                            try:
                                requests.post(
                                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                                    json={"chat_id": tg_chat, "text": msg},
                                    timeout=5
                                )
                            except Exception:
                                pass

                        _sync_active_trades_from_db()
                    except Exception as close_err:
                        print(f"   [SL/TP AUTO] Falha ao fechar trade {trade_id}: {close_err}")

        except Exception as e:
            print(f"   [_monitor_sl_tp_automatico] erro: {e}")

        time.sleep(10)


def _sync_active_trades_from_db():
    """Sincroniza moedas abertas para o dashboard, agrupando por símbolo."""
    try:
        _repair_open_trades()
        open_trades = db.get_open_trades(50)
        grouped = {}

        for t in open_trades:
            if (t.get('status') or '').lower() != 'open':
                continue

            raw_symbol = _canonicalize_symbol(t.get('pair'))
            if not raw_symbol:
                continue

            key = _normalize_symbol_key(raw_symbol)
            margin = float(t.get('profit', 0) or 0)
            entry_price = _extract_entry_price(t)
            if margin <= 0 or entry_price <= 0:
                continue

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
            if entry_price > 0:
                trade_group['entry_price'] = entry_price
            if int(t.get('id') or 0) >= trade_group['latest_trade_id']:
                trade_group['id'] = t.get('id')
                trade_group['latest_trade_id'] = int(t.get('id') or 0)
                trade_group['notes'] = t.get('notes', '')

        central_state['active_trades'] = sorted(grouped.values(), key=lambda trade: trade.get('latest_trade_id', 0), reverse=True)

        for trade in central_state['active_trades']:
            live = _get_live_price_snapshot(trade.get('raw_symbol') or trade.get('symbol'), trade.get('entry_price'), trade.get('side'))
            trade.update(live)
            entry_margin = float(trade.get('entry', 0) or 0)
            pnl_pct = float(trade.get('pnl_pct', 0) or 0)
            trade['open_pnl_value'] = round((entry_margin * pnl_pct) / 100, 2) if entry_margin else 0.0
    except Exception as e:
        print(f"⚠️ [_sync_active_trades_from_db] erro: {e}")
        central_state['active_trades'] = []


def _close_stale_open_trades(max_age_minutes=180):
    """Fecha trades marcados como open há muito tempo para evitar travamento do motor."""
    try:
        open_trades = db.get_open_trades(100)
        if not open_trades:
            return 0

        now = datetime.now()
        closed_count = 0

        conn = db._connect()
        cur = conn.cursor()

        for t in open_trades:
            created_raw = str(t.get('created_at', '') or '').strip()
            if not created_raw:
                continue

            created_dt = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    created_dt = datetime.strptime(created_raw, fmt)
                    break
                except Exception:
                    continue

            if created_dt is None:
                try:
                    created_dt = datetime.fromisoformat(created_raw.replace('Z', ''))
                except Exception:
                    continue

            if (now - created_dt) > timedelta(minutes=max_age_minutes):
                trade_id = t.get('id')
                pair = t.get('pair', 'N/A')
                cur.execute(
                    "UPDATE trades SET status='closed', notes=COALESCE(notes,'') || ' | AUTO_CLOSE_STALE' WHERE id=?",
                    (trade_id,)
                )
                closed_count += 1
                print(f"🧹 [STALE CLOSE] trade_id={trade_id} pair={pair} fechado por idade > {max_age_minutes}min")

        conn.commit()
        conn.close()
        return closed_count
    except Exception as e:
        print(f"⚠️ [_close_stale_open_trades] erro: {e}")
        return 0


def _settle_paper_trades():
    """Fecha paper trades apenas por TP/SL real e calcula P&L aberto."""
    if not TEST_MODE_ENABLED:
        return 0.0

    open_pnl_total = 0.0

    try:
        open_trades = db.get_open_trades(100)
        for trade in open_trades:
            trade_id = trade.get('id')
            symbol = trade.get('pair')
            side = trade.get('side')
            margin = float(trade.get('profit', 0) or 0)
            entry_price = _extract_entry_price(trade)

            if margin <= 0 or entry_price <= 0 or not symbol:
                continue

            live = _get_live_price_snapshot(symbol, entry_price, side)
            pnl_pct = float(live.get('pnl_pct', 0) or 0)
            current_price = float(live.get('current_price', 0) or 0)
            pnl_value = round(margin * (pnl_pct / 100), 2)

            if pnl_pct >= PAPER_TRADE_TP_PCT or pnl_pct <= PAPER_TRADE_SL_PCT:
                reason = 'PAPER_TP_100' if pnl_pct >= PAPER_TRADE_TP_PCT else 'PAPER_SL_3'
                notes = f"{trade.get('notes', '')} | {reason} @ {current_price:.8f}"
                db.close_trade(
                    trade_id=trade_id,
                    pnl_pct=round(pnl_pct, 4),
                    profit=pnl_value,
                    closed_at=time.strftime("%d/%m %H:%M", time.localtime()),
                    notes=notes,
                )
                print(f"📘 [PAPER CLOSE] {symbol} {side} {pnl_pct:.2f}% => ${pnl_value:.2f} ({reason})")
                continue

            open_pnl_total += pnl_value

        central_state['paper_open_pnl'] = round(open_pnl_total, 2)
        return round(open_pnl_total, 2)
    except Exception as e:
        print(f"⚠️ [_settle_paper_trades] erro: {e}")
        return 0.0


def _manual_close_open_trades(symbol, requested_by="dashboard"):
    """Fecha manualmente todos os trades abertos do símbolo informado."""
    canonical_symbol = _canonicalize_symbol(symbol)
    if not canonical_symbol:
        raise ValueError("Símbolo inválido para fechamento manual.")

    normalized_symbol = _normalize_symbol_key(canonical_symbol)
    open_trades = db.get_open_trades(200)
    matching_trades = [
        trade for trade in open_trades
        if _normalize_symbol_key(_canonicalize_symbol(trade.get('pair')) or trade.get('pair')) == normalized_symbol
    ]

    if not matching_trades:
        return {
            "symbol": _limpar_simbolo(canonical_symbol),
            "closed_count": 0,
            "total_pnl_value": 0.0,
            "current_price": 0.0,
        }

    closed_at = time.strftime("%d/%m %H:%M", time.localtime())
    total_pnl_value = 0.0
    current_price_reference = 0.0
    closed_count = 0

    for trade in matching_trades:
        trade_id = trade.get('id')
        side = trade.get('side')
        margin = _coerce_float(trade.get('profit'), default=0.0)
        entry_price = _extract_entry_price(trade)
        if not trade_id or margin <= 0 or entry_price <= 0:
            continue

        live = _get_live_price_snapshot(canonical_symbol, entry_price, side)
        current_price = _coerce_float(live.get('current_price'), default=0.0)
        if current_price <= 0:
            continue

        pnl_pct = round(_coerce_float(live.get('pnl_pct'), default=0.0), 4)
        pnl_value = round(margin * (pnl_pct / 100), 2)
        notes = f"{trade.get('notes', '')} | MANUAL_CLOSE_{str(requested_by).upper()} @ {current_price:.8f}"

        if db.close_trade(
            trade_id=trade_id,
            pnl_pct=pnl_pct,
            profit=pnl_value,
            closed_at=closed_at,
            notes=notes,
        ):
            total_pnl_value += pnl_value
            current_price_reference = current_price
            closed_count += 1

    if closed_count and cloud_db and getattr(cloud_db, "is_available", lambda: False)():
        try:
            cloud_db.close_open_trades_by_symbol(
                canonical_symbol,
                current_price=current_price_reference,
                closed_at=closed_at,
                note_suffix=f"MANUAL_CLOSE_{str(requested_by).upper()}",
            )
        except Exception as cloud_err:
            print(f"⚠️ [SUPABASE] Falha ao fechar trades manualmente em nuvem: {cloud_err}")

    _sync_active_trades_from_db()
    central_state['trades'] = db.get_recent_trades(20)
    if closed_count:
        central_state['status'] = f"✅ Saída manual executada em {_limpar_simbolo(canonical_symbol)}"

    return {
        "symbol": _limpar_simbolo(canonical_symbol),
        "closed_count": closed_count,
        "total_pnl_value": round(total_pnl_value, 2),
        "current_price": round(current_price_reference, 8) if current_price_reference > 0 else 0.0,
    }

def broadcast_ordem_global(symbol, side, entry_price, res_ia):
    """
    DISPARO EM MASSA: 
    Lê todos os investidores do SQLite e replica a ordem e o sinal.
    """
    slot_reserved = False
    try:
        can_open, reason = _reserve_signal_slot(symbol)
        if not can_open:
            print(f"🔒 Bloqueio de Segurança: {reason}")
            return
        slot_reserved = True

        signal_snapshot = _build_last_sniper_signal(
            symbol,
            side,
            entry_price,
            res_ia.get('probabilidade'),
            res_ia.get('motivo'),
        )
        central_state['last_sniper_signal'] = signal_snapshot
        _push_recent_sniper_signal(signal_snapshot)

        # 1. Notificação Master (Para o seu Grupo VIP ou seu Bot de Controle)
        master_tk, master_chat = _get_master_telegram_config()
        if master_tk and master_chat:
            m_msg = (f"🚀 *SINAL SNIPER BROADCAST*\n\n"
                     f"📦 *Ativo:* {symbol}\n📈 *Lado:* {side}\n"
                     f"🎯 *Entrada:* ${entry_price}\n🧠 *Confiança:* {res_ia.get('probabilidade')}%")
            requests.post(f"https://api.telegram.org/bot{master_tk}/sendMessage", 
                          json={"chat_id": master_chat, "text": m_msg, "parse_mode": "Markdown"})

        # 2. Loop de Execução para Clientes Cadastrados
        clientes = _get_registered_clients(active_only=True)
        for cliente in clientes:
            def task_cliente(c):
                try:
                    account_mode = _normalize_account_mode(c.get('account_mode', c.get('is_testnet')))
                    broker = _ensure_broker_class()(
                        c.get('bybit_key'),
                        c.get('bybit_secret'),
                        testnet=_is_testnet_account(account_mode),
                    )
                    
                    # Gestão Dinâmica: 5% Banca (GAIN) / 3% (RECOVERY)
                    margem = float(c.get('saldo_base', 1000.0)) * 0.05
                    qty = margem / entry_price

                    # --- EXECUÇÃO REAL NA EXCHANGE (PROTOCOLO SNIPER) ---
                    if _is_order_execution_enabled(APP_MODE):
                        exec_label = 'TESTNET' if APP_MODE == 'testnet' else 'REAL'
                        print(f"🚀 [EXECUÇÃO {exec_label}] {c.get('nome')} - {side} {qty:.4f} {symbol}")
                        order_result = broker.execute_market_order(symbol, side.lower(), qty)
                        
                        if order_result:
                            # ✅ Executa Proteção: TP +100% / SL -3%
                            broker.set_tp_sl_sniper(symbol, side.lower(), entry_price, qty)
                            print(f"✅ [ORDEM EXECUTADA] ID: {order_result.get('id', 'N/A')}")
                        else:
                            print(f"⚠️  [ORDEM FALHADA] {c.get('nome')} - Fallback para simulação")
                    else:
                        if APP_MODE == 'paper':
                            mode_label = "PAPER TRADING / PREÇO REAL"
                        elif APP_MODE == 'testnet':
                            mode_label = "TESTNET / ORDENS BLOQUEADAS"
                        else:
                            mode_label = "SALDO REAL / ORDENS BLOQUEADAS"
                        print(f"📊 [{mode_label}] {c.get('nome')} - execução real bloqueada por segurança")

                    # --- NOTIFICAÇÃO PRIVADA EDUCATIVA (SNIPER PROTOCOL) ---
                    c_msg = (f"🎯 *SNIPER GIVALDO v60.1 - DISPARO CONFIRMADO*\n\n"
                             f"👤 *Trader:* {c.get('nome')}\n"
                             f"📦 *Ativo:* {symbol}\n"
                             f"📈 *Lado:* {side.upper()}\n"
                             f"💰 *Margem:* ${margem:.2f} (5% da banca)\n"
                             f"🎯 *Quantidade:* {qty:.4f}\n"
                             f"📍 *Entrada:* ${entry_price:.2f}\n\n"
                             f"🧠 *Confiança Cérebro Triplo:* {res_ia.get('probabilidade')}%\n"
                             f"📝 *Motivo:* {res_ia.get('motivo')}\n"
                             f"🔐 *Modo:* {_mode_display_label(APP_MODE)} • {_execution_status_label(APP_MODE)}\n"
                             f"👤 *Conta:* {account_mode.upper()}\n\n"
                             f"🛡️  *PROTEÇÃO ATIVA:*\n"
                             f"✅ TP: ${entry_price * 1.10:.2f} (+100% lucro)\n"
                             f"❌ SL: ${entry_price * 0.97:.2f} (-3% trava)\n\n"
                             f"⏱️ *Cooldown Institucional:* 10 min após fechamento")
                    
                    client_tg_token = str(c.get('tg_token') or '').strip()
                    client_chat_id = str(c.get('chat_id') or '').strip()
                    if client_tg_token and client_chat_id:
                        url_tg = f"https://api.telegram.org/bot{client_tg_token}/sendMessage"
                        requests.post(url_tg, json={"chat_id": client_chat_id, "text": c_msg, "parse_mode": "Markdown"})

                    # Regista no histórico do cliente (com status OPEN)
                    closed_at = time.strftime("%d/%m %H:%M", time.localtime())
                    db.record_trade(c.get('id'), symbol, side, 0.0, round(margem, 2), closed_at, 
                                  notes=f"SNIPER v60.1 - Conf: {res_ia.get('probabilidade')}% | Entrada: {entry_price:.8f}", status="open", entry_price=entry_price)

                    # --- SINCRONIZAÇÃO NUVEM (SUPABASE) ---
                    if cloud_db:
                        try:
                            cloud_db.record_trade({
                                "client_id": c.get('id'),
                                "pair": symbol,
                                "side": side,
                                "pnl_pct": 0.0,
                                "profit": round(margem, 2),
                                "entry_price": round(entry_price, 8),
                                "closed_at": closed_at,
                                "notes": f"SNIPER v60.1 - Conf: {res_ia.get('probabilidade')}%",
                                "status": "open",
                                "nome_cliente": c.get('nome') # Campo extra para facilitar análise na nuvem
                            })
                        except Exception as cloud_err:
                            print(f"⚠️ [SUPABASE] Falha sync trade {c.get('nome')}: {cloud_err}")

                except Exception as e:
                    print(f"❌ Falha na conta de {c.get('nome')}: {e}")

            threading.Thread(target=task_cliente, args=(cliente,)).start()

    except Exception as e:
        print(f"⚠️ Erro Crítico no Broadcast: {e}")
    finally:
        if slot_reserved:
            _release_signal_slot(symbol)

def _executar_trade_teste():
    """Legacy no-op: vitórias aleatórias foram desativadas por segurança."""
    if ENABLE_RANDOM_TEST_TRADES:
        print("⚠️ ENABLE_RANDOM_TEST_TRADES está ativo, mas esse modo não é recomendado.")
    return False

def sniper_worker_loop():
    """Motor Sniper que varre o mercado e atualiza o Dashboard sem travar."""
    global central_state, BybitClient, IndicatorEngine, GroqValidator
    
    # ⏳ Carregamento Lazy (apenas quando worker inicia)
    print("⏳ Carregando dependências pesadas (primeira vez)...")
    try:
        from src.broker.bybit_client import BybitClient
        from src.engine.indicators import IndicatorEngine
        from src.ai_brain.validator import GroqValidator
        print("✅ Dependências carregadas com sucesso")
    except ImportError as e:
        print(f"❌ Erro ao carregar: {e}")
        time.sleep(5)
        return
    
    # Scanner Master
    master_broker = BybitClient(
        *get_bybit_credentials(),
        testnet=_mode_uses_testnet(APP_MODE),
    )
    validator = GroqValidator(os.getenv("GEMINI_API_KEY"), os.getenv("GROQ_API_KEY"))

    print(f"🚀 Motor Sniper v60.1 Operante. Rigor: {THRESHOLD_ENTRADA}%")
    
    if TEST_MODE_ENABLED:
        print(f"🧪 {_mode_display_label(APP_MODE)} ATIVO - Saldo base: {TEST_BALANCE} USDT")
    else:
        print(f"💼 {_mode_display_label(APP_MODE)} - Saldo inicial sincronizado dos clientes")
    
    # Cache de tickers com TTL
    tickers_cache = {"data": [], "timestamp": 0}
    TICKERS_CACHE_TTL = 60
    
    # Memória de seleção para evitar repetição excessiva da mesma moeda
    last_signal_symbol = None
    last_signal_at = 0
    same_symbol_streak = 0

    while True:
        try:
            _repair_open_trades()
            if TEST_MODE_ENABLED:
                _settle_paper_trades()
            else:
                _close_stale_open_trades(max_age_minutes=180)

            if TEST_MODE_ENABLED:
                central_state['test_balance'] = TEST_BALANCE
                central_state['test_mode'] = True
                central_state['operation_mode'] = APP_MODE
                central_state['operation_mode_label'] = _mode_display_label(APP_MODE)
                central_state['execution_enabled'] = _is_order_execution_enabled(APP_MODE)
                central_state['execution_label'] = _execution_status_label(APP_MODE)
            pnl_lucro = _calcular_pnl_trades()
            _atualizar_saldo_com_pnl(pnl_lucro)
            _sync_active_trades_from_db()
            if len(central_state['active_trades']) >= MAX_MOEDAS_ATIVAS:
                central_state['status'] = f'📊 Monitorando {MAX_MOEDAS_ATIVAS} posições abertas...'
                current_active_symbol = central_state['active_trades'][0]['symbol']
                central_state['symbol'] = current_active_symbol
                time.sleep(5)
                continue
            else:
                central_state['symbol'] = '---'
                central_state['confidence'] = 0
                try:
                    current_time = time.time()
                    if current_time - tickers_cache['timestamp'] > TICKERS_CACHE_TTL or not tickers_cache['data']:
                        tickers = master_broker.exchange.fetch_tickers(params={'category': 'linear'})
                        top_coins = sorted([t for t in tickers.values() if 'USDT' in t.get('symbol', '') and ':' in t['symbol']], key=lambda x: x.get('quoteVolume', 0), reverse=True)[:SCAN_TOP_COINS]
                        tickers_cache['data'] = top_coins
                        tickers_cache['timestamp'] = current_time
                    top_coins = tickers_cache['data']
                    oportunidades = []

                    for idx_loop, t in enumerate(top_coins):
                        sym = t['symbol']
                        clean_sym = _limpar_simbolo(sym)
                        central_state['status'] = f'🔍 Radar: {clean_sym} ({idx_loop+1}/{len(top_coins)})'
                        try:
                            df = master_broker.fetch_ohlcv(sym, timeframe='15m')
                            if df is None or len(df) < 200:
                                continue

                            engine = IndicatorEngine(df)
                            signals = engine.get_signals()
                            local_score = validator.local_signal(signals)
                            
                            print(f"DEBUG {clean_sym}: Trend {signals['trend']} | Price {signals['price']} | SMA {signals['sma_200']}")

                            # Filtro rápido local: não chama cloud em ativo sem confluência mínima.
                            if local_score < 25:
                                continue

                            res = validator.consensus_predict(
                                signals,
                                sym,
                                force_local_only=USE_LOCAL_BRAIN_ONLY
                            )

                            prob = float(res.get('probabilidade', 0))
                            decisao = str(res.get('decisao', 'ABORTAR')).upper()
                            volume = float(t.get('quoteVolume', 0) or 0)

                            if prob >= THRESHOLD_ENTRADA and decisao in ['COMPRAR', 'VENDER', 'BUY', 'SELL']:
                                money_flow = _build_money_flow_metrics(signals, t, decisao)
                                edge = _get_symbol_trade_edge(sym, decisao)
                                # Score final: confiança + fluxo de dinheiro + liquidez + histórico
                                score = (
                                    prob
                                    + min(20.0, volume / 1_000_000)
                                    + (money_flow['money_flow_score'] * 0.35)
                                    + edge['edge_score']
                                )
                                oportunidades.append({
                                    'symbol': sym,
                                    'clean_symbol': clean_sym,
                                    'score': score,
                                    'probabilidade': prob,
                                    'res': res,
                                    'money_flow_score': money_flow['money_flow_score'],
                                    'money_flow_side': money_flow['money_flow_side'],
                                    'institutional_pressure': money_flow['institutional_pressure'],
                                    'volume_ratio': money_flow['volume_ratio'],
                                    'quote_volume_millions': money_flow['quote_volume_millions'],
                                    'recent_return_pct': money_flow['recent_return_pct'],
                                    'profit_total': edge['profit_total'],
                                    'win_rate': edge['win_rate'],
                                    'sample_size': edge['sample_size'],
                                })
                        except Exception:
                            continue

                        time.sleep(SCAN_INTER_SYMBOL_DELAY_SECS)

                    # Publica o ranking para o dashboard (Top 5)
                    oportunidades_ordenadas = sorted(oportunidades, key=lambda x: x['score'], reverse=True)
                    central_state['opportunities'] = [
                        {
                            'symbol': o['clean_symbol'],
                            'score': round(float(o['score']), 2),
                            'score_ajustado': round(float(o.get('adjusted_score', o['score'])), 2),
                            'probabilidade': round(float(o['probabilidade']), 2),
                            'decisao': str(o['res'].get('decisao', 'ABORTAR')).upper(),
                            'motivo': str(o['res'].get('motivo', 'Sem motivo')),
                            'money_flow_score': round(float(o.get('money_flow_score', 0)), 2),
                            'money_flow_side': str(o.get('money_flow_side', 'WAIT')),
                            'volume_ratio': round(float(o.get('volume_ratio', 0)), 2),
                            'profit_total': round(float(o.get('profit_total', 0)), 2),
                            'win_rate': round(float(o.get('win_rate', 0)), 2),
                            'sample_size': int(o.get('sample_size', 0) or 0),
                        }
                        for o in oportunidades_ordenadas[:5]
                    ]

                    if oportunidades_ordenadas:
                        agora = time.time()
                        open_symbols = {str(t.get('symbol', '')).upper() for t in central_state.get('active_trades', [])}

                        # Aplica penalizações para diversificar escolhas
                        melhor = None
                        best_adjusted = -9999

                        for cand in oportunidades_ordenadas:
                            adjusted = float(cand['score'])
                            clean_upper = str(cand['clean_symbol']).upper()

                            if clean_upper in open_symbols:
                                adjusted -= PENALIDADE_MOEDA_JA_ABERTA

                            if cand['clean_symbol'] == last_signal_symbol:
                                # Bloqueio duro por janela de tempo
                                if (agora - last_signal_at) < BLOQUEIO_REPETICAO_MOEDA_SECS:
                                    adjusted -= 1000
                                # Penalidade por repetição sequencial
                                adjusted -= (same_symbol_streak * PENALIDADE_STREAK_MESMA_MOEDA)

                            cand['adjusted_score'] = adjusted
                            if adjusted > best_adjusted:
                                best_adjusted = adjusted
                                melhor = cand

                        # Atualiza painel já com score ajustado para leitura visual do ranking
                        central_state['opportunities'] = [
                            {
                                'symbol': o['clean_symbol'],
                                'score': round(float(o['score']), 2),
                                'score_ajustado': round(float(o.get('adjusted_score', o['score'])), 2),
                                'probabilidade': round(float(o['probabilidade']), 2),
                                'decisao': str(o['res'].get('decisao', 'ABORTAR')).upper(),
                                'motivo': str(o['res'].get('motivo', 'Sem motivo')),
                                'money_flow_score': round(float(o.get('money_flow_score', 0)), 2),
                                'money_flow_side': str(o.get('money_flow_side', 'WAIT')),
                                'volume_ratio': round(float(o.get('volume_ratio', 0)), 2),
                                'profit_total': round(float(o.get('profit_total', 0)), 2),
                                'win_rate': round(float(o.get('win_rate', 0)), 2),
                                'sample_size': int(o.get('sample_size', 0) or 0),
                            }
                            for o in sorted(oportunidades_ordenadas, key=lambda x: x.get('adjusted_score', x['score']), reverse=True)[:5]
                        ]

                        if melhor is None or best_adjusted <= 0:
                            central_state['status'] = '🔄 Diversificação ativa: aguardando novo ativo elegível.'
                            time.sleep(60)
                            continue

                        central_state['symbol'] = melhor['clean_symbol']
                        central_state['confidence'] = melhor['probabilidade']
                        central_state['ia2_decision']['motivo'] = melhor['res'].get('motivo', 'Confluência detectada')
                        broadcast_ordem_global(
                            melhor['symbol'],
                            melhor['res'].get('decisao', 'ABORTAR'),
                            master_broker.get_last_price(melhor['symbol']),
                            melhor['res']
                        )
                        central_state['status'] = f"📊 SINAL ABERTO: {melhor['clean_symbol']} ({melhor['probabilidade']:.0f}%)"

                        # Atualiza memória anti-repetição
                        if melhor['clean_symbol'] == last_signal_symbol:
                            same_symbol_streak += 1
                        else:
                            last_signal_symbol = melhor['clean_symbol']
                            same_symbol_streak = 1
                        last_signal_at = agora

                        time.sleep(COOLDOWN_INSTITUCIONAL_SECS)
                    else:
                        central_state['opportunities'] = []
                        central_state['status'] = f'✅ Analisados {len(top_coins)} ativos. Sem confluência no rigor atual.'

                    time.sleep(60)
                except Exception:
                    time.sleep(15)
        except Exception as e:
            print(f'⚠️ [LOOP ERRO] {e}')
            time.sleep(15)

def health_check():
    """Health check para monitorar worker thread."""
    try:
        return jsonify({
            "status": "online",
            "worker_status": central_state.get('status', 'unknown'),
            "balance": central_state.get('balance', 0),
            "active_trades": len(central_state.get('active_trades', [])),
            "timestamp": time.time()
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/api/investidores', methods=['GET'])
def get_investidores():
    """Lista investidores do Supabase quando disponível, com fallback local."""
    try:
        rows = _get_registered_clients(active_only=False)
        balance_map = {item.get('id'): item for item in _fetch_active_client_balances().get('items', [])}
        return jsonify([{
            "id": r.get('id'),
            "nome": r.get('nome'),
            "banca": (balance_map.get(r.get('id')) or {}).get('saldo_real', r.get('saldo_base', 0)),
            "saldo_real": (balance_map.get(r.get('id')) or {}).get('saldo_real'),
            "saldo_configurado": r.get('saldo_base', 0),
            "status": r.get('status'),
            "mode": _normalize_account_mode(r.get('account_mode', r.get('is_testnet'))).upper(),
            "account_mode": _normalize_account_mode(r.get('account_mode', r.get('is_testnet'))),
            "balance_source": r.get('balance_source'),
        } for r in rows])
    except: return jsonify([])


@app.route('/api/cliente/<int:client_id>', methods=['GET'])
def api_get_cliente(client_id):
    """Retorna os dados completos de um cliente por id."""
    try:
        c = _get_registered_client_by_id(client_id)
        if not c:
            return jsonify({"error": "Cliente não encontrado"}), 404
        return jsonify(c)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/cliente/<int:client_id>', methods=['PUT'])
def api_update_cliente(client_id):
    """Atualiza um cliente existente."""
    data = request.json or {}
    try:
        account_mode = _normalize_account_mode(data.get('account_mode', data.get('is_testnet')))
        existing_client = _get_registered_client_by_id(client_id)
        validation = validar_e_salvar_cliente(
            data.get('bybit_key'),
            data.get('bybit_secret'),
            _is_testnet_account(account_mode),
            client_payload=data,
            client_id=client_id,
            existing_client=existing_client,
        )
        ok = validation.get('valid', False)
        msg = validation.get('msg')
        record = validation.get('record')
        cloud_synced = validation.get('synced_to_cloud', False)
        local_synced = validation.get('synced_to_local', False)
        if record:
            return jsonify({
                "success": True,
                "msg": f"Cliente atualizado! Conta {validation.get('account_mode', account_mode).upper()} sincronizada com a Bybit.",
                "valid": ok,
                "api_error": None if ok else msg,
                "recv_window": validation.get('recv_window'),
                "bybit_base_url": validation.get('base_url'),
                "client": record,
                "synced_to_cloud": cloud_synced,
                "synced_to_local": local_synced,
            })
        return jsonify({
            "error": "Falha ao atualizar",
            "valid": ok,
            "synced_to_cloud": cloud_synced,
            "synced_to_local": local_synced,
        }), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/cliente/<int:client_id>', methods=['DELETE'])
def api_delete_cliente(client_id):
    """Deleta um cliente do sistema."""
    try:
        cloud_deleted, local_deleted = _delete_client_everywhere(client_id)
        if cloud_deleted or local_deleted:
            return jsonify({
                "success": True,
                "msg": "Cliente removido",
                "deleted_from_cloud": cloud_deleted,
                "deleted_from_local": local_deleted,
            })
        return jsonify({"error": "Falha ao remover cliente"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/vincular_cliente', methods=['POST'])
def add_cliente():
    """Recebe novos investidores do formulário SaaS."""
    data = request.json
    try:
        account_mode = _normalize_account_mode(data.get('account_mode', data.get('is_testnet')))
        validation = validar_e_salvar_cliente(
            data.get('bybit_key'),
            data.get('bybit_secret'),
            _is_testnet_account(account_mode),
            client_payload=data,
        )
        ok = validation.get('valid', False)
        msg = validation.get('msg')
        record = validation.get('record')
        cloud_synced = validation.get('synced_to_cloud', False)
        local_synced = validation.get('synced_to_local', False)
        if record:
            return jsonify({
                "status": "sucesso",
                "msg": f"Investidor conectado! Conta {validation.get('account_mode', account_mode).upper()} validada na Bybit.",
                "valid": ok,
                "api_error": None if ok else msg,
                "recv_window": validation.get('recv_window'),
                "bybit_base_url": validation.get('base_url'),
                "client": record,
                "synced_to_cloud": cloud_synced,
                "synced_to_local": local_synced,
            })
        return jsonify({"status": "erro", "msg": "Falha ao salvar investidor"}), 500
    except Exception as e:
        return jsonify({"status": "erro", "msg": str(e)}), 400


@app.route('/api/server-ip', methods=['GET'])
def get_server_ip():
    try:
        import urllib.request
        with urllib.request.urlopen('https://api.ipify.org', timeout=5) as resp:
            ip = resp.read().decode('utf-8').strip()
        return jsonify({'server_ip': ip})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        _repair_open_trades()
        _refresh_real_balance_state()
        _sync_active_trades_from_db()
        _refresh_last_sniper_signal()
        central_state['trades'] = db.get_recent_trades(20)
        return jsonify(central_state)
    except:
        return jsonify(central_state)


@app.route('/api/trade/manual-close', methods=['POST'])
def api_manual_close_trade():
    """Fecha manualmente uma operação aberta por símbolo."""
    data = request.json or {}
    try:
        symbol = data.get('symbol')
        result = _manual_close_open_trades(symbol, requested_by='dashboard')
        if result.get('closed_count', 0) <= 0:
            return jsonify({
                "success": False,
                "error": "Nenhuma operação aberta elegível para fechamento manual.",
                **result,
            }), 404

        return jsonify({
            "success": True,
            "msg": f"Saída manual executada em {result['symbol']}.",
            **result,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/trades/client/<int:client_id>', methods=['GET'])
def get_client_trades(client_id):
    """Retorna histórico de trades de um cliente específico."""
    try:
        conn = db._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, pair, side, pnl_pct, profit, closed_at, status 
            FROM trades 
            WHERE client_id = ? 
            ORDER BY id DESC LIMIT 50
        """, (client_id,))
        trades = [dict(row) for row in cur.fetchall()]
        conn.close()
        return jsonify(trades)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/performance/neural_memory', methods=['GET'])
def get_neural_performance():
    """Retorna relatório de performance do Cérebro Triplo."""
    try:
        from src.ai_brain.learning import TradeLearner
        learner = TradeLearner()
        report = learner.get_performance_report()
        return jsonify({"report": report})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/dashboard/balance', methods=['GET'])
def update_dashboard_balance():
    """Atualiza saldo do Dashboard em tempo real."""
    try:
        if TEST_MODE_ENABLED:
            return jsonify({
                "balance": TEST_BALANCE,
                "status": central_state.get('status'),
                "symbol": central_state['symbol'],
                "confidence": central_state['confidence'],
                "test_mode": True,
                "operation_mode": APP_MODE,
                "operation_mode_label": _mode_display_label(APP_MODE),
                "execution_enabled": _is_order_execution_enabled(APP_MODE),
                "execution_label": _execution_status_label(APP_MODE),
            })
        
        _refresh_real_balance_state(force=True)
        
        return jsonify({
            "balance": central_state['balance'],
            "status": central_state['status'],
            "symbol": central_state['symbol'],
            "confidence": central_state['confidence'],
            "test_mode": False,
            "operation_mode": APP_MODE,
            "operation_mode_label": _mode_display_label(APP_MODE),
            "execution_enabled": _is_order_execution_enabled(APP_MODE),
            "execution_label": _execution_status_label(APP_MODE),
            "real_client_balances": central_state.get('real_client_balances', []),
        })
    except Exception as e:
        # Fallback para saldo de teste se broker falhar
        return jsonify({
            "balance": TEST_BALANCE,
            "status": f"⚠️ Broker indisponível. Usando saldo teste: {TEST_BALANCE} USDT",
            "symbol": central_state['symbol'],
            "confidence": central_state['confidence'],
            "test_mode": True,
            "operation_mode": APP_MODE,
            "operation_mode_label": _mode_display_label(APP_MODE),
            "execution_enabled": _is_order_execution_enabled(APP_MODE),
            "execution_label": _execution_status_label(APP_MODE),
            "error": str(e)
        })

@app.route('/api/sinal/test', methods=['POST'])
def test_signal():
    """Testa um sinal manualmente (para debugging)."""
    data = request.json
    try:
        validator = GroqValidator(os.getenv("GEMINI_API_KEY"), os.getenv("GROQ_API_KEY"))
        
        # Simula dados técnicos
        tech_data = {
            'trend': data.get('trend', 'ALTA'),
            'price': float(data.get('price', 0)),
            'sma_200': float(data.get('sma_200', 0)),
            'rsi': float(data.get('rsi', 50)),
            'fib_618': float(data.get('fib_618', 0)),
            'volume_trend': data.get('volume_trend', 'ALTO')
        }
        
        result = validator.consensus_predict(tech_data, data.get('symbol', 'BTCUSDT'))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/test/set-balance', methods=['POST'])
def set_test_balance():
    """🧪 BOTÃO TESTE: Define saldo inicial para testes.
    
    Exemplo:
    POST /api/test/set-balance
    {"balance": 1000.50, "currency": "USDT"}
    """
    data = request.json
    try:
        test_balance = float(data.get('balance', 1000.0))
        currency = data.get('currency', 'USDT')
        global TEST_BALANCE
        TEST_BALANCE = round(test_balance, 2)
        
        # Armazena em memória + DB
        central_state['balance'] = TEST_BALANCE
        central_state['test_balance'] = TEST_BALANCE
        central_state['status'] = f"🧪 {_mode_display_label(APP_MODE)}: saldo base {TEST_BALANCE} {currency}"
        db.set_test_balance(TEST_BALANCE)
        db.set_config('INITIAL_BALANCE', str(TEST_BALANCE))
        
        print(f"🧪 [PAPER] Saldo configurado: {TEST_BALANCE} {currency}")
        return jsonify({
            "success": True,
            "balance": TEST_BALANCE,
            "currency": currency,
            "mode": "TEST",
            "msg": "✅ Saldo base do paper trading configurado com sucesso."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/test/get-balance', methods=['GET'])
def get_test_balance():
    """Retorna saldo atual de teste."""
    try:
        return jsonify({
            "balance": central_state.get('balance', 0),
            "status": central_state.get('status', 'desconhecido'),
            "mode": "TEST" if "TESTE" in central_state.get('status', '') else "LIVE"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/brain/only-local', methods=['POST'])
def force_local_brain():
    """🧠 FORÇAR 3º CÉREBRO APENAS: Usa só análise local (SMA 200, Fibonacci, RSI).
    
    Útil quando Groq/Gemini estão no limite. O sistema aprende com histórico.
    """
    global USE_LOCAL_BRAIN_ONLY
    try:
        action = request.json.get('action', 'toggle')
        
        if action == 'enable':
            USE_LOCAL_BRAIN_ONLY = True
            central_state['ia2_decision']['brains']['groq'] = 'disabled'
            central_state['ia2_decision']['brains']['gemini'] = 'disabled'
            central_state['ia2_decision']['brains']['local'] = 'ONLY'
            msg = "🧠 [3º CÉREBRO] Sistema usando APENAS análise LOCAL (matemática pura)"
        elif action == 'disable':
            USE_LOCAL_BRAIN_ONLY = False
            central_state['ia2_decision']['brains']['local'] = 'enabled'
            central_state['ia2_decision']['brains']['groq'] = 'online'
            central_state['ia2_decision']['brains']['gemini'] = 'online'
            msg = "🧠 [CÉREBRO TRIPLO] Sistema voltou ao consenso ponderado (Gemini 40% | Groq 35% | Local 25%)"
        
        print(msg)
        return jsonify({
            "success": True,
            "mode": action,
            "use_local_only": USE_LOCAL_BRAIN_ONLY,
            "brains": central_state['ia2_decision']['brains'],
            "msg": msg
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/brain/learn-from-history', methods=['POST'])
def learn_from_history():
    """📚 APRENDIZADO: 3º Cérebro aprende com histórico de trades para melhorar scores locais.
    
    POST /api/brain/learn-from-history
    {"last_n_trades": 50, "min_pnl_pct": 1.0}
    """
    try:
        last_n = int(request.json.get('last_n_trades', 50))
        min_pnl = float(request.json.get('min_pnl_pct', 0.5))
        
        # Busca trades recentes
        trades = db.get_recent_trades(last_n)
        winning_trades = [t for t in trades if t.get('pnl_pct', 0) >= min_pnl]
        losing_trades = [t for t in trades if t.get('pnl_pct', 0) < min_pnl]
        
        # Passa para TradeLearner
        from src.ai_brain.learning import TradeLearner
        learner = TradeLearner()
        
        for trade in winning_trades:
            learner.record_win(trade.get('symbol', 'UNKNOWN'), trade.get('pnl_pct', 0))
        
        for trade in losing_trades:
            learner.record_loss(trade.get('symbol', 'UNKNOWN'), trade.get('pnl_pct', 0))
        
        # Salva contexto
        learner.save_memory()
        
        stats = learner.get_performance_report()
        
        print(f"📚 [APRENDIZADO] Processados {last_n} trades: {len(winning_trades)} wins, {len(losing_trades)} losses")
        return jsonify({
            "success": True,
            "trades_processed": last_n,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": f"{(len(winning_trades)/max(1, last_n))*100:.1f}%",
            "stats": stats,
            "msg": "✅ 3º Cérebro aprendeu com o histórico!"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/mode/toggle', methods=['POST'])
def toggle_test_mode():
    """🔄 ALTERNAR ENTRE PAPER, TESTNET E REAL
    
    POST /api/mode/toggle
    {"mode": "paper"} | {"mode": "testnet"} | {"mode": "real"}
    """
    global APP_MODE, TEST_BALANCE
    
    try:
        new_mode = _normalize_operation_mode((request.json or {}).get('mode', 'paper'))
        
        if new_mode not in VALID_OPERATION_MODES:
            return jsonify({"error": "Mode deve ser 'paper', 'testnet' ou 'real'"}), 400
        
        APP_MODE = new_mode
        _sync_runtime_mode_state(persist=True)

        if TEST_MODE_ENABLED:
            TEST_BALANCE = db.get_test_balance()
            central_state['balance'] = TEST_BALANCE
            central_state['test_balance'] = TEST_BALANCE
        else:
            _refresh_real_balance_state(force=True)
        
        # Log
        mode_name = _mode_display_label(APP_MODE)
        mode_emoji = "🧪" if APP_MODE == 'paper' else ("🛰️" if APP_MODE == 'testnet' else "💼")
        print(f"\n{mode_emoji} ALTERNAÇÃO DE MODO: {mode_name}")
        print(f"   Status: {central_state['status']}")
        print(f"   Execução: {_execution_status_label(APP_MODE)}")
        if TEST_MODE_ENABLED:
            print(f"   Saldo: {TEST_BALANCE} USDT (paper trading)")
        print()
        
        return jsonify({
            "success": True,
            "mode": new_mode,
            "operation_mode": APP_MODE,
            "operation_mode_label": mode_name,
            "status": central_state['status'],
            "balance": TEST_BALANCE if TEST_MODE_ENABLED else "Broker (será buscado)",
            "execution_enabled": _is_order_execution_enabled(APP_MODE),
            "execution_label": _execution_status_label(APP_MODE),
            "message": f"✅ Sistema alternado para {mode_name}!"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/mode/current', methods=['GET'])
def get_current_mode():
    """📊 RETORNA MODO ATUAL (PAPER, TESTNET OU REAL)"""
    try:
        return jsonify({
            "mode": APP_MODE,
            "operation_mode": APP_MODE,
            "operation_mode_label": _mode_display_label(APP_MODE),
            "is_test": TEST_MODE_ENABLED,
            "status": central_state.get('status', 'desconhecido'),
            "balance": TEST_BALANCE if TEST_MODE_ENABLED else "Carregando do broker...",
            "execution_enabled": _is_order_execution_enabled(APP_MODE),
            "execution_label": _execution_status_label(APP_MODE),
            "emoji": "🧪" if APP_MODE == 'paper' else ("🛰️" if APP_MODE == 'testnet' else "💼")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/sniper/broadcast', methods=['POST'])
def sniper_broadcast_signal():
    """🚀 RECEBE SINAL SNIPER BROADCAST E EXECUTA OPERAÇÃO
    
    POST /api/sniper/broadcast
    {
        "symbol": "BTC/USDT",
        "side": "VENDER",
        "entry_price": 74486.1,
        "confidence": 70,
        "reason": "Confluência 70% detectada"
    }
    """
    slot_reserved = False
    try:
        payload = _sanitize_signal_payload(request.json)
        symbol = payload['symbol']
        side = payload['side']
        entry_price = payload['entry_price']
        confidence = payload['confidence']
        reason = payload['reason']
        can_open, block_reason = _reserve_signal_slot(symbol)
        if not can_open:
            return jsonify({"error": block_reason}), 409
        slot_reserved = True
        signal_snapshot = _build_last_sniper_signal(symbol, side, entry_price, confidence, reason)
        
        # Atualiza central_state
        symbol_limpo = _limpar_simbolo(symbol)
        central_state['symbol'] = symbol_limpo
        central_state['confidence'] = confidence
        central_state['status'] = f"🎯 SINAL BROADCAST: {side} {symbol_limpo} @ ${entry_price:.2f}"
        central_state['last_sniper_signal'] = signal_snapshot
        _push_recent_sniper_signal(signal_snapshot)
        central_state['ia2_decision']['motivo'] = reason
        
        # Registra operação no banco
        db.record_trade(
            client_id=1,
            pair=symbol,
            side=side,
            pnl_pct=0,
            profit=round(_get_initial_test_balance() * 0.05, 2),
            closed_at=time.strftime("%d/%m %H:%M", time.localtime()),
            notes=f"BROADCAST: {side} {symbol} @ {entry_price:.2f} | Conf: {confidence}% | {reason}",
            status="open",
            entry_price=entry_price,
        )

        # Atualiza ativo em aberto imediatamente para aparecer no frontend sem esperar o loop.
        _sync_active_trades_from_db()
        
        print(f"\n{'='*60}")
        print(f"🚀 SINAL SNIPER BROADCAST RECEBIDO")
        print(f"{'='*60}")
        print(f"   📦 Ativo: {symbol}")
        print(f"   📈 Lado: {side}")
        print(f"   🎯 Entrada: ${entry_price:.2f}")
        print(f"   🧠 Confiança: {confidence}%")
        print(f"   📝 Motivo: {reason}")
        print(f"{'='*60}\n")
        
        return jsonify({
            "success": True,
            "status": "✅ Sinal Broadcast Executado!",
            "symbol": symbol_limpo,
            "side": side,
            "entry_price": entry_price,
            "confidence": confidence,
            "message": f"Operação {side} {symbol} registrada com sucesso"
        })
    except Exception as e:
        print(f"❌ Erro ao processar broadcast: {e}")
        return jsonify({"error": str(e)}), 400
    finally:
        if slot_reserved:
            _release_signal_slot(symbol)

if __name__ == "__main__":
    render_port = int(os.getenv("PORT", "5000"))

    start_runtime_services()

    print(f"✅ DuoIA Maestro v60.1 Online na Porta {render_port}")

    print(f"💰 Saldo Carregado: {TEST_BALANCE} USDT")
    print(f"🧭 Modo operacional: {_mode_display_label(APP_MODE)}")
    print(f"⚡ Execução: {_execution_status_label(APP_MODE)}")
    if TEST_MODE_ENABLED:
        print("🧪 Paper ativo - preço real, saldo fictício, sem ordens")
    print(f"📊 Dashboard: http://0.0.0.0:{render_port}")
    print("🧠 Cérebro Triplo: ATIVO (Rigor 50%)")
    app.run(host='0.0.0.0', port=render_port, debug=False, use_reloader=False)

