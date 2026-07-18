import pandas as pd
import numpy as np

class IndicatorEngine:
    """
    🟢 CAMADA 1: MOTOR MATEMÁTICO (LOCAL)
    
    Base Técnica: Smart Money Concepts (SMC)
    Filtros: SMA 200 (Tendência Macro), Fibonacci 0.618 (Golden Zone), Volume, SuperTrend
    
    Função: Filtra o "ruído" do varejo e identifica posicionamento dos grandes bancos.
    """
    def __init__(self, df):
        """
        df: DataFrame com colunas ['ts', 'open', 'high', 'low', 'close', 'vol']
        """
        self.df = df.copy()
        self._calculate_indicators()

    def _calculate_indicators(self):
        """Calcula todos os indicadores técnicos necessários."""
        
        # SMA 200 - Tendência Macro
        self.df['sma_200'] = self.df['close'].rolling(window=200, min_periods=1).mean()
        
        # RSI (14) - Força do Movimento
        delta = self.df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
        rs = gain / (loss + 1e-9)
        self.df['rsi'] = 100 - (100 / (1 + rs))
        
        # ATR (14) - Volatilidade
        high_low = self.df['high'] - self.df['low']
        high_close = abs(self.df['high'] - self.df['close'].shift())
        low_close = abs(self.df['low'] - self.df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        self.df['atr'] = tr.rolling(window=14, min_periods=1).mean()
        
        # SuperTrend (10, 3)
        hl_avg = (self.df['high'] + self.df['low']) / 2
        matr = 3 * self.df['atr']
        self.df['basic_ub'] = hl_avg + matr
        self.df['basic_lb'] = hl_avg - matr
        
        self.df['final_ub'] = self.df['basic_ub']
        self.df['final_lb'] = self.df['basic_lb']
        
        for i in range(1, len(self.df)):
            if self.df['basic_ub'].iloc[i] < self.df['final_ub'].iloc[i-1] or self.df['close'].iloc[i-1] > self.df['final_ub'].iloc[i-1]:
                self.df.loc[i, 'final_ub'] = self.df['basic_ub'].iloc[i]
            else:
                self.df.loc[i, 'final_ub'] = self.df['final_ub'].iloc[i-1]
            
            if self.df['basic_lb'].iloc[i] > self.df['final_lb'].iloc[i-1] or self.df['close'].iloc[i-1] < self.df['final_lb'].iloc[i-1]:
                self.df.loc[i, 'final_lb'] = self.df['basic_lb'].iloc[i]
            else:
                self.df.loc[i, 'final_lb'] = self.df['final_lb'].iloc[i-1]
        
        # SuperTrend: máquina de estados — muda para baixista quando fecha abaixo da
        # banda inferior; muda para altista quando fecha acima da banda superior.
        self.df['supertrend'] = 1
        for i in range(1, len(self.df)):
            prev_st = int(self.df['supertrend'].iloc[i - 1])
            if prev_st == 1:
                # Em tendência de ALTA: continua se fechar acima da banda inferior
                if self.df['close'].iloc[i] < self.df['final_lb'].iloc[i]:
                    self.df.loc[i, 'supertrend'] = -1
                else:
                    self.df.loc[i, 'supertrend'] = 1
            else:
                # Em tendência de BAIXA: reverte se fechar acima da banda superior
                if self.df['close'].iloc[i] > self.df['final_ub'].iloc[i]:
                    self.df.loc[i, 'supertrend'] = 1
                else:
                    self.df.loc[i, 'supertrend'] = -1
        
        # Fibonacci Retracement (0.618)
        high_price = self.df['high'].rolling(window=20).max()
        low_price = self.df['low'].rolling(window=20).min()
        self.df['fib_618'] = high_price - (high_price - low_price) * 0.618
        
        # Volume Trend
        self.df['vol_ma'] = self.df['vol'].rolling(window=20, min_periods=1).mean()
        self.df['volume_ratio'] = self.df['vol'] / (self.df['vol_ma'] + 1e-9)

        # EMA 9 / EMA 21 — timing de entrada (fim de repique)
        self.df['ema_9'] = self.df['close'].ewm(span=9, adjust=False).mean()
        self.df['ema_21'] = self.df['close'].ewm(span=21, adjust=False).mean()
        # EMA 50 — tendência intermediária (leitura de gráfico)
        self.df['ema_50'] = self.df['close'].ewm(span=50, adjust=False).mean()

        # MACD (12, 26, 9) — confirmação de momentum de tendência
        ema_fast = self.df['close'].ewm(span=12, adjust=False).mean()
        ema_slow = self.df['close'].ewm(span=26, adjust=False).mean()
        self.df['macd'] = ema_fast - ema_slow
        self.df['macd_signal'] = self.df['macd'].ewm(span=9, adjust=False).mean()
        self.df['macd_hist'] = self.df['macd'] - self.df['macd_signal']

    def get_signals(self):
        """
        Retorna sinais técnicos consolidados para o Cérebro Triplo.
        
        Retorna dict com:
        - trend: ALTA, BAIXA ou NEUTRO
        - price: preço atual
        - sma_200: média móvel de 200 períodos
        - rsi: força do movimento
        - fib_618: nível de Fibonacci 0.618
        - volume_trend: ALTO ou BAIXO
        - supertrend_signal: 1 (ALTA) ou -1 (BAIXA)
        - atr: volatilidade
        """
        if len(self.df) < 1:
            return {
                'trend': 'NEUTRO',
                'price': 0,
                'sma_200': 0,
                'rsi': 50,
                'fib_618': 0,
                'volume_trend': 'BAIXO',
                'supertrend_signal': 0,
                'atr': 0,
                'recent_return_pct': 0,
                'candle_body_ratio': 0,
                'range_expansion': 0,
                'distance_from_sma_pct': 0,
                'money_flow_side': 'WAIT',
            }
        
        last = self.df.iloc[-1]
        current_price = last['close']
        sma = last['sma_200']
        
        # Tendência macro (SMA200)
        if current_price > sma * 1.01:
            trend = "ALTA"
        elif current_price < sma * 0.99:
            trend = "BAIXA"
        else:
            trend = "NEUTRO"

        # Tendência de curto prazo (EMA9/21)
        ema9 = float(last['ema_9']) if 'ema_9' in last else current_price
        ema21 = float(last['ema_21']) if 'ema_21' in last else current_price
        short_trend = 'ALTA' if ema9 > ema21 and current_price > ema9 else (
            'BAIXA' if ema9 < ema21 and current_price < ema9 else 'NEUTRO'
        )

        # Mantém tendência MACRO (ALTA/BAIXA) mesmo em repique de curto prazo.
        # O timing de entrada (entry_timing) decide o momento; não matar o candidato aqui.
        
        # Volume Trend
        vol_trend = "ALTO" if last['volume_ratio'] >= 1.5 else "BAIXO"
        
        # SuperTrend Signal
        st_signal = int(last['supertrend'])
        fib_distance_pct = (abs(current_price - last['fib_618']) / current_price * 100) if current_price else 0
        reference_close = self.df['close'].iloc[-4] if len(self.df) >= 4 else current_price
        recent_return_pct = ((current_price - reference_close) / reference_close * 100) if reference_close else 0
        candle_range = max(float(last['high'] - last['low']), 1e-9)
        candle_body_ratio = (abs(float(last['close'] - last['open'])) / candle_range) * 100
        range_expansion = float(candle_range / (float(last['atr']) + 1e-9))
        distance_from_sma_pct = (abs(current_price - sma) / sma * 100) if sma else 0

        # Fluxo agressivo: volume 1.15x + retorno OU SuperTrend alinhado à tendência
        money_flow_side = "WAIT"
        vol_ratio = float(last['volume_ratio'])
        if trend == "ALTA" and vol_ratio >= 1.15 and (recent_return_pct > 0 or st_signal == 1):
            money_flow_side = "BUY"
        elif trend == "BAIXA" and vol_ratio >= 1.15 and (recent_return_pct < 0 or st_signal == -1):
            money_flow_side = "SELL"

        try:
            from src.intelligence.regime_detector import detect_market_regime
            regime = detect_market_regime(self.df, {
                'trend': trend,
                'distance_from_sma_pct': distance_from_sma_pct,
                'range_expansion': range_expansion,
            })
        except Exception:
            regime = {
                'market_regime': 'UNKNOWN',
                'is_lateral': trend == 'NEUTRO',
                'adx': 0.0,
                'choppiness': 50.0,
            }

        # Camada incremental: pivôs + velas fortes + estrutura (não substitui o restante)
        try:
            from src.engine.chart_structure import analyze_chart_structure
            chart = analyze_chart_structure(self.df, {
                'trend': trend,
                'volume_ratio': float(last['volume_ratio']),
                'money_flow_side': money_flow_side,
            })
        except Exception:
            chart = {
                'pivot_high': 0.0,
                'pivot_low': 0.0,
                'near_pivot_support': False,
                'near_pivot_resistance': False,
                'bounce_from_pivot_low': False,
                'rejection_from_pivot_high': False,
                'strong_bullish_candle': False,
                'strong_bearish_candle': False,
                'structure_bias': 'NEUTRO',
                'chart_entry_score': 0.0,
                'chart_reasons': [],
            }

        ema50 = float(last['ema_50']) if 'ema_50' in last else float(ema21)
        macd_hist = float(last['macd_hist']) if 'macd_hist' in last else 0.0
        macd_trend = 'ALTA' if macd_hist > 0 else ('BAIXA' if macd_hist < 0 else 'NEUTRO')

        signals_out = {
            'trend': trend,
            'price': float(current_price),
            'sma_200': float(sma),
            'rsi': float(last['rsi']),
            'fib_618': float(last['fib_618']),
            'volume_trend': vol_trend,
            'volume_ratio': float(last['volume_ratio']),
            'fib_distance_pct': float(fib_distance_pct),
            'supertrend_signal': st_signal,
            'atr': float(last['atr']),
            'recent_return_pct': float(recent_return_pct),
            'candle_body_ratio': float(candle_body_ratio),
            'range_expansion': float(range_expansion),
            'distance_from_sma_pct': float(distance_from_sma_pct),
            'money_flow_side': money_flow_side,
            'market_regime': regime.get('market_regime', 'UNKNOWN'),
            'is_lateral': bool(regime.get('is_lateral', False)),
            'adx': float(regime.get('adx', 0) or 0),
            'choppiness': float(regime.get('choppiness', 50) or 50),
            'regime_label': str(regime.get('regime_label', '')),
            'amplitude_pct': float(regime.get('amplitude_pct', 0) or 0),
            'amplitude_lateral': bool(regime.get('amplitude_lateral', False)),
            'ema_9': float(last['ema_9']) if 'ema_9' in last else 0.0,
            'ema_21': float(last['ema_21']) if 'ema_21' in last else 0.0,
            'ema_50': ema50,
            'short_trend': short_trend,
            'macd_hist': macd_hist,
            'macd_trend': macd_trend,
            'pivot_high': float(chart.get('pivot_high') or 0),
            'pivot_low': float(chart.get('pivot_low') or 0),
            'near_pivot_support': bool(chart.get('near_pivot_support')),
            'near_pivot_resistance': bool(chart.get('near_pivot_resistance')),
            'bounce_from_pivot_low': bool(chart.get('bounce_from_pivot_low')),
            'rejection_from_pivot_high': bool(chart.get('rejection_from_pivot_high')),
            'strong_bullish_candle': bool(chart.get('strong_bullish_candle')),
            'strong_bearish_candle': bool(chart.get('strong_bearish_candle')),
            'structure_bias': str(chart.get('structure_bias') or 'NEUTRO'),
            'chart_entry_score': float(chart.get('chart_entry_score') or 0),
            'chart_reasons': list(chart.get('chart_reasons') or []),
        }
        # Camada incremental: rastreador institucional (VWAP + pegada de volume + spread)
        try:
            from src.engine.rastreador_institucional import RastreadorInstitucional
            inst = RastreadorInstitucional().get_latest_signal(self.df)
            signals_out.update(inst)
        except Exception:
            signals_out.update({
                'sinal_institucional': 'NEUTRO',
                'vwap': 0.0,
                'big_player_ativo': False,
                'institutional_spread': 0.0,
                'institutional_spread_ma': 0.0,
                'institutional_signal_low': 0.0,
                'institutional_signal_high': 0.0,
                'institutional_sl_price': 0.0,
                'amplitude_pct': float(signals_out.get('amplitude_pct', 0) or 0),
                'is_accumulation': False,
                'is_lateral_amplitude': False,
            })

        # Acumulação / amplitude baixa: força NEUTRO e bloqueia entrada
        if signals_out.get('is_lateral_amplitude') or signals_out.get('is_accumulation') or signals_out.get('amplitude_lateral') or signals_out.get('is_lateral'):
            signals_out['trend'] = 'NEUTRO'
            signals_out['is_lateral'] = True
            signals_out['sinal_institucional'] = 'NEUTRO'
            signals_out['money_flow_side'] = 'WAIT'
            if not signals_out.get('regime_label'):
                amp = float(signals_out.get('amplitude_pct', 0) or 0)
                signals_out['regime_label'] = f'LATERAL/ACUMULAÇÃO — amplitude {amp:.3f}% — sinais ignorados'

        # Fair Value Gap (SMC) — confirmação de imbalance institucional
        try:
            from src.engine.cautious_entry_gate import detect_fair_value_gap
            signals_out.update(detect_fair_value_gap(self.df))
        except Exception:
            signals_out.update({'fvg_bullish': False, 'fvg_bearish': False, 'fvg_mid': 0.0})

        try:
            from src.engine.market_heat import compute_candle_heat
            heat = compute_candle_heat(signals_out, self.df)
            signals_out.update(heat)
        except Exception:
            signals_out.update({
                'heat_score': 50.0,
                'heat_bias': 'NEUTRAL',
                'heat_label': 'Heat indisponível',
                'heat_reasons': [],
                'entry_heat_ok': False,
            })
        return signals_out

    def get_smart_money_zones(self):
        """
        Retorna os níveis de Smart Money para entrada (Ponto Zero).
        Baseado em Fibonacci 0.618 (Golden Zone).
        """
        if len(self.df) < 20:
            return []
        
        zones = []
        
        # Identifica os últimos 5 swings para calcular níveis de retração
        for i in range(len(self.df) - 5, len(self.df)):
            if i < 20:
                continue
            
            high_20 = self.df['high'].iloc[i-20:i].max()
            low_20 = self.df['low'].iloc[i-20:i].min()
            
            fib_618 = high_20 - (high_20 - low_20) * 0.618
            zones.append({
                'timestamp': self.df.iloc[i]['ts'],
                'fib_618_zone': fib_618,
                'price': self.df.iloc[i]['close'],
                'distance_pct': abs(self.df.iloc[i]['close'] - fib_618) / fib_618 * 100
            })
        
        return zones[-5:] if zones else []  # Últimas 5 zonas
