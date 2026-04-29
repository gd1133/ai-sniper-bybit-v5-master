import time
from datetime import datetime

from src.config import get_bybit_base_url, get_bybit_credentials, resolve_use_testnet

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
    return _ccxt_instance

def _get_pd():
    """Carrega Pandas lazy."""
    global _pd_instance
    if _pd_instance is None:
        import pandas as pd
        _pd_instance = pd
    return _pd_instance


def _get_pybit_http():
    """Carrega pybit HTTP lazy (apenas primeira vez)."""
    global _pybit_http_class
    if _pybit_http_class is None:
        from pybit.unified_trading import HTTP as pybit_http
        _pybit_http_class = pybit_http
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
        api_key = str(api_key or env_api_key or '').strip()
        api_secret = str(api_secret or env_api_secret or '').strip()
        self.testnet = resolve_use_testnet(testnet)
        self.active_endpoint = get_bybit_base_url(self.testnet)
        self.pybit_session = None

        # Não inclua chaves vazias na configuração — passar apiKey=None faz a API
        # interpretar como credencial inválida e causa erro 10003.
        cfg = {
            'enableRateLimit': True,
            'rateLimit': 100,  # Delay mínimo entre requisições
            'options': {
                'defaultType': 'swap', # Foco em Perpétuos (Linear)
                'adjustForTimeDifference': True,
                'recvWindow': 20000,
            }
        }
        if api_key and api_secret:
            cfg['apiKey'] = api_key
            cfg['secret'] = api_secret

        self.exchange = ccxt.bybit(cfg)
        self._configure_exchange_endpoint()

        if api_key and api_secret:
            self._init_pybit_session(api_key, api_secret)

        print(f"🔍 [BYBIT ENDPOINT] testnet={self.testnet} endpoint={self.active_endpoint}")

        # Indica se esta instância tem credenciais de escrita/autenticação
        self.authenticated = bool(api_key and api_secret)
        
        # --- SISTEMA DE CACHE E SEGURANÇA ---
        self.cache_ohlcv = {} 
        self.cache_ticker = {} 
        self.cache_ttl_ohlcv = 30
        self.cache_ttl_ticker = 3
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
        """Inicializa sessão pybit V5 com recv_window ampliado para ambientes com latência."""
        try:
            HTTP = _get_pybit_http()
            self.pybit_session = HTTP(
                testnet=self.testnet,
                api_key=api_key,
                api_secret=api_secret,
                recv_window=20000,
            )
            self.pybit_session.endpoint = self.active_endpoint
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
            or 'API key is invalid' in msg
            or '403' in msg
            or 'Forbidden' in msg
            or 'CloudFront' in msg
            or 'timestamp' in msg.lower()
        )
        # Nota: retCode genérico NÃO está aqui — erros como 10016 (account type
        # not found) são erros de parâmetro, não de autenticação.

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
            balance = self.exchange.fetch_balance(params={'accountType': 'UNIFIED'})
            usdt = _usdt_from(balance)
            if usdt is not None:
                return usdt
        except Exception as e:
            msg = str(e)
            if self._is_auth_error(msg):
                self.authenticated = False
                return None
            # Erro de tipo de conta ou outro — tenta próximo fallback

        # Tentativa 2: Conta de Contratos Clássica (não-UTA)
        try:
            balance = self.exchange.fetch_balance(params={'accountType': 'CONTRACT'})
            usdt = _usdt_from(balance)
            if usdt is not None:
                return usdt
        except Exception as e:
            msg = str(e)
            if self._is_auth_error(msg):
                self.authenticated = False
                return None

        # Tentativa 3: Swap/Linear (parâmetro legado)
        try:
            balance = self.exchange.fetch_balance(params={'type': 'swap'})
            usdt = _usdt_from(balance)
            if usdt is not None:
                return usdt
        except Exception as e:
            msg = str(e)
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

    def execute_market_order(self, symbol, side, qty):
        """Executa ordem a mercado para entrada instantânea."""
        try:
            if not self.authenticated:
                print(f"[ERRO BROKER] Ordem não executada: cliente sem credenciais.")
                return None
            print(f"🔥 [ORDEM SNIPER] {side.upper()} {qty} em {symbol}")
            params = {'category': 'linear'}
            order = self.exchange.create_market_order(symbol, side, qty, params=params)
            return order
        except Exception as e:
            print(f"❌ [ERRO EXECUÇÃO] Falha crítica na ordem: {e}")
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
                # 1) Validação principal via CCXT com fallback de accountType.
                bal = self.get_balance()
                if bal is not None:
                    return True, f"Autenticado OK (USDT {bal:.2f})"

                # 2) Fallback via pybit para capturar melhor mensagem de erro.
                if self.pybit_session is not None:
                    print(f"🔎 [BYBIT VALIDATION] endpoint={self.active_endpoint}")
                    pybit_errors = []
                    for account_type in ['UNIFIED', 'CONTRACT']:
                        try:
                            rsp = self.pybit_session.get_wallet_balance(accountType=account_type, coin='USDT')
                            if int((rsp or {}).get('retCode', -1)) == 0:
                                result = (rsp or {}).get('result') or {}
                                rows = result.get('list') or []
                                usdt_bal = 0.0
                                if rows:
                                    usdt_bal = float(rows[0].get('totalWalletBalance') or 0.0)
                                return True, f"Autenticado OK ({account_type}, USDT {usdt_bal:.2f})"
                            pybit_errors.append(self._format_bybit_error(rsp))
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
        Encerra posição se Stop Loss for acionado (Fallback se TP/SL falhar).
        Implementa o Protocolo Sniper de Rigor Máximo.
        """
        try:
            if not self.authenticated:
                return False
            
            # Identifica lado oposto para fechar
            close_side = "sell" if position_side.lower() == "buy" else "buy"
            
            # Busca tamanho da posição aberta
            positions = self.exchange.fetch_positions(params={'category': 'linear'})
            pos_size = next(
                (p['contracts'] for p in positions if symbol in p.get('symbol', '')), 
                0
            )
            
            if pos_size > 0:
                order = self.exchange.create_market_order(symbol, close_side, pos_size)
                print(f"🔒 [SL EXECUTADO] Posição {symbol} fechada com proteção")
                return True
            
            return False
        except Exception as e:
            print(f"❌ [SL FALLBACK] Erro ao fechar: {e}")
            return False
