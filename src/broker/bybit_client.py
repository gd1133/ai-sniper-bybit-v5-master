# -*- coding: utf-8 -*-
import time
import sys
import threading
import json
import re
from decimal import Decimal
from src.risk.position_sizing import (
    calculate_position_qty,
    calculate_tp_sl_prices,
    load_entry_after_stop_pct,
    load_entry_pct,
)

# Força UTF-8 no stdout sem reempacotar o stream (evita fechar stdout no Windows)
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

AUTH_10003_ALERT = (
    "ERRO DE AUTENTICAÇÃO: Verifique se a chave de API é de produção e se o 2FA está ativo na Bybit"
)

# Globals para carregamento em Lazy Loading com Thread Safety
_ccxt_instance = None
_pd_instance = None
_pybit_http_class = None
_ccxt_lock = threading.Lock()
_pd_lock = threading.Lock()
_pybit_lock = threading.Lock()

def _get_ccxt():
    """Carrega CCXT lazy (apenas na primeira vez) com thread lock."""
    global _ccxt_instance
    if _ccxt_instance is not None:
        return _ccxt_instance
    with _ccxt_lock:
        if _ccxt_instance is None:
            print("⏳ Carregando CCXT (primeira vez)...", flush=True)
            import ccxt as ccxt_lib
            _ccxt_instance = ccxt_lib
            print("✅ CCXT carregado com sucesso", flush=True)
    return _ccxt_instance

def _get_pd():
    """Carrega Pandas lazy com thread lock."""
    global _pd_instance
    if _pd_instance is not None:
        return _pd_instance
    with _pd_lock:
        if _pd_instance is None:
            print("⏳ Carregando Pandas...", flush=True)
            import pandas as pd
            _pd_instance = pd
            print("✅ Pandas carregado com sucesso", flush=True)
    return _pd_instance

def _get_pybit_http():
    """Carrega pybit HTTP lazy (apenas na primeira vez) com thread lock."""
    global _pybit_http_class
    if _pybit_http_class is not None:
        return _pybit_http_class
    with _pybit_lock:
        if _pybit_http_class is None:
            print("⏳ Carregando pybit HTTP...", flush=True)
            from pybit.unified_trading import HTTP as pybit_http
            _pybit_http_class = pybit_http
            print("✅ pybit HTTP carregado com sucesso", flush=True)
    return _pybit_http_class


