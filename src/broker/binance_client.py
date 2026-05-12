import os
import time

# Global lazy imports
_ccxt_instance = None
_pd_instance = None


def _get_ccxt():
    global _ccxt_instance
    if _ccxt_instance is None:
        import ccxt as ccxt_lib
        _ccxt_instance = ccxt_lib
    return _ccxt_instance


def _get_pd():
    global _pd_instance
    if _pd_instance is None:
        import pandas as pd
        _pd_instance = pd
    return _pd_instance


class BinanceClient:
    """
    Broker Client para Binance Futures USDM.
    Interface idêntica ao BybitClient para permitir troca transparente.
    Suporta testnet (Binance Futures Testnet) e conta real.
    """

    TESTNET_URL = 'https://testnet.binancefuture.com'
    REAL_URL = 'https://fapi.binance.com'

    def __init__(self, api_key=None, api_secret=None, testnet=False):
        ccxt = _get_ccxt()

        api_key = str(api_key or '').strip()
        api_secret = str(api_secret or '').strip()
        self.testnet = bool(testnet)
        self.active_endpoint = self.TESTNET_URL if self.testnet else self.REAL_URL

        # Lê configuração de proxy do ambiente
        proxy_url = str(os.getenv('PROXY_URL') or '').strip()
        self.proxy_url = proxy_url if proxy_url else None

        cfg = {
            'enableRateLimit': True,
            'rateLimit': 100,
            'timeout': 8000,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,
            },
        }
        if api_key and api_secret:
            cfg['apiKey'] = api_key
            cfg['secret'] = api_secret

        # Configura proxy se disponível
        if self.proxy_url:
            cfg['proxies'] = {
                'http': self.proxy_url,
                'https': self.proxy_url,
            }
            print(f"🌐 [PROXY] Usando proxy para Binance: {self.proxy_url}")

        try:
            self.exchange = ccxt.binanceusdm(cfg)

            if self.testnet:
                self.exchange.set_sandbox_mode(True)

            self.authenticated = bool(api_key and api_secret)

            # Cache & rate-limiting (mesmo padrão do BybitClient)
            self.cache_ohlcv = {}
            self.cache_ticker = {}
            self.cache_ttl_ohlcv = 30
            self.cache_ttl_ticker = 10
            self.ohlcv_failures = {}
            self.max_ohlcv_failures = 3
            self.last_request_time = {}
            self.adaptive_delay = 0.5
            self.rate_limit_block_until = 0

            mode_label = 'TESTNET' if self.testnet else 'REAL'
            proxy_info = f" proxy={self.proxy_url}" if self.proxy_url else ""
            print(f"🔍 [BINANCE ENDPOINT] testnet={self.testnet} mode={mode_label}{proxy_info}")
        except Exception as e:
            error_msg = str(e)
            if self.proxy_url:
                print(f"❌ [ERRO PROXY] Falha ao conectar Binance via proxy {self.proxy_url}: {error_msg}")
            else:
                print(f"❌ [ERRO CONEXÃO] Falha ao inicializar Binance: {error_msg}")
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_cache_valid(self, entry, ttl):
        return (time.time() - entry[1]) < ttl

    def _apply_rate_limit(self, endpoint='default'):
        now = time.time()
        if now < self.rate_limit_block_until:
            time.sleep(self.rate_limit_block_until - now)
        last = self.last_request_time.get(endpoint, 0)
        wait = self.adaptive_delay - (now - last)
        if wait > 0:
            time.sleep(wait)
        self.last_request_time[endpoint] = time.time()

    def _is_auth_error(self, msg):
        auth_keywords = ['AuthenticationError', '1100', '-2014', '-2015', 'invalid key', 'API key', 'signature']
        return any(kw.lower() in msg.lower() for kw in auth_keywords)

    # ------------------------------------------------------------------
    # Public interface (mirrors BybitClient)
    # ------------------------------------------------------------------

    def get_balance(self):
        """Retorna saldo USDT disponível na conta Futures."""
        if not self.authenticated:
            return None
        try:
            balance = self.exchange.fetch_balance(params={'type': 'future'})
            usdt = balance.get('USDT', {})
            free = usdt.get('free')
            total = usdt.get('total')
            value = free if free is not None else total
            if value is not None:
                return round(float(value), 2)
        except Exception as e:
            msg = str(e)
            if self._is_auth_error(msg):
                self.authenticated = False
            print(f"[ERRO BINANCE] Falha ao consultar saldo: {msg}")
        return None

    def fetch_ohlcv(self, symbol, timeframe='15m'):
        """Busca candles OHLCV com cache."""
        pd = _get_pd()
        cache_key = f"{symbol}_{timeframe}"

        if cache_key in self.cache_ohlcv and self._is_cache_valid(self.cache_ohlcv[cache_key], self.cache_ttl_ohlcv):
            return self.cache_ohlcv[cache_key][0]

        try:
            self._apply_rate_limit('fetch_ohlcv')
            data = self.exchange.fetch_ohlcv(symbol, timeframe, limit=250)
            df = pd.DataFrame(data, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
            self.cache_ohlcv[cache_key] = (df, time.time())
            self.ohlcv_failures[cache_key] = 0
            return df
        except Exception as e:
            print(f"[ERRO BINANCE] Dados {symbol} falharam: {e}")
            fail_count = self.ohlcv_failures.get(cache_key, 0) + 1
            self.ohlcv_failures[cache_key] = fail_count
            if fail_count >= self.max_ohlcv_failures:
                if cache_key in self.cache_ohlcv:
                    del self.cache_ohlcv[cache_key]
                return None
            return self.cache_ohlcv[cache_key][0] if cache_key in self.cache_ohlcv else None

    def get_last_price(self, symbol):
        """Preço em tempo real com cache curto."""
        if symbol in self.cache_ticker and self._is_cache_valid(self.cache_ticker[symbol], self.cache_ttl_ticker):
            return self.cache_ticker[symbol][0]
        try:
            self._apply_rate_limit('get_last_price')
            ticker = self.exchange.fetch_ticker(symbol)
            price = float(ticker['last'])
            self.cache_ticker[symbol] = (price, time.time())
            return price
        except Exception as e:
            print(f"[ERRO BINANCE] Preço {symbol} falhou: {e}")
            return self.cache_ticker[symbol][0] if symbol in self.cache_ticker else 0.0

    def execute_market_order(self, symbol, side, qty):
        """Executa ordem a mercado na Binance Futures."""
        try:
            if not self.authenticated:
                print('[ERRO BINANCE] Ordem não executada: sem credenciais.')
                return None
            print(f"🔥 [BINANCE ORDER] {side.upper()} {qty} em {symbol}")
            order = self.exchange.create_order(symbol, 'market', side, qty)
            return order
        except Exception as e:
            print(f"❌ [ERRO BINANCE] Falha na ordem: {e}")
            return None

    def set_tp_sl_sniper(self, symbol, side, entry_price, position_qty):
        """Define Take Profit (+10%) e Stop Loss (-3%) via ordens limitadas."""
        try:
            if not self.authenticated:
                return False

            tp_price = round(entry_price * 1.10, 8)
            sl_price = round(entry_price * 0.97, 8)

            close_side = 'sell' if side.lower() in ('buy', 'long') else 'buy'

            print(f"🛡️ [BINANCE TP/SL] {symbol} TP={tp_price} SL={sl_price}")

            # Take profit — limit reduceOnly
            self.exchange.create_order(
                symbol, 'TAKE_PROFIT_MARKET', close_side, position_qty,
                params={'stopPrice': tp_price, 'closePosition': True, 'workingType': 'MARK_PRICE'},
            )
            # Stop loss — stop market reduceOnly
            self.exchange.create_order(
                symbol, 'STOP_MARKET', close_side, position_qty,
                params={'stopPrice': sl_price, 'closePosition': True, 'workingType': 'MARK_PRICE'},
            )
            print('✅ [BINANCE TP/SL SETADO]')
            return True
        except Exception as e:
            print(f"⚠️ [BINANCE TP/SL] {e}")
            return False

    def test_connection(self):
        """Valida conectividade com a Binance Futures.
        Retorna (True, mensagem) ou (False, mensagem).
        """
        try:
            if self.authenticated:
                balance = self.get_balance()
                if balance is not None:
                    success_msg = f"Binance Autenticado OK (USDT {balance:.2f})"
                    if self.proxy_url:
                        success_msg = f"[Via Proxy] {success_msg}"
                    return True, success_msg
                # Tenta via fetch_balance direto para obter melhor mensagem de erro
                try:
                    self.exchange.fetch_balance(params={'type': 'future'})
                except Exception as inner:
                    error_msg = str(inner).split('\n')[0][:200]
                    if self.proxy_url:
                        error_msg = f"[Via Proxy {self.proxy_url}] {error_msg}"
                    return False, error_msg
                error_msg = '❌ ERRO: Chave API Binance inválida ou sem permissão Futures. Verifique se sua API Key está configurada como "No IP Restriction" (ou adicione o IP do proxy na whitelist) e se as permissões de Futures Trading estão ativas.'
                if self.proxy_url:
                    error_msg = f"[Via Proxy] {error_msg}"
                return False, error_msg
            else:
                self.exchange.fetch_tickers()
                success_msg = 'API pública Binance OK (sem credenciais)'
                if self.proxy_url:
                    success_msg = f"[Via Proxy] {success_msg}"
                return True, success_msg
        except Exception as e:
            error_msg = str(e).split('\n')[0][:200]
            if self.proxy_url:
                # Verifica se é um erro de conexão de proxy
                if any(keyword in error_msg.lower() for keyword in ['proxy', 'connection', 'timeout', 'timed out', 'refused']):
                    error_msg = f"❌ ERRO DE PROXY: Não foi possível conectar via {self.proxy_url}. Verifique se o proxy está ativo e acessível. Erro: {error_msg}"
                else:
                    error_msg = f"[Via Proxy {self.proxy_url}] {error_msg}"
            return False, error_msg
