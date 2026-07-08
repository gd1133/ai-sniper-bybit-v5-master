import sqlite3
import os
from typing import List, Dict, Any
from src.config import get_environment_config

# DB path with fallback logic for writable locations
def _get_db_path():
    """
    Determine writable database path with fallbacks (always returns ABSOLUTE path):
    1. SQLITE_DB_PATH environment variable (converted to absolute)
    2. Render/Linux: /tmp/ai-sniper/database.db (evita disk I/O em FS efêmero)
    3. ./database.db (repository root, converted to absolute)
    4. /tmp/ai-sniper/database.db (absolute path as fallback)
    """
    env_path = os.getenv('SQLITE_DB_PATH')
    if env_path:
        if "/app/data/" in env_path and os.name == 'nt':
            repo_path = os.path.abspath(os.path.join(os.getcwd(), 'database.db'))
            print(f"📂 [DATABASE] Detectado caminho Docker em Windows. Usando local: {repo_path}")
            return repo_path
        abs_env_path = os.path.abspath(env_path)
        print(f"📂 [DATABASE] Usando SQLITE_DB_PATH: {abs_env_path}")
        return abs_env_path

    if os.getenv('RENDER') or (os.name != 'nt' and not os.access(os.getcwd(), os.W_OK)):
        render_tmp = '/tmp/ai-sniper/database.db'
        try:
            os.makedirs(os.path.dirname(render_tmp), exist_ok=True)
            print(f"📂 [DATABASE] Usando caminho Render/tmp: {render_tmp}")
            return render_tmp
        except (OSError, IOError):
            pass

    repo_path = os.path.abspath(os.path.join(os.getcwd(), 'database.db'))
    try:
        test_dir = os.path.dirname(repo_path)
        if os.access(test_dir, os.W_OK):
            print(f"📂 [DATABASE] Usando caminho do repositório: {repo_path}")
            return repo_path
    except (OSError, IOError):
        pass

    fallback_path = '/tmp/ai-sniper/database.db'
    try:
        os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
    except (OSError, IOError):
        pass
    print(f"📂 [DATABASE] Usando caminho de fallback: {fallback_path}")
    return fallback_path

DB_PATH = _get_db_path()
print(f"✅ [DATABASE] Caminho absoluto do banco: {DB_PATH}")
# Sistema opera apenas em modo REAL
VALID_ACCOUNT_MODES = {'real'}
VALID_OPERATION_MODES = {'real'}
VALID_BALANCE_SOURCES = {'broker_real_balance', 'training_fake_balance'}


def is_truthy(value: Any) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def normalize_account_mode(value: Any) -> str:
    raw = str(value or '').strip().lower()
    if raw in ('demo', 'demos', 'demo_trading'):
        return 'demo'
    if raw in ('testnet', 'test', 'teste'):
        return 'testnet'
    if raw in ('real', 'mainnet', 'producao', 'produção', 'prod'):
        return 'real'
    if value is True or raw in ('1', 'true', 'yes', 'on'):
        return 'testnet'
    return 'real'


def normalize_operation_mode(value: Any) -> str:
    """Sempre retorna 'real' - sistema opera apenas em modo real"""
    return 'real'

def normalize_balance_source(value: Any) -> str:
    raw = str(value or '').strip().lower()
    if not raw or raw in {'broker_testnet_balance', 'real', 'broker'}:
        return 'broker_real_balance'
    if raw in {'training_fake_balance', 'fake', 'training', 'teste', 'test'}:
        return 'training_fake_balance'
    if raw in VALID_BALANCE_SOURCES:
        return raw
    return 'broker_real_balance'


def _connect():
    """Conecta ao banco com timeout e retry (evita travamento disk I/O no Render)."""
    import time as _time
    last_err = None
    for attempt in range(4):
        try:
            conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA busy_timeout=10000')
            return conn
        except sqlite3.OperationalError as err:
            last_err = err
            msg = str(err).lower()
            if 'disk i/o' in msg or 'locked' in msg or 'unable to open' in msg:
                _time.sleep(0.35 * (attempt + 1))
                continue
            raise
    raise last_err


