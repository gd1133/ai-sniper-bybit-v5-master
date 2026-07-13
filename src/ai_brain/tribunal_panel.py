"""
Tribunal de IAs — painel de evidência para o cliente.

Quatro analistas conversam sobre a entrada (Gemini, Groq, Analista de Dados, Aprendizado),
explicam o estudo das velas e estimam assertividade de vitória.
"""

from __future__ import annotations

import os
from typing import Any

import requests

try:
    from groq import Groq
except Exception:
    Groq = None


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _side_label(side: str) -> str:
    s = str(side or '').upper()
    if s in ('BUY', 'COMPRAR', 'LONG'):
        return 'COMPRA'
    if s in ('SELL', 'VENDER', 'SHORT'):
        return 'VENDA'
    return s or 'SCANNER'


def build_candle_study(df, signals: dict | None = None, limit: int = 48) -> dict[str, Any]:
    """Extrai velas recentes + notas de estudo (SMC / volume / estrutura)."""
    signals = signals or {}
    candles = []
    if df is not None and len(df) > 0:
        tail = df.iloc[-limit:]
        for _, row in tail.iterrows():
            candles.append({
                't': int(row['ts']) if 'ts' in row and row['ts'] == row['ts'] else 0,
                'o': round(float(row['open']), 6),
                'h': round(float(row['high']), 6),
                'l': round(float(row['low']), 6),
                'c': round(float(row['close']), 6),
                'v': round(float(row['vol']), 4),
            })

    notes = []
    trend = str(signals.get('trend', 'NEUTRO')).upper()
    if trend in ('ALTA', 'BAIXA'):
        notes.append(f'Tendência macro SMA200: {trend}')
    vol = float(signals.get('volume_ratio', 0) or 0)
    if vol >= 2.0:
        notes.append(f'Volume Clímax ({vol:.1f}× média) — fluxo institucional')
    elif vol >= 1.5:
        notes.append(f'Volume institucional ({vol:.1f}×)')
    fib = float(signals.get('fib_distance_pct', 99) or 99)
    if fib <= 1.5:
        notes.append(f'Preço na Golden Zone Fib 0.618 (distância {fib:.2f}%)')
    elif fib <= 3.0:
        notes.append(f'Próximo da zona Fib 0.618 ({fib:.2f}%)')
    if signals.get('strong_bullish_candle'):
        notes.append('Vela forte de alta (corpo dominante)')
    if signals.get('strong_bearish_candle'):
        notes.append('Vela forte de baixa (corpo dominante)')
    if signals.get('bounce_from_pivot_low'):
        notes.append('Reação em pivô de suporte')
    if signals.get('rejection_from_pivot_high'):
        notes.append('Rejeição em pivô de resistência')
    st = int(signals.get('supertrend_signal', 0) or 0)
    if st == 1:
        notes.append('SuperTrend altista')
    elif st == -1:
        notes.append('SuperTrend baixista')
    adx = float(signals.get('adx', 0) or 0)
    if adx:
        notes.append(f'ADX={adx:.1f} ({"tendência" if adx > 22 else "frágil/lateral"})')
    if not notes:
        notes.append('Aguardando confluência estrutural completa')

    return {
        'candles': candles,
        'entry_price': float(signals.get('price', 0) or 0),
        'fib_618': float(signals.get('fib_618', 0) or 0),
        'sma_200': float(signals.get('sma_200', 0) or 0),
        'study_notes': notes,
    }


def _estimate_assertiveness(
    score: float,
    side: str,
    intel_ctx: dict | None = None,
    learning_stats: dict | None = None,
) -> float:
    """Combina score do agente + win rate histórico + inteligência."""
    intel_ctx = intel_ctx or {}
    learning_stats = learning_stats or {}
    hist_wr = float(learning_stats.get('win_rate', 50) or 50)
    sample = int(learning_stats.get('total_trades', 0) or 0)
    intel = float(intel_ctx.get('intelligence_score', 50) or 50)
    timing = float(intel_ctx.get('timing_score', 50) or 50)

    base = float(score) * 0.45 + hist_wr * 0.25 + intel * 0.15 + timing * 0.15
    if sample < 3:
        base = base * 0.92  # penaliza baixa amostragem
    if not intel_ctx.get('allow_entry', True):
        base *= 0.5
    side_u = str(side or '').upper()
    trend_news = str(intel_ctx.get('global_trend', 'NEUTRAL')).upper()
    if side_u in ('BUY', 'COMPRAR') and trend_news == 'BEARISH':
        base -= 8
    if side_u in ('SELL', 'VENDER') and trend_news == 'BULLISH':
        base -= 8
    return round(max(5.0, min(97.0, base)), 1)


