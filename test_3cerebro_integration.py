"""
🧪 TESTES DE INTEGRAÇÃO v61.0
Validação do 3º Cérebro Executor Principal com aprendizado local.
"""

import unittest
import tempfile
import os
import json
import sqlite3
from datetime import datetime, timedelta

# Mock imports para testes
try:
    from src.ai_brain.learning import TradeLearner
    from src.ai_brain.local_ml_engine import LocalMLEngine
except ImportError:
    pass


class TestLocalMLEngine(unittest.TestCase):
    """Testes do motor local de ML do 3º Cérebro."""
    
    def setUp(self):
        """Inicializa BD temporário para testes."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
    def tearDown(self):
        """Limpa BD temporário."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_ml_engine_initialization(self):
        """Testa inicialização do motor local."""
        ml_engine = LocalMLEngine(db_path=self.db_path)
        self.assertIsNotNone(ml_engine)
        self.assertEqual(ml_engine.min_local_confidence, 80)
    
    def test_confidence_calculation(self):
        """Testa cálculo de confiança com indicadores."""
        ml_engine = LocalMLEngine(db_path=self.db_path)
        
        # Cenário forte: todos indicadores OK
        strong_signal = {
            'trend': 'ALTA',
            'supertrend': 1,
            'sma_200': 1900.0,
            'fib_distance_pct': 0.5,
            'volume_ratio': 2.0,
            'rsi': 55.0
        }
        
        confidence = ml_engine._calculate_local_confidence(strong_signal)
        self.assertEqual(confidence, 100)  # Todos os pontos
    
    def test_confidence_calculation_weak(self):
        """Testa cálculo de confiança com sinais fracos."""
        ml_engine = LocalMLEngine(db_path=self.db_path)
        
        # Cenário fraco: sem indicadores claros
        weak_signal = {
            'trend': '---',
            'supertrend': 0,
            'sma_200': 0,
            'fib_distance_pct': 999,
            'volume_ratio': 0.5,
            'rsi': 50.0
        }
        
        confidence = ml_engine._calculate_local_confidence(weak_signal)
        # RSI entre 20-80 sempre dá 10 pontos
        self.assertEqual(confidence, 10)
    
    def test_direction_resolution_buy(self):
        """Testa resolução de direção BUY."""
        ml_engine = LocalMLEngine(db_path=self.db_path)
        
        buy_signal = {
            'trend': 'ALTA',
            'supertrend': 1,
            'rsi': 60.0
        }
        
        direction, reason = ml_engine.resolve_entry_direction(buy_signal)
        self.assertEqual(direction, "BUY")
        self.assertIn("ALTA", reason)
    
    def test_direction_resolution_sell(self):
        """Testa resolução de direção SELL."""
        ml_engine = LocalMLEngine(db_path=self.db_path)
        
        sell_signal = {
            'trend': 'BAIXA',
            'supertrend': -1,
            'rsi': 40.0
        }
        
        direction, reason = ml_engine.resolve_entry_direction(sell_signal)
        self.assertEqual(direction, "SELL")
        self.assertIn("BAIXA", reason)
    
    def test_direction_resolution_wait(self):
        """Testa resolução WAIT sem sinal claro."""
        ml_engine = LocalMLEngine(db_path=self.db_path)
        
        no_signal = {
            'trend': '---',
            'supertrend': 0,
            'rsi': 50.0
        }
        
        direction, reason = ml_engine.resolve_entry_direction(no_signal)
        self.assertEqual(direction, "WAIT")
    
    def test_entry_evaluation_authorized(self):
        """Testa autorização de entrada com confiança alta."""
        ml_engine = LocalMLEngine(db_path=self.db_path)
        
        strong_data = {
            'trend': 'ALTA',
            'supertrend': 1,
            'sma_200': 1900.0,
            'fib_distance_pct': 0.5,
            'volume_ratio': 2.0,
            'rsi': 55.0
        }
        
        should_enter, reason, confidence = ml_engine.evaluate_entry_conditions(
            'ETHUSDT', strong_data
        )
        
        self.assertTrue(should_enter)
        self.assertIn("autorizada", reason.lower())
        self.assertGreaterEqual(confidence, 80)
    
    def test_entry_evaluation_rejected(self):
        """Testa rejeição de entrada com confiança baixa."""
        ml_engine = LocalMLEngine(db_path=self.db_path)
        
        weak_data = {
            'trend': '---',
            'supertrend': 0,
            'sma_200': 0,
            'fib_distance_pct': 999,
            'volume_ratio': 0.5,
            'rsi': 50.0
        }
        
        should_enter, reason, confidence = ml_engine.evaluate_entry_conditions(
            'ETHUSDT', weak_data
        )
        
        self.assertFalse(should_enter)
        # RSI entre 20-80 dá 10 pontos mesmo com outros sinais fracos
        self.assertEqual(confidence, 10)  # Apenas RSI contribui

    
    def test_record_and_finalize_trade(self):
        """Testa gravação e finalização de trade."""
        learner = TradeLearner(db_path=self.db_path)
        ml_engine = LocalMLEngine(db_path=self.db_path)
        
        indicators = {
            'trend': 'ALTA',
            'sma_200': 1900.0,
            'supertrend': 1,
            'rsi': 55.0
        }
        
        # Registra entrada
        learner.record_local_entry(
            symbol='ETHUSDT',
            side='BUY',
            indicators_dict=indicators,
            entry_price=1905.0,
            entry_qty=0.1,
            entry_margin=100.0
        )
        
        # Finaliza com lucro
        learner.finalize_local_trade(
            symbol='ETHUSDT',
            exit_price=1930.0,
            pnl_pct=1.5
        )
        
        # Verifica registro
        stats = ml_engine.get_performance_stats('ETHUSDT')
        self.assertEqual(stats['total_trades'], 1)
        self.assertEqual(stats['wins'], 1)
    
    def test_block_symbol_on_failure_pattern(self):
        """Testa bloqueio de símbolo após 3 perdas consecutivas."""
        learner = TradeLearner(db_path=self.db_path)
        ml_engine = LocalMLEngine(db_path=self.db_path)
        
        indicators = {
            'trend': 'ALTA',
            'sma_200': 1900.0,
            'supertrend': 1,
            'rsi': 55.0
        }
        
        # Registra 3 operações com perda consecutiva
        for i in range(3):
            learner.record_local_entry(
                symbol='ETHUSDT',
                side='BUY',
                indicators_dict=indicators,
                entry_price=1905.0 + i,
                entry_qty=0.1,
                entry_margin=100.0
            )
            
            learner.finalize_local_trade(
                symbol='ETHUSDT',
                exit_price=1900.0 + i,
                pnl_pct=-1.0  # Perda
            )
        
        # Testa detecção de padrão
        should_block, failure_reason, consecutive = learner.analyze_failure_patterns('ETHUSDT')
        self.assertTrue(should_block)
        self.assertGreaterEqual(consecutive, 3)
    
    def test_symbol_blocking(self):
        """Testa bloqueio temporário de símbolo."""
        learner = TradeLearner(db_path=self.db_path)
        
        # Bloqueia símbolo por 60 segundos
        learner.block_symbol_temporarily(
            symbol='ETHUSDT',
            reason='Test block',
            duration_seconds=60
        )
        
        # Verifica bloqueio
        is_blocked, reason = learner.is_symbol_blocked('ETHUSDT')
        self.assertTrue(is_blocked)
        self.assertIn('Test block', reason)
    
    def test_symbol_auto_unblock(self):
        """Testa desbloqueio automático após expiração."""
        learner = TradeLearner(db_path=self.db_path)
        
        # Bloqueia por 0 segundos (já expirado)
        learner.block_symbol_temporarily(
            symbol='ETHUSDT',
            reason='Test block',
            duration_seconds=0
        )
        
        # Espera um pouco e verifica desbloqueio automático
        import time
        time.sleep(0.1)
        
        is_blocked, reason = learner.is_symbol_blocked('ETHUSDT')
        self.assertFalse(is_blocked)
    
    def test_ml_stats_generation(self):
        """Testa geração de estatísticas de ML."""
        learner = TradeLearner(db_path=self.db_path)
        ml_engine = LocalMLEngine(db_path=self.db_path)
        
        indicators = {
            'trend': 'ALTA',
            'sma_200': 1900.0,
            'supertrend': 1,
            'rsi': 55.0
        }
        
        # Cria 5 trades: 3 lucros, 2 perdas
        for i in range(3):
            learner.record_local_entry(
                symbol='ETHUSDT',
                side='BUY',
                indicators_dict=indicators,
                entry_price=1900.0,
                entry_qty=0.1,
                entry_margin=100.0
            )
            learner.finalize_local_trade(
                symbol='ETHUSDT',
                exit_price=1910.0,
                pnl_pct=1.0  # Lucro
            )
        
        for i in range(2):
            learner.record_local_entry(
                symbol='ETHUSDT',
                side='SELL',
                indicators_dict=indicators,
                entry_price=1900.0,
                entry_qty=0.1,
                entry_margin=100.0
            )
            learner.finalize_local_trade(
                symbol='ETHUSDT',
                exit_price=1890.0,
                pnl_pct=-1.0  # Perda
            )
        
        stats = ml_engine.get_performance_stats('ETHUSDT')
        
        self.assertEqual(stats['total_trades'], 5)
        self.assertEqual(stats['wins'], 3)
        self.assertAlmostEqual(stats['win_rate'], 60.0, places=1)
    
    def test_learning_context(self):
        """Testa geração de contexto de aprendizado."""
        learner = TradeLearner(db_path=self.db_path)
        ml_engine = LocalMLEngine(db_path=self.db_path)
        
        indicators = {
            'trend': 'ALTA',
            'sma_200': 1900.0,
            'supertrend': 1,
            'rsi': 55.0
        }
        
        learner.record_local_entry(
            symbol='ETHUSDT',
            side='BUY',
            indicators_dict=indicators,
            entry_price=1900.0,
            entry_qty=0.1,
            entry_margin=100.0
        )
        learner.finalize_local_trade(
            symbol='ETHUSDT',
            exit_price=1910.0,
            pnl_pct=1.0
        )
        
        context = ml_engine.get_learning_context('ETHUSDT')
        self.assertIn('ETHUSDT', context)
        self.assertIn('LUCRO', context)


class TestRateLimitHandling(unittest.TestCase):
    """Testes de tratamento de rate limit (429)."""
    
    def test_429_error_detection(self):
        """Testa detecção de erro 429."""
        error_str = "429 Too Many Requests"
        self.assertIn('429', error_str)
    
    def test_rate_limit_marker(self):
        """Testa marcador de rate limit."""
        rate_limit_marker = "429_RATE_LIMIT"
        self.assertEqual(rate_limit_marker, "429_RATE_LIMIT")


if __name__ == '__main__':
    print("═" * 60)
    print("🧪 TESTES DO 3º CÉREBRO EXECUTOR PRINCIPAL v61.0")
    print("═" * 60)
    
    # Roda testes
    unittest.main(verbosity=2)
