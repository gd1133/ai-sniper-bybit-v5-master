"""Reproduce Groq-429 → Maestro cascade + radar pressure locally (no live orders)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.debug_agent_log import agent_dbg
from src.ai_brain.validator import GroqValidator
from src.intelligence import news_analyzer as na


def main():
    agent_dbg('C', 'reproduce_rate_limit_cascade.py', 'start', {
        'scan_top_sim': 40,
        'delay_sim': 0.9,
    }, run_id='post-fix')

    symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'APT/USDT:USDT', 'XRP/USDT:USDT']
    validator = GroqValidator()
    maestro_count = 0
    c2_down_count = 0
    groq_attempts = 0
    groq_skipped_cooldown = 0

    def _fake_groq(symbol, tech_summary, groq_key):
        nonlocal groq_attempts, groq_skipped_cooldown
        now = time.time()
        if now < na._GROQ_COOLDOWN_UNTIL:
            groq_skipped_cooldown += 1
            agent_dbg('B', 'reproduce:fake_groq', 'skipped_cooldown', {
                'symbol': symbol, 'cooldown_until': na._GROQ_COOLDOWN_UNTIL,
            }, run_id='post-fix')
            return None
        groq_attempts += 1
        na._GROQ_COOLDOWN_UNTIL = now + 180
        na._GROQ_FAIL_STREAK += 1
        agent_dbg('B', 'reproduce:fake_groq', 'simulated_429', {
            'symbol': symbol, 'attempt': groq_attempts,
            'cooldown_until': na._GROQ_COOLDOWN_UNTIL,
        }, run_id='post-fix')
        print(f"[NEWS AI] Groq indisponivel: Error code: 429 simulated for {symbol}", flush=True)
        return None

    na._ai_analyze_with_groq = _fake_groq
    os.environ['GROQ_API_KEY'] = 'test-key-debug'
    os.environ['ENABLE_NEWS_AI'] = 'true'

    na._fetch_web_headlines = lambda coin, limit=6: [{'title': f'{coin} crypto trend', 'source': 'sim'}]
    na._fetch_coingecko_trending = lambda: []
    na._fetch_coingecko_sentiment = lambda coin_id: {}
    na._ai_analyze_with_gemini = lambda *a, **k: None
    na._CACHE.clear()
    na._GROQ_COOLDOWN_UNTIL = 0.0
    na._GROQ_FAIL_STREAK = 0

    tech = {
        'trend': 'BAIXA',
        'supertrend_signal': -1,
        'rsi': 40,
        'volume_ratio': 1.8,
        'fib_distance_pct': 1.0,
        'candle_body_ratio': 55,
        'range_expansion': 1.1,
        'is_lateral': False,
        'adx': 28,
        'heat_score': 60,
        'heat_bias': 'BEAR',
    }

    for sym in symbols:
        news = na.analyze_news_sentiment(sym, tech, {'is_lateral': False}, {})
        agent_dbg('A', 'reproduce:news_result', 'news_flags', {
            'symbol': sym,
            'ai_unavailable': news.get('ai_unavailable'),
            'cloud_ai_degraded': news.get('cloud_ai_degraded'),
            'source': news.get('source'),
        }, run_id='post-fix')
        intel = {
            'allow_entry': True,
            'ai_assistants_unavailable': False,
            'autonomous_mode': False,
            'cloud_news_degraded': bool(news.get('cloud_ai_degraded')),
            'intelligence_score': 55,
            'timing_score': 60,
            'sentiment_score': news.get('sentiment_score'),
            'global_trend': news.get('global_trend'),
            'news_risk': news.get('news_risk'),
            'headlines': news.get('headlines'),
            'summary': news.get('reason'),
            'whale_aligned': False,
        }
        res = validator.consensus_predict(tech, sym, intelligence_context=intel)
        brains = res.get('brains') or {}
        if brains.get('cerebro2') == 'unavailable':
            c2_down_count += 1
        if res.get('autonomous_mode'):
            maestro_count += 1
        agent_dbg('E', 'reproduce:consensus', 'consensus_result', {
            'symbol': sym,
            'autonomous': res.get('autonomous_mode'),
            'c1': brains.get('cerebro1'),
            'c2': brains.get('cerebro2'),
            'decisao': res.get('decisao'),
        }, run_id='post-fix')

    agent_dbg('C', 'reproduce_rate_limit_cascade.py', 'summary', {
        'groq_attempts': groq_attempts,
        'groq_skipped_cooldown': groq_skipped_cooldown,
        'c2_down_count': c2_down_count,
        'maestro_count': maestro_count,
        'fix_ok': maestro_count == 0 and c2_down_count == 0 and groq_attempts == 1,
    }, run_id='post-fix')
    print(
        f'REPRO_SUMMARY groq_attempts={groq_attempts} skipped={groq_skipped_cooldown} '
        f'c2_down={c2_down_count} maestro={maestro_count}/{len(symbols)}',
        flush=True,
    )


if __name__ == '__main__':
    main()
