# -*- coding: utf-8 -*-
"""
Filtro de maturidade do ativo — exige histórico mínimo em velas diárias (Bybit V5 intervalo D).
Moedas recém-listadas (< MIN_DAILY_CANDLES dias) são descartadas antes da análise no radar.
"""
from __future__ import annotations

import os
from typing import Any, Dict

MIN_DAILY_CANDLES = max(1, int(os.getenv('MIN_DAILY_CANDLES', '30')))


def check_asset_maturity(broker, symbol: str) -> Dict[str, Any]:
    """
    Consulta velas diárias ('D') e valida idade mínima do par.

    Returns:
        dict com keys: allowed (bool), candle_count (int), reason (str)
    """
    try:
        count_fn = getattr(broker, 'count_daily_candles', None)
        if not callable(count_fn):
            return {
                'allowed': False,
                'candle_count': 0,
                'reason': 'broker sem suporte a count_daily_candles',
            }

        candle_count = count_fn(symbol)
        if candle_count is None:
            return {
                'allowed': False,
                'candle_count': 0,
                'reason': 'falha ao consultar velas D na Bybit V5',
            }

        candle_count = int(candle_count)
        if candle_count < MIN_DAILY_CANDLES:
            return {
                'allowed': False,
                'candle_count': candle_count,
                'reason': (
                    f'apenas {candle_count} velas D '
                    f'(mínimo {MIN_DAILY_CANDLES} dias de listagem)'
                ),
            }

        return {
            'allowed': True,
            'candle_count': candle_count,
            'reason': 'ok',
        }
    except Exception as err:
        return {
            'allowed': False,
            'candle_count': 0,
            'reason': f'erro ao validar maturidade: {err}',
        }
