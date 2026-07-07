# Inteligência de Mercado — IA Institucional

## O que foi adicionado

O robô agora possui uma **camada de inteligência institucional** que analisa:

1. **Regime de mercado** — detecta mercado **lateral** (range) e **bloqueia entradas**
2. **Atividade de baleias** — volume institucional, fluxo de dinheiro, horário NY/Londres
3. **Notícias e sentimento global** — CoinGecko trending + IA (Groq/Gemini)
4. **Timing de entrada** — golden zone Fibonacci + alinhamento com grandes players
5. **Ranking de oportunidades** — escolhe a **melhor moeda** do radar, não a primeira

## Fluxo atualizado

```
Radar (top 50 moedas)
    ↓
Indicadores técnicos + regime (ADX, Choppiness)
    ↓
Bloqueio se LATERAL ou NEUTRO
    ↓
IA Institucional (baleias + notícias + timing)
    ↓
Consenso 4 cérebros (local + analista + IA mercado + aprendizado)
    ↓
Ranking por score composto
    ↓
Entrada na MELHOR oportunidade
```

## Os 4 cérebros do consenso

| Cérebro | Peso | Função |
|---------|------|--------|
| Local | 20% | Confluências técnicas (Fib, volume, trend) |
| Analista | 30% | SuperTrend, RSI, volume institucional |
| **IA Mercado** | **30%** | **Regime, baleias, notícias, timing** |
| Aprendizado | 20% | Histórico de trades no SQLite |

## Filtros anti-lateral

Mercado classificado como **LATERAL** quando:
- ADX < 20 (sem tendência forte)
- Choppiness > 55 (mercado picado/consolidação)
- Preço preso na SMA200 (trend NEUTRO)
- Bandas de Bollinger comprimidas

## Detecção de baleias

Pontua atividade institucional com:
- Volume 1.5x–2x+ acima da média
- Candle de convicção (corpo forte + expansão ATR)
- `money_flow_side` alinhado com tendência
- Spike de volume na última barra
- Horários NY/Londres (13–16 UTC, 7–10 UTC)

## Notícias e sentimento (IA)

1. **CoinGecko** — moedas em trending + sentimento da comunidade
2. **Groq** (se `GROQ_API_KEY`) — análise contextual em JSON
3. **Gemini** (se `GEMINI_API_KEY`) — fallback de análise

## Variáveis de ambiente

```env
ENABLE_MARKET_INTELLIGENCE=true   # Liga/desliga toda a camada
BLOCK_LATERAL_MARKETS=true        # Bloqueia mercado lateral
ENABLE_NEWS_AI=true               # Notícias + sentimento
GROQ_API_KEY=...                  # IA para análise de contexto
GEMINI_API_KEY=...                # Fallback IA
```

## Arquivos

```
src/intelligence/
├── regime_detector.py      # ADX, Choppiness, lateral vs tendência
├── whale_detector.py       # Fluxo institucional e timing de sessão
├── news_analyzer.py        # Trending + sentimento + Groq/Gemini
└── market_intelligence.py  # Orquestrador principal
```

## Score final de oportunidade

```
score = probabilidade_IA
      + intelligence_score × 0.25
      + timing_score × 0.10
      + liquidez_24h
      + money_flow × 0.25
      + edge_historico
```

A moeda com **maior score** é escolhida para entrada.
