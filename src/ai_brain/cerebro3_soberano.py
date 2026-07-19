# -*- coding: utf-8 -*-
"""
Cérebro 3 — decisão soberana com aprendizado por condição de mercado.

Incremental sobre AdaptiveStrategyWeights (não remove strategy_weights).
- pesos_estrategias por condicao_mercado (SQLite)
- blend 70% técnica + 20% fluxo Groq + 10% sentimento Gemini
- persiste json_ia_insights no log de sinais (coluna opcional)
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from src.ai_brain.adaptive_weights import AdaptiveStrategyWeights, BASE_WEIGHTS, STRATEGIES


def _resolve_db_path() -> str:
    try:
        from src.database.manager import DB_PATH
        if DB_PATH:
            return str(DB_PATH)
    except Exception:
        pass
    return './data/database.db'


def market_condition_from_signals(signals: dict | None, regime: dict | None = None) -> str:
    """Rotula a condição para pesos por regime."""
    signals = signals or {}
    regime = regime or {}
    if regime.get('is_lateral') or signals.get('is_lateral') or signals.get('is_accumulation'):
        return 'LATERAL'
    trend = str(signals.get('trend') or regime.get('market_regime') or 'NEUTRO').upper()
    if trend in ('ALTA', 'TREND_UP', 'BULLISH'):
        return 'TENDENCIA_ALTA'
    if trend in ('BAIXA', 'TREND_DOWN', 'BEARISH'):
        return 'TENDENCIA_BAIXA'
    return 'NEUTRO'


class Cerebro3DecisaoSoberana:
    """
    Camada de aprendizado + blend IA auxiliar.
    Mantém AdaptiveStrategyWeights como fonte global; adiciona pesos por condição.
    """

    TAXA_APRENDIZADO = 0.02

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or _resolve_db_path()
        self.adaptive = AdaptiveStrategyWeights(self.db_path)
        self.inicializar_tabela_pesos()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def inicializar_tabela_pesos(self):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pesos_estrategias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    condicao_mercado TEXT UNIQUE,
                    peso_sma200 REAL DEFAULT 0.20,
                    peso_supertrend REAL DEFAULT 0.20,
                    peso_fibonacci REAL DEFAULT 0.20,
                    peso_volume_climax REAL DEFAULT 0.20,
                    peso_suporte_resistencia REAL DEFAULT 0.20,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Extensão opcional do log existente (não quebra se falhar)
            try:
                cur.execute('ALTER TABLE strategy_signal_log ADD COLUMN json_ia_insights TEXT')
            except sqlite3.OperationalError:
                pass
            try:
                cur.execute('ALTER TABLE strategy_signal_log ADD COLUMN condicao_mercado TEXT')
            except sqlite3.OperationalError:
                pass
            conn.commit()
        finally:
            conn.close()

    def obter_pesos_atuais(self, condicao_mercado: str) -> dict[str, float]:
        cond = str(condicao_mercado or 'NEUTRO').upper()
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute('SELECT * FROM pesos_estrategias WHERE condicao_mercado = ?', (cond,))
            row = cur.fetchone()
            if not row:
                cur.execute(
                    'INSERT INTO pesos_estrategias (condicao_mercado) VALUES (?)',
                    (cond,),
                )
                conn.commit()
                return {
                    'sma200': 0.20,
                    'supertrend': 0.20,
                    'fibonacci': 0.20,
                    'volume_climax': 0.20,
                    'sup_res': 0.20,
                }
            return {
                'sma200': float(row['peso_sma200']),
                'supertrend': float(row['peso_supertrend']),
                'fibonacci': float(row['peso_fibonacci']),
                'volume_climax': float(row['peso_volume_climax']),
                'sup_res': float(row['peso_suporte_resistencia']),
            }
        finally:
            conn.close()

    def _normalize_strategy_scores(self, sinais_5: dict) -> dict[str, float]:
        """Aceita 0/1 ou pesos ativos; normaliza para 0..1."""
        mapping = {
            'sma200': ('sma200', 'sma'),
            'supertrend': ('supertrend',),
            'fibonacci': ('fibonacci',),
            'volume_climax': ('volume_climax', 'volume'),
            'sup_res': ('sup_res', 'support_resistance'),
        }
        out = {}
        for canon, aliases in mapping.items():
            val = 0.0
            for a in aliases:
                if a in sinais_5:
                    try:
                        val = float(sinais_5[a])
                    except (TypeError, ValueError):
                        val = 1.0 if sinais_5[a] else 0.0
                    break
            out[canon] = max(0.0, min(1.0, val))
        return out

    def calcular_score_tecnico(self, sinais_5_estrategias: dict, condicao_mercado: str) -> float:
        """Score técnico 0..1 a partir dos pesos por condição."""
        pesos = self.obter_pesos_atuais(condicao_mercado)
        s = self._normalize_strategy_scores(sinais_5_estrategias)
        score = (
            s['sma200'] * pesos['sma200']
            + s['supertrend'] * pesos['supertrend']
            + s['fibonacci'] * pesos['fibonacci']
            + s['volume_climax'] * pesos['volume_climax']
            + s['sup_res'] * pesos['sup_res']
        )
        return max(0.0, min(1.0, float(score)))

    def calcular_probabilidade_sucesso(
        self,
        sinais_5_estrategias: dict,
        condicao_mercado: str,
        dados_groq: dict | None = None,
        dados_gemini: dict | None = None,
        tech_confidence_0_100: float | None = None,
    ) -> dict[str, Any]:
        """
        70% técnica + 20% fluxo Groq + 10% sentimento Gemini.
        Retorna probabilidade 0..100 e metadados.
        """
        groq = dados_groq or {}
        gemini = dados_gemini or {}

        # Soft: filtro Gemini hard só se já veio True (respeita ALLOW_NEWS_HARD_VETO no analyzer)
        hard_veto = bool(gemini.get('filtro_noticia_travar_bot', False))
        if hard_veto:
            print(
                '[CÉREBRO 3 - VETO] Gemini detectou notícia crítica de alto risco. Entrada abortada.',
                flush=True,
            )
            return {
                'probabilidade': 0.0,
                'veto': True,
                'motivo_veto': gemini.get('narrativa_dominante', 'filtro_noticia_travar_bot'),
                'score_tecnico': 0.0,
                'score_fluxo': float(groq.get('score_fluxo', 0) or 0),
                'score_noticias': float(gemini.get('score_sentimento_noticias', 0) or 0),
            }

        if tech_confidence_0_100 is not None:
            score_tecnico = max(0.0, min(1.0, float(tech_confidence_0_100) / 100.0))
        else:
            score_tecnico = self.calcular_score_tecnico(sinais_5_estrategias, condicao_mercado)

        score_fluxo = float(groq.get('score_fluxo', 0) or 0)  # -1..1
        score_noticias = float(gemini.get('score_sentimento_noticias', 0) or 0)  # -1..1

        # Normaliza fluxo/notícias de [-1,1] para [0,1] (0.5 = neutro)
        fluxo_01 = (score_fluxo + 1.0) / 2.0
        news_01 = (score_noticias + 1.0) / 2.0

        probabilidade_01 = (score_tecnico * 0.70) + (fluxo_01 * 0.20) + (news_01 * 0.10)
        probabilidade = max(0.0, min(100.0, probabilidade_01 * 100.0))

        return {
            'probabilidade': round(probabilidade, 2),
            'veto': False,
            'motivo_veto': '',
            'score_tecnico': round(score_tecnico, 4),
            'score_fluxo': score_fluxo,
            'score_noticias': score_noticias,
            'blend': '0.70*tech + 0.20*groq_flow + 0.10*gemini_news',
            'condicao_mercado': condicao_mercado,
            'json_ia_insights': {
                'groq': {
                    'score_fluxo': score_fluxo,
                    'forca_agressao': groq.get('forca_agressao'),
                    'zona_defesa_institucional': groq.get('zona_defesa_institucional'),
                    'alerta_liquidacao': groq.get('alerta_liquidacao'),
                    'source': groq.get('source'),
                },
                'gemini': {
                    'score_sentimento_noticias': score_noticias,
                    'impacto_volatilidade': gemini.get('impacto_volatilidade'),
                    'narrativa_dominante': gemini.get('narrativa_dominante'),
                    'filtro_noticia_travar_bot': gemini.get('filtro_noticia_travar_bot'),
                    'filtro_noticia_travar_bot_sugerido': gemini.get('filtro_noticia_travar_bot_sugerido'),
                    'source': gemini.get('source'),
                },
            },
        }

    def aprender_com_resultado(
        self,
        resultado: str,
        condicao_mercado: str,
        sinais_usados: dict,
        symbol: str | None = None,
        pnl_pct: float | None = None,
    ) -> bool:
        """
        Reforço nos pesos por condição + (se symbol/pnl) AdaptiveStrategyWeights global.
        resultado: 'GANHOU' | 'PERDEU'
        sinais_usados: chaves sma200/supertrend/... com 1/0
        """
        resultado_u = str(resultado or '').upper()
        pesos = self.obter_pesos_atuais(condicao_mercado)
        colmap = {
            'sma200': 'peso_sma200',
            'supertrend': 'peso_supertrend',
            'fibonacci': 'peso_fibonacci',
            'volume_climax': 'peso_volume_climax',
            'sup_res': 'peso_suporte_resistencia',
            # aliases do sistema legado
            'sma': 'peso_sma200',
            'volume': 'peso_volume_climax',
            'support_resistance': 'peso_suporte_resistencia',
        }
        key_alias = {
            'sma': 'sma200',
            'volume': 'volume_climax',
            'support_resistance': 'sup_res',
        }

        conn = self._connect()
        try:
            cur = conn.cursor()
            for estrategia, acertou in (sinais_usados or {}).items():
                canon = key_alias.get(estrategia, estrategia)
                coluna = colmap.get(estrategia) or colmap.get(canon)
                if not coluna or canon not in pesos:
                    continue
                peso_atual = float(pesos.get(canon, 0.2))
                acertou_i = 1 if acertou in (1, True, '1') else 0
                if resultado_u in ('GANHOU', 'WIN') and acertou_i == 1:
                    novo = peso_atual + self.TAXA_APRENDIZADO
                elif resultado_u in ('PERDEU', 'LOSS') and acertou_i == 1:
                    novo = max(0.05, peso_atual - self.TAXA_APRENDIZADO)
                else:
                    novo = peso_atual
                cur.execute(
                    f'UPDATE pesos_estrategias SET {coluna} = ?, updated_at = CURRENT_TIMESTAMP '
                    f'WHERE condicao_mercado = ?',
                    (novo, condicao_mercado),
                )
            conn.commit()
            print(
                f"[CÉREBRO 3 - APRENDIZADO] Pesos atualizados para a condição '{condicao_mercado}'",
                flush=True,
            )
        finally:
            conn.close()

        # Mantém o aprendizado global existente intacto
        if symbol is not None and pnl_pct is not None:
            try:
                self.adaptive.record_outcome(symbol, pnl_pct)
            except Exception:
                pass
        return True

    def log_entry_with_insights(
        self,
        symbol: str,
        signals_bool: dict,
        condicao_mercado: str,
        json_ia_insights: dict | None = None,
    ):
        """Estende log_entry com insights IA (melhor esforço)."""
        sig = self.adaptive.log_entry(symbol, signals_bool)
        if not json_ia_insights and not condicao_mercado:
            return sig
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE strategy_signal_log
                SET json_ia_insights = ?, condicao_mercado = ?
                WHERE id = (
                    SELECT id FROM strategy_signal_log
                    WHERE symbol = ? AND status = 'OPEN'
                    ORDER BY id DESC LIMIT 1
                )
                """,
                (
                    json.dumps(json_ia_insights or {}, ensure_ascii=False),
                    condicao_mercado,
                    symbol,
                ),
            )
            conn.commit()
        except Exception as exc:
            print(f'⚠️ [CÉREBRO 3] log insights: {exc}', flush=True)
        finally:
            conn.close()
        return sig


# Singleton leve
_INSTANCE: Cerebro3DecisaoSoberana | None = None


def get_cerebro3_soberano() -> Cerebro3DecisaoSoberana:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Cerebro3DecisaoSoberana()
    return _INSTANCE
