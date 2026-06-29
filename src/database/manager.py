import sqlite3
import os
import threading
from datetime import datetime
from typing import List, Dict, Any
from src.config import get_environment_config

# DB path with fallback logic for writable locations
def _get_db_path():
    """
    Determine writable database path with fallbacks (always returns ABSOLUTE path):
    1. SQLITE_DB_PATH environment variable (converted to absolute)
    2. ./database.db (repository root, converted to absolute)
    3. /tmp/ai-sniper/database.db (absolute path as fallback)
    """
    env_path = os.getenv('SQLITE_DB_PATH')
    if env_path:
        # Corrige caminhos do Docker/Railway se estiver rodando localmente (Windows)
        if "/app/data/" in env_path and os.name == 'nt':
            repo_path = os.path.abspath(os.path.join(os.getcwd(), 'database.db'))
            print(f"📂 [DATABASE] Detectado caminho Docker em Windows. Usando local: {repo_path}")
            return repo_path
            
        # Convert to absolute path if relative
        abs_env_path = os.path.abspath(env_path)
        print(f"📂 [DATABASE] Usando SQLITE_DB_PATH: {abs_env_path}")
        return abs_env_path

    # Try repository root (convert to absolute)
    repo_path = os.path.abspath(os.path.join(os.getcwd(), 'database.db'))
    try:
        # Test if we can write to this location
        test_dir = os.path.dirname(repo_path)
        if os.access(test_dir, os.W_OK):
            print(f"📂 [DATABASE] Usando caminho do repositório: {repo_path}")
            return repo_path
    except (OSError, IOError):
        pass

    # Fallback to /tmp (absolute path)
    fallback_path = '/tmp/ai-sniper/database.db'
    print(f"📂 [DATABASE] Usando caminho de fallback: {fallback_path}")
    return fallback_path

DB_PATH = _get_db_path()
print(f"✅ [DATABASE] Caminho absoluto do banco: {DB_PATH}")
FALLBACK_DB_PATH = '/tmp/ai-sniper/database.db'
_DB_RUNTIME_LOCK = threading.Lock()
_DB_RUNTIME_PATH = DB_PATH
_SCHEMA_READY_LOCK = threading.Lock()
_SCHEMA_READY_PATHS = set()
# Sistema opera apenas em modo REAL
VALID_ACCOUNT_MODES = {'real'}
VALID_OPERATION_MODES = {'real'}
VALID_BALANCE_SOURCES = {'broker_real_balance', 'training_fake_balance'}


def is_truthy(value: Any) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def normalize_account_mode(value: Any) -> str:
    """Sempre retorna 'real' - sistema opera apenas em modo real"""
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


def _is_disk_io_error(err: Exception) -> bool:
    msg = str(err or '').lower()
    return (
        'disk i/o error' in msg
        or 'readonly database' in msg
        or 'database disk image is malformed' in msg
    )


def _get_runtime_db_path() -> str:
    with _DB_RUNTIME_LOCK:
        return _DB_RUNTIME_PATH


def _set_runtime_db_path(path: str, reason: str = ''):
    global _DB_RUNTIME_PATH
    normalized = os.path.abspath(path)
    with _DB_RUNTIME_LOCK:
        if _DB_RUNTIME_PATH != normalized:
            _DB_RUNTIME_PATH = normalized
            print(f"⚠️ [DATABASE] Alternando banco ativo para: {normalized} | motivo: {reason}")


def _is_schema_ready_for_path(path: str) -> bool:
    normalized = os.path.abspath(path)
    with _SCHEMA_READY_LOCK:
        return normalized in _SCHEMA_READY_PATHS


def _mark_schema_ready_for_path(path: str):
    normalized = os.path.abspath(path)
    with _SCHEMA_READY_LOCK:
        _SCHEMA_READY_PATHS.add(normalized)


def _configure_connection(conn, *, prefer_wal: bool = True):
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=30000;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    if prefer_wal:
        try:
            conn.execute('PRAGMA journal_mode=WAL;')
            return
        except Exception as wal_err:
            print(f"⚠️ [DATABASE] Falha ao ativar WAL neste volume: {wal_err} | usando DELETE journal", flush=True)
    conn.execute('PRAGMA journal_mode=DELETE;')


