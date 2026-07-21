import sqlite3
import os
import re
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from src.config import get_environment_config

# DB path with fallback logic for writable locations
def _get_db_path():
    """
    Determine writable database path with fallbacks (always returns ABSOLUTE path):
    1. SQLITE_DB_PATH environment variable (converted to absolute)
    2. ./data/database.db (persistente no disco do projeto — preferido)
    3. ./database.db (repository root)
    4. /tmp/ai-sniper/database.db (último recurso; efêmero no Render)
    """
    env_path = os.getenv('SQLITE_DB_PATH')
    if env_path:
        if "/app/data/" in env_path and os.name == 'nt':
            repo_path = os.path.abspath(os.path.join(os.getcwd(), 'data', 'database.db'))
            print(f"📂 [DATABASE] Detectado caminho Docker em Windows. Usando local: {repo_path}")
            return repo_path
        # Evita /tmp por padrão (dados somem no restart do Render)
        abs_env_path = os.path.abspath(env_path)
        if '/tmp/' in abs_env_path.replace('\\', '/').lower() and not os.getenv('FORCE_TMP_SQLITE'):
            data_path = os.path.abspath(os.path.join(os.getcwd(), 'data', 'database.db'))
            try:
                os.makedirs(os.path.dirname(data_path), exist_ok=True)
                print(f"📂 [DATABASE] SQLITE_DB_PATH em /tmp ignorado (efêmero). Usando: {data_path}")
                return data_path
            except (OSError, IOError):
                pass
        print(f"📂 [DATABASE] Usando SQLITE_DB_PATH: {abs_env_path}")
        return abs_env_path

    # Preferência: pasta data/ no projeto (persiste entre restarts do processo)
    data_path = os.path.abspath(os.path.join(os.getcwd(), 'data', 'database.db'))
    try:
        os.makedirs(os.path.dirname(data_path), exist_ok=True)
        if os.access(os.path.dirname(data_path), os.W_OK):
            print(f"📂 [DATABASE] Usando caminho persistente data/: {data_path}")
            return data_path
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
    print(f"📂 [DATABASE] Usando caminho de fallback (efêmero): {fallback_path}")
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
    """Sistema 100% REAL — sempre conta real (sem testnet/demo/paper)."""
    return 'real'


def normalize_operation_mode(value: Any) -> str:
    """Sempre retorna 'real' - sistema opera apenas em modo real"""
    return 'real'

def normalize_balance_source(value: Any) -> str:
    """Única fonte válida: saldo real do broker (Bybit/Binance)."""
    return 'broker_real_balance'


def _connect():
    """
    Conecta ao banco com:
    - check_same_thread=False (Flask + threads do radar)
    - timeout / busy_timeout (evita lock)
    - WAL + synchronous FULL em escritas críticas via helper
    """
    import time as _time
    last_err = None
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        try:
            os.makedirs(db_dir, exist_ok=True)
        except (OSError, IOError):
            pass
    for attempt in range(4):
        try:
            conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA busy_timeout=15000')
            conn.execute('PRAGMA foreign_keys=ON')
            return conn
        except sqlite3.OperationalError as err:
            last_err = err
            msg = str(err).lower()
            if 'disk i/o' in msg or 'locked' in msg or 'unable to open' in msg:
                _time.sleep(0.35 * (attempt + 1))
                continue
            raise
    raise last_err


