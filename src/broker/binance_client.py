# -*- coding: utf-8 -*-
import time
import sys
import io
import threading
from decimal import Decimal

# Força UTF-8 no stdout do Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Globals para Lazy Loading com Thread Safety
_ccxt_instance = None
_pd_instance = None
_ccxt_lock = threading.Lock()
_pd_lock = threading.Lock()

def _get_ccxt():
    global _ccxt_instance
    if _ccxt_instance is not None:
        return _ccxt_instance
    with _ccxt_lock:
        if _ccxt_instance is None:
            print("⏳ Carregando CCXT para Binance...", flush=True)
            import ccxt as ccxt_lib
            _ccxt_instance = ccxt_lib
            print("✅ CCXT Binance carregado com sucesso", flush=True)
    return _ccxt_instance

def _get_pd():
    global _pd_instance
    if _pd_instance is not None:
        return _pd_instance
    with _pd_lock:
        if _pd_instance is None:
            import pandas as pd
            _pd_instance = pd
    return _pd_instance


class BinanceClient:
    """
    IA 1 (Binance): Responsável pela comunicação estrita com a Binance Futures.
    Mecanismo de proteção Decimal via String + amount_to_precision nativo do CCXT.
    """
    def __init__(self, api_key=None, api_secret=None, testnet=False, client_name=None):
        # Lazy loading de configurações internas para evitar importação circular
        from src.config import resolve_use_testnet
        from src.broker.order_calculator import OrderCalculator

        ccxt = _get_ccxt()
        self.client_name = client_name or 'cliente-genérico'
        self.testnet = resolve_use_testnet(testnet)
        self.authenticated = bool(api_key and api_secret)

        cfg = {
            'enableRateLimit': True,
            'rateLimit': 50,
            'timeout': 15000,
            'options': {
                'defaultType': 'future',  # 🚀 Alvo estrito: Binance Futures (USDT-M)
                'adjustForTimeDifference': True,
                'recvWindow': 10000,
            }
        }

        if self.authenticated:
            cfg['apiKey'] = str(api_key).strip()
            cfg['secret'] = str(api_secret).strip()

        self.exchange = ccxt.binance(cfg)
        self.order_calculator = OrderCalculator(exchange_name='binance')

        if self.testnet:
            self.exchange.set_sandbox_mode(True)

        # Sincronização de relógio inicial anti-mismatch
        if self.authenticated:
            try:
                self.exchange.load_time_difference()
                print("✅ [BINANCE TIME SYNC] Relógio sincronizado com o servidor Futures")
            except Exception as sync_err:
                print(f"⚠️ [BINANCE TIME SYNC] Aviso: {sync_err}")

        # 🔍 LOG CLARO DE IDENTIFICAÇÃO: Mostra o ambiente e cliente
        ambiente_tag = "🧪 [SIMULAÇÃO]" if self.testnet else "🔴 [CONTA REAL]"
        print(f"{ambiente_tag} [BINANCE] Instanciando cliente '{self.client_name}' em modo {'SIMULAÇÃO' if self.testnet else 'CONTA REAL'}", flush=True)

        # Sistema de Cache Local
        self.cache_ohlcv = {}
        self.cache_ticker = {}
        self.cache_ttl_ohlcv = 30
        self.cache_ttl_ticker = 5

    def _is_cache_valid(self, cache_entry, ttl):
        if cache_entry is None: return False
        _, timestamp = cache_entry
        return (time.time() - timestamp) < ttl

    def get_last_price(self, symbol):
        """Busca o último preço de mercado com cache rápido."""
        if symbol in self.cache_ticker and self._is_cache_valid(self.cache_ticker[symbol], self.cache_ttl_ticker):
            return self.cache_ticker[symbol][0]

        try:
            ticker = self.exchange.fetch_ticker(symbol)
            price = float(ticker['last'])
            self.cache_ticker[symbol] = (price, time.time())
            return price
        except Exception as e:
            print(f"❌ [ERRO BINANCE PRICE] Falha ao obter preço de {symbol}: {e}")
            return self.cache_ticker[symbol][0] if symbol in self.cache_ticker else 0.0

    def get_balance(self):
        """Busca o saldo disponível em USDT na carteira de Futuros."""
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = balance.get('total', {}).get('USDT')
            return float(usdt_balance) if usdt_balance is not None else 0.0
        except Exception as e:
            print(f"❌ [ERRO BINANCE BALANCE] Falha ao ler carteira Futures: {e}")
            return None

    def fetch_ohlcv(self, symbol, timeframe="15m"):
        """Busca histórico de velas para os indicadores."""
        pd = _get_pd()
        cache_key = f"{symbol}_{timeframe}"
        if cache_key in self.cache_ohlcv and self._is_cache_valid(self.cache_ohlcv[cache_key], self.cache_ttl_ohlcv):
            return self.cache_ohlcv[cache_key][0]

        try:
            data = self.exchange.fetch_ohlcv(symbol, timeframe, limit=200)
            df = pd.DataFrame(data, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
            self.cache_ohlcv[cache_key] = (df, time.time())
            return df
        except Exception as e:
            print(f"❌ [ERRO BINANCE OHLCV] Falha em {symbol}: {e}")
            return self.cache_ohlcv[cache_key][0] if cache_key in self.cache_ohlcv else None

    def _normalize_order_qty(self, symbol, qty):
        """
        🔧 CORREÇÃO DEFINITIVA BINANCE V2:
        Conversão Decimal via String + amount_to_precision nativo do CCXT.
        """
        try:
            # Conversão segura de float para Decimal usando string
            qty_decimal = Decimal(str(float(qty)))
        except (TypeError, ValueError):
            raise ValueError(f"Quantidade inválida: {qty}")

        if qty_decimal <= 0:
            raise ValueError(f"Quantidade deve ser positiva: {qty}")

        current_price = self.get_last_price(symbol)
        if current_price <= 0:
            raise ValueError(f"Preço inválido para {symbol}")

        try:
            self.exchange.load_markets()
            market = self.exchange.market(symbol)
            limits = market.get('limits', {})

            min_amount = limits.get('amount', {}).get('min')
            if min_amount is None or str(min_amount).lower() == 'none' or min_amount <= 0:
                min_amount = 0.001

            # Piso de custo padrão da Binance Futures é $5.0. Usamos $5.5 como margem de segurança.
            min_cost = limits.get('cost', {}).get('min')
            if min_cost is None or str(min_cost).lower() == 'none' or min_cost <= 0:
                min_cost = 5.5

            print(f"   📊 [BINANCE LIMITS] {symbol}: min_amount={min_amount}, min_notional={min_cost} USDT", flush=True)
        except Exception as market_err:
            print(f"⚠️ [BINANCE MARKET] Erro ao ler limites: {market_err}, usando defaults", flush=True)
            min_amount = 0.001
            min_cost = 5.5

        # Conversões seguras usando Decimal(str())
        min_cost_decimal = Decimal(str(min_cost))
        current_price_decimal = Decimal(str(current_price))
        min_qty_for_notional = min_cost_decimal / current_price_decimal

        required_min_qty = max(Decimal(str(min_amount)), min_qty_for_notional)

        if qty_decimal < required_min_qty:
            print(f"⚠️ [BINANCE QTY] Quantidade {qty_decimal} abaixo do piso. Ajustando para {required_min_qty}", flush=True)
            qty_decimal = required_min_qty

        # Delega arredondamento final estritamente ao CCXT
        final_qty = self.exchange.amount_to_precision(symbol, float(qty_decimal))

        # Proteção pós-arredondamento contra quebras de centavos nocionais
        final_qty_decimal = Decimal(str(final_qty))
        notional_value_decimal = final_qty_decimal * current_price_decimal

        if notional_value_decimal < min_cost_decimal:
            adjusted_qty = min_cost_decimal / current_price_decimal
            final_qty = self.exchange.amount_to_precision(symbol, float(adjusted_qty) * 1.05)
            final_qty_decimal = Decimal(str(final_qty))
            notional_value_decimal = final_qty_decimal * current_price_decimal
            print(f"   🔧 [BINANCE NOTIONAL RE-ADJUSTED] Elevando lote mínimo: qty={final_qty}", flush=True)

        print(f"   ✅ [BINANCE ORDER VALIDA] qty={final_qty} (notional={float(notional_value_decimal):.2f} USDT >= {float(min_cost_decimal)} USDT)", flush=True)
        return str(final_qty)

    def execute_market_order(self, symbol, side, qty, raise_on_error=False):
        """Executa ordem de mercado instantânea na Binance Futures."""
        try:
            if not self.authenticated:
                raise RuntimeError("Cliente sem credenciais autenticadas para operar na Binance.")

            normalized_qty = self._normalize_order_qty(symbol, qty)
            ccxt_qty = float(normalized_qty)

            print(f"🔥 [ORDEM SNIPER BINANCE] {side.upper()} {normalized_qty} em {symbol}", flush=True)
            
            # Execução direta via CCXT Futures
            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),
                amount=ccxt_qty
            )
            
            order_id = order.get('id', 'N/A')
            print(f"✅ [BINANCE FUTURES] Ordem criada com sucesso - ID: {order_id}", flush=True)
            return order

        except Exception as e:
            print(f"❌ [ERRO CRÍTICO EXECUÇÃO BINANCE]: {e}", flush=True)
            if raise_on_error:
                raise
            return None

    def set_tp_sl_sniper(self, symbol, side, entry_price, position_qty):
        """
        🎯 PROTOCOLO 100/50 - SETAGEM AUTOMÁTICA DE TP/SL NA BINANCE FUTURES
        Take Profit: +10% de movimento (+100% de lucro sobre margem com alavancagem 10x)
        Stop Loss: -50% de perda sobre o valor da entrada (Proteção Institucional)
        """
        try:
            if not self.authenticated: return False

            # Lado reverso para fechar
            exit_side = 'sell' if side.lower() == 'buy' else 'buy'

            # Cálculo estrito dos alvos de preço com base na direção
            if side.lower() == 'buy':
                tp_price = entry_price * 1.10  # +10% movimento
                sl_price = entry_price * 0.50  # -50% do valor de entrada (Stop Loss de 50%)
            else:
                tp_price = entry_price * 0.90  # -10% movimento (lucra na queda)
                sl_price = entry_price * 1.50  # +50% do valor de entrada (Stop Loss de 50%)

            price_to_precision = getattr(self.exchange, 'price_to_precision', None)
            if callable(price_to_precision):
                tp_price = float(price_to_precision(symbol, tp_price))
                sl_price = float(price_to_precision(symbol, sl_price))

            print(f"🛡️ [BINANCE PROTEÇÃO] Ativo: {symbol}")
            print(f"   📍 Entrada: ${entry_price:.4f}")
            print(f"   ✅ Target TP (+100%): ${tp_price:.4f}")
            print(f"   ❌ Target SL (-50%): ${sl_price:.4f}")

            # Envia o Stop Loss como ordem de gatilho acoplada
            self.exchange.create_order(
                symbol=symbol,
                type='STOP_MARKET',
                side=exit_side,
                amount=float(position_qty),
                params={'stopPrice': sl_price, 'reduceOnly': True}
            )
            print(f"✅ [BINANCE TP/SL] Trava de Stop Loss configurada com sucesso.")
            return True
        except Exception as e:
            print(f"⚠️ [BINANCE TP/SL] Falha ao configurar proteção de capital: {e}")
            return False
