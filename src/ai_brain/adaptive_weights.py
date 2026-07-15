"""
🧠 ADAPTIVE STRATEGY WEIGHTS — Auto-ajuste de parâmetros por aprendizado.

O Cérebro 3 pontua a entrada com base em 5 estratégias clássicas:
  1. SMA (tendência macro)
  2. SuperTrend (pivô / confirmação de tendência)
  3. Fibonacci (Golden Zone 0.618)
  4. Volume (fluxo institucional)
  5. Suporte/Resistência (pivôs de estrutura)

Cada estratégia tem um PESO. Este módulo aprende, a partir do resultado real
(win/loss) de cada trade, quais estratégias mais acertam e ajusta os pesos
automaticamente (peso = peso_base × multiplicador_de_desempenho).

Comportamento seguro:
- Antes de acumular amostras suficientes (MIN_SAMPLES), usa o peso base
  (comportamento idêntico ao atual — nenhum choque no robô ao vivo).
- Multiplicador limitado a [MIN_MULT, MAX_MULT] para evitar oscilações bruscas.
- Persistência em SQLite, tolerante a locks concorrentes (Flask + threads).
"""

import sqlite3
import time
import json
from datetime import datetime

# Ordem canônica das 5 estratégias
STRATEGIES = ['sma', 'supertrend', 'fibonacci', 'volume', 'support_resistance']

# Pesos base (usados até haver aprendizado suficiente)
BASE_WEIGHTS = {
    'sma': 22.0,
    'supertrend': 18.0,
    'fibonacci': 13.0,
    'volume': 10.0,
    'support_resistance': 12.0,
}

MIN_SAMPLES = 10   # nº de resultados por estratégia antes de ajustar o peso
MIN_MULT = 0.60    # peso pode cair até 60% do base (estratégia ruim)
MAX_MULT = 1.40    # peso pode subir até 140% do base (estratégia boa)


def _resolve_db_path():
    """Usa o mesmo banco do app (manager.DB_PATH) para o aprendizado ser consistente."""
    try:
        from src.database.manager import DB_PATH
        if DB_PATH:
            return DB_PATH
    except Exception:
        pass
    return "database.db"