def _execute_write(operation_name: str, sql_fn) -> Any:
    """
    Executa uma escrita em conexão isolada, com commit físico e fechamento imediato.

    ``sqlite3.Connection`` como context manager não fecha a conexão sozinho; por isso
    usamos ``closing(sqlite3.connect(...))`` e commit explícito.
    sql_fn(cur, conn) -> valor de retorno (opcional).
    """
    import time as _time

    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        try:
            os.makedirs(db_dir, exist_ok=True)
        except (OSError, IOError):
            pass

    last_error = None
    for attempt in range(4):
        try:
            # closing garante close imediato; o bloco interno isola a transação.
            with closing(
                sqlite3.connect(
                    DB_PATH,
                    check_same_thread=False,
                    timeout=30.0,
                )
            ) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=FULL')
                conn.execute('PRAGMA busy_timeout=15000')
                conn.execute('PRAGMA foreign_keys=ON')

                try:
                    cur = conn.cursor()
                    result = sql_fn(cur, conn)
                    conn.commit()  # obrigatório: grava a transação antes do close
                except Exception:
                    conn.rollback()
                    raise

                # Consolida o WAL após a gravação sem tornar falha de checkpoint fatal.
                try:
                    conn.execute('PRAGMA wal_checkpoint(PASSIVE)')
                except sqlite3.Error:
                    pass
                return result
        except sqlite3.OperationalError as error:
            last_error = error
            message = str(error).lower()
            if (
                attempt < 3
                and ('locked' in message or 'busy' in message or 'disk i/o' in message)
            ):
                _time.sleep(0.35 * (attempt + 1))
                continue
            break
        except Exception as error:
            last_error = error
            break

    print(f"❌ [DATABASE] {operation_name}: {last_error}")
    import traceback
    traceback.print_exception(type(last_error), last_error, last_error.__traceback__)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Falha desconhecida na escrita SQLite: {operation_name}")


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

    def _schema(cur, conn):
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
        # Sistema 100% REAL: força todos os clientes existentes para conta real.
        cur.execute("""
            UPDATE clientes_sniper
            SET is_testnet = 0,
                account_mode = 'real',
                balance_source = 'broker_real_balance'
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
        _ensure_column(cur, 'trades', 'protection_status', "TEXT DEFAULT 'AGUARDANDO_PROTECAO'")

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

        # Castigo pós Stop Loss — bloqueia reentrada na mesma moeda por 24h
        cur.execute('''
        CREATE TABLE IF NOT EXISTS cooldown_moedas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            motivo TEXT DEFAULT 'STOP_LOSS',
            bloqueado_ate TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_cooldown_symbol ON cooldown_moedas(symbol)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_cooldown_bloqueado ON cooldown_moedas(bloqueado_ate)')
        return True

    _execute_write('init_db', _schema)
    print(f"✅ [DATABASE] Schema inicializado em {DB_PATH}")

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


def find_client_by_name(nome: str) -> Dict[str, Any] | None:
    """Busca cliente pelo nome (case-insensitive). Evita duplicar 'Márcio' etc."""
    name = str(nome or '').strip()
    if not name:
        return None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM clientes_sniper WHERE LOWER(TRIM(nome)) = LOWER(?) ORDER BY id DESC LIMIT 1",
            (name,),
        )
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"⚠️ [DATABASE] find_client_by_name: {e}")
        return None


def add_client(data: Dict[str, Any]):
    """Adiciona ou espelha um cliente localmente. Retorna o id persistido. Commit obrigatório."""
    try:
        print(f"🔵 [DATABASE] add_client: Iniciando inserção de cliente: {data.get('nome')}")
        # Se já existe cliente com o mesmo nome, atualiza em vez de duplicar
        if data.get('id') is None:
            existing = find_client_by_name(data.get('nome'))
            if existing and existing.get('id'):
                eid = int(existing['id'])
                print(f"🔵 [DATABASE] add_client: Nome já existe (id={eid}) — atualizando")
                return eid if update_client(eid, {**data, 'id': eid}) else False

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
                print(f"🔵 [DATABASE] add_client: Cliente já existe, atualizando...")
                return int(explicit_id) if update_client(int(explicit_id), data) else False

            def _insert_with_id(cur, conn):
                cur.execute(
                    'INSERT INTO clientes_sniper (id, nome, bybit_key, bybit_secret, tg_token, tg_api_key, chat_id, status, saldo_base, is_testnet, account_mode, balance_source, exchange) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (int(explicit_id), *payload),
                )
                return int(explicit_id)

            inserted_id = _execute_write('add_client(explicit_id)', _insert_with_id)
        else:
            print(f"🔵 [DATABASE] add_client: Novo cliente sem ID, gerando automaticamente")

            def _insert_auto(cur, conn):
                cur.execute(
                    'INSERT INTO clientes_sniper (nome, bybit_key, bybit_secret, tg_token, tg_api_key, chat_id, status, saldo_base, is_testnet, account_mode, balance_source, exchange) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    payload,
                )
                return int(cur.lastrowid)

            inserted_id = _execute_write('add_client(auto)', _insert_auto)

        print(f"✅ [DATABASE] add_client: Cliente persistido no disco! ID: {inserted_id} path={DB_PATH}")
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
    notes_clean = (notes or '').strip()
    try:
        notes_clean = notes_clean.upper()
    except Exception:
        notes_clean = str(notes_clean)

    def _op(cur, conn):
        cur.execute(
            'INSERT INTO trades (client_id, pair, side, pnl_pct, profit, entry_price, exit_price, quantity, margin, closed_at, notes, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (client_id, pair, side, pnl_pct, profit, entry_price, exit_price, quantity, margin, closed_at, notes_clean, status.lower()),
        )
        return cur.lastrowid

    try:
        return _execute_write('record_trade', _op)
    except Exception:
        return None


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

    def _op(cur, conn):
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
        return True

    try:
        return bool(_execute_write('close_trade', _op))
    except Exception as e:
        print(f"⚠️ Erro ao fechar trade {trade_id}: {e}")
        return False


def get_client_by_id(client_id: int) -> Dict[str, Any]:
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute('SELECT * FROM clientes_sniper WHERE id=?', (client_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def update_client(client_id: int, data: Dict[str, Any]) -> bool:
    """Atualiza informações de um cliente existente. Commit obrigatório via _execute_write."""
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

    def _op(cur, conn):
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
        return True

    try:
        ok = bool(_execute_write(f'update_client({client_id})', _op))
        if ok:
            print(f"✅ [DATABASE] update_client: Cliente {client_id} persistido em {DB_PATH}")
        return ok
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
    """Remove um cliente e seus trades associados. Commit obrigatório via _execute_write."""
    def _op(cur, conn):
        cur.execute("DELETE FROM trades WHERE client_id = ?", (client_id,))
        cur.execute("DELETE FROM clientes_sniper WHERE id = ?", (client_id,))
        return True

    try:
        return bool(_execute_write(f'delete_client({client_id})', _op))
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


def mark_trade_profit_shield(
    client_id: int,
    symbol: str,
    new_sl: float,
    roi_pct: float,
) -> bool:
    """Marca a operação aberta como PROTEGIDO_50 após Escada de Lucro."""
    notes_extra = f"PROTEGIDO_50|SL={new_sl}|ROI={roi_pct:.1f}%"

    def _op(cur, conn):
        cur.execute(
            """
            UPDATE trades
            SET protection_status = 'PROTEGIDO_50',
                notes = TRIM(COALESCE(notes, '') || ' | ' || ?)
            WHERE client_id = ?
              AND LOWER(COALESCE(status, 'open')) = 'open'
              AND (
                    REPLACE(UPPER(pair), '/', '') = REPLACE(UPPER(?), '/', '')
                 OR REPLACE(UPPER(pair), ':USDT', '') LIKE '%' || REPLACE(REPLACE(UPPER(?), '/USDT', ''), 'USDT', '') || '%'
              )
            """,
            (notes_extra, client_id, symbol, symbol),
        )
        return cur.rowcount > 0

    try:
        return bool(_execute_write('mark_trade_profit_shield', _op))
    except Exception as e:
        print(f"⚠️ [DATABASE] mark_trade_profit_shield: {e}")
        return False


# ============================================================================
# ⏸️ COOLDOWN PÓS STOP LOSS (anti-reentrada na mesma moeda)
# ============================================================================

COOLDOWN_AFTER_STOP_HOURS = float(os.getenv('COOLDOWN_AFTER_STOP_HOURS', '24'))


def _normalize_cooldown_symbol(symbol: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', str(symbol or '').upper())


def register_symbol_cooldown(
    symbol: str,
    hours: float = None,
    motivo: str = 'STOP_LOSS',
) -> bool:
    """Registra castigo de reentrada para o símbolo (padrão: 24h após Stop Loss)."""
    sym = _normalize_cooldown_symbol(symbol)
    if not sym:
        print("⚠️ [COOLDOWN] Símbolo inválido — castigo não registrado", flush=True)
        return False

    block_hours = float(hours if hours is not None else COOLDOWN_AFTER_STOP_HOURS)
    blocked_until = (datetime.now(timezone.utc) + timedelta(hours=block_hours)).isoformat()
    motivo_clean = str(motivo or 'STOP_LOSS').strip().upper()

    def _op(cur, conn):
        cur.execute(
            '''
            INSERT INTO cooldown_moedas (symbol, motivo, bloqueado_ate)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                motivo = excluded.motivo,
                bloqueado_ate = excluded.bloqueado_ate,
                created_at = CURRENT_TIMESTAMP
            ''',
            (sym, motivo_clean, blocked_until),
        )
        return True

    try:
        ok = bool(_execute_write('register_symbol_cooldown', _op))
        if ok:
            print(
                f"⏸️ [COOLDOWN] {sym} bloqueada por {block_hours:.0f}h "
                f"(desbloqueio ~ {blocked_until}) — motivo: {motivo_clean}",
                flush=True,
            )
        return ok
    except Exception as err:
        print(f"⚠️ [COOLDOWN] Erro ao registrar castigo para {sym}: {err}", flush=True)
        return False


def is_symbol_in_cooldown(symbol: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Verifica se o par está em período de castigo.

    Returns:
        (bloqueado, bloqueado_ate_iso, motivo)
    """
    sym = _normalize_cooldown_symbol(symbol)
    if not sym:
        return False, None, None

    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT bloqueado_ate, motivo FROM cooldown_moedas
            WHERE symbol = ?
            ORDER BY id DESC
            LIMIT 1
            ''',
            (sym,),
        )
        row = cur.fetchone()
        if not row:
            return False, None, None

        until_raw = str(row['bloqueado_ate'] or '').strip()
        motivo = str(row['motivo'] or 'STOP_LOSS')
        if not until_raw:
            return False, None, None

        try:
            until_dt = datetime.fromisoformat(until_raw.replace('Z', '+00:00'))
        except ValueError:
            return False, None, None

        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)

        now_utc = datetime.now(timezone.utc)
        if now_utc < until_dt:
            return True, until_dt.isoformat(), motivo

        def _purge(cur, _conn):
            cur.execute('DELETE FROM cooldown_moedas WHERE symbol = ?', (sym,))
            return True

        try:
            _execute_write('purge_expired_cooldown', _purge)
        except Exception:
            pass
        return False, None, None
    except Exception as err:
        print(f"⚠️ [COOLDOWN] Erro ao consultar castigo de {sym}: {err}", flush=True)
        return False, None, None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


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
    """Escreve/atualiza uma configuração com commit obrigatório."""
    def _op(cur, conn):
        cur.execute("DELETE FROM config WHERE k = ?", (key,))
        cur.execute("INSERT INTO config (k, v) VALUES (?, ?)", (key, str(value)))
        return True

    try:
        return bool(_execute_write(f'set_config({key})', _op))
    except Exception as e:
        print(f"❌ Erro ao set_config({key}): {e}")
        return False


def is_test_mode_enabled() -> bool:
    """Sistema 100% REAL — modo teste removido."""
    return False


def get_operation_mode() -> str:
    mode = normalize_operation_mode(get_config('APP_MODE', ''))
    if mode in VALID_OPERATION_MODES and get_config('APP_MODE') is not None:
        return mode
    return get_environment_config().default_operation_mode


def set_operation_mode(mode: str) -> bool:
    return set_config('APP_MODE', normalize_operation_mode(mode))


def enable_test_mode() -> bool:
    """Sistema 100% REAL — modo teste desativado permanentemente."""
    set_config('TEST_MODE', 'false')
    return False
