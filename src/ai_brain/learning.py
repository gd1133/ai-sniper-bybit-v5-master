import sqlite3
import os
import time
import json
from datetime import datetime, timedelta

class TradeLearner:
    """
    🧠 MEMÓRIA NEURAL v61.0 - GIVALDO SUPREME (THREAD-SAFE)
    Com 3º Cérebro Executor Principal e aprendizado adaptativo local.
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
        """Garante que a estrutura de memória neural, trades e ML local existe."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Tabela de Aprendizado IA (existente)
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
            
            # 🧠 NOVA TABELA: Aprendizado Local ML do 3º Cérebro
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS local_ml_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL,
                    entry_indicators TEXT,
                    sma_200_price REAL,
                    supertrend_value REAL,
                    rsi_value REAL,
                    entry_margin REAL,
                    entry_qty REAL,
                    exit_price REAL,
                    exit_time DATETIME,
                    pnl_pct REAL,
                    block_reason TEXT,
                    status TEXT DEFAULT 'OPEN',
                    brain_mode TEXT DEFAULT 'LOCAL'
                )
            ''')
            
            # Tabela de bloqueio temporário por padrão de falha
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS symbol_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL UNIQUE,
                    block_until DATETIME NOT NULL,
                    reason TEXT,
                    consecutive_losses INTEGER DEFAULT 0,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
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

    # ═══════════════════════════════════════════════════════════════════════════
    # 🧠 LOCAL ML ENGINE - 3º CÉREBRO EXECUTOR PRINCIPAL
    # ═══════════════════════════════════════════════════════════════════════════

    def record_local_entry(self, symbol, side, indicators_dict, entry_price, entry_qty, entry_margin):
        """Registra entrada do 3º Cérebro com todos os indicadores técnicos."""
        def _operation(cursor):
            indicators_json = json.dumps(indicators_dict) if indicators_dict else "{}"
            cursor.execute('''
                INSERT INTO local_ml_trades 
                (symbol, side, entry_price, entry_indicators, sma_200_price, 
                 supertrend_value, rsi_value, entry_qty, entry_margin, status, brain_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 'LOCAL')
            ''', (
                symbol,
                side,
                entry_price,
                indicators_json,
                indicators_dict.get('sma_200', 0),
                indicators_dict.get('supertrend', 0),
                indicators_dict.get('rsi', 50),
                entry_qty,
                entry_margin
            ))

        if self._execute_write_with_retry("record_local_entry", _operation):
            print(f"🧠 [3º CÉREBRO] Entrada Local registrada: {symbol} {side} @ {entry_price} (Qtd: {entry_qty})")

    def finalize_local_trade(self, symbol, exit_price, pnl_pct, exit_time=None):
        """Finaliza trade do 3º Cérebro com resultado."""
        exit_time = exit_time or datetime.utcnow().isoformat()
        
        def _operation(cursor):
            cursor.execute('''
                UPDATE local_ml_trades 
                SET exit_price = ?, pnl_pct = ?, exit_time = ?, status = 'CLOSED'
                WHERE symbol = ? AND status = 'OPEN'
                ORDER BY timestamp DESC LIMIT 1
            ''', (exit_price, pnl_pct, exit_time, symbol))

        if self._execute_write_with_retry("finalize_local_trade", _operation):
            result_label = "✅ LUCRO" if pnl_pct > 0 else "❌ PERDA"
            print(f"🧠 [3º CÉREBRO] Trade finalizado: {symbol} {result_label} {pnl_pct:.2f}%")

    def get_last_50_trades(self, symbol):
        """Retorna últimas 50 operações do símbolo para análise de padrões."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM local_ml_trades 
                WHERE symbol = ? AND status = 'CLOSED'
                ORDER BY timestamp DESC LIMIT 50
            ''', (symbol,))
            return [dict(r) for r in cursor.fetchall()]
        except sqlite3.DatabaseError as e:
            print(f"❌ [SQLite] Erro get_last_50_trades: {e}")
            return []
        finally:
            conn.close()

    def analyze_failure_patterns(self, symbol):
        """
        Analisa últimas 50 operações e detecta 3+ perdas consecutivas
        sob as mesmas condições de SMA/Supertrend.
        Retorna: (should_block, reason, consecutive_losses)
        """
        trades = self.get_last_50_trades(symbol)
        if len(trades) < 3:
            return False, "Histórico insuficiente", 0

        consecutive_losses = 0
        last_sma_200 = None
        loss_pattern = []

        for trade in trades[:10]:  # Verificar últimas 10 operações
            try:
                pnl = float(trade.get('pnl_pct', 0) or 0)
                indicators = json.loads(trade.get('entry_indicators', '{}'))
                sma_200 = float(indicators.get('sma_200', 0))

                if pnl < 0:  # Perda
                    if last_sma_200 is None or abs(sma_200 - last_sma_200) / last_sma_200 < 0.02:
                        consecutive_losses += 1
                        loss_pattern.append({
                            'symbol': symbol,
                            'pnl': pnl,
                            'sma_200': sma_200
                        })
                    else:
                        consecutive_losses = 1
                        last_sma_200 = sma_200
                else:  # Lucro - reseta contador
                    consecutive_losses = 0
                    last_sma_200 = None

                if consecutive_losses >= 3:
                    reason = f"3+ perdas consecutivas sob SMA 200 ≈ {sma_200:.2f}"
                    print(f"⛔ [3º CÉREBRO] Bloqueio ativado para {symbol}: {reason}")
                    return True, reason, consecutive_losses

            except (ValueError, TypeError, KeyError):
                continue

        return False, "", 0

    def is_symbol_blocked(self, symbol):
        """Verifica se símbolo está temporariamente bloqueado."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT block_until FROM symbol_blocks 
                WHERE symbol = ?
            ''', (symbol,))
            row = cursor.fetchone()
            
            if not row:
                return False, ""
            
            block_until = datetime.fromisoformat(row['block_until'])
            now = datetime.utcnow()
            
            if now < block_until:
                remaining = (block_until - now).total_seconds()
                reason = row.get('reason', 'Bloqueio temporário ativo')
                return True, f"{reason} (restam {remaining:.0f}s)"
            else:
                # Desbloqueia automaticamente
                cursor.execute('DELETE FROM symbol_blocks WHERE symbol = ?', (symbol,))
                conn.commit()
                return False, ""
        except Exception as e:
            print(f"❌ [SQLite] Erro is_symbol_blocked: {e}")
            return False, ""
        finally:
            conn.close()

    def block_symbol_temporarily(self, symbol, reason, duration_seconds=3600):
        """Bloqueia símbolo temporariamente por N segundos."""
        def _operation(cursor):
            block_until = (datetime.utcnow() + timedelta(seconds=duration_seconds)).isoformat()
            cursor.execute('''
                INSERT OR REPLACE INTO symbol_blocks (symbol, block_until, reason)
                VALUES (?, ?, ?)
            ''', (symbol, block_until, reason))

        if self._execute_write_with_retry("block_symbol_temporarily", _operation):
            print(f"⛔ [3º CÉREBRO] {symbol} bloqueado por {duration_seconds}s: {reason}")

    def should_allow_entry(self, symbol):
        """
        Verifica se entrada é permitida baseado em aprendizado local.
        Combina: bloqueio temporário + análise de padrões.
        """
        # Verificar bloqueio temporário
        is_blocked, block_reason = self.is_symbol_blocked(symbol)
        if is_blocked:
            return False, f"Símbolo bloqueado: {block_reason}"

        # Analisar padrões de falha
        should_block, failure_reason, consecutive_losses = self.analyze_failure_patterns(symbol)
        if should_block:
            self.block_symbol_temporarily(symbol, failure_reason, duration_seconds=1800)
            return False, f"Padrão de perda detectado: {failure_reason}"

        return True, "✅ Entrada autorizada pelo 3º Cérebro"

    def get_local_ml_stats(self, symbol=None):
        """Retorna estatísticas do 3º Cérebro (Local ML)."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute('''
                    SELECT COUNT(*) FROM local_ml_trades WHERE symbol = ? AND status = 'CLOSED'
                ''', (symbol,))
            else:
                cursor.execute('SELECT COUNT(*) FROM local_ml_trades WHERE status = "CLOSED"')
            
            total = cursor.fetchone()[0]
            
            if symbol:
                cursor.execute('''
                    SELECT COUNT(*) FROM local_ml_trades 
                    WHERE symbol = ? AND pnl_pct > 0 AND status = 'CLOSED'
                ''', (symbol,))
            else:
                cursor.execute('''
                    SELECT COUNT(*) FROM local_ml_trades 
                    WHERE pnl_pct > 0 AND status = 'CLOSED'
                ''')
            
            wins = cursor.fetchone()[0]
            
            if symbol:
                cursor.execute('''
                    SELECT SUM(pnl_pct) FROM local_ml_trades 
                    WHERE symbol = ? AND status = 'CLOSED'
                ''', (symbol,))
            else:
                cursor.execute('''
                    SELECT SUM(pnl_pct) FROM local_ml_trades WHERE status = 'CLOSED'
                ''')
            
            total_pnl = cursor.fetchone()[0] or 0.0
            win_rate = (wins / total * 100) if total > 0 else 0

            symbol_filter = f" {symbol}" if symbol else ""
            return {
                'total_trades': total,
                'wins': wins,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'summary': f"3º Cérebro{symbol_filter}: {total} trades | ✅ {wins} wins | 🎯 {win_rate:.1f}% | 💰 {total_pnl:.2f}%"
            }
        except sqlite3.DatabaseError as e:
            print(f"❌ [SQLite] Erro get_local_ml_stats: {e}")
            return {'total_trades': 0, 'wins': 0, 'win_rate': 0, 'total_pnl': 0, 'summary': '⚠️ Erro ao carregar stats'}
        finally:
            conn.close()