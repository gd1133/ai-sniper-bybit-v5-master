# -*- coding: utf-8 -*-
"""
Teste real do Agente Abacus (Analista Sniper V5).

Uso:
  ABACUS_AGENT_API_KEY=... python scripts/test_abacus_agent.py
ou
  ABACUS_AGENT_DEPLOYMENT_TOKEN=... python scripts/test_abacus_agent.py
"""

from __future__ import annotations

import json

from src.intelligence.abacus_agent_client import (
    abacus_agent_chat,
    parse_abacus_agent_json_response,
)


def build_sample_payload() -> dict:
    return {
        'symbol': 'BTCUSDT',
        'price': 64000.0,
        'gates_advisory': {'is_lateral': False, 'volume_score': 'Institucional'},
        'cerebro1': {
            'trend': {'macro': 'ALTA', 'short': 'ALTA', 'supertrend_signal': 1},
            'structure': {'adx': 28.0, 'is_lateral': False},
            'momentum': {'rsi': 58.0},
            'volatility_volume': {'atr': 820.0},
            'levels': {'near_support': True, 'near_resistance': False},
        },
        'cerebro2': {
            'order_flow': {
                'available': True,
                'score_fluxo': 0.36,
                'forca_agressao': 67,
                'zona_defesa_institucional': True,
                'alerta_liquidacao': False,
            }
        },
        'intel': {'timing_score': 78.0},
        'signals_snapshot': {'volume_ratio': 1.9, 'money_flow_side': 'BUY'},
    }


def main() -> int:
    payload = build_sample_payload()
    msg = (
        'Contexto de mercado:\n'
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        'Decida BUY/SELL/HOLD com gestão de risco e retorne apenas JSON.'
    )
    text = abacus_agent_chat(msg, purpose='manual_test')
    if not text:
        print('❌ Sem resposta do Abacus Agent (verifique API metering/chaves/cooldown).')
        return 1

    parsed = parse_abacus_agent_json_response(text)
    if not parsed:
        print('⚠️ Resposta recebida, mas sem JSON parseável:')
        print(text)
        return 2

    print('✅ Decisão parseada do Analista Sniper V5:')
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
