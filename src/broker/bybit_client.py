import time
from decimal import Decimal, ROUND_DOWN
from datetime import datetime

from src.config import get_bybit_base_url, get_bybit_credentials, resolve_use_testnet
from src.broker.order_calculator import OrderCalculator, sanitize_numeric_string

AUTH_10003_ALERT = (
    "ERRO DE AUTENTICAÇÃO: Verifique se a chave de API é de produção e se o 2FA está ativo na Bybit"
)

# Global para carregar CCXT apenas uma vez
_ccxt_instance = None
_pd_instance = None
_pybit_http_class = None

def _get_ccxt():
    """Carrega CCXT lazy (apenas primeira vez)."""
    global _ccxt_instance
    if _ccxt_instance is None:
        print("⏳ Carregando CCXT (primeira vez)...", flush=True)
        import ccxt as ccxt_lib
        _ccxt_instance = ccxt_lib
        print("✅ CCXT carregado com sucesso", flush=True)
    return _ccxt_instance

def _get_pd():
    """Carrega Pandas lazy."""
    global _pd_instance
    if _pd_instance is None:
        print("⏳ Carregando Pandas...", flush=True)
        import pandas as pd
        _pd_instance = pd
        print("✅ Pandas carregado com sucesso", flush=True)
    return _pd_instance


def _get_pybit_http():
    """Carrega pybit HTTP lazy (apenas primeira vez)."""
    global _pybit_http_class
    if _pybit_http_class is None:
        print("⏳ Carregando pybit HTTP...", flush=True)
        from pybit.unified_trading import HTTP as pybit_http
        _pybit_http_class = pybit_http
        print("✅ pybit HTTP carregado com sucesso", flush=True)
    return _pybit_http_class