def _cloud_gemini_comment(symbol: str, side: str, tech_summary: str) -> str | None:
    key = os.getenv('GEMINI_API_KEY', '').strip()
    if not key or not _env_bool('ENABLE_AI_TRIBUNAL_CLOUD', True):
        return None
    try:
        url = (
            'https://generativelanguage.googleapis.com/v1beta/models/'
            f'gemini-2.0-flash:generateContent?key={key}'
        )
        prompt = (
            f'Você é o analista Gemini do robô Motor Sniper. Em 2 frases curtas em português, '
            f'explique por que a entrada {side} em {symbol} faz sentido (ou o risco). '
            f'Dados:\n{tech_summary}\nResponda só o texto, sem JSON.'
        )
        rsp = requests.post(
            url,
            json={'contents': [{'parts': [{'text': prompt}]}]},
            timeout=12,
        )
        if rsp.status_code != 200:
            return None
        text = (
            ((rsp.json() or {}).get('candidates') or [{}])[0]
            .get('content', {})
            .get('parts', [{}])[0]
            .get('text', '')
        )
        return (text or '').strip()[:320] or None
    except Exception as exc:
        print(f'⚠️ [TRIBUNAL] Gemini indisponível: {exc}', flush=True)
        return None


def _cloud_groq_comment(symbol: str, side: str, tech_summary: str) -> str | None:
    key = os.getenv('GROQ_API_KEY', '').strip()
    if not key or Groq is None or not _env_bool('ENABLE_AI_TRIBUNAL_CLOUD', True):
        return None
    try:
        client = Groq(api_key=key)
        prompt = (
            f'Você é o analista Groq tático do Motor Sniper. Em 2 frases curtas em português, '
            f'debata a entrada {side} em {symbol} com foco em timing/volume/risco.\n{tech_summary}'
        )
        rsp = client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.3,
            max_tokens=180,
        )
        text = (rsp.choices[0].message.content or '').strip()
        return text[:320] or None
    except Exception as exc:
        print(f'⚠️ [TRIBUNAL] Groq indisponível: {exc}', flush=True)
        return None


