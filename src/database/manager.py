import sqlite3
import os
from typing import List, Dict, Any
from src.config import get_environment_config

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'database.db')
VALID_ACCOUNT_MODES = {'testnet', 'real'}
VALID_OPERATION_MODES = {'paper', 'testnet', 'real'}


def is_truthy(value: Any) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def normalize_account_mode(value: Any) -> str:
    normalized = str(value or '').strip().lower()
    if normalized in VALID_ACCOUNT_MODES:
        return normalized
    if value in [True, 1, '1', 'true', 'TRUE', 'True']:
        return 'testnet'
    if value in [False, 0, '0', 'false', 'FALSE', 'False']:
        return 'real'
    return 'testnet'


def normalize_operation_mode(value: Any) -> str:
    normalized = str(value or '').strip().lower()
    if normalized == 'test':
        return 'paper'
    if normalized in VALID_OPERATION_MODES:
        return normalized
    return 'paper'


def _connect():
    """Conecta ao banco com timeout de 5s para evitar travamentos"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    # Habilita WAL mode para evitar travamentos
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    return conn


def _ensure_column(cur, table: str, column: str, definition: str):
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cur.fetchall()}
    if column not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    """Inicializa banco com tabelas otimizadas e sem travamentos"""
    conn = _connect()
    cur = conn.cursor()
    
    # Tabela principal: Clientes/Pessoas cadastradas
    cur.execute('''
    CREATE TABLE IF NOT EXISTS clientes_sniper (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        bybit_key TEXT,
        bybit_secret TEXT,
        tg_token TEXT,
        tg_api_key TEXT,
        chat_id TEXT,
        status TEXT DEFAULT 'ativo',
        saldo_base REAL DEFAULT 1000.0,
        is_testnet INTEGER DEFAULT 1,
        account_mode TEXT DEFAULT 'testnet',
        balance_source TEXT DEFAULT 'broker_testnet_balance',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    _ensure_column(cur, 'clientes_sniper', 'account_mode', "TEXT DEFAULT 'testnet'")
    _ensure_column(cur, 'clientes_sniper', 'balance_source', "TEXT DEFAULT 'broker_testnet_balance'")
    cur.execute("""
        UPDATE clientes_sniper
        SET account_mode = CASE
            WHEN COALESCE(is_testnet, 1) = 1 THEN 'testnet'
            ELSE 'real'
        END
        WHERE account_mode IS NULL OR TRIM(account_mode) = ''
    """)
    cur.execute("""
        UPDATE clientes_sniper
        SET balance_source = CASE
            WHEN COALESCE(account_mode, 'testnet') = 'testnet' THEN 'broker_testnet_balance'
            ELSE 'broker_real_balance'
        END
        WHERE balance_source IS NULL OR TRIM(balance_source) = ''
    """)

    # Tabela de histórico de trades (para P&L tracking)
    cur.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        pair TEXT,
        side TEXT,
        pnl_pct REAL,
        profit REAL,
        entry_price REAL DEFAULT 0,
        closed_at TEXT,
        notes TEXT,
        status TEXT DEFAULT 'closed',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    _ensure_column(cur, 'trades', 'entry_price', 'REAL DEFAULT 0')

    # Tabela de configuração global (TEST_MODE, TEST_BALANCE, etc)
    cur.execute('''
    CREATE TABLE IF NOT EXISTS config (
        k TEXT PRIMARY KEY,
        v TEXT
    )
    ''')

    conn.commit()
    conn.close()


def get_active_clients() -> List[Dict[str, Any]]:
    """Retorna apenas clientes cadastrados com status ativo"""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM clientes_sniper WHERE status='ativo' ORDER BY created_at DESC")
        rows = cur.fetchall()
        clients = [dict(r) for r in rows]
        conn.close()
        return clients
    except Exception as e:
        print(f"⚠️ Erro ao buscar clientes ativos: {e}")
        return []


def get_all_clients() -> List[Dict[str, Any]]:
    """Retorna todos os clientes cadastrados"""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM clientes_sniper ORDER BY created_at DESC")
        rows = cur.fetchall()
        clients = [dict(r) for r in rows]
        conn.close()
        return clients
    except Exception as e:
        print(f"⚠️ Erro ao buscar clientes: {e}")
        return []


def add_client(data: Dict[str, Any]):
    """Adiciona ou espelha um cliente localmente. Retorna o id persistido."""
    try:
        conn = _connect()
        cur = conn.cursor()
        account_mode = normalize_account_mode(data.get('account_mode', data.get('is_testnet')))
        balance_source = str(
            data.get(
                'balance_source',
                'broker_testnet_balance' if account_mode == 'testnet' else 'broker_real_balance',
            )
        )
        payload = (
            data.get('nome'),
            data.get('bybit_key'),
            data.get('bybit_secret'),
            data.get('tg_token'),
            data.get('tg_api_key'),
            data.get('chat_id'),
            data.get('status', 'ativo'),
            data.get('saldo_base', 1000.0),
            1 if account_mode == 'testnet' else 0,
            account_mode,
            balance_source,
        )
        explicit_id = data.get('id')

        if explicit_id is not None:
            existing = get_client_by_id(int(explicit_id))
            if existing:
                conn.close()
                return int(explicit_id) if update_client(int(explicit_id), data) else False

            cur.execute(
                'INSERT INTO clientes_sniper (id, nome, bybit_key, bybit_secret, tg_token, tg_api_key, chat_id, status, saldo_base, is_testnet, account_mode, balance_source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (int(explicit_id), *payload)
            )
            inserted_id = int(explicit_id)
        else:
            cur.execute(
                'INSERT INTO clientes_sniper (nome, bybit_key, bybit_secret, tg_token, tg_api_key, chat_id, status, saldo_base, is_testnet, account_mode, balance_source) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                payload
            )
            inserted_id = cur.lastrowid
        conn.commit()
        conn.close()
        return inserted_id
    except Exception as e:
        print(f"⚠️ Erro ao adicionar cliente: {e}")
        return False


def record_trade(
    client_id: int,
    pair: str,
    side: str,
    pnl_pct: float,
    profit: float,
    closed_at: str,
    notes: str = '',
    status: str = 'closed',
    entry_price: float = 0.0,
):
    # Normaliza notas para facilitar filtros na UI (ex: SNIPER, BROADCAST, AUTO)
    notes_clean = (notes or '').strip()
    try:
        notes_clean = notes_clean.upper()
    except Exception:
        notes_clean = str(notes_clean)

    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO trades (client_id, pair, side, pnl_pct, profit, entry_price, closed_at, notes, status) VALUES (?,?,?,?,?,?,?,?,?)',
        (client_id, pair, side, pnl_pct, profit, entry_price, closed_at, notes_clean, status.lower())
    )
    conn.commit()
    conn.close()


def close_trade(
    trade_id: int,
    pnl_pct: float,
    profit: float,
    closed_at: str,
    notes: str = '',
) -> bool:
    """Fecha um trade em aberto preservando histórico e notas."""
    notes_clean = (notes or '').strip()
    try:
        notes_clean = notes_clean.upper()
    except Exception:
        notes_clean = str(notes_clean)

    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            '''
            UPDATE trades
            SET pnl_pct = ?,
                profit = ?,
                closed_at = ?,
                notes = ?,
                status = 'closed'
            WHERE id = ?
            ''',
            (pnl_pct, profit, closed_at, notes_clean, trade_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️ Erro ao fechar trade {trade_id}: {e}")
        return False


def get_client_by_id(client_id: int) -> Dict[str, Any]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute('SELECT * FROM clientes_sniper WHERE id=?', (client_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_client(client_id: int, data: Dict[str, Any]) -> bool:
    """Atualiza informações de um cliente existente."""
    try:
        conn = _connect()
        cur = conn.cursor()
        account_mode = normalize_account_mode(data.get('account_mode', data.get('is_testnet')))
        balance_source = str(
            data.get(
                'balance_source',
                'broker_testnet_balance' if account_mode == 'testnet' else 'broker_real_balance',
            )
        )
        cur.execute(
            "UPDATE clientes_sniper SET nome=?, bybit_key=?, bybit_secret=?, tg_token=?, tg_api_key=?, chat_id=?, status=?, saldo_base=?, is_testnet=?, account_mode=?, balance_source=? WHERE id=?",
            (
                data.get('nome'),
                data.get('bybit_key'),
                data.get('bybit_secret'),
                data.get('tg_token'),
                data.get('tg_api_key'),
                data.get('chat_id'),
                data.get('status', 'ativo'),
                data.get('saldo_base', 1000.0),
                1 if account_mode == 'testnet' else 0,
                account_mode,
                balance_source,
                client_id,
            ),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️ Erro ao atualizar cliente {client_id}: {e}")
        return False


def upsert_client_local(data: Dict[str, Any]) -> bool:
    """Espelha um cliente vindo da nuvem no SQLite local."""
    client_id = data.get('id')
    if client_id is None:
        return bool(add_client(data))

    if get_client_by_id(int(client_id)):
        return update_client(int(client_id), data)

    return bool(add_client(data))


def delete_client(client_id: int) -> bool:
    """Remove um cliente e seus trades associados para evitar erros de integridade."""
    try:
        conn = _connect()
        cur = conn.cursor()
        # Primeiro remove os trades do cliente
        cur.execute("DELETE FROM trades WHERE client_id = ?", (client_id,))
        # Depois remove o cliente
        cur.execute("DELETE FROM clientes_sniper WHERE id = ?", (client_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️ Erro ao deletar cliente {client_id}: {e}")
        return False


def get_open_trades(limit: int = 50) -> List[Dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT t.*, c.nome FROM trades t "
        "LEFT JOIN clientes_sniper c ON c.id = t.client_id "
        "WHERE LOWER(COALESCE(t.status, 'closed')) = 'open' "
        "ORDER BY t.id DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    trades = [dict(r) for r in rows]
    conn.close()
    return trades


def get_recent_trades(limit: int = 50) -> List[Dict[str, Any]]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute('SELECT t.*, c.nome FROM trades t LEFT JOIN clientes_sniper c ON c.id = t.client_id ORDER BY t.id DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    trades = [dict(r) for r in rows]
    conn.close()
    return trades


def get_last_closed_trade(client_id: int) -> Dict[str, Any]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM trades WHERE client_id = ? AND LOWER(COALESCE(status, 'closed')) = 'closed' ORDER BY id DESC LIMIT 1",
        (client_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ============================================================================
# 🧪 CONFIGURAÇÕES DE TESTE (TEST BALANCE & MODE)
# ============================================================================

def get_config(key: str, default: str = None) -> str:
    """Lê uma configuração do banco de dados"""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT v FROM config WHERE k = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default


def set_config(key: str, value: str) -> bool:
    """Escreve/atualiza uma configuração"""
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM config WHERE k = ?", (key,))
        cur.execute("INSERT INTO config (k, v) VALUES (?, ?)", (key, str(value)))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Erro ao set_config({key}): {e}")
        return False


def get_test_balance() -> float:
    """Retorna o saldo de teste configurado (padrão: 1000)"""
    val = get_config('TEST_BALANCE', '1000')
    try:
        return float(val)
    except:
        return 1000.0


def set_test_balance(amount: float) -> bool:
    """Define o saldo de teste"""
    return set_config('TEST_BALANCE', str(amount))


def is_test_mode_enabled() -> bool:
    """Verifica se modo teste está ativo"""
    return get_config('TEST_MODE', 'false').lower() == 'true'


def get_operation_mode() -> str:
    mode = normalize_operation_mode(get_config('APP_MODE', ''))
    if mode in VALID_OPERATION_MODES and get_config('APP_MODE') is not None:
        return mode
    if is_test_mode_enabled():
        return 'paper'
    return get_environment_config().default_operation_mode


def set_operation_mode(mode: str) -> bool:
    return set_config('APP_MODE', normalize_operation_mode(mode))


def enable_test_mode() -> bool:
    """Ativa modo teste"""
    return set_config('TEST_MODE', 'true')