def _ensure_column(cur, table: str, column: str, definition: str):
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cur.fetchall()}
    if column not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    """Inicializa banco com tabelas otimizadas e sem travamentos"""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:  # Only create directory if there's a directory component
        os.makedirs(db_dir, exist_ok=True)
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
        is_testnet INTEGER DEFAULT 0,
        account_mode TEXT DEFAULT 'real',
        balance_source TEXT DEFAULT 'broker_real_balance',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    _ensure_column(cur, 'clientes_sniper', 'account_mode', "TEXT DEFAULT 'real'")
    _ensure_column(cur, 'clientes_sniper', 'balance_source', "TEXT DEFAULT 'broker_real_balance'")
    _ensure_column(cur, 'clientes_sniper', 'exchange', "TEXT DEFAULT 'bybit'")
    # Preenche account_mode vazio sem resetar is_testnet de clientes existentes.
    cur.execute("""
        UPDATE clientes_sniper
        SET account_mode = CASE
            WHEN COALESCE(is_testnet, 0) = 1 THEN 'testnet'
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
        exit_price REAL DEFAULT 0,
        quantity REAL DEFAULT 0,
        margin REAL DEFAULT 0,
        closed_at TEXT,
        notes TEXT,
        status TEXT DEFAULT 'closed',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    _ensure_column(cur, 'trades', 'entry_price', 'REAL DEFAULT 0')
    _ensure_column(cur, 'trades', 'exit_price', 'REAL DEFAULT 0')
    _ensure_column(cur, 'trades', 'quantity', 'REAL DEFAULT 0')
    _ensure_column(cur, 'trades', 'margin', 'REAL DEFAULT 0')

    # Tabela de configuração global (TEST_MODE, TEST_BALANCE, etc)
    cur.execute('''
    CREATE TABLE IF NOT EXISTS config (
        k TEXT PRIMARY KEY,
        v TEXT
    )
    ''')

    # ÍNDICES PARA PERFORMANCE
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trades_client_id ON trades(client_id)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trades_pair ON trades(pair)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_clientes_status ON clientes_sniper(status)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_config_k ON config(k)')

    conn.commit()
    conn.close()

    # Inicializa tabela de histórico avançado para a IA analista
    try:
        from src.trade_history import init_trade_history_table
        init_trade_history_table()
    except Exception as th_err:
        print(f"⚠️ [DATABASE] Aviso ao inicializar trade_history: {th_err}")


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
        print(f"🔵 [DATABASE] add_client: Iniciando inserção de cliente: {data.get('nome')}")
        conn = _connect()
        cur = conn.cursor()
        account_mode = normalize_account_mode(data.get('account_mode', data.get('is_testnet')))
        is_testnet_flag = 1 if account_mode in ('testnet', 'demo') else 0
        balance_source = normalize_balance_source(data.get('balance_source'))
        exchange = str(data.get('exchange') or 'bybit').strip().lower()
        if exchange not in ('bybit', 'binance'):
            exchange = 'bybit'
        payload = (
            data.get('nome'),
            data.get('bybit_key'),
            data.get('bybit_secret'),
            data.get('tg_token'),
            data.get('tg_api_key'),
            data.get('chat_id'),
            data.get('status', 'ativo'),
            data.get('saldo_base', 1000.0),
            1 if is_testnet_flag else 0,
            account_mode,
            balance_source,
            exchange,
        )
        explicit_id = data.get('id')

        if explicit_id is not None:
            print(f"🔵 [DATABASE] add_client: Cliente com ID explícito: {explicit_id}")
            existing = get_client_by_id(int(explicit_id))
            if existing:
                conn.close()
                print(f"🔵 [DATABASE] add_client: Cliente já existe, atualizando...")
                return int(explicit_id) if update_client(int(explicit_id), data) else False

            cur.execute(
                'INSERT INTO clientes_sniper (id, nome, bybit_key, bybit_secret, tg_token, tg_api_key, chat_id, status, saldo_base, is_testnet, account_mode, balance_source, exchange) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (int(explicit_id), *payload)
            )
            inserted_id = int(explicit_id)
        else:
            print(f"🔵 [DATABASE] add_client: Novo cliente sem ID, gerando automaticamente")
            cur.execute(
                'INSERT INTO clientes_sniper (nome, bybit_key, bybit_secret, tg_token, tg_api_key, chat_id, status, saldo_base, is_testnet, account_mode, balance_source, exchange) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                payload
            )
            inserted_id = cur.lastrowid
        conn.commit()
        conn.close()
        print(f"✅ [DATABASE] add_client: Cliente inserido com sucesso! ID: {inserted_id}")
        return inserted_id
    except Exception as e:
        print(f"❌ [DATABASE] add_client: Erro ao adicionar cliente: {e}")
        import traceback
        traceback.print_exc()
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
    exit_price: float = 0.0,
    quantity: float = 0.0,
    margin: float = 0.0,
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
        'INSERT INTO trades (client_id, pair, side, pnl_pct, profit, entry_price, exit_price, quantity, margin, closed_at, notes, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        (client_id, pair, side, pnl_pct, profit, entry_price, exit_price, quantity, margin, closed_at, notes_clean, status.lower())
    )
    conn.commit()
    conn.close()


def close_trade(
    trade_id: int,
    pnl_pct: float,
    profit: float = None,
    exit_price: float = 0.0,
    closed_at: str = '',
    notes: str = '',
    entry_price: float = 0.0,
    quantity: float = 0.0,
    side: str = '',
) -> bool:
    """
    Fecha um trade em aberto preservando histórico e notas.
    Se profit não for fornecido, calcula automaticamente baseado em side, entry_price, exit_price e quantity.
    
    P&L Calculation:
    - LONG: profit = (exit_price - entry_price) * quantity
    - SHORT: profit = (entry_price - exit_price) * quantity
    """
    notes_clean = (notes or '').strip()
    try:
        notes_clean = notes_clean.upper()
    except Exception:
        notes_clean = str(notes_clean)

    # Se profit não foi fornecido, calcula automaticamente
    if profit is None and exit_price > 0 and entry_price > 0 and quantity > 0:
        side_normalized = str(side or '').upper()
        if side_normalized in ('VENDER', 'SELL', 'SHORT'):
            # SHORT: Lucro = (Preço de Entrada - Preço de Saída) * Quantidade
            profit = (entry_price - exit_price) * quantity
        else:
            # LONG: Lucro = (Preço de Saída - Preço de Entrada) * Quantidade
            profit = (exit_price - entry_price) * quantity
    elif profit is None:
        profit = 0.0

    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            '''
            UPDATE trades
            SET pnl_pct = ?,
                profit = ?,
                exit_price = ?,
                closed_at = ?,
                notes = ?,
                status = 'closed'
            WHERE id = ?
            ''',
            (pnl_pct, profit, exit_price, closed_at, notes_clean, trade_id),
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
        is_testnet = 1 if account_mode in ('testnet', 'demo') else 0
        balance_source = normalize_balance_source(
            data.get(
                'balance_source',
                'broker_real_balance',
            )
        )
        exchange = str(data.get('exchange') or 'bybit').strip().lower()
        if exchange not in ('bybit', 'binance'):
            exchange = 'bybit'
        cur.execute(
            "UPDATE clientes_sniper SET nome=?, bybit_key=?, bybit_secret=?, tg_token=?, tg_api_key=?, chat_id=?, status=?, saldo_base=?, is_testnet=?, account_mode=?, balance_source=?, exchange=? WHERE id=?",
            (
                data.get('nome'),
                data.get('bybit_key'),
                data.get('bybit_secret'),
                data.get('tg_token'),
                data.get('tg_api_key'),
                data.get('chat_id'),
                data.get('status', 'ativo'),
                data.get('saldo_base', 1000.0),
                is_testnet,
                account_mode,
                balance_source,
                exchange,
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


def is_test_mode_enabled() -> bool:
    """Verifica se modo teste está ativo"""
    return get_config('TEST_MODE', 'false').lower() == 'true'


def get_operation_mode() -> str:
    mode = normalize_operation_mode(get_config('APP_MODE', ''))
    if mode in VALID_OPERATION_MODES and get_config('APP_MODE') is not None:
        return mode
    return get_environment_config().default_operation_mode


def set_operation_mode(mode: str) -> bool:
    return set_config('APP_MODE', normalize_operation_mode(mode))


def enable_test_mode() -> bool:
    """Ativa modo teste"""
    return set_config('TEST_MODE', 'true')
