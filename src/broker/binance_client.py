import time

# Global lazy imports
_ccxt_instance = None
_pd_instance = None


def _get_ccxt():
    global _ccxt_instance
    if _ccxt_instance is None:
        print("⏳ Carregando CCXT (primeira vez)...", flush=True)
        import ccxt as ccxt_lib
        _ccxt_instance = ccxt_lib
        print("✅ CCXT carregado com sucesso", flush=True)
    return _ccxt_instance


def _get_pd():
    global _pd_instance
    if _pd_instance is None:
        print("⏳ Carregando Pandas...", flush=True)
        import pandas as pd
        _pd_instance = pd
        print("✅ Pandas carregado com sucesso", flush=True)
    return _pd_instance


# Import order calculator
from src.broker.order_calculator import OrderCalculator, sanitize_numeric_string


class BinanceClient:
    """
    Broker Client para Binance Futures USDM.
    Interface idêntica ao BybitClient para permitir troca transparente.
    Suporta testnet (Binance Futures Testnet) e conta real.
    """

    TESTNET_URL = 'https://testnet.binancefuture.com'
    BINANCE_FUTURES_HOSTS = (
        'https://fapi.binance.com',
        'https://fapi1.binance.com',
        'https://fapi2.binance.com',
    )
    REAL_URL = BINANCE_FUTURES_HOSTS[0]

    def __init__(self, api_key=None, api_secret=None, testnet=False):
        # 🔧 SANITIZAÇÃO: Remove espaços, quebras de linha e caracteres invisíveis
        api_key = str(api_key or '').strip().replace('\n', '').replace('\r', '')
        api_secret = str(api_secret or '').strip().replace('\n', '').replace('\r', '')
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = bool(testnet)
        self.endpoint_index = 0
        self.api_hosts = [self.TESTNET_URL] if self.testnet else list(self.BINANCE_FUTURES_HOSTS)
        self.active_endpoint = self.TESTNET_URL if self.testnet else self.REAL_URL

        self.exchange = self._create_exchange()

        # 🔧 SINCRONIZAÇÃO DE TEMPO: Executa ao inicializar para evitar erros de timestamp
        if api_key and api_secret:
            try:
                self.exchange.load_time_difference()
                print(f"✅ [BINANCE TIME SYNC] Diferença de tempo sincronizada com servidor")
            except Exception as sync_err:
                print(f"⚠️ [BINANCE TIME SYNC] Aviso: {sync_err}")

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
        auth_status = '🔐 Autenticado' if self.authenticated else '🔓 Público'
        print(f"🔍 [BINANCE] Modo: {mode_label} | Status: {auth_status} | Endpoint: {self.active_endpoint}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_cache_valid(self, entry, ttl):
        return (time.time() - entry[1]) < ttl

    def _build_exchange_urls(self, api_host):
        return {
            'api': {
                'fapiPublic': api_host,
                'fapiPrivate': api_host,
            },
        }

    def _build_exchange_config(self):
        cfg = {
            'enableRateLimit': True,
            'rateLimit': 100,
            'timeout': 8000,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,  # 🔧 OBRIGATÓRIO: Ajuste automático de diferença de tempo
                'recvWindow': 10000,  # 🔧 OBRIGATÓRIO: 10s de tolerância para evitar erros InvalidNonce
            },
        }
        if self.api_key and self.api_secret:
            cfg['apiKey'] = self.api_key
            cfg['secret'] = self.api_secret
        if not self.testnet:
            cfg['urls'] = self._build_exchange_urls(self.active_endpoint)

        # Inicializa calculadora de ordens dinâmica
        if not hasattr(self, 'order_calculator'):
            self.order_calculator = OrderCalculator(exchange_name='binance')

        return cfg

    def _apply_exchange_urls(self, exchange, api_host):
        if self.testnet:
            return
        urls = self._build_exchange_urls(api_host)
        exchange.urls = getattr(exchange, 'urls', {}) or {}
        exchange.urls['api'] = dict(urls['api'])
        exchange.options = getattr(exchange, 'options', {}) or {}
        exchange.options['adjustForTimeDifference'] = True

    def _create_exchange(self):
        ccxt = _get_ccxt()
        exchange = ccxt.binanceusdm(self._build_exchange_config())
        if self.testnet:
            exchange.set_sandbox_mode(True)
        else:
            self._apply_exchange_urls(exchange, self.active_endpoint)
        return exchange

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

    def _is_http_451_error(self, error):
        status_code = getattr(error, 'status', None) or getattr(error, 'http_status_code', None)
        if str(status_code) == '451':
            return True
        msg = str(error)
        return '451' in msg and 'legal reasons' in msg.lower()

    def _rotate_binance_api_endpoint(self):
        if self.testnet or len(self.api_hosts) <= 1:
            return False

        next_index = self.endpoint_index + 1
        if next_index >= len(self.api_hosts):
            return False

        self.endpoint_index = next_index
        self.active_endpoint = self.api_hosts[self.endpoint_index]
        self._apply_exchange_urls(self.exchange, self.active_endpoint)
        print(f"⚠️ [BINANCE ENDPOINT] HTTP 451 detectado; alternando para {self.active_endpoint}")
        return True

    def _call_with_451_retry(self, operation):
        attempts = 1 if self.testnet else len(self.api_hosts)
        for current_attempt in range(attempts):
            try:
                return operation()
            except Exception as e:
                if not self._is_http_451_error(e):
                    raise
                has_next_endpoint = current_attempt < (attempts - 1) and self._rotate_binance_api_endpoint()
                if not has_next_endpoint:
                    raise

    # ------------------------------------------------------------------
    # Public interface (mirrors BybitClient)
    # ------------------------------------------------------------------

    def get_balance(self):
        """Retorna saldo USDT disponível na conta Futures."""
        if not self.authenticated:
            return None
        try:
            balance = self._call_with_451_retry(
                lambda: self.exchange.fetch_balance(params={'type': 'future'})
            )
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
            data = self._call_with_451_retry(
                lambda: self.exchange.fetch_ohlcv(symbol, timeframe, limit=250)
            )
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
            ticker = self._call_with_451_retry(lambda: self.exchange.fetch_ticker(symbol))
            price = float(ticker['last'])
            self.cache_ticker[symbol] = (price, time.time())
            return price
        except Exception as e:
            print(f"[ERRO BINANCE] Preço {symbol} falhou: {e}")
            return self.cache_ticker[symbol][0] if symbol in self.cache_ticker else 0.0

    def calculate_dynamic_order_qty(self, symbol: str, balance=None):
        """
        🆕 CALCULADORA DINÂMICA DE ORDENS v1.0

        Calcula a quantidade de uma ordem baseada nos limites ESTRITOS da corretora,
        eliminando completamente o modelo de percentual fixo (5%, 15%, etc.).

        Fluxo:
        1. Busca dinamicamente: market["limits"]["amount"]["min"] e market["limits"]["cost"]["min"]
        2. Calcula quantidade EXATA para atingir o nocional mínimo + margem de segurança
        3. Aplica amount_to_precision do CCXT obrigatoriamente
        4. Se saldo fornecido, pode usar múltiplo do mínimo (opcional)

        Args:
            symbol: Par de negociação (ex: 'BTCUSDT', 'ETH/USDT')
            balance: Saldo disponível em USDT (opcional). Se None, usa apenas valor mínimo

        Returns:
            Tuple (quantidade_final, metadata)
        """
        current_price = self.get_last_price(symbol)
        if current_price <= 0:
            raise ValueError(f"Não foi possível obter preço atual para {symbol}")

        if balance is None or balance <= 0:
            # Usa apenas o valor mínimo absoluto da corretora
            return self.order_calculator.calculate_minimum_order_qty(
                self.exchange, symbol, current_price
            )
        else:
            # Usa saldo para calcular com possível múltiplo do mínimo
            return self.order_calculator.calculate_order_qty_from_balance(
                self.exchange, symbol, current_price, balance, risk_multiplier=1.0
            )

    def _normalize_order_qty(self, symbol, qty):
        """
        Normaliza quantidade para precisão aceita pela Binance, evitando Qty invalid.
        🔧 CORREÇÃO: Considera simultaneamente min amount e min notional.
        """
        from decimal import Decimal, ROUND_UP

        try:
            qty_value = float(qty)
        except (TypeError, ValueError):
            raise ValueError(f"Quantidade inválida: {qty}")

        if qty_value <= 0:
            raise ValueError(f"Quantidade deve ser positiva: {qty}")

        # 🔧 PASSO 1: Busca preço atual do ativo
        current_price = self.get_last_price(symbol)
        if current_price <= 0:
            raise ValueError(f"Não foi possível obter preço atual para {symbol}")

        # 🔧 PASSO 2: Carrega limites do mercado (min amount e min notional)
        try:
            self.exchange.load_markets()
            market = self.exchange.market(symbol)
            limits = market.get('limits', {})

            # Min amount (quantidade mínima em contratos/moedas)
            min_amount = limits.get('amount', {}).get('min', 0.001)

            # Min notional (valor mínimo em USDT)
            min_cost = limits.get('cost', {}).get('min', 5.0)  # Binance Futures geralmente exige >= 5 USDT

            # Precisão da quantidade
            amount_precision = market.get('precision', {}).get('amount', 3)

            print(f"   📊 [BINANCE LIMITS] {symbol}: min_amount={min_amount}, min_notional={min_cost} USDT, precision={amount_precision}")
        except Exception as market_err:
            print(f"⚠️ [BINANCE MARKET] Erro ao carregar limites: {market_err}, usando defaults")
            min_amount = 0.001
            min_cost = 5.0
            amount_precision = 3

        # 🔧 PASSO 3: Calcula quantidade mínima para satisfazer min notional
        min_qty_for_notional = Decimal(str(min_cost)) / Decimal(str(current_price))

        # 🔧 PASSO 4: Usa o maior entre min_amount e min_qty_for_notional
        required_min_qty = max(Decimal(str(min_amount)), min_qty_for_notional)

        # Se quantidade fornecida for menor que o mínimo, usa o mínimo
        if Decimal(str(qty_value)) < required_min_qty:
            print(f"⚠️ [BINANCE QTY] Quantidade {qty_value} abaixo do mínimo. Ajustando para {required_min_qty}")
            qty_value = float(required_min_qty)

        # 🔧 PASSO 5: Arredonda para cima respeitando precisão da exchange
        step = Decimal('1').scaleb(-amount_precision)
        quantized = Decimal(str(qty_value)).quantize(step, rounding=ROUND_UP)

        # Garante que após arredondamento ainda atende min notional
        notional_value = float(quantized) * current_price
        if notional_value < min_cost:
            # Arredonda para cima até atingir min notional
            quantized = (Decimal(str(min_cost)) / Decimal(str(current_price))).quantize(step, rounding=ROUND_UP)
            notional_value = float(quantized) * current_price
            print(f"   🔧 [BINANCE NOTIONAL] Ajustado para qty={quantized} (notional={notional_value:.2f} USDT >= {min_cost} USDT)")

        normalized = format(quantized, 'f')
        final_qty = normalized.rstrip('0').rstrip('.') if '.' in normalized else normalized

        # 🔧 PASSO 6: Exibe informações de validação
        final_notional = float(final_qty) * current_price
        print(f"   ✅ [BINANCE ORDER] qty={final_qty} (notional={final_notional:.2f} USDT, min_amount={min_amount}, min_notional={min_cost} USDT)")

        return final_qty

    def execute_market_order(self, symbol, side, qty, raise_on_error=False):
        """Executa ordem a mercado na Binance Futures."""
        try:
            if not self.authenticated:
                print('[ERRO BINANCE] Ordem não executada: sem credenciais.')
                if raise_on_error:
                    raise RuntimeError('Cliente sem credenciais autenticadas para enviar ordem na Binance.')
                return None

            # 🔧 FORMATAÇÃO ESTRITA: Normaliza quantidade usando CCXT precision
            normalized_qty = self._normalize_order_qty(symbol, qty)

            print(f"🔥 [BINANCE ORDER] {side.upper()} {normalized_qty} em {symbol}")
            print(f"   🌐 Endpoint: {self.active_endpoint}")
            print(f"   🔐 Autenticado: {self.authenticated}")
            print(f"   🧪 Modo Testnet: {self.testnet}")

            print(f"   📤 Enviando ordem via CCXT: symbol={symbol}, type=market, side={side}, qty={normalized_qty}")
            order = self._call_with_451_retry(
                lambda: self.exchange.create_order(symbol, 'market', side, float(normalized_qty))
            )
            print(f"   📥 Resposta da API Binance: {order}")
            print(f"✅ [BINANCE] Ordem criada com sucesso - ID: {order.get('id', 'N/A')}")
            return order
        except Exception as e:
            # Importa ccxt para capturar erros específicos da corretora
            ccxt = _get_ccxt()

            if isinstance(e, ccxt.BaseError):
                error_details = str(e)
                print(f"❌ ERRO REAL DA CORRETORA BINANCE: {error_details}")

                # Extrai código HTTP se disponível
                http_status = getattr(e, 'status', None) or getattr(e, 'http_status_code', None)
                if http_status:
                    print(f"   🌐 HTTP STATUS CODE: {http_status}")
                    if http_status in [400, 429, 451]:
                        print(f"   ⚠️  ERRO CRÍTICO HTTP {http_status} - Verifique configurações da API")

                # Diagnóstico detalhado de erros CCXT
                if isinstance(e, ccxt.InsufficientFunds):
                    print(f"   💰 SALDO INSUFICIENTE: Deposite fundos na conta Binance Futures ou reduza o tamanho da ordem")
                elif isinstance(e, ccxt.InvalidOrder):
                    print(f"   📏 ORDEM INVÁLIDA: Verifique tamanho mínimo de lote, preço ou quantidade")
                    if "lot size" in error_details.lower() or "min" in error_details.lower():
                        print(f"   ⚠️  TAMANHO MÍNIMO DE LOTE INVÁLIDO: Quantidade {qty:.4f} abaixo do mínimo permitido")
                    if "notional" in error_details.lower():
                        print(f"   ⚠️  NOCIONAL MÍNIMO: Valor da ordem abaixo do mínimo exigido (geralmente >= 5 USDT)")
                        print(f"   💡 SOLUÇÃO: Aumente a quantidade ou escolha um ativo com preço mais alto")
                elif isinstance(e, ccxt.AuthenticationError):
                    print(f"   🔑 ERRO DE AUTENTICAÇÃO: Verifique suas credenciais API Binance (key/secret)")
                    if "API-key" in error_details or "Invalid API" in error_details or "Invalid Api-Key ID" in error_details:
                        print(f"   ⚠️  API Key inválida ou expirada")
                        print(f"   💡 SOLUÇÃO:")
                        print(f"      1. Verifique se API Key e Secret estão corretos (sem espaços extras)")
                        print(f"      2. Confirme que as permissões de FUTURES estão habilitadas")
                        print(f"      3. Verifique se seu IP está na whitelist (se configurado)")
                        print(f"      4. Gere novas credenciais se necessário")
                    elif "Signature" in error_details:
                        print(f"   ⚠️  Assinatura inválida - verifique o API Secret")
                        print(f"   💡 SOLUÇÃO: Verifique se API Secret está correto e recvWindow está configurado")
                    elif "Timestamp" in error_details or "recvWindow" in error_details:
                        print(f"   ⏰ ERRO DE TIMESTAMP: Dessincronização de relógio")
                        print(f"   💡 SOLUÇÃO: Sincronize o relógio do sistema com NTP")
                elif isinstance(e, ccxt.PermissionDenied):
                    print(f"   🚫 PERMISSÕES INSUFICIENTES: Habilite permissões de trading Futures na API Binance")
                    if "451" in error_details:
                        print(f"   🚫 HTTP 451: Região bloqueada pela Binance - tentando endpoints alternativos")
                elif isinstance(e, ccxt.ExchangeNotAvailable) or isinstance(e, ccxt.NetworkError):
                    print(f"   🌐 ERRO DE REDE/EXCHANGE: Binance temporariamente indisponível ou problema de conexão")
                elif isinstance(e, ccxt.RateLimitExceeded):
                    print(f"   ⏱️  RATE LIMIT EXCEDIDO: Muitas requisições - aguarde alguns segundos")
                    print(f"   💡 SOLUÇÃO: Implementar backoff exponencial ou reduzir frequência de requisições")
                else:
                    # Erro CCXT genérico
                    print(f"   ⚠️  Erro CCXT: {type(e).__name__}")
            else:
                # Erro não-CCXT
                error_details = str(e)
                print(f"❌ [ERRO BINANCE] Falha na ordem: {error_details}")
                if "API-key" in error_details or "Invalid API" in error_details or "Invalid Api-Key ID" in error_details:
                    print(f"   🔑 ERRO DE AUTENTICAÇÃO: Verifique suas credenciais API Binance")
                    print(f"   💡 SOLUÇÃO:")
                    print(f"      1. Verifique se API Key e Secret estão corretos (sem espaços extras)")
                    print(f"      2. Confirme que as permissões de FUTURES estão habilitadas")
                    print(f"      3. Verifique se seu IP está na whitelist (se configurado)")
                    print(f"      4. Gere novas credenciais se necessário")
                elif "Signature" in error_details:
                    print(f"   🔐 ERRO DE ASSINATURA: Verifique o API Secret Binance")
                    print(f"   💡 SOLUÇÃO: Confirme que timestamp está sincronizado e recvWindow=10000")
                elif "insufficient balance" in error_details.lower() or "balance is not enough" in error_details.lower():
                    print(f"   💰 SALDO INSUFICIENTE: Deposite fundos na conta Binance Futures")
                elif "notional" in error_details.lower():
                    print(f"   📊 NOCIONAL MÍNIMO: Valor da ordem abaixo do mínimo exigido")
                    print(f"   💡 SOLUÇÃO: Aumente a quantidade ou escolha um ativo com preço mais alto")
                elif "451" in error_details:
                    print(f"   🚫 HTTP 451: Região bloqueada - tentando endpoints alternativos")

            if raise_on_error:
                raise
            return None

    def set_tp_sl_sniper(self, symbol, side, entry_price, position_qty):
        """Define Take Profit (+10% = +100% margem) e Stop Loss (-5% = -50% margem) via ordens limitadas."""
        try:
            if not self.authenticated:
                return False

            # TP = +10% preço = +100% margem (10x leverage)
            # SL = -5% preço = -50% margem (10x leverage)
            tp_price = round(entry_price * 1.10, 8)
            sl_price = round(entry_price * 0.95, 8)

            close_side = 'sell' if side.lower() in ('buy', 'long') else 'buy'

            print(f"🛡️ [BINANCE TP/SL] {symbol} TP={tp_price} (+10% = +100% margem) SL={sl_price} (-5% = -50% margem)")

            # Take profit — limit reduceOnly
            self._call_with_451_retry(
                lambda: self.exchange.create_order(
                    symbol, 'TAKE_PROFIT_MARKET', close_side, position_qty,
                    params={'stopPrice': tp_price, 'closePosition': True, 'workingType': 'MARK_PRICE'},
                )
            )
            # Stop loss — stop market reduceOnly
            self._call_with_451_retry(
                lambda: self.exchange.create_order(
                    symbol, 'STOP_MARKET', close_side, position_qty,
                    params={'stopPrice': sl_price, 'closePosition': True, 'workingType': 'MARK_PRICE'},
                )
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
                    return True, f"Binance Autenticado OK (USDT {balance:.2f})"
                # Tenta via fetch_balance direto para obter melhor mensagem de erro
                try:
                    self._call_with_451_retry(
                        lambda: self.exchange.fetch_balance(params={'type': 'future'})
                    )
                except Exception as inner:
                    return False, str(inner).split('\n')[0][:200]
                return False, 'Chave API Binance inválida ou sem permissão Futures'
            else:
                self._call_with_451_retry(self.exchange.fetch_tickers)
                return True, 'API pública Binance OK (sem credenciais)'
        except Exception as e:
            return False, str(e).split('\n')[0][:200]

    def pre_flight_check(self, symbol, side, qty):
        """
        Validação pré-voo antes de executar ordem (compatível com BybitClient).

        Retorna: (bool, str categoria, str mensagem)
        categoria: 'OK', 'ERRO_CORRETORA', 'ERRO_ROBO'
        """
        try:
            # 1. Valida autenticação
            if not self.authenticated:
                return False, 'ERRO_ROBO', 'Cliente Binance não autenticado (sem API key/secret)'

            # 2. Valida conectividade e saldo
            balance = self.get_balance()
            if balance is None:
                return False, 'ERRO_CORRETORA', 'Falha ao consultar saldo Binance - verifique API Key e permissões'

            if balance <= 0:
                return False, 'ERRO_ROBO', f'Saldo insuficiente: {balance} USDT'

            # 3. Valida margem necessária
            try:
                price = self.get_last_price(symbol)
                if price <= 0:
                    return False, 'ERRO_CORRETORA', f'Falha ao obter preço do símbolo {symbol}'

                margin_needed = price * qty
                if margin_needed > balance:
                    return False, 'ERRO_ROBO', f'Margem insuficiente: necessário {margin_needed:.2f} USDT, disponível {balance:.2f} USDT'

            except Exception as price_err:
                return False, 'ERRO_CORRETORA', f'Erro ao validar símbolo {symbol}: {str(price_err)[:100]}'

            # 4. Valida que o símbolo existe
            try:
                self.exchange.load_markets()
                if symbol not in self.exchange.markets:
                    return False, 'ERRO_ROBO', f'Símbolo {symbol} não encontrado na Binance Futures'
            except Exception as market_err:
                return False, 'ERRO_CORRETORA', f'Erro ao carregar mercados: {str(market_err)[:100]}'

            # Tudo OK
            mode_label = 'TESTNET' if self.testnet else 'REAL'
            return True, 'OK', f'Binance {mode_label}: Validações OK (saldo={balance:.2f} USDT)'

        except Exception as e:
            error_msg = str(e)
            if self._is_auth_error(error_msg):
                return False, 'ERRO_CORRETORA', f'Erro de autenticação Binance: {error_msg[:100]}'
            return False, 'ERRO_ROBO', f'Erro na validação pré-voo: {error_msg[:100]}'