def build_ai_tribunal_evidence(
    *,
    symbol: str,
    side: str,
    tech_data: dict,
    consensus: dict,
    intelligence_context: dict | None = None,
    df=None,
    learning_stats: dict | None = None,
    threshold: float = 60.0,
    max_positions: int = 5,
) -> dict[str, Any]:
    """
    Monta o payload completo dos 4 cards + diálogo + gráfico de velas + assertividade.
    """
    intel = intelligence_context or consensus.get('intelligence') or {}
    learning_stats = learning_stats or {}
    agents_raw = consensus.get('agents') or []
    probabilidade = float(consensus.get('probabilidade', 0) or 0)
    decisao = str(consensus.get('decisao', side) or side).upper()
    side_lbl = _side_label(decisao if decisao in ('BUY', 'SELL', 'COMPRAR', 'VENDER') else side)

    # Garante 4 agentes nomeados (gemini, groq, analyst, learner)
    by_id = {a.get('id'): a for a in agents_raw if isinstance(a, dict)}
    defaults = [
        ('gemini', 'Gemini Estratégico', 25, 'Visão macro, notícias e viés institucional'),
        ('groq', 'Groq Tático', 25, 'Timing, volume e execução rápida'),
        ('analyst', 'Analista de Dados', 30, 'SMC, Fibonacci, SuperTrend e velas'),
        ('learner', 'Aprendizado Neural', 20, 'Memória das entradas anteriores'),
    ]
    agents = []
    for aid, label, weight, role in defaults:
        src = by_id.get(aid) or {}
        score = float(src.get('score', probabilidade) or 0)
        action = str(src.get('action', decisao) or 'WAIT').upper()
        motivo = str(src.get('motivo') or consensus.get('motivo') or role)
        assertiveness = _estimate_assertiveness(score, side_lbl, intel, learning_stats)
        agents.append({
            'id': aid,
            'label': label,
            'role': role,
            'provider': src.get('provider', 'local'),
            'score': round(score, 1),
            'weight': weight,
            'action': action,
            'motivo': motivo,
            'assertiveness': assertiveness,
            'learning_notes': src.get('learning_notes') or (
                learning_stats.get('summary') if aid == 'learner' else ''
            ),
        })

    tech_summary = (
        f"Symbol={symbol} side={side_lbl} score={probabilidade:.1f}\n"
        f"trend={tech_data.get('trend')} RSI={tech_data.get('rsi')} "
        f"vol×={tech_data.get('volume_ratio')} fib_dist={tech_data.get('fib_distance_pct')}\n"
        f"ADX={tech_data.get('adx')} regime={intel.get('market_regime')} "
        f"whales={intel.get('whale_score')} news={intel.get('global_trend')}\n"
        f"motivo={str(consensus.get('motivo', ''))[:240]}"
    )

    gemini_cloud = _cloud_gemini_comment(symbol, side_lbl, tech_summary)
    groq_cloud = _cloud_groq_comment(symbol, side_lbl, tech_summary)
    if gemini_cloud:
        agents[0]['motivo'] = gemini_cloud
        agents[0]['provider'] = 'gemini'
    if groq_cloud:
        agents[1]['motivo'] = groq_cloud
        agents[1]['provider'] = 'groq'

    # Diálogo (conversa entre as IAs)
    dialogue = []
    g, q, a, l = agents[0], agents[1], agents[2], agents[3]
    dialogue.append({
        'speaker': 'gemini',
        'label': g['label'],
        'text': (
            f"Estou vendo {symbol} para {side_lbl}. {g['motivo'][:180]} "
            f"Assertividade estimada: {g['assertiveness']}%."
        ),
    })
    dialogue.append({
        'speaker': 'groq',
        'label': q['label'],
        'text': (
            f"Concordo em debater o timing. {q['motivo'][:160]} "
            f"Meu score tático: {q['score']}/100."
        ),
    })
    dialogue.append({
        'speaker': 'analyst',
        'label': a['label'],
        'text': (
            f"No gráfico: {a['motivo'][:180]} "
            f"Estudo SMC/Volume aponta ação {a['action']}."
        ),
    })
    hist_line = learning_stats.get('summary') or l.get('learning_notes') or 'Ainda poucas amostras neste par.'
    dialogue.append({
        'speaker': 'learner',
        'label': l['label'],
        'text': (
            f"Com base nas entradas anteriores: {hist_line} "
            f"Win rate histórico {float(learning_stats.get('win_rate', 0) or 0):.1f}% "
            f"({int(learning_stats.get('total_trades', 0) or 0)} trades)."
        ),
    })
    dialogue.append({
        'speaker': 'consensus',
        'label': 'Veredito do Tribunal',
        'text': (
            f"Decisão final: {side_lbl} com confiança {probabilidade:.0f}%. "
            f"Assertividade combinada {_estimate_assertiveness(probabilidade, side_lbl, intel, learning_stats)}%. "
            f"{'Entrada autorizada pelos cérebros.' if probabilidade >= threshold and decisao in ('BUY', 'SELL', 'COMPRAR', 'VENDER') else 'Ainda em observação — aguardando confluência total.'}"
        ),
    })

    candle_study = build_candle_study(df, tech_data)
    overall_assert = _estimate_assertiveness(probabilidade, side_lbl, intel, learning_stats)

    brains = {
        agent['id']: {
            'label': agent['label'],
            'score': agent['score'],
            'weight': agent['weight'],
            'action': agent['action'],
            'motivo': agent['motivo'],
            'assertiveness': agent['assertiveness'],
            'provider': agent['provider'],
        }
        for agent in agents
    }

    checks = []
    for label, active, detail in [
        ('Tendência macro alinhada', str(tech_data.get('trend', '')).upper() in ('ALTA', 'BAIXA'), tech_data.get('trend')),
        ('Volume / fluxo', float(tech_data.get('volume_ratio', 0) or 0) >= 1.5, f"×{float(tech_data.get('volume_ratio', 0) or 0):.2f}"),
        ('Fib / zona institucional', float(tech_data.get('fib_distance_pct', 99) or 99) <= 3.0, f"{float(tech_data.get('fib_distance_pct', 99) or 99):.2f}%"),
        ('ADX tendência', float(tech_data.get('adx', 0) or 0) > 22, f"ADX {float(tech_data.get('adx', 0) or 0):.1f}"),
        ('Baleias / intel', bool(intel.get('whale_aligned') or float(intel.get('whale_score', 0) or 0) >= 40), f"score {intel.get('whale_score', 0)}"),
        ('Sentimento notícias', str(intel.get('global_trend', 'NEUTRAL')).upper() != 'BEARISH' or side_lbl == 'VENDA', intel.get('global_trend')),
        ('Consenso ≥ rigor', probabilidade >= threshold, f"{probabilidade:.0f}% / {threshold:.0f}%"),
    ]:
        checks.append({'label': label, 'active': bool(active), 'detail': str(detail or '')})

    return {
        'symbol': str(symbol or '').replace('/USDT:USDT', '').replace('/USDT', ''),
        'side': side_lbl,
        'confidence': round(probabilidade, 1),
        'assertiveness': overall_assert,
        'threshold': threshold,
        'max_positions': max_positions,
        'strategic_reason': g['motivo'],
        'tactical_reason': q['motivo'],
        'local_reason': a['motivo'],
        'learning_reason': l['motivo'],
        'agents': agents,
        'brains': brains,
        'dialogue': dialogue,
        'candle_study': candle_study,
        'learning_from_history': {
            'sample_size': int(learning_stats.get('total_trades', 0) or 0),
            'win_rate': float(learning_stats.get('win_rate', 0) or 0),
            'total_pnl': float(learning_stats.get('total_pnl', 0) or 0),
            'summary': learning_stats.get('summary') or '',
            'recent': learning_stats.get('recent') or [],
        },
        'checks': checks,
        'updated_at': __import__('time').time(),
    }
