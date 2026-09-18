# -*- coding: utf-8 -*-
"""Macro cloud removido — retorno neutro para o C3 Python local."""

from __future__ import annotations

from typing import Any


def analyze_gemini_macro_news(
    symbol: str,
    headlines: list | None = None,
    news_blob: str = '',
    signals: dict | None = None,
) -> dict[str, Any]:
    return {
        'score_sentimento_noticias': 0.0,
        'impacto_volatilidade': 'BAIXO',
        'narrativa_dominante': 'Macro cloud removido — C3 Python local',
        'filtro_noticia_travar_bot': False,
        'source': 'local_python',
        'available': False,
    }
