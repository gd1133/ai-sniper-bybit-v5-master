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

        # RSI rápido para leitura de microexaustão (proxy do 5m em dados comprimidos)
        gain_fast = (delta.where(delta > 0, 0)).rolling(window=5, min_periods=1).mean()
        loss_fast = (-delta.where(delta < 0, 0)).rolling(window=5, min_periods=1).mean()
        rs_fast = gain_fast / (loss_fast + 1e-9)
        self.df['rsi_fast'] = 100 - (100 / (1 + rs_fast))
        
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

        # Suportes/Resistências históricas (janela curta para armadilhas locais)
        self.df['resistance_lookback'] = self.df['high'].rolling(window=60, min_periods=5).max()
        self.df['support_lookback'] = self.df['low'].rolling(window=60, min_periods=5).min()

        # Smart Money: identificação simples de sweep de liquidez com rejeição
        candle_range = (self.df['high'] - self.df['low']).replace(0, 1e-9)
        lower_wick = (self.df[['open', 'close']].min(axis=1) - self.df['low']).clip(lower=0)
        upper_wick = (self.df['high'] - self.df[['open', 'close']].max(axis=1)).clip(lower=0)
        self.df['lower_wick_ratio'] = lower_wick / candle_range
        self.df['upper_wick_ratio'] = upper_wick / candle_range
        self.df['volume_climax'] = self.df['volume_ratio'] >= 1.8

        prev_low_break = self.df['low'] < self.df['low'].shift(1).rolling(window=10, min_periods=3).min()
        prev_high_break = self.df['high'] > self.df['high'].shift(1).rolling(window=10, min_periods=3).max()
        self.df['bullish_liquidity_sweep'] = (
            prev_low_break
            & (self.df['lower_wick_ratio'] >= 0.45)
            & self.df['volume_climax']
            & (self.df['close'] > self.df['open'])
        )
        self.df['bearish_liquidity_sweep'] = (
            prev_high_break
            & (self.df['upper_wick_ratio'] >= 0.45)
            & self.df['volume_climax']
            & (self.df['close'] < self.df['open'])
        )

        # FVG simplificado (3 candles)
        self.df['bullish_fvg'] = self.df['low'] > self.df['high'].shift(2)
        self.df['bearish_fvg'] = self.df['high'] < self.df['low'].shift(2)

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
        
        # Determina Tendência pela SMA 200
        if current_price > sma * 1.01:
            trend = "ALTA"
        elif current_price < sma * 0.99:
            trend = "BAIXA"
        else:
            trend = "NEUTRO"
        
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

        money_flow_side = "WAIT"
        if trend == "ALTA" and recent_return_pct > 0 and float(last['volume_ratio']) >= 1.3:
            money_flow_side = "BUY"
        elif trend == "BAIXA" and recent_return_pct < 0 and float(last['volume_ratio']) >= 1.3:
            money_flow_side = "SELL"

        resistance = float(last['resistance_lookback']) if pd.notna(last['resistance_lookback']) else float(current_price)
        support = float(last['support_lookback']) if pd.notna(last['support_lookback']) else float(current_price)
        near_resistance_pct = ((resistance - current_price) / current_price * 100) if current_price else 0.0
        near_support_pct = ((current_price - support) / current_price * 100) if current_price else 0.0
        near_resistance = resistance > 0 and near_resistance_pct <= 0.45
        near_support = support > 0 and near_support_pct <= 0.45

        # Zonas premium/discount da faixa recente para OB/FVG
        swing_high = float(self.df['high'].iloc[-50:].max()) if len(self.df) >= 5 else float(current_price)
        swing_low = float(self.df['low'].iloc[-50:].min()) if len(self.df) >= 5 else float(current_price)
        swing_mid = (swing_high + swing_low) / 2.0 if swing_high > swing_low else float(current_price)
        in_discount_zone = current_price <= swing_mid
        in_premium_zone = current_price >= swing_mid

        bullish_sweep = bool(last.get('bullish_liquidity_sweep', False))
        bearish_sweep = bool(last.get('bearish_liquidity_sweep', False))
        bullish_fvg = bool(last.get('bullish_fvg', False))
        bearish_fvg = bool(last.get('bearish_fvg', False))
        volume_climax = bool(last.get('volume_climax', False))

        # "Order block" simplificado: zona institucional válida com volume e rejeição.
        bullish_order_block = bool(in_discount_zone and (bullish_sweep or bullish_fvg) and float(last['volume_ratio']) >= 1.2)
        bearish_order_block = bool(in_premium_zone and (bearish_sweep or bearish_fvg) and float(last['volume_ratio']) >= 1.2)

        # Filtro anti-armadilha: proíbe compra em topo esticado e venda em fundo esticado.
        block_long_trap = bool(near_resistance or float(last['rsi']) >= 70.0 or float(last['rsi_fast']) >= 72.0)
        block_short_trap = bool(near_support or float(last['rsi']) <= 30.0 or float(last['rsi_fast']) <= 28.0)

        return {
            'trend': trend,
            'price': float(current_price),
            'sma_200': float(sma),
            'rsi': float(last['rsi']),
            'rsi_fast': float(last['rsi_fast']),
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
            'support_lookback': support,
            'resistance_lookback': resistance,
            'near_resistance': bool(near_resistance),
            'near_support': bool(near_support),
            'near_resistance_pct': float(max(near_resistance_pct, 0.0)),
            'near_support_pct': float(max(near_support_pct, 0.0)),
            'volume_climax': volume_climax,
            'bullish_liquidity_sweep': bullish_sweep,
            'bearish_liquidity_sweep': bearish_sweep,
            'bullish_fvg': bullish_fvg,
            'bearish_fvg': bearish_fvg,
            'bullish_order_block': bullish_order_block,
            'bearish_order_block': bearish_order_block,
            'in_discount_zone': bool(in_discount_zone),
            'in_premium_zone': bool(in_premium_zone),
            'block_long_trap': block_long_trap,
            'block_short_trap': block_short_trap,
        }

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