class BybitClient:
    """
    IA 1: Responsável pela comunicação com a Bybit.
    Versão 1.8.2: Importação Lazy de CCXT (carrega apenas quando usado) + Rate Limiting + Cache.
    Blindagem contra bloqueios de API.
    """
    def __init__(self, api_key=None, api_secret=None, testnet=None):
        # Carrega CCXT apenas quando BybitClient é instanciado
        ccxt = _get_ccxt()

        env_api_key, env_api_secret = get_bybit_credentials()
        # 🔧 SANITIZAÇÃO: Remove espaços, quebras de linha e caracteres invisíveis
        api_key = str(api_key or env_api_key or '').strip().replace('\n', '').replace('\r', '')
        api_secret = str(api_secret or env_api_secret or '').strip().replace('\n', '').replace('\r', '')
        self.testnet = resolve_use_testnet(testnet)
        self.active_endpoint = get_bybit_base_url(self.testnet)
        self.pybit_session = None

        # Não inclua chaves vazias na configuração — passar apiKey=None faz a API
        # interpretar como credencial inválida e causa erro 10003.
        cfg = {
            'enableRateLimit': True,
            'rateLimit': 100,  # Delay mínimo entre requisições
            'timeout': 15000,   # Timeout HTTP de 15s para evitar travamento
            'options': {
                'defaultType': 'swap', # Foco em Perpétuos
                'defaultSubType': 'linear',
                'adjustForTimeDifference': True,
                'recvWindow': 20000,  # Janela de 20s para tolerar drift de relógio
            }
        }

        # Inicializa calculadora de ordens dinâmica
        self.order_calculator = OrderCalculator(exchange_name='bybit')
        if api_key and api_secret:
            cfg['apiKey'] = api_key
            cfg['secret'] = api_secret

        self.exchange = ccxt.bybit(cfg)
        self._configure_exchange_endpoint()

        # 🔧 SINCRONIZAÇÃO DE TEMPO: Executa ao inicializar para evitar erros de timestamp
        if api_key and api_secret:
            try:
                self.exchange.load_time_difference()
                print(f"✅ [BYBIT TIME SYNC] Diferença de tempo sincronizada com servidor")
            except Exception as sync_err:
                print(f"⚠️ [BYBIT TIME SYNC] Aviso: {sync_err}")

        self.pybit_api_version = 'v5'
        self.pybit_sdk_module = ''

        if api_key and api_secret:
            self._init_pybit_session(api_key, api_secret)

        print(f"🔍 [BYBIT ENDPOINT] testnet={self.testnet} endpoint={self.active_endpoint}")

        # Indica se esta instância tem credenciais de escrita/autenticação
        self.authenticated = bool(api_key and api_secret)
        
        # --- SISTEMA DE CACHE E SEGURANÇA ---
        self.cache_ohlcv = {} 
        self.cache_ticker = {} 
        self.cache_ttl_ohlcv = 30
        self.cache_ttl_ticker = 10
        self.ohlcv_failures = {}
        self.max_ohlcv_failures = 3
        self.last_request_time = {}
        self.adaptive_delay = 0.5 
        self.rate_limit_block_until = 0

    def _configure_exchange_endpoint(self):
        """Aplica e valida o endpoint exato exigido pelo ambiente configurado."""
        if self.testnet:
            self.exchange.set_sandbox_mode(True)

        api_urls = self.exchange.urls.get('api')
        if isinstance(api_urls, dict):
            for key in list(api_urls.keys()):
                api_urls[key] = self.active_endpoint
        else:
            self.exchange.urls['api'] = self.active_endpoint

        self._validate_exchange_endpoint()

    def _validate_exchange_endpoint(self):
        api_urls = self.exchange.urls.get('api')
        if isinstance(api_urls, dict):
            invalid_urls = {key: value for key, value in api_urls.items() if value != self.active_endpoint}
            if invalid_urls:
                raise RuntimeError(
                    f"Endpoint Bybit inconsistente para USE_TESTNET={self.testnet}: {invalid_urls}"
                )
            return

        if api_urls != self.active_endpoint:
            raise RuntimeError(
                f"Endpoint Bybit inconsistente para USE_TESTNET={self.testnet}: {api_urls}"
            )

    def _init_pybit_session(self, api_key, api_secret):
        """Inicializa sessão pybit V5 com recv_window ampliado para ambientes com latência e dessincronização de relógio."""
        try:
            HTTP = _get_pybit_http()
            self.pybit_sdk_module = getattr(HTTP, '__module__', '')
            if 'pybit.unified_trading' not in self.pybit_sdk_module:
                raise RuntimeError(
                    f"SDK pybit incompatível: esperado pybit.unified_trading (V5), recebido {self.pybit_sdk_module or 'desconhecido'}"
                )
            self.pybit_session = HTTP(
                testnet=self.testnet,
                api_key=api_key,
                api_secret=api_secret,
                recv_window=20000,  # Janela de 20s para compensar latências de servidores em nuvem
            )
            self.pybit_session.endpoint = self.active_endpoint
            print(f"🔌 [PYBIT V5] módulo={self.pybit_sdk_module} endpoint={self.active_endpoint} recv_window=20000ms")
        except Exception as e:
            print(f"⚠️ [PYBIT] Sessão HTTP indisponível: {e}")
            self.pybit_session = None

    def _format_bybit_error(self, payload):
        """Normaliza erros da Bybit V5 para o front-end receber mensagem clara."""
        try:
            if isinstance(payload, dict):
                code = payload.get('retCode')
                msg = payload.get('retMsg') or 'Erro Bybit'
                return f"Bybit retCode={code}: {msg}"
        except Exception:
            pass
        return str(payload)

    def _apply_rate_limit(self, endpoint):
        """Aplica delay adaptativo para evitar expulsão da API."""
        if endpoint in self.last_request_time:
            elapsed = time.time() - self.last_request_time[endpoint]
            if elapsed < self.adaptive_delay:
                time.sleep(self.adaptive_delay - elapsed)
        self.last_request_time[endpoint] = time.time()

    def _is_cache_valid(self, cache_entry, ttl):
        if cache_entry is None: return False
        data, timestamp = cache_entry
        return (time.time() - timestamp) < ttl

    def _is_auth_error(self, msg):
        """Retorna True apenas para erros reais de autenticação/autorização da Bybit."""
        return (
            '10003' in msg          # Invalid API Key
            or '10004' in msg       # Invalid sign / timestamp mismatch
            or '10002' in msg       # Invalid request / timestamp issue / InvalidNonce
            or 'API key is invalid' in msg
            or '403' in msg
            or 'Forbidden' in msg
            or 'CloudFront' in msg
            or 'timestamp' in msg.lower()
            or 'nonce' in msg.lower()
        )
        # Nota: retCode genérico NÃO está aqui — erros como 10016 (account type
        # not found) são erros de parâmetro, não de autenticação.

    def _emit_authentication_alert(self):
        print(AUTH_10003_ALERT)

    def _handle_v5_ret_code(self, payload, route_label):
        """Valida retCode padronizado da API V5 e dispara alerta de autenticação quando necessário."""
        if not isinstance(payload, dict):
            return False, str(payload)

        ret_code = payload.get('retCode')
        if str(ret_code) in {'0', 'None'} or ret_code is None:
            return True, ''

        ret_msg = str(payload.get('retMsg') or 'Erro Bybit').strip()
        message = f"{route_label} falhou: retCode={ret_code} retMsg={ret_msg}"
        if str(ret_code) == '10003':
            self.authenticated = False
            self._emit_authentication_alert()
        return False, message

    def _normalize_v5_symbol(self, symbol):
        raw = str(symbol or '').strip().upper()
        if not raw:
            return raw
        return raw.replace('/', '').replace(':USDT', '')

    def _normalize_v5_side(self, side):
        normalized = str(side or '').strip().lower()
        return 'Buy' if normalized == 'buy' else 'Sell'

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
            symbol: Par de negociação (ex: 'DOGEUSDT', 'BTC/USDT:USDT')
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
        Normaliza quantidade para precisão aceita pela corretora, evitando Qty invalid.
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

            # Min notional (valor mínimo em USDT) - Bybit geralmente exige >= 5 USDT
            min_cost = limits.get('cost', {}).get('min', 5.0)

            # Precisão da quantidade
            amount_precision = market.get('precision', {}).get('amount', 2)

            print(f"   📊 [BYBIT LIMITS] {symbol}: min_amount={min_amount}, min_notional={min_cost} USDT, precision={amount_precision}")
        except Exception as market_err:
            print(f"⚠️ [BYBIT MARKET] Erro ao carregar limites: {market_err}, usando defaults")
            min_amount = 0.001
            min_cost = 5.0
            amount_precision = 2

        # 🔧 PASSO 3: Calcula quantidade mínima para satisfazer min notional
        min_qty_for_notional = Decimal(str(min_cost)) / Decimal(str(current_price))

        # 🔧 PASSO 4: Usa o maior entre min_amount e min_qty_for_notional
        required_min_qty = max(Decimal(str(min_amount)), min_qty_for_notional)

        # Se quantidade fornecida for menor que o mínimo, usa o mínimo
        if Decimal(str(qty_value)) < required_min_qty:
            print(f"⚠️ [BYBIT QTY] Quantidade {qty_value} abaixo do mínimo. Ajustando para {required_min_qty}")
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
            print(f"   🔧 [BYBIT NOTIONAL] Ajustado para qty={quantized} (notional={notional_value:.2f} USDT >= {min_cost} USDT)")

        normalized = format(quantized, 'f')
        final_qty = normalized.rstrip('0').rstrip('.') if '.' in normalized else normalized

        # 🔧 PASSO 6: Exibe informações de validação
        final_notional = float(final_qty) * current_price
        print(f"   ✅ [BYBIT ORDER] qty={final_qty} (notional={final_notional:.2f} USDT, min_amount={min_amount}, min_notional={min_cost} USDT)")

        return final_qty

    def _validate_insurance_fund(self):
        """Consulta o fundo de seguros V5 apenas para validar conectividade inicial."""
        if self.pybit_session is None:
            return True, "SDK pybit V5 indisponível para validar fundo de seguros"

        try:
            rsp = self.pybit_session.get_insurance(coin='USDT')
            ok, error_message = self._handle_v5_ret_code(rsp, 'v5/market/insurance')
            if not ok:
                return False, error_message

            items = ((rsp or {}).get('result') or {}).get('list') or []
            return True, f"Fundo de seguros OK ({len(items)} registros)"
        except Exception as e:
            return False, str(e).split('\n')[0][:220]

    def get_balance(self):
        """Busca saldo USDT com fallback para múltiplos tipos de conta Bybit.

        Tenta em ordem: Conta Unificada (UTA) → Conta de Contratos Clássica →
        Swap (legado).  Apenas erros reais de autenticação invalidam as
        credenciais; erros de tipo-de-conta (ex.: 10016) avançam para o
        próximo fallback.
        """
        def _usdt_from(balance):
            total = (balance or {}).get('total') or {}
            usdt = total.get('USDT')
            return float(usdt) if usdt is not None else None

        # Tentativa 1: Conta Unificada (UTA)
        try:
            print(f"📊 [BYBIT] Tentando fetch_balance (UNIFIED) para {self.exchange.apiKey[:4]}...")
            balance = self.exchange.fetch_balance(params={'accountType': 'UNIFIED'})
            usdt = _usdt_from(balance)
            if usdt is not None:
                return usdt
        except Exception as e:
            msg = str(e)
            print(f"⚠️ [BYBIT] Erro (UNIFIED): {msg}")
            if self._is_auth_error(msg):
                self.authenticated = False
                return None
            # Erro de tipo de conta ou outro — tenta próximo fallback

        # Tentativa 2: Conta de Contratos Clássica (não-UTA)
        try:
            print(f"📊 [BYBIT] Tentando fetch_balance (CONTRACT)...")
            balance = self.exchange.fetch_balance(params={'accountType': 'CONTRACT'})
            usdt = _usdt_from(balance)
            if usdt is not None:
                return usdt
        except Exception as e:
            msg = str(e)
            print(f"⚠️ [BYBIT] Erro (CONTRACT): {msg}")
            if self._is_auth_error(msg):
                self.authenticated = False
                return None

        # Tentativa 3: Swap/Linear (parâmetro legado)
        try:
            print(f"📊 [BYBIT] Tentando fetch_balance (type=swap)...")
            balance = self.exchange.fetch_balance(params={'type': 'swap'})
            usdt = _usdt_from(balance)
            if usdt is not None:
                return usdt
        except Exception as e:
            msg = str(e)
            print(f"⚠️ [BYBIT] Erro (SWAP): {msg}")
            if self._is_auth_error(msg):
                self.authenticated = False
                return None
            print(f"[ERRO BROKER] Falha ao consultar saldo: {msg}")
            return None

        return 0.0

    def fetch_ohlcv(self, symbol, timeframe="15m"):
        """Fetch dados com Cache para não sobrecarregar a Bybit."""
        pd = _get_pd()
        cache_key = f"{symbol}_{timeframe}"
        
        if cache_key in self.cache_ohlcv and self._is_cache_valid(self.cache_ohlcv[cache_key], self.cache_ttl_ohlcv):
            return self.cache_ohlcv[cache_key][0]

        try:
            self._apply_rate_limit('fetch_ohlcv')
            params = {'category': 'linear'}
            data = self.exchange.fetch_ohlcv(symbol, timeframe, limit=250, params=params)
            df = pd.DataFrame(data, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
            
            self.cache_ohlcv[cache_key] = (df, time.time())
            self.ohlcv_failures[cache_key] = 0
            return df
        except Exception as e:
            print(f"[ERRO BROKER] Dados {symbol} falharam: {e}")
            fail_count = self.ohlcv_failures.get(cache_key, 0) + 1
            self.ohlcv_failures[cache_key] = fail_count

            if fail_count >= self.max_ohlcv_failures:
                if cache_key in self.cache_ohlcv:
                    del self.cache_ohlcv[cache_key]
                print(f"⚠️ [CACHE INVALIDADO] {symbol} {timeframe} após {fail_count} falhas consecutivas de OHLCV")
                return None

            return self.cache_ohlcv[cache_key][0] if cache_key in self.cache_ohlcv else None

    def get_last_price(self, symbol):
        """Preço em tempo real com cache curto (essencial para Ponto Zero)."""
        if symbol in self.cache_ticker and self._is_cache_valid(self.cache_ticker[symbol], self.cache_ttl_ticker):
            return self.cache_ticker[symbol][0]

        try:
            self._apply_rate_limit('get_last_price')
            ticker = self.exchange.fetch_ticker(symbol, params={'category': 'linear'})
            price = float(ticker['last'])
            self.cache_ticker[symbol] = (price, time.time())
            return price
        except Exception as e:
            print(f"[ERRO BROKER] Preço {symbol} falhou: {e}")
            return self.cache_ticker[symbol][0] if symbol in self.cache_ticker else 0.0

    def execute_market_order(self, symbol, side, qty, raise_on_error=False):
        """Executa ordem a mercado para entrada instantânea."""
        try:
            if not self.authenticated:
                print(f"[ERRO BROKER] Ordem não executada: cliente sem credenciais.")
                if raise_on_error:
                    raise RuntimeError('Cliente sem credenciais autenticadas para enviar ordem na Bybit.')
                return None

            normalized_qty = self._normalize_order_qty(symbol, qty)
            ccxt_qty = float(normalized_qty)

            print(f"🔥 [ORDEM SNIPER BYBIT] {side.upper()} {normalized_qty} em {symbol}")
            print(f"   🌐 Endpoint: {self.active_endpoint}")
            print(f"   🔐 Autenticado: {self.authenticated}")
            print(f"   🧪 Modo Testnet: {self.testnet}")

            if self.pybit_session is not None:
                v5_symbol = self._normalize_v5_symbol(symbol)
                payload = {
                    'category': 'linear',  # Obrigatório para futuros/perpétuos USDT conforme Bybit V5 API
                    'symbol': v5_symbol,
                    'side': self._normalize_v5_side(side),
                    'orderType': 'Market',
                    'qty': normalized_qty,
                }
                print(f"   📤 Enviando ordem via Pybit V5 (/v5/order/create): {payload}")
                rsp = self.pybit_session.place_order(**payload)
                print(f"   📥 Resposta da API Bybit: {rsp}")

                ok, error_message = self._handle_v5_ret_code(rsp, 'v5/order/create')
                if not ok:
                    print(f"❌ [ERRO EXECUÇÃO BYBIT] {error_message}")
                    print(f"   🔍 ERRO BRUTO DA CORRETORA: retCode={rsp.get('retCode')}, retMsg={rsp.get('retMsg')}")
                    if raise_on_error:
                        raise RuntimeError(error_message)
                    return None

                result = (rsp or {}).get('result') or {}
                order_id = result.get('orderId') or result.get('orderLinkId')
                print(f"✅ [BYBIT] Ordem criada com sucesso - ID: {order_id}")
                return {
                    **result,
                    'id': order_id,
                    'route': 'v5/order/create',
                    'category': 'linear',
                    'symbol': v5_symbol,
                }

            # Fallback para CCXT se pybit não estiver disponível
            params = {'category': 'linear'}  # Obrigatório para futuros/perpétuos USDT conforme Bybit V5 API
            print(f"   📤 Enviando ordem via CCXT: symbol={symbol}, type=market, side={side}, qty={normalized_qty}, params={params}")
            order = self.exchange.create_order(symbol, 'market', side, ccxt_qty, params=params)
            print(f"   📥 Resposta CCXT: {order}")
            print(f"✅ [BYBIT CCXT] Ordem criada - ID: {order.get('id', 'N/A')}")
            return order
        except Exception as e:
            # Importa ccxt para capturar erros específicos da corretora
            ccxt = _get_ccxt()

            if isinstance(e, ccxt.BaseError):
                error_details = str(e)
                print(f"❌ ERRO REAL DA CORRETORA BYBIT: {error_details}")

                # Extrai código HTTP se disponível
                http_status = getattr(e, 'status', None) or getattr(e, 'http_status_code', None)
                if http_status:
                    print(f"   🌐 HTTP STATUS CODE: {http_status}")
                    if http_status in [400, 429, 451]:
                        print(f"   ⚠️  ERRO CRÍTICO HTTP {http_status} - Verifique configurações da API")

                # Diagnóstico detalhado de erros CCXT
                if isinstance(e, ccxt.InsufficientFunds):
                    print(f"   💰 SALDO INSUFICIENTE: Deposite fundos na conta ou reduza o tamanho da ordem")
                elif isinstance(e, ccxt.InvalidOrder):
                    print(f"   📏 ORDEM INVÁLIDA: Verifique tamanho mínimo de lote, preço ou quantidade")
                    if "lot size" in error_details.lower() or "min" in error_details.lower():
                        print(f"   ⚠️  TAMANHO MÍNIMO DE LOTE INVÁLIDO: Quantidade {qty:.4f} abaixo do mínimo permitido")
                    if "notional" in error_details.lower() or "order cost" in error_details.lower():
                        print(f"   ⚠️  NOCIONAL MÍNIMO: Valor da ordem abaixo do mínimo exigido (geralmente >= 5 USDT)")
                        print(f"   💡 SOLUÇÃO: Aumente a quantidade ou escolha um ativo com preço mais alto")
                    if "category" in error_details.lower():
                        print(f"   ⚠️  CATEGORIA INVÁLIDA: Use category=linear para derivativos perpétuos/futuros")
                        print(f"   💡 SOLUÇÃO: O sistema já força category=linear, mas a API pode estar rejeitando")
                elif isinstance(e, ccxt.AuthenticationError):
                    print(f"   🔑 ERRO DE AUTENTICAÇÃO: Verifique suas credenciais API (key/secret)")
                    if "10003" in error_details or "Invalid API key" in error_details:
                        print(f"   ⚠️  API Key inválida ou expirada")
                        print(f"   💡 SOLUÇÃO:")
                        print(f"      1. Verifique se API Key e Secret estão corretos (sem espaços extras)")
                        print(f"      2. Desative 2FA na API Key (não na conta principal!)")
                        print(f"      3. Verifique se a chave é de PRODUÇÃO e não de testnet")
                        print(f"      4. Gere novas credenciais se necessário")
                    elif "10004" in error_details or "Invalid sign" in error_details:
                        print(f"   ⚠️  Assinatura inválida - verifique o API Secret")
                        print(f"   💡 SOLUÇÃO: Verifique se API Secret está correto e recvWindow está configurado")
                    elif "10002" in error_details or "InvalidNonce" in error_details or "timestamp" in error_details.lower():
                        print(f"   ⏰ ERRO DE TIMESTAMP/NONCE: Dessincronização entre relógio local e servidor")
                        print(f"   💡 SOLUÇÃO: Sincronize o relógio do sistema ou use NTP. recvWindow aumentado para 10000ms")
                        print(f"   ℹ️  Este erro ocorre quando a diferença de tempo excede a janela de recepção permitida")
                elif isinstance(e, ccxt.PermissionDenied):
                    print(f"   🚫 PERMISSÕES INSUFICIENTES: Habilite permissões de trading na API")
                    if "positionIdx" in error_details or "position idx" in error_details.lower():
                        print(f"   ⚠️  ERRO DE POSITION IDX: Modo de posição (one-way/hedge) incompatível")
                        print(f"   💡 SOLUÇÃO: Verifique Position Mode na Bybit:")
                        print(f"      - One-Way Mode: positionIdx=0")
                        print(f"      - Hedge Mode Long: positionIdx=1")
                        print(f"      - Hedge Mode Short: positionIdx=2")
                elif isinstance(e, ccxt.ExchangeNotAvailable) or isinstance(e, ccxt.NetworkError):
                    print(f"   🌐 ERRO DE REDE/EXCHANGE: Exchange temporariamente indisponível ou problema de conexão")
                elif isinstance(e, ccxt.RateLimitExceeded):
                    print(f"   ⏱️  RATE LIMIT EXCEDIDO: Muitas requisições - aguarde alguns segundos")
                    print(f"   💡 SOLUÇÃO: Implementar backoff exponencial ou reduzir frequência de requisições")
                else:
                    # Erro CCXT genérico
                    print(f"   ⚠️  Erro CCXT: {type(e).__name__}")
            else:
                # Erro não-CCXT
                error_details = str(e)
                print(f"❌ [ERRO EXECUÇÃO BYBIT] Falha crítica na ordem: {error_details}")
                if "10003" in error_details or "Invalid API key" in error_details:
                    print(f"   🔑 ERRO DE AUTENTICAÇÃO: Verifique suas credenciais API")
                    print(f"   💡 SOLUÇÃO:")
                    print(f"      1. Verifique se API Key e Secret estão corretos (sem espaços extras)")
                    print(f"      2. Desative 2FA na API Key (não na conta principal!)")
                    print(f"      3. Verifique se a chave é de PRODUÇÃO e não de testnet")
                    print(f"      4. Gere novas credenciais se necessário")
                elif "10004" in error_details or "Invalid sign" in error_details:
                    print(f"   🔐 ERRO DE ASSINATURA: Verifique o API Secret")
                    print(f"   💡 SOLUÇÃO: Confirme que timestamp está sincronizado e recvWindow=10000ms")
                elif "10002" in error_details or "InvalidNonce" in error_details or "timestamp" in error_details.lower():
                    print(f"   ⏰ ERRO DE TIMESTAMP/NONCE: Dessincronização entre relógio local e servidor")
                    print(f"   💡 SOLUÇÃO: Sincronize o relógio do sistema ou use NTP. recvWindow aumentado para 10000ms")
                    print(f"   ℹ️  Este erro ocorre quando a diferença de tempo excede a janela de recepção permitida")
                elif "insufficient balance" in error_details.lower():
                    print(f"   💰 SALDO INSUFICIENTE: Deposite fundos na conta")
                elif "category" in error_details.lower():
                    print(f"   📊 ERRO DE CATEGORIA: Use category=linear para derivativos perpétuos")
                    print(f"   💡 O sistema já força category=linear automaticamente")
                elif "positionIdx" in error_details or "position idx" in error_details.lower():
                    print(f"   ⚠️  ERRO DE POSITION IDX: Modo de posição (one-way/hedge) incompatível")
                    print(f"   💡 SOLUÇÃO: Verifique Position Mode na Bybit:")
                    print(f"      - One-Way Mode: positionIdx=0")
                    print(f"      - Hedge Mode Long: positionIdx=1")
                    print(f"      - Hedge Mode Short: positionIdx=2")
                elif "notional" in error_details.lower() or "order cost" in error_details.lower():
                    print(f"   📊 NOCIONAL MÍNIMO: Valor da ordem abaixo do mínimo exigido")
                    print(f"   💡 SOLUÇÃO: Aumente a quantidade ou escolha um ativo com preço mais alto")

            if raise_on_error:
                raise
            return None

    def test_connection(self):
        """Valida a conectividade mínima com a Bybit.

        - Se tem credenciais, valida por múltiplos tipos de conta para evitar
          falso negativo em demo/testnet (UNIFIED vs CONTRACT).
        - Caso contrário, tenta um endpoint público (tickers).
        Retorna (True, mensagem) em caso de sucesso, (False, mensagem) em caso de falha.
        """
        try:
            if self.authenticated:
                insurance_ok, insurance_message = self._validate_insurance_fund()
                if not insurance_ok:
                    return False, insurance_message

                # 1) Validação principal via CCXT com fallback de accountType.
                bal = self.get_balance()
                if bal is not None:
                    return True, f"{insurance_message} | Autenticado OK (USDT {bal:.2f})"

                # 2) Fallback via pybit para capturar melhor mensagem de erro.
                if self.pybit_session is not None:
                    print(f"🔎 [BYBIT VALIDATION] endpoint={self.active_endpoint}")
                    pybit_errors = []
                    for account_type in ['UNIFIED', 'CONTRACT']:
                        try:
                            rsp = self.pybit_session.get_wallet_balance(accountType=account_type, coin='USDT')
                            ok, error_message = self._handle_v5_ret_code(
                                rsp,
                                f'v5/account/wallet-balance ({account_type})',
                            )
                            if ok:
                                result = (rsp or {}).get('result') or {}
                                rows = result.get('list') or []
                                usdt_bal = 0.0
                                if rows:
                                    usdt_bal = float(rows[0].get('totalWalletBalance') or 0.0)
                                return True, f"{insurance_message} | Autenticado OK ({account_type}, USDT {usdt_bal:.2f})"
                            pybit_errors.append(error_message)
                        except Exception as pybit_err:
                            pybit_errors.append(str(pybit_err).split('\n')[0][:220])

                    if pybit_errors:
                        return False, pybit_errors[0][:220]

                # 3) Último fallback para retornar erro limpo.
                try:
                    self.exchange.fetch_balance(params={'accountType': 'UNIFIED'})
                except Exception as inner_e:
                    inner_msg = str(inner_e)
                    short = inner_msg.split('\n')[0][:200]
                    return False, short
                return False, "Chave API inválida ou sem permissão de leitura de saldo"
            else:
                _ = self.exchange.fetch_tickers()
                return True, "API pública OK (sem credenciais)"
        except Exception as e:
            return False, str(e).split('\n')[0][:200]

    def set_tp_sl_sniper(self, symbol, side, entry_price, position_qty):
        """
        🎯 REGRA 100/3 PROTOCOL - SETAGEM AUTOMÁTICA DE TP/SL

        Take Profit: +100% de lucro sobre a margem
        Stop Loss: -3% de perda fixa (TRAVA INSTITUCIONAL)

        Funciona pós-entrada para garantir proteção de capital.
        """
        try:
            if not self.authenticated:
                print(f"❌ [TP/SL] Não autenticado. Proteção de capital FALHADA.")
                return False

            # Cálculo de TP/SL (Bybit usa preços absolutos, não percentuais)
            tp_price = entry_price * 1.10  # +10% = +100% de margem (alavancagem 10x)
            sl_price = entry_price * 0.97  # -3% = Stop Loss Institucional

            # 🔧 FORMATAÇÃO ESTRITA: Usa price_to_precision do CCXT para evitar rejeição
            price_to_precision = getattr(self.exchange, 'price_to_precision', None)
            if callable(price_to_precision):
                try:
                    tp_price = float(price_to_precision(symbol, tp_price))
                    sl_price = float(price_to_precision(symbol, sl_price))
                except Exception as precision_error:
                    print(f"⚠️ [TP/SL] price_to_precision falhou: {precision_error} - usando valores brutos")

            print(f"🛡️  [PROTEÇÃO SNIPER] {symbol}")
            print(f"   📍 Entrada: ${entry_price:.2f}")
            print(f"   ✅ TP: ${tp_price:.2f} (+100% margem)")
            print(f"   ❌ SL: ${sl_price:.2f} (-3% trava)")

            params = {
                'category': 'linear',
                'takeProfit': {'triggerPrice': str(tp_price)},
                'stopLoss': {'triggerPrice': str(sl_price)}
            }

            # Executa ordem de TP/SL em posição aberta
            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=position_qty,
                params=params
            )

            print(f"✅ [TP/SL SETADO] Ordem protegida no Sistema Sniper")
            return True

        except Exception as e:
            print(f"⚠️  [TP/SL FALHOU] {e}")
            return False

    def close_position_with_sl(self, symbol, position_side):
        """
        Encerra posição de emergência com fallback robusto para positionIdx.
        🔧 CORREÇÃO: Busca posições abertas e usa positionIdx real + reduceOnly.
        """
        try:
            if not self.authenticated:
                print("❌ [CLOSE POSITION] Não autenticado")
                return False

            # Identifica lado oposto para fechar
            close_side = "sell" if position_side.lower() == "buy" else "buy"

            print(f"🔒 [CLOSE POSITION] Tentando fechar {symbol} (lado original: {position_side})")

            # 🔧 PASSO 1: Busca posições abertas com category=linear
            positions = self.exchange.fetch_positions(params={'category': 'linear'})

            # 🔧 PASSO 2: Encontra a posição correta e extrai positionIdx real
            target_position = None
            for p in positions:
                pos_symbol = p.get('symbol', '')
                pos_contracts = float(p.get('contracts') or 0)
                pos_side = str(p.get('side', '')).lower()

                # Verifica se é a posição que queremos fechar
                if symbol in pos_symbol and pos_contracts > 0:
                    # Verifica se o lado bate (long/buy ou short/sell)
                    if (position_side.lower() in ('buy', 'long') and pos_side == 'long') or \
                       (position_side.lower() in ('sell', 'short') and pos_side == 'short'):
                        target_position = p
                        break

            if not target_position:
                print(f"⚠️ [CLOSE POSITION] Nenhuma posição aberta encontrada para {symbol} no lado {position_side}")
                return False

            pos_size = float(target_position.get('contracts') or 0)
            if pos_size <= 0:
                print(f"⚠️ [CLOSE POSITION] Tamanho da posição é zero")
                return False

            # 🔧 PASSO 3: Extrai positionIdx da posição real (se disponível)
            position_info = target_position.get('info', {})
            position_idx = position_info.get('positionIdx')

            print(f"   📊 [CLOSE POSITION] Tamanho: {pos_size}, positionIdx: {position_idx}")

            # 🔧 PASSO 4: Monta params com category=linear, reduceOnly e positionIdx
            params = {
                'category': 'linear',  # Obrigatório para derivativos lineares
                'reduceOnly': True,     # Garante que só fecha posição existente
            }

            # Adiciona positionIdx apenas se estiver disponível
            if position_idx is not None:
                params['positionIdx'] = position_idx

            # 🔧 PASSO 5: Normaliza quantidade
            normalized_qty = self._normalize_order_qty(symbol, pos_size)

            print(f"   📤 [CLOSE POSITION] Enviando ordem: side={close_side}, qty={normalized_qty}, params={params}")

            # 🔧 PASSO 6: Envia ordem de fechamento via create_order (não create_market_order)
            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=close_side,
                amount=float(normalized_qty),
                params=params  # 🔧 CORREÇÃO: params como argumento nomeado
            )

            print(f"✅ [CLOSE POSITION] Posição {symbol} fechada com sucesso - Order ID: {order.get('id', 'N/A')}")
            return True

        except Exception as e:
            error_msg = str(e)
            print(f"❌ [CLOSE POSITION] Erro ao fechar: {error_msg}")

            # 🔧 DIAGNÓSTICO: Trata erro de position idx mismatch
            if 'position idx' in error_msg.lower() or 'positionIdx' in error_msg:
                print(f"   ⚠️ ERRO DE POSITION IDX: O modo de posição (one-way/hedge) não corresponde ao positionIdx usado")
                print(f"   💡 SOLUÇÃO: Verifique o modo de posição na Bybit (Position Mode) e use positionIdx correto:")
                print(f"      - One-Way Mode: positionIdx=0")
                print(f"      - Hedge Mode Long: positionIdx=1")
                print(f"      - Hedge Mode Short: positionIdx=2")

            return False
