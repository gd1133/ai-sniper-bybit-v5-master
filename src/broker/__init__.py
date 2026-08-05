# -*- coding: utf-8 -*-
"""
Adaptadores de exchange (Bybit / Binance).

NÃO reexporte BybitClient / OrderCalculator aqui — imports eager neste
__init__ causam circular import (partially initialized module) sob gunicorn
multi-thread no Render. Importe sempre dos submódulos:

    from src.broker.bybit_client import BybitClient
    from src.broker.order_calculator import OrderCalculator
"""

from __future__ import annotations

__all__: list[str] = []
