#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validador de configuração de ambiente para Motor Sniper v60.7
Verifica se todas as variáveis de ambiente necessárias estão configuradas corretamente.
"""
import os
import sys

# Tenta carregar .env se dotenv estiver disponível
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv não instalado, continua sem ele

# Cores para output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_status(emoji, color, message):
    """Imprime mensagem colorida"""
    print(f"{emoji} {color}{message}{RESET}")

def validate_environment():
    """Valida configuração do ambiente"""
    print("\n" + "="*70)
    print("🔍 VALIDADOR DE AMBIENTE - Motor Sniper v60.7")
    print("="*70 + "\n")

    issues = []
    warnings = []
    success = []

    # 1. Verificar ENVIRONMENT
    environment = os.getenv('ENVIRONMENT', '').strip().lower()
    if not environment:
        environment = 'development'
        warnings.append("ENVIRONMENT não definido, usando 'development' como padrão")
    elif environment not in ['development', 'production']:
        issues.append(f"ENVIRONMENT='{environment}' inválido. Use 'development' ou 'production'")
    else:
        success.append(f"ENVIRONMENT={environment}")

    # 2. Verificar credenciais Bybit
    bybit_key = os.getenv('BYBIT_API_KEY', '').strip()
    bybit_secret = os.getenv('BYBIT_API_SECRET', '').strip()

    if not bybit_key:
        issues.append("BYBIT_API_KEY não configurada (OBRIGATÓRIA)")
    elif len(bybit_key) < 10:
        issues.append("BYBIT_API_KEY parece inválida (muito curta)")
    else:
        success.append(f"BYBIT_API_KEY configurada ({len(bybit_key)} chars)")

    if not bybit_secret:
        issues.append("BYBIT_API_SECRET não configurada (OBRIGATÓRIA)")
    elif len(bybit_secret) < 10:
        issues.append("BYBIT_API_SECRET parece inválida (muito curta)")
    else:
        success.append(f"BYBIT_API_SECRET configurada ({len(bybit_secret)} chars)")

    # 3. Verificar chaves de IA
    gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
    groq_key = os.getenv('GROQ_API_KEY', '').strip()

    if not gemini_key:
        warnings.append("GEMINI_API_KEY não configurada (validação de IA limitada)")
    else:
        success.append(f"GEMINI_API_KEY configurada ({len(gemini_key)} chars)")

    if not groq_key:
        warnings.append("GROQ_API_KEY não configurada (validação de IA limitada)")
    else:
        success.append(f"GROQ_API_KEY configurada ({len(groq_key)} chars)")

    # 4. Verificar Telegram
    telegram_token = os.getenv('TELEGRAM_TOKEN', '').strip()
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '').strip()

    if not telegram_token:
        warnings.append("TELEGRAM_TOKEN não configurada (notificações desabilitadas)")
    else:
        success.append(f"TELEGRAM_TOKEN configurada ({len(telegram_token)} chars)")

    if not telegram_chat_id:
        warnings.append("TELEGRAM_CHAT_ID não configurada (notificações desabilitadas)")
    else:
        success.append(f"TELEGRAM_CHAT_ID configurada")

    # 5. Verificar VITE_API_BASE
    vite_api_base = os.getenv('VITE_API_BASE', '').strip()

    if not vite_api_base:
        warnings.append("VITE_API_BASE não configurada (frontend usará window.location.origin)")
    elif vite_api_base == 'http://localhost:5000':
        warnings.append("VITE_API_BASE está apontando para localhost (OK para desenvolvimento)")
        success.append(f"VITE_API_BASE={vite_api_base}")
    elif not vite_api_base.startswith('http://') and not vite_api_base.startswith('https://'):
        issues.append(f"VITE_API_BASE='{vite_api_base}' FALTA o protocolo (https://)")
        issues.append("  → Corrija para: https://" + vite_api_base)
    elif vite_api_base.startswith('http://') and environment == 'production':
        warnings.append(f"VITE_API_BASE usa HTTP em produção (recomendado: HTTPS)")
        success.append(f"VITE_API_BASE={vite_api_base}")
    else:
        success.append(f"VITE_API_BASE={vite_api_base}")

    # 6. Verificar flags de controle
    use_testnet = os.getenv('USE_TESTNET', '').strip().lower()
    allow_real = os.getenv('ALLOW_REAL_TRADING', '').strip().lower()
    allow_exec = os.getenv('ALLOW_ORDER_EXECUTION', '').strip().lower()

    if use_testnet:
        success.append(f"USE_TESTNET={use_testnet} (sobrescreve padrão)")

    if allow_real:
        success.append(f"ALLOW_REAL_TRADING={allow_real} (sobrescreve padrão)")

    if allow_exec:
        success.append(f"ALLOW_ORDER_EXECUTION={allow_exec} (sobrescreve padrão)")

    # 7. Verificar DATABASE_URL vs SQLITE_DB_PATH
    database_url = os.getenv('DATABASE_URL', '').strip()
    sqlite_db_path = os.getenv('SQLITE_DB_PATH', '').strip()

    if database_url and not sqlite_db_path:
        issues.append("DATABASE_URL configurada, mas o sistema usa SQLITE_DB_PATH")
        issues.append("  → Remova DATABASE_URL e adicione SQLITE_DB_PATH (ou deixe vazio para usar padrão)")
    elif sqlite_db_path:
        success.append(f"SQLITE_DB_PATH={sqlite_db_path}")
    else:
        warnings.append("SQLITE_DB_PATH não configurada (usará padrão: /app/data/database.db)")

    # 8. Verificar Binance (opcional)
    binance_key = os.getenv('BINANCE_API_KEY', '').strip()
    binance_secret = os.getenv('BINANCE_API_SECRET', '').strip()

    if binance_key or binance_secret:
        if binance_key and binance_secret:
            success.append(f"BINANCE_API_KEY e SECRET configuradas (conta mestra Binance)")
        else:
            issues.append("BINANCE_API_KEY ou SECRET está incompleta")

    # 9. Determinar configuração efetiva
    print(f"{BLUE}📊 CONFIGURAÇÃO EFETIVA:{RESET}\n")

    is_production = environment == 'production'
    effective_testnet = use_testnet in ['1', 'true', 'yes', 'on'] if use_testnet else (not is_production)
    effective_real_trading = allow_real in ['1', 'true', 'yes', 'on'] if allow_real else is_production
    effective_execution = allow_exec in ['1', 'true', 'yes', 'on'] if allow_exec else is_production

    print(f"  Ambiente: {YELLOW}{environment.upper()}{RESET}")
    print(f"  Usar Testnet: {YELLOW}{effective_testnet}{RESET}")
    print(f"  Trading Real Permitido: {YELLOW}{effective_real_trading}{RESET}")
    print(f"  Execução de Ordens Permitida: {YELLOW}{effective_execution}{RESET}")
    print()

    # Avisos de segurança
    if is_production and effective_testnet:
        warnings.append("PRODUCTION com USE_TESTNET=true (trading apenas em testnet)")

    if is_production and not effective_real_trading:
        warnings.append("PRODUCTION com ALLOW_REAL_TRADING=false (trading bloqueado)")

    if is_production and not effective_execution:
        warnings.append("PRODUCTION com ALLOW_ORDER_EXECUTION=false (ordens bloqueadas)")

    # Imprimir resultados
    if success:
        print(f"{GREEN}✅ CONFIGURAÇÕES OK ({len(success)}):{RESET}\n")
        for item in success:
            print(f"  ✓ {item}")
        print()

    if warnings:
        print(f"{YELLOW}⚠️  AVISOS ({len(warnings)}):{RESET}\n")
        for warning in warnings:
            print(f"  ⚠  {warning}")
        print()

    if issues:
        print(f"{RED}❌ PROBLEMAS CRÍTICOS ({len(issues)}):{RESET}\n")
        for issue in issues:
            print(f"  ✗ {issue}")
        print()

    # Resumo final
    print("="*70)
    if issues:
        print_status("❌", RED, f"VALIDAÇÃO FALHOU - {len(issues)} problema(s) crítico(s)")
        print(f"\n{RED}Corrija os problemas acima antes de fazer deploy!{RESET}")
        print(f"{BLUE}Veja docs/RAILWAY_SETUP.md para instruções detalhadas.{RESET}\n")
        return False
    elif warnings:
        print_status("⚠️ ", YELLOW, f"VALIDAÇÃO OK COM AVISOS - {len(warnings)} aviso(s)")
        print(f"\n{YELLOW}Sistema funcionará, mas pode ter funcionalidades limitadas.{RESET}")
        print(f"{BLUE}Veja docs/RAILWAY_SETUP.md para otimizar sua configuração.{RESET}\n")
        return True
    else:
        print_status("✅", GREEN, "VALIDAÇÃO COMPLETA - Configuração perfeita!")
        print(f"\n{GREEN}Sistema pronto para deploy no Railway! 🚀{RESET}\n")
        return True

if __name__ == '__main__':
    try:
        result = validate_environment()
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n{RED}❌ ERRO ao validar ambiente: {e}{RESET}\n")
        sys.exit(1)