class BybitClient:
    """
    IA 1: Responsável pela comunicação com a Bybit.
    Versão 1.8.6: Correção estrita de tipos Decimal/Float + Tratamento nativo CCXT + Protocolo 100/50.
    Blindagem contra bloqueios de API e vazamento de memória.
    """
    def __init__(self, api_key=None, api_secret=None, testnet=None, base_url=None, allow_env_credentials=True):
        # LAZY LOADING: Evita importação circular puxando apenas no escopo local
        from src.config import get_bybit_base_url, get_bybit_credentials, resolve_use_testnet
        from src.broker.order_calculator import OrderCalculator

        ccxt = _get_ccxt()

        # allow_env_credentials=False: market data público sem herdar BYBIT_API_* do .env
        if allow_env_credentials:
            env_api_key, env_api_secret = get_bybit_credentials()
        else:
            env_api_key, env_api_secret = '', ''

        # SANITIZAÇÃO: Remove espaços, quebras de linha e caracteres invisíveis
        api_key = str(api_key or env_api_key or '').strip().replace('\n', '').replace('\r', '')
        api_secret = str(api_secret or env_api_secret or '').strip().replace('\n', '').replace('\r', '')

        normalized_base_url = str(base_url or '').strip()
        if normalized_base_url:
            self.active_endpoint = normalized_base_url
            self.is_demo = 'api-demo.bybit.com' in normalized_base_url
            self.testnet = 'api-testnet.bybit.com' in normalized_base_url
        else:
            self.testnet = resolve_use_testnet(testnet)
            self.is_demo = False
            self.active_endpoint = get_bybit_base_url(self.testnet)
        self.use_sandbox = bool(self.testnet or self.is_demo)
        self.pybit_session = None

        cfg = {
            'enableRateLimit': True,
            'rateLimit': 100,  # Delay mínimo tolerável entre requisições
            'timeout': 15000,   # Timeout HTTP de 15s para evitar travamento da thread
            'options': {
                'defaultType': 'swap',  # Foco absoluto em contratos perpétuos
                'defaultSubType': 'linear',
                'adjustForTimeDifference': True,
                'recvWindow': 20000,  # Janela ampla para tolerar latência do servidor em nuvem
            }
        }

        # Inicializa a calculadora de ordens dinâmica
        self.order_calculator = OrderCalculator(exchange_name='bybit')
        if api_key and api_secret:
            cfg['apiKey'] = api_key
            cfg['secret'] = api_secret

        self.exchange = ccxt.bybit(cfg)
        self._configure_exchange_endpoint()

        # SINCRONIZAÇÃO DE TEMPO: Executa na inicialização para mitigar drift de timestamp
        if api_key and api_secret:
            try:
                self.exchange.load_time_difference()
                print("✅ [BYBIT TIME SYNC] Diferença de tempo sincronizada com o servidor", flush=True)
            except Exception as sync_err:
                print(f"⚠️ [BYBIT TIME SYNC] Aviso: {sync_err}", flush=True)

        self.pybit_api_version = 'v5'
        self.pybit_sdk_module = ''

        if api_key and api_secret:
            self._init_pybit_session(api_key, api_secret)

        print(
            f"🔍 [BYBIT ENDPOINT] testnet={self.testnet} demo={self.is_demo} endpoint={self.active_endpoint}",
            flush=True,
        )

        self.authenticated = bool(api_key and api_secret)

        # --- SISTEMA DE CACHE E PROTEÇÃO CONTRA EXPULSÃO ---
        self.cache_ohlcv = {}
        self.cache_ticker = {}
        self.cache_ttl_ohlcv = 30
        self.cache_ttl_ticker = 10
        self.ohlcv_failures = {}
        self.max_ohlcv_failures = 3
        self.last_request_time = {}
        self.adaptive_delay = 0.5
        self.rate_limit_block_until = 0
        self._public_market_exchange = None

    def _configure_exchange_endpoint(self):
        """Aplica e valida o endpoint exato exigido pelo ambiente configurado."""
        if self.use_sandbox:
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
                raise RuntimeError(f"Endpoint Bybit inconsistente para USE_TESTNET={self.testnet}: {invalid_urls}")
            return

        if api_urls != self.active_endpoint:
            raise RuntimeError(f"Endpoint Bybit inconsistente para USE_TESTNET={self.testnet}: {api_urls}")

    def _init_pybit_session(self, api_key, api_secret):
        """Inicializa sessão pybit V5 com recv_window ampliado para ambientes com latência."""
        try:
            HTTP = _get_pybit_http()
            self.pybit_sdk_module = getattr(HTTP, '__module__', '')
            if 'pybit.unified_trading' not in self.pybit_sdk_module:
                raise RuntimeError(f"SDK pybit incompatível: esperado pybit.unified_trading, recebido {self.pybit_sdk_module}")

            self.pybit_session = HTTP(
                testnet=self.testnet,
                demo=self.is_demo,
                api_key=api_key,
                api_secret=api_secret,
                recv_window=20000,
            )
            if not self.is_demo and not self.testnet:
                self.pybit_session.endpoint = self.active_endpoint
            print(
                f"🔌 [PYBIT V5] módulo={self.pybit_sdk_module} testnet={self.testnet} demo={self.is_demo} "
                f"endpoint={self.pybit_session.endpoint} recv_window=20000ms",
                flush=True,
            )
        except Exception as e:
            print(f"⚠️ [PYBIT] Sessão HTTP indisponível: {e}", flush=True)
            self.pybit_session = None

    def _format_bybit_error(self, payload):
        """Normaliza erros da Bybit V5 para o front-end."""
        try:
            if isinstance(payload, dict):
                code = payload.get('retCode')
                msg = payload.get('retMsg') or 'Erro Bybit'
                return f"Bybit retCode={code}: {msg}"
        except Exception:
            pass
        return str(payload)

    def _apply_rate_limit(self, endpoint):
        """Aplica delay adaptativo para evitar estouro de chamadas."""
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
        """Retorna True apenas para erros reais de credenciais inválidas."""
        return (
            '10003' in msg
            or '10004' in msg
            or '10002' in msg
            or 'API key is invalid' in msg
            or '403' in msg
            or 'Forbidden' in msg
            or 'timestamp' in msg.lower()
            or 'nonce' in msg.lower()
        )

    def _extract_bybit_ret_code(self, error):
        """Extrai retCode de erros (ccxt/pybit) sem depender do formato exato."""
        try:
            if isinstance(error, dict) and 'retCode' in error:
                code = error.get('retCode')
                return str(code) if code is not None else None
        except Exception:
            pass

        for attr in ('error_code', 'code', 'retCode'):
            try:
                code = getattr(error, attr, None)
                if code is not None:
                    return str(code)
            except Exception:
                pass

        text = str(error or '')
        match = re.search(r'retCode\\s*["\']?\\s*[:=]\\s*(\\d+)', text)
        if match:
            return match.group(1)

        # Formato comum: bybit {"retCode":10003,"retMsg":"..."}
        match = re.search(r'(\{.*?\})', text)
        if match:
            try:
                payload = json.loads(match.group(1))
                code = payload.get('retCode')
                return str(code) if code is not None else None
            except Exception:
                return None
        return None

    def _record_last_auth_error(self, error):
        try:
            self.last_auth_error_code = self._extract_bybit_ret_code(error)
            self.last_auth_error_message = str(error).split('\n')[0][:240]
        except Exception:
            self.last_auth_error_code = None
            self.last_auth_error_message = None

    def _emit_authentication_alert(self):
        print(AUTH_10003_ALERT, flush=True)

    def _handle_v5_ret_code(self, payload, route_label):
        """Valida códigos de resposta oficiais da API Bybit V5."""
        if not isinstance(payload, dict):
            return False, str(payload)

        ret_code = payload.get('retCode')
        if str(ret_code) in {'0', 'None'} or ret_code is None:
            return True, ''

        ret_msg = str(payload.get('retMsg') or 'Erro Bybit').strip()
        message = f"{route_label} falhou: retCode={ret_code} retMsg={ret_msg}"
        if str(ret_code) == '10003':
            self.authenticated = False
            self._record_last_auth_error(payload)
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

    def calculate_dynamic_order_qty(self, symbol: str, balance=None, leverage=None, after_stop: bool = False):
        """Calcula quantidade com percentual da banca (padrão 5%), não mínimo da moeda."""
        current_price = self.get_last_price(symbol)
        if current_price <= 0:
            raise ValueError(f"Não foi possível obter preço atual para {symbol}")

        balance_val = float(balance or self.get_balance() or 0)
        if balance_val <= 0:
            raise ValueError("Saldo indisponível para cálculo percentual da banca")

        lev = float(leverage or getattr(self, 'default_leverage', 10) or 10)
        margin, qty = calculate_position_qty(
            balance_val, current_price, lev, after_stop=after_stop,
        )
        metadata = {
            'min_amount': 0.0,
            'min_cost': 0.0,
            'calculated_cost': round(qty * current_price, 2),
            'margin_usdt': margin,
            'entry_pct': load_entry_after_stop_pct() if after_stop else load_entry_pct(),
            'leverage': lev,
            'exchange': 'bybit',
        }
        return qty, metadata

    def _get_market_limits(self, symbol):
        """Retorna (min_amount, min_cost) do mercado."""
        try:
            self.exchange.load_markets()
            market = self.exchange.market(symbol)
            limits = market.get('limits', {})
            min_amount = limits.get('amount', {}).get('min')
            if min_amount is None or str(min_amount).lower() == 'none' or min_amount <= 0:
                min_amount = 0.001
            min_cost = limits.get('cost', {}).get('min')
            if min_cost is None or str(min_cost).lower() == 'none' or min_cost <= 0:
                min_cost = 6.0
            return float(min_amount), float(min_cost)
        except Exception as market_err:
            print(f"⚠️ [BYBIT MARKET] Erro ao carregar limites: {market_err}, usando defaults", flush=True)
            return 0.001, 6.0

    def validate_pct_sizing_qty(self, symbol, qty, strict=True):
        """
        Valida qty calculada por % da banca.
        strict=True: aborta se abaixo do mínimo da exchange (não aumenta para o mínimo).
        Retorna (qty_normalizada, ok, motivo).
        """
        try:
            qty_decimal = Decimal(str(float(qty)))
        except (TypeError, ValueError):
            return 0.0, False, f"Quantidade inválida: {qty}"

        if qty_decimal <= 0:
            return 0.0, False, f"Quantidade deve ser positiva: {qty}"

        current_price = self.get_last_price(symbol)
        if current_price <= 0:
            return 0.0, False, f"Preço indisponível para {symbol}"

        min_amount, min_cost = self._get_market_limits(symbol)
        min_qty_for_notional = Decimal(str(min_cost)) / Decimal(str(current_price))
        required_min_qty = max(Decimal(str(min_amount)), min_qty_for_notional)

        if strict and qty_decimal < required_min_qty:
            notional = float(qty_decimal) * current_price
            return (
                float(qty_decimal),
                False,
                (
                    f"5% da banca (${notional:.2f} nocional) abaixo do mínimo da exchange "
                    f"(${min_cost:.2f}). Aumente o saldo ou o percentual — não usamos mínimo da moeda."
                ),
            )

        final_qty = float(self.exchange.amount_to_precision(symbol, float(qty_decimal)))
        final_notional = final_qty * current_price
        if strict and final_notional < min_cost:
            return (
                final_qty,
                False,
                f"Nocional ${final_notional:.2f} abaixo do mínimo ${min_cost:.2f} após precisão",
            )

        print(
            f"   ✅ [BYBIT ORDER VALIDA] qty={final_qty} (notional=${final_notional:.2f}, "
            f"mínimo exchange=${min_cost:.2f})",
            flush=True,
        )
        return final_qty, True, "OK"

    def _normalize_order_qty(self, symbol, qty, strict_pct_sizing=False):
        """
        Normaliza quantidade para precisão aceita pela corretora.
        strict_pct_sizing=True: não aumenta qty para o mínimo da exchange (modo 5% banca).
        """
        if strict_pct_sizing:
            final_qty, ok, reason = self.validate_pct_sizing_qty(symbol, qty, strict=True)
            if not ok:
                raise ValueError(reason)
            return str(final_qty)

        try:
            # Conversão segura de float para Decimal usando string
            qty_decimal = Decimal(str(float(qty)))
        except (TypeError, ValueError):
            raise ValueError(f"Quantidade inválida: {qty}")

        if qty_decimal <= 0:
            raise ValueError(f"Quantidade deve ser positiva: {qty}")

        current_price = self.get_last_price(symbol)
        if current_price <= 0:
            raise ValueError(f"Não foi possível obter preço atual para {symbol}")

        try:
            self.exchange.load_markets()
            market = self.exchange.market(symbol)
            limits = market.get('limits', {})

            min_amount = limits.get('amount', {}).get('min')
            if min_amount is None or str(min_amount).lower() == 'none' or min_amount <= 0:
                min_amount = 0.001

            min_cost = limits.get('cost', {}).get('min')
            if min_cost is None or str(min_cost).lower() == 'none' or min_cost <= 0:
                min_cost = 6.0

            print(f"   📊 [BYBIT LIMITS] {symbol}: min_amount={min_amount}, min_notional={min_cost} USDT", flush=True)
        except Exception as market_err:
            print(f"⚠️ [BYBIT MARKET] Erro ao carregar limites: {market_err}, usando defaults", flush=True)
            min_amount = 0.001
            min_cost = 6.0

        # Conversões seguras usando Decimal(str())
        min_cost_decimal = Decimal(str(min_cost))
        current_price_decimal = Decimal(str(current_price))
        min_qty_for_notional = min_cost_decimal / current_price_decimal

        required_min_qty = max(Decimal(str(min_amount)), min_qty_for_notional)

        if qty_decimal < required_min_qty:
            print(f"⚠️ [BYBIT QTY] Quantidade {qty_decimal} abaixo do mínimo necessário. Ajustando para {required_min_qty}", flush=True)
            qty_decimal = required_min_qty

        # Delega arredondamento final estritamente ao CCXT
        final_qty = self.exchange.amount_to_precision(symbol, float(qty_decimal))

        final_qty_decimal = Decimal(str(final_qty))
        notional_value_decimal = final_qty_decimal * current_price_decimal

        if notional_value_decimal < min_cost_decimal:
            adjusted_qty = min_cost_decimal / current_price_decimal
            final_qty = self.exchange.amount_to_precision(symbol, float(adjusted_qty) * 1.05)
            final_qty_decimal = Decimal(str(final_qty))
            notional_value_decimal = final_qty_decimal * current_price_decimal
            print(f"   🔧 [BYBIT NOTIONAL RE-ADJUSTED] Qty recalculada para cima para bater o piso: qty={final_qty}", flush=True)

        print(f"   ✅ [BYBIT ORDER VALIDA] qty={final_qty} (notional={float(notional_value_decimal):.2f} USDT >= {float(min_cost_decimal)} USDT)", flush=True)

        return str(final_qty)

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
        """Busca saldo USDT com fallback seguro para múltiplos perfis de conta Bybit."""
        # Se já sabemos que o cliente não está autenticado (ex.: retCode=10003),
        # não insistimos em novos fetch_balance — evita spam e throttling.
        if not getattr(self, 'authenticated', False):
            return None

        def _usdt_from(balance):
            total = (balance or {}).get('total') or {}
            usdt = total.get('USDT')
            return float(usdt) if usdt is not None else None

        def _extract_unified_available_usdt(wallet_response):
            try:
                result = (wallet_response or {}).get('result') or {}
                wallet_list = result.get('list') or []
                for wallet_data in wallet_list:
                    coin_list = wallet_data.get('coin') or []
                    for coin in coin_list:
                        if str(coin.get('coin') or '').upper() != 'USDT':
                            continue
                        for field in ('availableBalance', 'availableToWithdraw', 'walletBalance', 'equity'):
                            raw = coin.get(field)
                            if raw is None:
                                continue
                            return float(raw)
                    for field in ('totalAvailableBalance', 'totalWalletBalance'):
                        raw = wallet_data.get(field)
                        if raw is None:
                            continue
                        return float(raw)
            except Exception:
                return None
            return None

        ccxt = _get_ccxt()

        def _handle_ccxt_balance_error(scope_label, err):
            self._record_last_auth_error(err)
            msg = str(err)
            print(f"⚠️ [BYBIT] Erro ({scope_label}): {msg}", flush=True)
            if isinstance(err, ccxt.AuthenticationError) or self._is_auth_error(msg):
                self.authenticated = False
                if str(self.last_auth_error_code) == '10003':
                    self._emit_authentication_alert()
                return True
            return False

        # Fallback 0: Tenta usar pybit diretamente (mais confiável para saldo)
        if self.pybit_session and self.authenticated:
            try:
                print(f"📊 [BYBIT] Tentando get_wallet_balance (pybit UNIFIED) para {self.exchange.apiKey[:4]}...", flush=True)
                wallet_response = self.pybit_session.get_wallet_balance(accountType='UNIFIED')
                ok, err = self._handle_v5_ret_code(wallet_response, 'get_wallet_balance')

                if ok:
                    wallet_balance = _extract_unified_available_usdt(wallet_response)
                    if wallet_balance is not None:
                        print(f"✅ [BYBIT] Saldo disponível UNIFIED via pybit: ${float(wallet_balance):.2f} USDT", flush=True)
                        return float(wallet_balance)
                else:
                    print(f"⚠️ [BYBIT] Erro pybit get_wallet_balance: {err}", flush=True)
                    self._record_last_auth_error(wallet_response)
            except Exception as e:
                self._record_last_auth_error(e)
                print(f"⚠️ [BYBIT] Exceção em pybit get_wallet_balance: {e}", flush=True)

        # Demo Trading: CCXT chama endpoints não suportados (retCode 10032).
        if self.is_demo:
            print("⚠️ [BYBIT] Saldo indisponível via pybit no ambiente DEMO.", flush=True)
            return None

        # Fallback 1: Conta Unificada (UTA) via CCXT
        try:
            print(f"📊 [BYBIT] Tentando fetch_balance (UNIFIED) para {self.exchange.apiKey[:4]}...", flush=True)
            balance = self.exchange.fetch_balance(params={'accountType': 'UNIFIED'})
            usdt = _usdt_from(balance)
            if usdt is not None: return usdt
        except Exception as e:
            if _handle_ccxt_balance_error('UNIFIED', e):
                return None

        # Fallback 2: Conta Standard/Contratos Clássica
        try:
            print(f"📊 [BYBIT] Tentando fetch_balance (CONTRACT)...", flush=True)
            balance = self.exchange.fetch_balance(params={'accountType': 'CONTRACT'})
            usdt = _usdt_from(balance)
            if usdt is not None: return usdt
        except Exception as e:
            if _handle_ccxt_balance_error('CONTRACT', e):
                return None

        # Fallback 3: Swap Param Legado
        try:
            print(f"📊 [BYBIT] Tentando fetch_balance (type=swap)...", flush=True)
            balance = self.exchange.fetch_balance(params={'type': 'swap'})
            usdt = _usdt_from(balance)
            if usdt is not None: return usdt
        except Exception as e:
            if _handle_ccxt_balance_error('SWAP', e):
                return None
            msg = str(e)
            print(f"[ERRO BROKER] Falha crítica ao consultar saldo total: {msg}", flush=True)
            return None

        return None

    def fetch_ohlcv(self, symbol, timeframe="15m"):
        """Busca base de dados histórica filtrada por cache atômico."""
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
            print(f"[ERRO BROKER] Dados {symbol} falharam: {e}", flush=True)
            fail_count = self.ohlcv_failures.get(cache_key, 0) + 1
            self.ohlcv_failures[cache_key] = fail_count

            if fail_count >= self.max_ohlcv_failures:
                if cache_key in self.cache_ohlcv:
                    del self.cache_ohlcv[cache_key]
                print(f"⚠️ [CACHE INVALIDADO] {symbol} {timeframe} devido a falhas consecutivas de rede", flush=True)
                return None

            return self.cache_ohlcv[cache_key][0] if cache_key in self.cache_ohlcv else None

    def _ensure_public_market_exchange(self):
        """CCXT Bybit mainnet sem API keys — tickers públicos (evita retCode 10003)."""
        if self._public_market_exchange is not None:
            return self._public_market_exchange

        from src.config import get_bybit_base_url

        ccxt = _get_ccxt()
        endpoint = get_bybit_base_url(False)
        exchange = ccxt.bybit({
            'enableRateLimit': True,
            'timeout': 15000,
            'options': {
                'defaultType': 'swap',
                'defaultSubType': 'linear',
                'adjustForTimeDifference': True,
            },
        })
        api_urls = exchange.urls.get('api')
        if isinstance(api_urls, dict):
            for key in list(api_urls.keys()):
                api_urls[key] = endpoint
        else:
            exchange.urls['api'] = endpoint
        self._public_market_exchange = exchange
        return exchange

    def _fetch_public_last_price(self, symbol):
        """Preço via endpoint público mainnet, sem autenticação."""
        exchange = self._ensure_public_market_exchange()
        self._apply_rate_limit('get_last_price_public')
        ticker = exchange.fetch_ticker(symbol, params={'category': 'linear'})
        return float(ticker.get('last') or 0)

    def get_last_price(self, symbol):
        """Preço em tempo real do ativo (com fallback público se a sessão autenticada falhar)."""
        if symbol in self.cache_ticker and self._is_cache_valid(self.cache_ticker[symbol], self.cache_ttl_ticker):
            return self.cache_ticker[symbol][0]

        try:
            self._apply_rate_limit('get_last_price')
            ticker = self.exchange.fetch_ticker(symbol, params={'category': 'linear'})
            price = float(ticker['last'])
            if price > 0:
                self.cache_ticker[symbol] = (price, time.time())
                return price
        except Exception as e:
            print(f"[ERRO BROKER] Preço para {symbol} falhou: {e}", flush=True)

        # Chaves inválidas / endpoint errado (ex.: 10003) não podem zerar o dashboard.
        try:
            price = self._fetch_public_last_price(symbol)
            if price > 0:
                self.cache_ticker[symbol] = (price, time.time())
                print(f"[BROKER] Preço público mainnet {symbol}: {price}", flush=True)
                return price
        except Exception as public_err:
            print(f"[ERRO BROKER] Preço público para {symbol} falhou: {public_err}", flush=True)

        return self.cache_ticker[symbol][0] if symbol in self.cache_ticker else 0.0

    def fetch_order_details(self, symbol, order_id):
        """Busca a ficha descritiva completa de uma boleta de mercado executada."""
        try:
            self._apply_rate_limit('fetch_order')
            params = {'category': 'linear'}
            print(f"   🔍 Buscando detalhes da ordem {order_id} para {symbol}...", flush=True)
            order_details = self.exchange.fetch_order(order_id, symbol, params=params)
            print("   ✅ Detalhes da ordem obtidos com sucesso", flush=True)
            return order_details
        except Exception as e:
            print(f"   ⚠️ Não foi possível buscar os metadados da ordem {order_id}: {e}", flush=True)
            return None

    def execute_market_order(self, symbol, side, qty, raise_on_error=False, strict_pct_sizing=False):
        """Executa ordem a mercado para entrada instantânea na Bybit V5."""
        try:
            if not self.authenticated:
                print("[ERRO BROKER] Ordem abortada: chaves ausentes ou inválidas.", flush=True)
                if raise_on_error:
                    raise RuntimeError('Cliente sem credenciais válidas na exchange.')
                return None

            normalized_qty = self._normalize_order_qty(symbol, qty, strict_pct_sizing=strict_pct_sizing)
            ccxt_qty = float(normalized_qty)

            print(f"🔥 [ORDEM SNIPER BYBIT] {side.upper()} {normalized_qty} em {symbol}", flush=True)

            if self.pybit_session is not None:
                v5_symbol = self._normalize_v5_symbol(symbol)

                # Mapeia positionIdx para Hedge Mode (Modo Bidirecional)
                position_idx = 1 if side.lower() == 'buy' else 2

                payload = {
                    'category': 'linear',
                    'symbol': v5_symbol,
                    'side': self._normalize_v5_side(side),
                    'orderType': 'Market',
                    'qty': normalized_qty,
                    'positionIdx': position_idx,
                }
                print(f"   📤 Enviando via Pybit V5 (/v5/order/create): {payload}", flush=True)
                rsp = self.pybit_session.place_order(**payload)
                print(f"   📥 Resposta Bybit: {rsp}", flush=True)

                ok, error_message = self._handle_v5_ret_code(rsp, 'v5/order/create')
                if not ok:
                    print(f"❌ [ERRO EXECUÇÃO BYBIT] {error_message}", flush=True)
                    if raise_on_error: raise RuntimeError(error_message)
                    return None

                result = (rsp or {}).get('result') or {}
                order_id = result.get('orderId') or result.get('orderLinkId')
                print(f"✅ [BYBIT] Ordem preenchida na exchange - ID: {order_id}", flush=True)

                order_details = self.fetch_order_details(symbol, order_id)
                if order_details:
                    return {**order_details, 'route': 'v5/order/create', 'category': 'linear'}
                else:
                    return {**result, 'id': order_id, 'route': 'v5/order/create', 'category': 'linear', 'symbol': v5_symbol}

            # Fallback nativo via Core CCXT Engine
            # Mapeia positionIdx para Hedge Mode (Modo Bidirecional)
            position_idx = 1 if side.lower() == 'buy' else 2
            params = {'category': 'linear', 'positionIdx': position_idx}
            print(f"   📤 Enviando via CCXT Fallback: {symbol} | qty={normalized_qty} | positionIdx={position_idx}", flush=True)
            order = self.exchange.create_order(symbol, 'market', side, ccxt_qty, params=params)
            order_id = order.get('id', 'N/A')
            print(f"✅ [BYBIT CCXT] Ordem preenchida - ID: {order_id}", flush=True)

            if order_id != 'N/A':
                order_details = self.fetch_order_details(symbol, order_id)
                if order_details: return order_details

            return order
        except Exception as e:
            ccxt = _get_ccxt()
            if isinstance(e, ccxt.BaseError):
                print(f"❌ ERRO DA CORRETORA BYBIT (CCXT): {e}", flush=True)
            else:
                print(f"❌ [ERRO EXECUÇÃO BYBIT] Falha de infraestrutura: {e}", flush=True)
            if raise_on_error: raise
            return None

    def test_connection(self):
        """Testa o canal de comunicação seguro de dados privados."""
        try:
            if self.authenticated:
                insurance_ok, insurance_message = self._validate_insurance_fund()
                if not insurance_ok: return False, insurance_message

                bal = self.get_balance()
                if bal is not None:
                    return True, f"{insurance_message} | Autenticado OK (USDT {bal:.2f})"

                if self.pybit_session is not None:
                    pybit_errors = []
                    for account_type in ['UNIFIED', 'CONTRACT']:
                        try:
                            rsp = self.pybit_session.get_wallet_balance(accountType=account_type, coin='USDT')
                            ok, err_msg = self._handle_v5_ret_code(rsp, f'v5/balance ({account_type})')
                            if ok:
                                result = (rsp or {}).get('result') or {}
                                rows = result.get('list') or []
                                usdt_bal = float(rows[0].get('totalWalletBalance') or 0.0) if rows else 0.0
                                return True, f"{insurance_message} | Autenticado OK ({account_type}, USDT {usdt_bal:.2f})"
                            pybit_errors.append(err_msg)
                        except Exception as pybit_err:
                            pybit_errors.append(str(pybit_err).split('\n')[0][:220])

                    if pybit_errors: return False, pybit_errors[0]

                return False, "Chave API sem privilégios ou inválida na Bybit"
            else:
                self.exchange.fetch_tickers()
                return True, "Canal Público OK"
        except Exception as e:
            return False, str(e).split('\n')[0][:200]

    def _fetch_open_position_leverage(self, symbol, side):
        """Lê alavancagem real da posição aberta na Bybit (evita SL/TP com leverage errado)."""
        if not self.pybit_session:
            return None
        try:
            v5_symbol = self._normalize_v5_symbol(symbol)
            side_norm = str(side or '').strip().lower()
            pos_idx = 1 if side_norm in ('buy', 'comprar', 'long') else 2
            rsp = self.pybit_session.get_positions(category='linear', symbol=v5_symbol, settleCoin='USDT')
            ok, _ = self._handle_v5_ret_code(rsp, 'get_positions')
            if not ok:
                return None
            for pos in (rsp.get('result') or {}).get('list', []):
                if float(pos.get('size') or 0) <= 0:
                    continue
                idx = int(pos.get('positionIdx') or 0)
                if idx not in (0, pos_idx):
                    continue
                lev = float(pos.get('leverage') or 0)
                if lev > 0:
                    return lev
        except Exception:
            pass
        return None

    def set_tp_sl_sniper(self, symbol, side, entry_price, position_qty, leverage=None):
        """
        TP/SL proporcionais à margem com alavancagem (Bybit V5 set_trading_stop):
        - TP: +100% da margem
        - SL: -50% da margem
        """
        try:
            if not self.authenticated:
                print("❌ [TP/SL] Não autenticado. Proteção de capital ABORTADA.")
                return False
            if not self.pybit_session:
                print("❌ [TP/SL] Sessão pybit indisponível.")
                return False

            side_norm = str(side or '').strip().lower()
            pos_idx = 1 if side_norm in ('buy', 'comprar', 'long') else 2
            lev = self._fetch_open_position_leverage(symbol, side)
            if not lev or lev <= 0:
                lev = float(leverage or getattr(self, 'default_leverage', 20) or 20)
            tp_price, sl_price = calculate_tp_sl_prices(entry_price, side, lev)

            price_to_precision = getattr(self.exchange, 'price_to_precision', None)
            if callable(price_to_precision):
                try:
                    tp_price = float(price_to_precision(symbol, tp_price))
                    sl_price = float(price_to_precision(symbol, sl_price))
                except Exception as precision_error:
                    print(f"⚠️ [TP/SL] Falha na formatação de casas decimais: {precision_error}")

            v5_symbol = self._normalize_v5_symbol(symbol)
            print(f"🛡️  [PROTEÇÃO SNIPER] {v5_symbol} | Entrada: ${entry_price:.8f} | {lev}x | idx={pos_idx}")
            print(f"   ✅ TP (+100% margem): ${tp_price:.8f} | ❌ SL (-50% margem): ${sl_price:.8f}")

            for attempt in range(1, 4):
                rsp = self.pybit_session.set_trading_stop(
                    category='linear',
                    symbol=v5_symbol,
                    takeProfit=str(tp_price),
                    stopLoss=str(sl_price),
                    positionIdx=pos_idx,
                    tpslMode='Full',
                )
                ok, err = self._handle_v5_ret_code(rsp, 'set_trading_stop')
                if ok:
                    print("✅ [TP/SL APLICADO] Alvos registrados na Bybit via set_trading_stop.", flush=True)
                    return True
                if attempt < 3 and ('position not exists' in err.lower() or '110017' in err):
                    time.sleep(1.5)
                    continue
                print(f"⚠️ [TP/SL FALHOU] {err}", flush=True)
                return False
            return False

        except Exception as e:
            print(f"⚠️ [TP/SL FALHOU] Erro na injeção de alvos Bybit: {e}", flush=True)
            return False

    def close_position_with_sl(self, symbol, position_side):
        """Encerra posição aberta na Bybit (pybit V5 primeiro, CCXT como fallback)."""
        try:
            if not self.authenticated:
                return False

            print(f"🔒 [CLOSE POSITION] Disparando fechamento para {symbol}", flush=True)

            requested_side = str(position_side or '').strip().lower()
            if requested_side in ('buy', 'long', 'comprar'):
                requested_bucket = 'long'
            elif requested_side in ('sell', 'short', 'vender'):
                requested_bucket = 'short'
            else:
                requested_bucket = None

            def _symbol_keys(value):
                raw = str(value or '').strip().upper()
                if not raw:
                    return set()
                cleaned = ''.join(ch for ch in raw if ch.isalnum())
                keys = {cleaned}
                if ':' in raw:
                    keys.add(''.join(ch for ch in raw.split(':', 1)[0] if ch.isalnum()))
                if '/' in raw:
                    base, quote = raw.split('/', 1)
                    quote = quote.split(':', 1)[0]
                    if base and quote:
                        keys.add(f"{base}{quote}")
                if raw.endswith('USDT') and len(raw) > 4:
                    keys.add(raw[:-4] + 'USDT')
                return {k for k in keys if k}

            requested_symbol_keys = _symbol_keys(symbol)
            v5_symbol = self._normalize_v5_symbol(symbol)

            # ── Caminho principal: pybit V5 ──────────────────────────────────
            if self.pybit_session:
                try:
                    positions_response = self.pybit_session.get_positions(
                        category='linear', symbol=v5_symbol, settleCoin='USDT',
                    )
                    ok, err = self._handle_v5_ret_code(positions_response, 'get_positions')
                    if ok:
                        for pos in (positions_response.get('result') or {}).get('list', []):
                            size = float(pos.get('size') or 0)
                            if size <= 0:
                                continue
                            pos_side = str(pos.get('side') or '').lower()
                            pos_idx = int(pos.get('positionIdx') or (1 if pos_side == 'buy' else 2))
                            bucket = 'long' if pos_side in ('buy', 'long') or pos_idx == 1 else 'short'
                            if requested_bucket and bucket != requested_bucket:
                                continue
                            close_side = 'Sell' if bucket == 'long' else 'Buy'
                            qty = self._normalize_order_qty(v5_symbol, size)
                            rsp = self.pybit_session.place_order(
                                category='linear',
                                symbol=v5_symbol,
                                side=close_side,
                                orderType='Market',
                                qty=str(qty),
                                reduceOnly=True,
                                positionIdx=pos_idx,
                            )
                            ok_order, err_order = self._handle_v5_ret_code(rsp, 'place_order')
                            if ok_order:
                                order_id = ((rsp.get('result') or {}).get('orderId') or 'N/A')
                                print(f"✅ [CLOSE POSITION] Fechada via pybit. ID: {order_id}", flush=True)
                                return True
                            print(f"⚠️ [CLOSE POSITION] pybit place_order falhou: {err_order}", flush=True)
                except Exception as pybit_err:
                    print(f"⚠️ [CLOSE POSITION] pybit falhou, tentando CCXT: {pybit_err}", flush=True)

            # ── Fallback: CCXT ─────────────────────────────────────────────────
            positions = self.exchange.fetch_positions(params={'category': 'linear'})
            target_position = None
            target_bucket = requested_bucket

            for p in positions:
                pos_symbol = p.get('symbol') or p.get('info', {}).get('symbol') or ''
                pos_contracts = float(p.get('contracts') or 0)
                pos_side = str(p.get('side', '')).lower()
                pos_info = p.get('info', {}) or {}
                pos_symbol_keys = _symbol_keys(pos_symbol)
                pos_idx = str(pos_info.get('positionIdx') or '').strip()

                if requested_symbol_keys and not requested_symbol_keys.intersection(pos_symbol_keys):
                    continue

                if pos_contracts <= 0:
                    continue

                if pos_side in ('long', 'buy'):
                    current_bucket = 'long'
                elif pos_side in ('short', 'sell'):
                    current_bucket = 'short'
                elif pos_idx == '1':
                    current_bucket = 'long'
                elif pos_idx == '2':
                    current_bucket = 'short'
                else:
                    current_bucket = None

                if requested_bucket and current_bucket and requested_bucket != current_bucket:
                    continue

                target_position = p
                if current_bucket:
                    target_bucket = current_bucket
                break

            if not target_position:
                print(f"⚠️ [CLOSE POSITION] Nenhuma posição aberta encontrada para {symbol}", flush=True)
                return False

            close_side = 'sell' if target_bucket == 'long' else 'buy'
            order_symbol = target_position.get('symbol') or symbol
            pos_size = float(target_position.get('contracts') or target_position.get('info', {}).get('size') or 0)
            position_idx = target_position.get('info', {}).get('positionIdx')

            params = {'category': 'linear', 'reduceOnly': True}
            if position_idx is not None:
                params['positionIdx'] = position_idx

            normalized_qty = self._normalize_order_qty(order_symbol, pos_size)

            order = self.exchange.create_order(
                symbol=order_symbol,
                type='market',
                side=close_side,
                amount=float(normalized_qty),
                params=params
            )

            print(f"✅ [CLOSE POSITION] Posição finalizada via CCXT. ID: {order.get('id', 'N/A')}", flush=True)
            return True
        except Exception as e:
            print(f"❌ [CLOSE POSITION] Erro crítico no fechamento de {symbol}: {e}", flush=True)
            return False