def _apply_schema(cur):
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
    _ensure_column(cur, 'clientes_sniper', 'is_testnet', 'INTEGER DEFAULT 0')
    _ensure_column(cur, 'clientes_sniper', 'account_mode', "TEXT DEFAULT 'real'")
    _ensure_column(cur, 'clientes_sniper', 'balance_source', "TEXT DEFAULT 'broker_real_balance'")
    _ensure_column(cur, 'clientes_sniper', 'exchange', "TEXT DEFAULT 'bybit'")
    # Atualiza registros existentes para modo real
    cur.execute("""
        UPDATE clientes_sniper
        SET account_mode = 'real',
            is_testnet = 0,
            balance_source = 'broker_real_balance'
        WHERE account_mode IS NULL OR TRIM(account_mode) = '' OR account_mode = 'testnet'
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

    # Histórico permanente de P&L para ranking/acumulado diário (paper + real)
    cur.execute('''
    CREATE TABLE IF NOT EXISTS historico_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_id INTEGER,
        cliente_id INTEGER,
        symbol TEXT,
        side TEXT,
        lucro_lucrado REAL,
        data_fechamento TEXT
    )
    ''')
    _ensure_column(cur, 'historico_trades', 'trade_id', 'INTEGER')

    # ÍNDICES PARA PERFORMANCE
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trades_client_id ON trades(client_id)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trades_pair ON trades(pair)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_clientes_status ON clientes_sniper(status)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_config_k ON config(k)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_historico_cliente ON historico_trades(cliente_id)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_historico_symbol ON historico_trades(symbol)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_historico_fechamento ON historico_trades(data_fechamento)')
    cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_historico_trade_id_unique ON historico_trades(trade_id) WHERE trade_id IS NOT NULL')

    # Só tenta deduplicar quando a tabela existe e está acessível.
    try:
        removed_duplicates = _cleanup_duplicate_historico_trades(cur)
        if removed_duplicates > 0:
            print(f"🧹 [DATABASE] Limpeza de duplicados no histórico: {removed_duplicates} registro(s) removido(s).", flush=True)
    except Exception as dedup_err:
        print(f"⚠️ [DATABASE] Aviso ao deduplicar histórico: {dedup_err}", flush=True)


def _ensure_runtime_schema(conn, db_path: str):
    if _is_schema_ready_for_path(db_path):
        return
    cur = conn.cursor()
    _apply_schema(cur)
    conn.commit()
    _mark_schema_ready_for_path(db_path)
    print(f"✅ [DATABASE] Schema validado em runtime: {os.path.abspath(db_path)}", flush=True)


def _connect(*, ensure_schema: bool = True):
    """Conecta ao banco com timeout estendido para evitar lock contention."""
    current_path = _get_runtime_db_path()
    try:
        conn = sqlite3.connect(current_path, check_same_thread=False, timeout=30.0)
        _configure_connection(conn, prefer_wal=True)
        if ensure_schema:
            _ensure_runtime_schema(conn, current_path)
        return conn
    except sqlite3.OperationalError as err:
        if not _is_disk_io_error(err):
            raise
        # Failover em tempo de execução para manter API viva quando /data ficar indisponível.
        os.makedirs(os.path.dirname(FALLBACK_DB_PATH), exist_ok=True)
        _set_runtime_db_path(FALLBACK_DB_PATH, reason=f"sqlite I/O failure no volume primário: {err}")
        conn = sqlite3.connect(_get_runtime_db_path(), check_same_thread=False, timeout=30.0)
        _configure_connection(conn, prefer_wal=False)
        if ensure_schema:
            _ensure_runtime_schema(conn, _get_runtime_db_path())
        return conn


def _force_runtime_failover(reason: str = ''):
    """Força failover do runtime DB para o caminho de fallback."""
    try:
        os.makedirs(os.path.dirname(FALLBACK_DB_PATH), exist_ok=True)
    except Exception:
        pass
    _set_runtime_db_path(FALLBACK_DB_PATH, reason=reason or "forced failover")


def _ensure_column(cur, table: str, column: str, definition: str):
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cur.fetchall()}
    if column not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _cleanup_duplicate_historico_trades(cur) -> int:
    """
    Remove duplicidades antigas no histórico mantendo somente o último registro
    por chave de fechamento (trade_id quando existir, senão assinatura lógica).
    """
    before_count_row = cur.execute("SELECT COUNT(1) FROM historico_trades").fetchone()
    before_count = int((before_count_row[0] if before_count_row else 0) or 0)

    cur.execute(
        '''
        DELETE FROM historico_trades
        WHERE id NOT IN (
            SELECT MAX(h.id)
            FROM historico_trades h
            GROUP BY
                CASE
                    WHEN h.trade_id IS NOT NULL THEN 'T|' || CAST(h.trade_id AS TEXT)
                    ELSE
                        'S|' ||
                        CAST(COALESCE(h.cliente_id, 0) AS TEXT) || '|' ||
                        UPPER(COALESCE(h.symbol, '')) || '|' ||
                        COALESCE(h.data_fechamento, '') || '|' ||
                        printf('%.8f', ROUND(COALESCE(h.lucro_lucrado, 0.0), 8))
                END
        )
        '''
    )

    after_count_row = cur.execute("SELECT COUNT(1) FROM historico_trades").fetchone()
    after_count = int((after_count_row[0] if after_count_row else 0) or 0)
    removed = max(0, before_count - after_count)
    return removed


def init_db():
    """Inicializa banco com tabelas otimizadas e sem travamentos"""
    conn = None
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:  # Only create directory if there's a directory component
        os.makedirs(db_dir, exist_ok=True)
    try:
        conn = _connect(ensure_schema=False)
        cur = conn.cursor()
        _apply_schema(cur)
        conn.commit()
        _mark_schema_ready_for_path(_get_runtime_db_path())
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

    # Inicializa tabela de histórico avançado para a IA analista
    try:
        from src.trade_history import init_trade_history_table
        init_trade_history_table()
    except Exception as th_err:
        print(f"⚠️ [DATABASE] Aviso ao inicializar trade_history: {th_err}")


def get_active_clients(_retry_on_disk_io: bool = True) -> List[Dict[str, Any]]:
    """Retorna apenas clientes cadastrados com status ativo"""
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM clientes_sniper WHERE status='ativo' ORDER BY created_at DESC")
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as e:
        if _retry_on_disk_io and _is_disk_io_error(e):
            _force_runtime_failover(reason=f"disk I/O em get_active_clients: {e}")
            return get_active_clients(_retry_on_disk_io=False)
        print(f"⚠️ Erro ao buscar clientes ativos: {e}")
        return []
    except Exception as e:
        print(f"⚠️ Erro ao buscar clientes ativos: {e}")
        return []
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def get_all_clients(_retry_on_disk_io: bool = True) -> List[Dict[str, Any]]:
    """Retorna todos os clientes cadastrados"""
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM clientes_sniper ORDER BY created_at DESC")
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as e:
        if _retry_on_disk_io and _is_disk_io_error(e):
            _force_runtime_failover(reason=f"disk I/O em get_all_clients: {e}")
            return get_all_clients(_retry_on_disk_io=False)
        print(f"⚠️ Erro ao buscar clientes: {e}")
        return []
    except Exception as e:
        print(f"⚠️ Erro ao buscar clientes: {e}")
        return []
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def add_client(data: Dict[str, Any], _retry_on_disk_io: bool = True):
    """Adiciona ou espelha um cliente localmente. Retorna o id persistido."""
    conn = None
    try:
        print(f"🔵 [DATABASE] add_client: Iniciando inserção de cliente: {data.get('nome')}")
        conn = _connect()
        cur = conn.cursor()
        # Sistema sempre opera em modo real
        account_mode = 'real'
        balance_source = normalize_balance_source(data.get('balance_source'))
        # Plataforma unificada: Bybit-only.
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
            1 if is_truthy(data.get('is_testnet')) else 0,
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
                conn = None
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
        conn = None
        print(f"✅ [DATABASE] add_client: Cliente inserido com sucesso! ID: {inserted_id}")
        return inserted_id
    except sqlite3.OperationalError as e:
        if _retry_on_disk_io and _is_disk_io_error(e):
            print(f"⚠️ [DATABASE] add_client detectou disk I/O; acionando failover e retry único...", flush=True)
            _force_runtime_failover(reason=f"disk I/O em add_client: {e}")
            return add_client(data, _retry_on_disk_io=False)
        print(f"❌ [DATABASE] add_client: Erro ao adicionar cliente: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"❌ [DATABASE] add_client: Erro ao adicionar cliente: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


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

    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO trades (client_id, pair, side, pnl_pct, profit, entry_price, exit_price, quantity, margin, closed_at, notes, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (client_id, pair, side, pnl_pct, profit, entry_price, exit_price, quantity, margin, closed_at, notes_clean, status.lower())
        )
        conn.commit()
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


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

    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        # Lock de escrita evita corrida entre loops paralelos no fechamento.
        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            "SELECT client_id, pair, side, status, closed_at, profit FROM trades WHERE id = ?",
            (trade_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        row_data = dict(row)
        current_status = str(row_data.get('status') or '').lower()
        if current_status != 'open':
            # Já estava encerrado; evita duplicar histórico.
            return True

        closed_at_value = str(closed_at or row_data.get('closed_at') or '').strip()
        if not closed_at_value:
            closed_at_value = datetime.now().isoformat(timespec='seconds')

        historico_cliente_id = int(row_data.get('client_id') or 0)
        historico_symbol = str(row_data.get('pair') or '')
        historico_side = str(row_data.get('side') or side or '')
        historico_profit = round(float(profit or 0.0), 8)

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
            (pnl_pct, profit, exit_price, closed_at_value, notes_clean, trade_id),
        )
        # 1) Trava por ID de posição (trade_id) - evita duplicação de loop concorrente.
        cur.execute(
            "SELECT 1 FROM historico_trades WHERE trade_id = ? LIMIT 1",
            (trade_id,),
        )
        duplicate_by_trade_id = cur.fetchone() is not None

        # 2) Pré-checagem por assinatura do fechamento (cliente/símbolo/data/lucro).
        duplicate_by_signature = False
        if not duplicate_by_trade_id:
            cur.execute(
                '''
                SELECT 1
                FROM historico_trades
                WHERE cliente_id = ?
                  AND symbol = ?
                  AND data_fechamento = ?
                  AND ROUND(COALESCE(lucro_lucrado, 0.0), 8) = ?
                LIMIT 1
                ''',
                (
                    historico_cliente_id,
                    historico_symbol,
                    closed_at_value,
                    historico_profit,
                ),
            )
            duplicate_by_signature = cur.fetchone() is not None

        # Persistência definitiva do fechamento para acumulado/ranking.
        if not duplicate_by_trade_id and not duplicate_by_signature:
            cur.execute(
                '''
                INSERT INTO historico_trades (trade_id, cliente_id, symbol, side, lucro_lucrado, data_fechamento)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    trade_id,
                    historico_cliente_id,
                    historico_symbol,
                    historico_side,
                    historico_profit,
                    closed_at_value,
                ),
            )
        else:
            print(
                f"⚠️ [HISTORICO] Registro duplicado ignorado para trade_id={trade_id} ({historico_symbol})",
                flush=True,
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"⚠️ Erro ao fechar trade {trade_id}: {e}")
        return False
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def get_client_by_id(client_id: int) -> Dict[str, Any]:
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute('SELECT * FROM clientes_sniper WHERE id=?', (client_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def update_client(client_id: int, data: Dict[str, Any]) -> bool:
    """Atualiza informações de um cliente existente."""
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        is_testnet = 1 if is_truthy(data.get('is_testnet')) else 0
        account_mode = normalize_account_mode(data.get('account_mode'))
        balance_source = normalize_balance_source(
            data.get(
                'balance_source',
                'broker_real_balance',
            )
        )
        # Plataforma unificada: Bybit-only.
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
        conn = None
        return True
    except Exception as e:
        print(f"⚠️ Erro ao atualizar cliente {client_id}: {e}")
        return False
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


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
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        # Primeiro remove os trades do cliente
        cur.execute("DELETE FROM trades WHERE client_id = ?", (client_id,))
        # Depois remove o cliente
        cur.execute("DELETE FROM clientes_sniper WHERE id = ?", (client_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"⚠️ Erro ao deletar cliente {client_id}: {e}")
        return False
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def get_open_trades(limit: int = 50) -> List[Dict[str, Any]]:
    conn = None
    try:
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
        return [dict(r) for r in rows]
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def get_recent_trades(limit: int = 50) -> List[Dict[str, Any]]:
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            '''
            WITH dedup_ids AS (
                SELECT MAX(t.id) AS trade_id
                FROM trades t
                GROUP BY
                    CASE
                        WHEN LOWER(COALESCE(t.status, 'closed')) = 'closed' THEN COALESCE(t.client_id, 0)
                        ELSE t.id
                    END,
                    CASE
                        WHEN LOWER(COALESCE(t.status, 'closed')) = 'closed' THEN UPPER(COALESCE(t.pair, ''))
                        ELSE printf('OPEN_PAIR|%s', t.id)
                    END,
                    CASE
                        WHEN LOWER(COALESCE(t.status, 'closed')) = 'closed' THEN UPPER(COALESCE(t.side, ''))
                        ELSE printf('OPEN_SIDE|%s', t.id)
                    END,
                    CASE
                        WHEN LOWER(COALESCE(t.status, 'closed')) = 'closed' THEN COALESCE(t.closed_at, '')
                        ELSE printf('OPEN_TIME|%s', t.id)
                    END,
                    CASE
                        WHEN LOWER(COALESCE(t.status, 'closed')) = 'closed' THEN ROUND(COALESCE(t.profit, 0.0), 8)
                        ELSE CAST(t.id AS REAL)
                    END
            )
            SELECT t.*, c.nome
            FROM trades t
            INNER JOIN dedup_ids d ON d.trade_id = t.id
            LEFT JOIN clientes_sniper c ON c.id = t.client_id
            ORDER BY t.id DESC
            LIMIT ?
            ''',
            (limit,),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def get_last_closed_trade(client_id: int) -> Dict[str, Any]:
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM trades WHERE client_id = ? AND LOWER(COALESCE(status, 'closed')) = 'closed' ORDER BY id DESC LIMIT 1",
            (client_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def get_historico_pnl_map() -> Dict[int, float]:
    """
    Retorna acumulado histórico por cliente:
    {cliente_id: soma(lucro_lucrado)}
    """
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT cliente_id, COALESCE(SUM(lucro_lucrado), 0.0) AS pnl_historico_acumulado
            FROM historico_trades
            GROUP BY cliente_id
            '''
        )
        rows = cur.fetchall()
        return {
            int((r['cliente_id'] if isinstance(r, sqlite3.Row) else r[0]) or 0): float(
                (r['pnl_historico_acumulado'] if isinstance(r, sqlite3.Row) else r[1]) or 0.0
            )
            for r in rows
            if int((r['cliente_id'] if isinstance(r, sqlite3.Row) else r[0]) or 0) > 0
        }
    except Exception as e:
        print(f"⚠️ Erro ao calcular mapa de histórico de P&L: {e}")
        return {}
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def get_historico_pnl_total(cliente_id: int | None = None) -> float:
    """Retorna o total acumulado no historico_trades (global ou por cliente)."""
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        if cliente_id is None:
            cur.execute("SELECT COALESCE(SUM(lucro_lucrado), 0.0) FROM historico_trades")
        else:
            cur.execute(
                "SELECT COALESCE(SUM(lucro_lucrado), 0.0) FROM historico_trades WHERE cliente_id = ?",
                (int(cliente_id),),
            )
        row = cur.fetchone()
        if row is None:
            return 0.0
        return float((row[0] if not isinstance(row, sqlite3.Row) else list(row)[0]) or 0.0)
    except Exception as e:
        print(f"⚠️ Erro ao calcular histórico acumulado: {e}")
        return 0.0
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


# ============================================================================
# 🧪 CONFIGURAÇÕES DE TESTE (TEST BALANCE & MODE)
# ============================================================================

def get_config(key: str, default: str = None) -> str:
    """Lê uma configuração do banco de dados"""
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT v FROM config WHERE k = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else default
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def set_config(key: str, value: str) -> bool:
    """Escreve/atualiza uma configuração"""
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM config WHERE k = ?", (key,))
        cur.execute("INSERT INTO config (k, v) VALUES (?, ?)", (key, str(value)))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Erro ao set_config({key}): {e}")
        return False
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


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
