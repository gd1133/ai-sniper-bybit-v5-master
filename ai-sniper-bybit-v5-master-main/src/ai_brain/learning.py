import sqlite3
import os
import time
from datetime import datetime

class TradeLearner:
    """
    🧠 MEMÓRIA NEURAL v60.1 - GIVALDO SUPREME (THREAD-SAFE)
    Otimizado para evitar travamentos no Dashboard através de conexões síncronas.
    """
    def __init__(self, db_path="database.db"):
        self.db_path = db_path
        self._ensure_table()

    def _get_conn(self):
        """Cria uma conexão segura para multi-threading (Flask + Bot)."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self):
        """Garante que a estrutura de memória neural e trades existe."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Tabela de Aprendizado IA
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS neural_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT NOT NULL,
                    lado TEXT NOT NULL,
                    ia_mode TEXT NOT NULL,
                    pnl_pct REAL DEFAULT 0,
                    motivo_entrada TEXT,
                    licao_aprendida TEXT,
                    status TEXT DEFAULT 'OPEN'
                )
            ''')
            conn.commit()
        finally:
            conn.close()

    def _execute_write_with_retry(self, operation_name, operation, max_retries=5, base_delay=0.2):
        """Executa escrita no SQLite com retry exponencial para contornar lock concorrente."""
        for attempt in range(max_retries):
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                operation(cursor)
                conn.commit()
                return True
            except sqlite3.OperationalError as e:
                conn.rollback()
                error_text = str(e).lower()
                is_locked = "database is locked" in error_text or "database table is locked" in error_text
                if is_locked and attempt < (max_retries - 1):
                    delay = base_delay * (2 ** attempt)
                    print(f"⚠️ [SQLite Retry] {operation_name} bloqueado, nova tentativa em {delay:.2f}s")
                    time.sleep(delay)
                    continue

                print(f"❌ [SQLite] Falha em {operation_name}: {e}")
                return False
            except sqlite3.DatabaseError as e:
                conn.rollback()
                print(f"❌ [SQLite] DatabaseError em {operation_name}: {e}")
                return False
            finally:
                conn.close()

        return False

    def record_entry(self, symbol, side, ia_mode, reason):
        """Registra o início de uma operação para o Dashboard detectar."""
        def _operation(cursor):
            cursor.execute('''
                INSERT INTO neural_memory (symbol, lado, ia_mode, motivo_entrada, status)
                VALUES (?, ?, ?, ?, ?)
            ''', (symbol, side, ia_mode.upper(), reason, 'OPEN'))

        if self._execute_write_with_retry("record_entry", _operation):
            print(f"🧠 [MEMÓRIA] Snapshot {ia_mode} guardado: {symbol}")

    def record_trade(self, symbol, side, pnl, motivo, licao):
        """Finaliza o trade e libera o robô para o próximo scan."""
        def _operation(cursor):
            cursor.execute('''
                UPDATE neural_memory 
                SET pnl_pct = ?, licao_aprendida = ?, status = 'CLOSED'
                WHERE symbol = ? AND status = 'OPEN'
            ''', (pnl, licao, symbol))
            
            if cursor.rowcount == 0:
                cursor.execute('''
                    INSERT INTO neural_memory (symbol, lado, ia_mode, pnl_pct, licao_aprendida, status)
                    VALUES (?, ?, ?, ?, ?, 'CLOSED')
                ''', (symbol, side, 'CLOUD', pnl, licao))

        if self._execute_write_with_retry("record_trade", _operation):
            print(f"✅ [MEMÓRIA] Ciclo {symbol} finalizado com {pnl}%")

    def get_open_trades(self):
        """Busca trades abertos para o Monitor Sniper do Dashboard."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM neural_memory WHERE status = 'OPEN' ORDER BY timestamp DESC")
            return [dict(r) for r in cursor.fetchall()]
        except sqlite3.DatabaseError as e:
            print(f"❌ [SQLite] Erro get_open_trades: {e}")
            return []
        finally:
            conn.close()

    def get_recent_trades(self, limit=10):
        """Busca histórico para a tabela de Histórico de Saídas."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM neural_memory WHERE status = 'CLOSED' ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]
        except sqlite3.DatabaseError as e:
            print(f"❌ [SQLite] Erro get_recent_trades: {e}")
            return []
        finally:
            conn.close()

    def get_context(self):
        """Recupera aprendizados para o Gemini não repetir erros."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT symbol, ia_mode, pnl_pct, licao_aprendida 
                FROM neural_memory WHERE status = 'CLOSED' 
                ORDER BY timestamp DESC LIMIT 5
            ''')
            rows = cursor.fetchall()
            if not rows: return "Fase inicial: Sem histórico."
            
            ctx = "Treino: "
            for r in rows:
                res = "LUCRO" if r['pnl_pct'] > 0 else "PERDA"
                ctx += f"[{r['symbol']} ({r['ia_mode']}) {res}: {r['licao_aprendida']}] "
            return ctx
        finally:
            conn.close()

    def get_performance_report(self):
        """Relatório para o Telegram do Givaldo."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM neural_memory WHERE status = 'CLOSED'")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM neural_memory WHERE pnl_pct > 0 AND status = 'CLOSED'")
            wins = cursor.fetchone()[0]
            
            cursor.execute("SELECT SUM(pnl_pct) FROM neural_memory WHERE status = 'CLOSED'")
            total_pnl = cursor.fetchone()[0] or 0.0

            win_rate = (wins / total * 100) if total > 0 else 0

            return (f"📊 *RELATÓRIO TRIPLO CÉREBRO v60.1*\n\n"
                    f"📈 Trades: {total} | ✅ Wins: {wins}\n"
                    f"🎯 Assertividade: {win_rate:.2f}%\n"
                    f"💰 PnL Total: {total_pnl:.2f}%")
        except sqlite3.DatabaseError as e:
            print(f"❌ [SQLite] Erro get_performance_report: {e}")
            return "⚠️ Erro no relatório."
        finally:
            conn.close()