#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                    API TESTER - BYBIT & BINANCE                               ║
║                   Teste Manual de Conectividade                               ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Este é o "MECÂNICO" do sistema - testa se o motor (API) e o combustível (Saldo)
estão prontos para a corrida!

FUNÇÃO:
- Valida chaves de API da Bybit e Binance
- Testa conectividade e autenticação
- Verifica saldo disponível (USDT)
- Testa acesso a dados de mercado
- Valida IP whitelisting
- Identifica se está em testnet ou produção

USO:
    python api_tester.py                    # Testa ambas exchanges
    python api_tester.py --bybit            # Testa apenas Bybit
    python api_tester.py --binance          # Testa apenas Binance
    python api_tester.py --full             # Testa com mais detalhes
"""

import os
import sys
import time
import argparse
from decimal import Decimal

# Carrega variáveis de ambiente
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  python-dotenv não instalado. Usando variáveis de ambiente do sistema.")

# Cores para terminal
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


def print_header(text, color=Colors.BLUE):
    """Imprime cabeçalho formatado."""
    width = 80
    print(f"\n{color}{Colors.BOLD}{'=' * width}{Colors.RESET}")
    print(f"{color}{Colors.BOLD}{text.center(width)}{Colors.RESET}")
    print(f"{color}{Colors.BOLD}{'=' * width}{Colors.RESET}\n")


def print_subheader(text):
    """Imprime subcabeçalho."""
    print(f"\n{Colors.CYAN}{Colors.BOLD}▶ {text}{Colors.RESET}")
    print(f"{Colors.CYAN}{'─' * 78}{Colors.RESET}")


def print_success(text, prefix="✅"):
    """Imprime mensagem de sucesso."""
    print(f"{Colors.GREEN}{prefix} {text}{Colors.RESET}")


def print_error(text, prefix="❌"):
    """Imprime mensagem de erro."""
    print(f"{Colors.RED}{prefix} {text}{Colors.RESET}")


def print_warning(text, prefix="⚠️"):
    """Imprime mensagem de aviso."""
    print(f"{Colors.YELLOW}{prefix} {text}{Colors.RESET}")


def print_info(text, prefix="ℹ️"):
    """Imprime mensagem informativa."""
    print(f"{Colors.BLUE}{prefix} {text}{Colors.RESET}")


def print_detail(label, value, success=True):
    """Imprime detalhe com label e valor."""
    color = Colors.GREEN if success else Colors.RED
    print(f"   {Colors.DIM}{label}:{Colors.RESET} {color}{value}{Colors.RESET}")


def test_bybit_api(full_test=False):
    """
    Testa API da Bybit.

    Args:
        full_test: Se True, executa testes adicionais de mercado

    Returns:
        bool: True se todos os testes passaram
    """
    print_header("🟡 TESTE DA API BYBIT", Colors.YELLOW)

    issues = []
    warnings = []

    # Verifica modo testnet
    use_testnet = str(os.getenv('USE_TESTNET', 'false')).strip().lower() == 'true'

    if use_testnet:
        print_warning("Modo TESTNET ativo - usando contas de teste")
        endpoint = "https://api-testnet.bybit.com"
    else:
        print_success("Modo PRODUÇÃO ativo - usando contas reais")
        endpoint = "https://api.bybit.com"

    print_detail("Endpoint", endpoint, True)
    print()

    # ===============================================
    # 1. VALIDAÇÃO DE CREDENCIAIS
    # ===============================================
    print_subheader("1. Validação de Credenciais")

    api_key = os.getenv('BYBIT_API_KEY', '').strip()
    api_secret = os.getenv('BYBIT_API_SECRET', '').strip()

    if not api_key or api_key.startswith('YOUR_'):
        print_error("API Key não configurada")
        issues.append("Bybit API Key ausente")
        return False

    if not api_secret or api_secret.startswith('YOUR_'):
        print_error("API Secret não configurado")
        issues.append("Bybit API Secret ausente")
        return False

    print_success(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print_success(f"API Secret: {api_secret[:10]}...{api_secret[-4:]}")

    # ===============================================
    # 2. TESTE DE CONECTIVIDADE
    # ===============================================
    print_subheader("2. Teste de Conectividade")

    try:
        # Usa pybit para teste direto
        from pybit.unified_trading import HTTP

        print_info("Inicializando cliente Bybit...")
        session = HTTP(
            testnet=use_testnet,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=20000
        )

        # Força endpoint correto
        session.endpoint = endpoint

        print_success("Cliente inicializado com sucesso")

    except ImportError:
        print_error("Biblioteca 'pybit' não instalada")
        print_info("Execute: pip install pybit")
        return False
    except Exception as e:
        print_error(f"Erro ao inicializar cliente: {e}")
        return False

    # ===============================================
    # 3. TESTE DE AUTENTICAÇÃO
    # ===============================================
    print_subheader("3. Teste de Autenticação")

    try:
        print_info("Testando autenticação com API Key...")

        # Tenta obter informação da API Key
        result = session.get_api_key_information()

        ret_code = result.get('retCode', -1)
        ret_msg = result.get('retMsg', 'Unknown')

        if ret_code == 0:
            print_success("Autenticação bem-sucedida!")

            # Mostra informações da API Key
            api_info = result.get('result', {})
            if api_info:
                print_detail("User ID", api_info.get('userId', 'N/A'), True)
                print_detail("Read Only", api_info.get('readOnly', 'N/A'), True)

                permissions = api_info.get('permissions', {})
                if permissions:
                    print_info("Permissões:")
                    for perm_type, perm_list in permissions.items():
                        if isinstance(perm_list, list):
                            print(f"      {perm_type}: {', '.join(perm_list)}")
        else:
            print_error(f"Falha na autenticação (retCode: {ret_code})")
            print_error(f"Mensagem: {ret_msg}")

            if ret_code == 10003:
                print_warning("Erro 10003: Chave de API inválida ou 2FA ativo")
                print_info("Verifique se a chave é de produção e se o 2FA está desativado na API")

            issues.append(f"Falha de autenticação: {ret_msg}")
            return False

    except Exception as e:
        print_error(f"Erro ao testar autenticação: {e}")
        issues.append(f"Erro de autenticação: {str(e)}")
        return False

    # ===============================================
    # 4. TESTE DE SALDO (COMBUSTÍVEL)
    # ===============================================
    print_subheader("4. Teste de Saldo (Combustível)")

    try:
        print_info("Consultando saldo USDT...")

        balance_result = session.get_wallet_balance(
            accountType="UNIFIED",
            coin="USDT"
        )

        ret_code = balance_result.get('retCode', -1)
        ret_msg = balance_result.get('retMsg', 'Unknown')

        if ret_code == 0:
            account_list = balance_result.get('result', {}).get('list', [])

            if account_list:
                account = account_list[0]
                total_balance = account.get('totalWalletBalance', '0')
                available_balance = account.get('totalAvailableBalance', '0')
                equity = account.get('totalEquity', '0')

                print_success("Saldo obtido com sucesso!")
                print_detail("Saldo Total", f"${float(total_balance):,.2f} USDT", True)
                print_detail("Saldo Disponível", f"${float(available_balance):,.2f} USDT", True)
                print_detail("Equity", f"${float(equity):,.2f} USDT", True)

                if float(available_balance) < 10:
                    print_warning("Saldo disponível baixo (< $10 USDT)")
                    warnings.append("Saldo Bybit baixo")
            else:
                print_warning("Nenhuma conta encontrada")
                warnings.append("Conta Bybit sem saldo")
        else:
            print_error(f"Falha ao obter saldo (retCode: {ret_code})")
            print_error(f"Mensagem: {ret_msg}")
            issues.append(f"Erro ao obter saldo: {ret_msg}")
            return False

    except Exception as e:
        print_error(f"Erro ao consultar saldo: {e}")
        issues.append(f"Erro de saldo: {str(e)}")
        return False

    # ===============================================
    # 5. TESTE DE DADOS DE MERCADO (OPCIONAL)
    # ===============================================
    if full_test:
        print_subheader("5. Teste de Dados de Mercado")

        try:
            print_info("Consultando ticker BTC/USDT...")

            ticker_result = session.get_tickers(
                category="linear",
                symbol="BTCUSDT"
            )

            ret_code = ticker_result.get('retCode', -1)

            if ret_code == 0:
                ticker_list = ticker_result.get('result', {}).get('list', [])
                if ticker_list:
                    ticker = ticker_list[0]
                    last_price = ticker.get('lastPrice', 'N/A')
                    volume_24h = ticker.get('turnover24h', 'N/A')

                    print_success("Dados de mercado acessíveis!")
                    print_detail("BTC/USDT Preço", f"${float(last_price):,.2f}", True)
                    print_detail("Volume 24h", f"${float(volume_24h):,.0f}", True)
            else:
                print_warning("Não foi possível obter dados de mercado")
                warnings.append("Dados de mercado Bybit inacessíveis")

        except Exception as e:
            print_warning(f"Erro ao consultar mercado: {e}")
            warnings.append(f"Erro de mercado Bybit: {str(e)}")

    # ===============================================
    # 6. TESTE DE IP WHITELISTING
    # ===============================================
    print_subheader("6. Validação de IP")

    try:
        import requests
        response = requests.get('https://api.ipify.org?format=json', timeout=5)
        if response.ok:
            ip = response.json().get('ip', 'Unknown')
            print_info(f"IP público do servidor: {ip}")
            print_warning("Certifique-se de que este IP está na whitelist da Bybit")
    except:
        print_warning("Não foi possível detectar o IP público")

    # ===============================================
    # RESUMO FINAL
    # ===============================================
    print_subheader("Resumo do Teste Bybit")

    if not issues:
        print_success("🎉 TODOS OS TESTES BYBIT PASSARAM!")
        print_info("O motor (API) está funcionando e o combustível (Saldo) está pronto!")
        if warnings:
            print()
            for warning in warnings:
                print_warning(warning)
        return True
    else:
        print_error("TESTES BYBIT FALHARAM")
        for issue in issues:
            print_error(issue)
        return False


def test_binance_api(full_test=False):
    """
    Testa API da Binance.

    Args:
        full_test: Se True, executa testes adicionais de mercado

    Returns:
        bool: True se todos os testes passaram
    """
    print_header("🟠 TESTE DA API BINANCE", Colors.YELLOW)

    issues = []
    warnings = []

    # Verifica modo testnet
    use_testnet = str(os.getenv('USE_TESTNET', 'false')).strip().lower() == 'true'

    if use_testnet:
        print_warning("Modo TESTNET ativo - usando contas de teste")
        endpoint = "https://testnet.binancefuture.com"
    else:
        print_success("Modo PRODUÇÃO ativo - usando contas reais")
        endpoint = "https://fapi.binance.com"

    print_detail("Endpoint", endpoint, True)
    print()

    # ===============================================
    # 1. VALIDAÇÃO DE CREDENCIAIS
    # ===============================================
    print_subheader("1. Validação de Credenciais")

    api_key = os.getenv('BINANCE_API_KEY', '').strip()
    api_secret = os.getenv('BINANCE_API_SECRET', '').strip()

    if not api_key or api_key.startswith('YOUR_'):
        print_warning("API Key não configurada (apenas dados públicos disponíveis)")
        warnings.append("Binance API Key ausente")
        # Continua em modo público
    else:
        print_success(f"API Key: {api_key[:10]}...{api_key[-4:]}")

    if not api_secret or api_secret.startswith('YOUR_'):
        if api_key:
            print_warning("API Secret não configurado")
            warnings.append("Binance API Secret ausente")
    else:
        if api_key:
            print_success(f"API Secret: {api_secret[:10]}...{api_secret[-4:]}")

    # ===============================================
    # 2. TESTE DE CONECTIVIDADE
    # ===============================================
    print_subheader("2. Teste de Conectividade")

    try:
        # Usa CCXT para Binance
        import ccxt

        print_info("Inicializando cliente Binance Futures...")

        config = {
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,
                'recvWindow': 10000,
            }
        }

        if api_key and api_secret:
            config['apiKey'] = api_key
            config['secret'] = api_secret

        exchange = ccxt.binance(config)

        # Configura endpoint
        if use_testnet:
            exchange.set_sandbox_mode(True)
        else:
            exchange.urls['api']['fapiPublic'] = endpoint
            exchange.urls['api']['fapiPrivate'] = endpoint

        print_success("Cliente inicializado com sucesso")

    except ImportError:
        print_error("Biblioteca 'ccxt' não instalada")
        print_info("Execute: pip install ccxt")
        return False
    except Exception as e:
        print_error(f"Erro ao inicializar cliente: {e}")
        issues.append(f"Erro de inicialização: {str(e)}")
        return False

    # ===============================================
    # 3. TESTE DE AUTENTICAÇÃO (SE CREDENCIAIS DISPONÍVEIS)
    # ===============================================
    if api_key and api_secret:
        print_subheader("3. Teste de Autenticação")

        try:
            print_info("Testando autenticação...")

            # Sincroniza tempo
            exchange.load_time_difference()

            # Tenta obter saldo
            balance = exchange.fetch_balance()

            print_success("Autenticação bem-sucedida!")

        except ccxt.AuthenticationError as e:
            print_error(f"Falha na autenticação: {e}")
            print_warning("Verifique se as credenciais estão corretas")
            issues.append(f"Falha de autenticação: {str(e)}")
            return False
        except Exception as e:
            print_error(f"Erro ao testar autenticação: {e}")
            issues.append(f"Erro de autenticação: {str(e)}")
            return False

        # ===============================================
        # 4. TESTE DE SALDO (COMBUSTÍVEL)
        # ===============================================
        print_subheader("4. Teste de Saldo (Combustível)")

        try:
            print_info("Consultando saldo USDT...")

            usdt_balance = balance.get('USDT', {})
            total = usdt_balance.get('total', 0)
            free = usdt_balance.get('free', 0)
            used = usdt_balance.get('used', 0)

            print_success("Saldo obtido com sucesso!")
            print_detail("Saldo Total", f"${float(total):,.2f} USDT", True)
            print_detail("Saldo Disponível", f"${float(free):,.2f} USDT", True)
            print_detail("Saldo em Uso", f"${float(used):,.2f} USDT", True)

            if float(free) < 10:
                print_warning("Saldo disponível baixo (< $10 USDT)")
                warnings.append("Saldo Binance baixo")

        except Exception as e:
            print_error(f"Erro ao consultar saldo: {e}")
            issues.append(f"Erro de saldo: {str(e)}")
            return False

    # ===============================================
    # 5. TESTE DE DADOS DE MERCADO (PÚBLICO)
    # ===============================================
    print_subheader("5. Teste de Dados de Mercado (Público)")

    try:
        print_info("Consultando ticker BTC/USDT...")

        ticker = exchange.fetch_ticker('BTC/USDT')

        last_price = ticker.get('last', 0)
        volume = ticker.get('quoteVolume', 0)

        print_success("Dados de mercado acessíveis!")
        print_detail("BTC/USDT Preço", f"${float(last_price):,.2f}", True)
        print_detail("Volume 24h", f"${float(volume):,.0f}", True)

    except Exception as e:
        print_error(f"Erro ao consultar mercado: {e}")
        issues.append(f"Erro de mercado: {str(e)}")
        return False

    # ===============================================
    # 6. TESTE DE ORDERBOOK (OPCIONAL)
    # ===============================================
    if full_test:
        print_subheader("6. Teste de Order Book")

        try:
            print_info("Consultando order book...")

            orderbook = exchange.fetch_order_book('BTC/USDT', limit=5)

            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])

            if bids and asks:
                print_success("Order book acessível!")
                print_detail("Melhor Bid", f"${bids[0][0]:,.2f}", True)
                print_detail("Melhor Ask", f"${asks[0][0]:,.2f}", True)
            else:
                print_warning("Order book vazio")

        except Exception as e:
            print_warning(f"Erro ao consultar order book: {e}")
            warnings.append(f"Order book inacessível: {str(e)}")

    # ===============================================
    # RESUMO FINAL
    # ===============================================
    print_subheader("Resumo do Teste Binance")

    if not issues:
        print_success("🎉 TODOS OS TESTES BINANCE PASSARAM!")
        print_info("O motor (API) está funcionando e o combustível (Saldo) está pronto!")
        if warnings:
            print()
            for warning in warnings:
                print_warning(warning)
        return True
    else:
        print_error("TESTES BINANCE FALHARAM")
        for issue in issues:
            print_error(issue)
        return False


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description='Teste manual de APIs Bybit e Binance',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python api_tester.py              # Testa ambas exchanges
  python api_tester.py --bybit      # Testa apenas Bybit
  python api_tester.py --binance    # Testa apenas Binance
  python api_tester.py --full       # Testes completos com dados de mercado
        """
    )

    parser.add_argument('--bybit', action='store_true', help='Testa apenas Bybit')
    parser.add_argument('--binance', action='store_true', help='Testa apenas Binance')
    parser.add_argument('--full', action='store_true', help='Executa testes completos')

    args = parser.parse_args()

    # Banner inicial
    print(f"\n{Colors.BOLD}{Colors.MAGENTA}")
    print("╔═══════════════════════════════════════════════════════════════════════════════╗")
    print("║                                                                               ║")
    print("║                    🔧 API TESTER - BYBIT & BINANCE 🔧                        ║")
    print("║                                                                               ║")
    print("║              Validador de Conectividade e Autenticação                       ║")
    print("║                                                                               ║")
    print("╚═══════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.RESET}")

    print_info("Este script testa se o 'motor' (API) e o 'combustível' (Saldo) estão prontos!")
    print()

    # Verifica configuração geral
    print_subheader("Configuração do Sistema")

    allow_order_exec = str(os.getenv('ALLOW_ORDER_EXECUTION', 'false')).strip().lower() == 'true'
    allow_real_trading = str(os.getenv('ALLOW_REAL_TRADING', 'false')).strip().lower() == 'true'
    use_testnet = str(os.getenv('USE_TESTNET', 'false')).strip().lower() == 'true'

    print_detail("ALLOW_ORDER_EXECUTION", str(allow_order_exec), allow_order_exec)
    print_detail("ALLOW_REAL_TRADING", str(allow_real_trading), allow_real_trading)
    print_detail("USE_TESTNET", str(use_testnet), not use_testnet)

    if not allow_order_exec:
        print_warning("Execução de ordens está DESABILITADA")

    if not allow_real_trading:
        print_warning("Trading real está DESABILITADO")

    if use_testnet:
        print_warning("Sistema em modo TESTNET (não afeta contas reais)")

    # Executa testes
    results = []

    try:
        if args.bybit or (not args.bybit and not args.binance):
            time.sleep(1)
            result = test_bybit_api(full_test=args.full)
            results.append(('Bybit', result))

        if args.binance or (not args.bybit and not args.binance):
            time.sleep(1)
            result = test_binance_api(full_test=args.full)
            results.append(('Binance', result))

    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Testes interrompidos pelo usuário.{Colors.RESET}")
        return 130
    except Exception as e:
        print_error(f"Erro inesperado: {e}")
        return 1

    # Resumo final
    print_header("📊 RESUMO FINAL DOS TESTES", Colors.MAGENTA)

    all_passed = True
    for exchange, passed in results:
        if passed:
            print_success(f"{exchange}: PASSOU ✓")
        else:
            print_error(f"{exchange}: FALHOU ✗")
            all_passed = False

    print()

    if all_passed:
        print(f"{Colors.GREEN}{Colors.BOLD}")
        print("╔═══════════════════════════════════════════════════════════════════════════════╗")
        print("║                                                                               ║")
        print("║                     🎉 SISTEMA PRONTO PARA OPERAR! 🎉                        ║")
        print("║                                                                               ║")
        print("║              O motor está ligado e o tanque está cheio!                      ║")
        print("║                                                                               ║")
        print("╚═══════════════════════════════════════════════════════════════════════════════╝")
        print(f"{Colors.RESET}\n")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}")
        print("╔═══════════════════════════════════════════════════════════════════════════════╗")
        print("║                                                                               ║")
        print("║                    ⚠️  PROBLEMAS DETECTADOS  ⚠️                              ║")
        print("║                                                                               ║")
        print("║           Corrija os erros acima antes de iniciar o robô                     ║")
        print("║                                                                               ║")
        print("╚═══════════════════════════════════════════════════════════════════════════════╝")
        print(f"{Colors.RESET}\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
