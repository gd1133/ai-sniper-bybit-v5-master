"""Blindagem anti-travamento: Cérebro 1/2 isolados + Cérebro 3 soberano."""

from __future__ import annotations

from src.ai_brain.validator import AI_UNAVAILABLE_REPORT, GroqValidator


def _tech_alta():
    return {
        'trend': 'ALTA',
        'supertrend_signal': 1,
        'rsi': 55,
        'volume_ratio': 2.0,
        'fib_distance_pct': 1.0,
        'candle_body_ratio': 70,
        'range_expansion': 1.5,
        'adx': 28,
        'price': 100.0,
        'sma_200': 95.0,
        'fib_618': 98.0,
    }


def test_consensus_returns_four_agents_compat():
    res = GroqValidator().consensus_predict(
        _tech_alta(),
        'BTC/USDT:USDT',
        intelligence_context={
            'allow_entry': True,
            'intelligence_score': 70,
            'timing_score': 80,
            'whale_aligned': True,
            'summary': 'Fluxo institucional ok',
            'global_trend': 'BULLISH',
        },
    )
    assert 'agents' in res
    assert [a['id'] for a in res['agents']] == ['gemini', 'groq', 'analyst', 'learner']
    assert res.get('autonomous_mode') is False


def test_cerebro3_autonomous_when_assistants_unavailable():
    res = GroqValidator().consensus_predict(
        _tech_alta(),
        'ETH/USDT:USDT',
        intelligence_context={
            'allow_entry': True,
            'ai_assistants_unavailable': True,
            'autonomous_mode': True,
            'intelligence_score': 40,
            'timing_score': 50,
            'summary': AI_UNAVAILABLE_REPORT,
            'global_trend': 'NEUTRAL',
        },
    )
    assert res.get('autonomous_mode') is True
    assert res['brains']['cerebro3'] == 'autonomous'
    assert res['cerebro_reports']['cerebro2']['report'] == AI_UNAVAILABLE_REPORT
    # Não trava o ativo: probabilidade vem da matemática local / histórico
    assert float(res.get('probabilidade', 0)) >= 0
    assert res.get('decisao') in ('BUY', 'SELL', 'WAIT')


def test_hard_veto_still_blocks():
    res = GroqValidator().consensus_predict(
        _tech_alta(),
        'SOL/USDT:USDT',
        intelligence_context={
            'allow_entry': False,
            'hard_veto_reasons': ['Mercado LATERAL'],
            'veto_reasons': ['Mercado LATERAL'],
            'soft_ai_veto_only': False,
        },
    )
    assert res['decisao'] == 'WAIT'
    assert res['probabilidade'] == 0
    assert 'bloqueou' in res['motivo'].lower() or 'LATERAL' in res['motivo']


def test_api_soft_path_does_not_hard_block_in_consensus():
    """allow_entry=False + autonomous_mode → Cérebro 3 assume, não retorna 0 cego."""
    res = GroqValidator().consensus_predict(
        _tech_alta(),
        'XRP/USDT:USDT',
        intelligence_context={
            'allow_entry': False,
            'ai_assistants_unavailable': True,
            'autonomous_mode': True,
            'veto_reasons': ['Notícias/sentimento'],
            'hard_veto_reasons': [],
            'soft_ai_veto_only': True,
        },
    )
    assert res.get('autonomous_mode') is True
    assert 'agents' in res
    assert len(res['agents']) == 4