class AdaptiveStrategyWeights:
    """Aprende e ajusta os pesos das 5 estratégias com base no resultado real."""

    def __init__(self, db_path=None):
        self.db_path = db_path or _resolve_db_path()
        self._ensure_tables()

    # ────────────────────────────────────────────────────────────── infra
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS strategy_weights (
                    strategy TEXT PRIMARY KEY,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    weight REAL DEFAULT 0,
                    base_weight REAL DEFAULT 0,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Log de sinais na ENTRADA (consumido no fechamento para aprender)
            cur.execute('''
                CREATE TABLE IF NOT EXISTS strategy_signal_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    signals_json TEXT NOT NULL,
                    status TEXT DEFAULT 'OPEN',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Semeia as 5 estratégias com o peso base, se ainda não existirem
            for name in STRATEGIES:
                cur.execute('''
                    INSERT OR IGNORE INTO strategy_weights (strategy, wins, losses, weight, base_weight)
                    VALUES (?, 0, 0, ?, ?)
                ''', (name, BASE_WEIGHTS[name], BASE_WEIGHTS[name]))
            conn.commit()
        except sqlite3.DatabaseError as e:
            print(f"❌ [PESOS IA] Erro ao criar tabelas: {e}", flush=True)
        finally:
            conn.close()

    def _write_with_retry(self, name, op, max_retries=5, base_delay=0.15):
        for attempt in range(max_retries):
            conn = self._get_conn()
            try:
                cur = conn.cursor()
                op(cur)
                conn.commit()
                return True
            except sqlite3.OperationalError as e:
                conn.rollback()
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(base_delay * (2 ** attempt))
                    continue
                print(f"❌ [PESOS IA] Falha em {name}: {e}", flush=True)
                return False
            except sqlite3.DatabaseError as e:
                conn.rollback()
                print(f"❌ [PESOS IA] DatabaseError em {name}: {e}", flush=True)
                return False
            finally:
                conn.close()
        return False

    # ─────────────────────────────────────────────────────────── cálculo
    @staticmethod
    def _multiplier(wins, losses):
        """Multiplicador de desempenho a partir do histórico da estratégia."""
        total = int(wins) + int(losses)
        if total < MIN_SAMPLES:
            return 1.0
        # Win-rate suavizado (Laplace) para evitar extremos com poucas amostras
        wr = (wins + 1.0) / (total + 2.0)
        # wr=0.5 → 1.0 | wr=1.0 → 1.4 | wr=0.0 → 0.6
        mult = 1.0 + (wr - 0.5) * 0.8
        return max(MIN_MULT, min(MAX_MULT, mult))

    def get_weights(self):
        """Retorna {estrategia: peso_atual} recalculado a partir do histórico."""
        weights = dict(BASE_WEIGHTS)
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT strategy, wins, losses, base_weight FROM strategy_weights")
            for row in cur.fetchall():
                name = row['strategy']
                if name not in weights:
                    continue
                base = float(row['base_weight'] or BASE_WEIGHTS.get(name, 0))
                weights[name] = round(base * self._multiplier(row['wins'], row['losses']), 3)
        except sqlite3.DatabaseError as e:
            print(f"⚠️ [PESOS IA] get_weights fallback base: {e}", flush=True)
        finally:
            conn.close()
        return weights

    # ─────────────────────────────────────────────── ciclo de aprendizado
    def log_entry(self, symbol, signals):
        """Registra as estratégias ativas na ENTRADA (uma pendência por símbolo)."""
        sig = {k: bool(signals.get(k)) for k in STRATEGIES}
        payload = json.dumps(sig)

        def _op(cur):
            # Mantém apenas a pendência mais recente por símbolo
            cur.execute("DELETE FROM strategy_signal_log WHERE symbol = ? AND status = 'OPEN'", (symbol,))
            cur.execute(
                "INSERT INTO strategy_signal_log (symbol, signals_json, status) VALUES (?, ?, 'OPEN')",
                (symbol, payload),
            )

        self._write_with_retry("log_entry", _op)
        return sig

    def record_outcome(self, symbol, pnl_pct):
        """
        No FECHAMENTO, consome a pendência do símbolo e credita win/loss para
        cada estratégia que estava ativa na entrada, recalculando os pesos.
        Retorna True se aprendeu (havia pendência), False caso contrário.
        """
        win = float(pnl_pct) > 0
        conn = self._get_conn()
        signals = None
        row_id = None
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, signals_json FROM strategy_signal_log WHERE symbol = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                row_id = row['id']
                signals = json.loads(row['signals_json'] or '{}')
        except sqlite3.DatabaseError as e:
            print(f"⚠️ [PESOS IA] record_outcome leitura: {e}", flush=True)
        finally:
            conn.close()

        if not signals or row_id is None:
            return False

        col = 'wins' if win else 'losses'

        def _op(cur):
            for name in STRATEGIES:
                if signals.get(name):
                    cur.execute(
                        f"UPDATE strategy_weights SET {col} = {col} + 1, updated_at = CURRENT_TIMESTAMP WHERE strategy = ?",
                        (name,),
                    )
            cur.execute("UPDATE strategy_signal_log SET status = 'CLOSED' WHERE id = ?", (row_id,))

        ok = self._write_with_retry("record_outcome", _op)
        if ok:
            # Persiste o peso recalculado (para relatório) — best-effort
            weights = self.get_weights()

            def _op2(cur):
                for name, w in weights.items():
                    cur.execute(
                        "UPDATE strategy_weights SET weight = ? WHERE strategy = ?",
                        (round(float(w), 3), name),
                    )
            self._write_with_retry("persist_weights", _op2)
            result = "✅ WIN" if win else "❌ LOSS"
            active = [k for k in STRATEGIES if signals.get(k)]
            print(f"🧠 [PESOS IA] {symbol} {result} → ajustando {active}", flush=True)
        return ok

    # ─────────────────────────────────────────────────────────── relatório
    def get_report(self):
        """Relatório dos pesos aprendidos (para dashboard/API)."""
        weights = self.get_weights()
        out = []
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT strategy, wins, losses, base_weight, updated_at FROM strategy_weights")
            rows = {r['strategy']: r for r in cur.fetchall()}
        except sqlite3.DatabaseError:
            rows = {}
        finally:
            conn.close()

        for name in STRATEGIES:
            r = rows.get(name)
            wins = int(r['wins']) if r else 0
            losses = int(r['losses']) if r else 0
            total = wins + losses
            base = float(r['base_weight']) if r else BASE_WEIGHTS[name]
            wr = (wins / total * 100.0) if total else 0.0
            out.append({
                'strategy': name,
                'base_weight': round(base, 2),
                'weight': round(float(weights.get(name, base)), 2),
                'wins': wins,
                'losses': losses,
                'samples': total,
                'win_rate': round(wr, 1),
                'multiplier': round(self._multiplier(wins, losses), 3),
                'learning': total >= MIN_SAMPLES,
            })
        return out
