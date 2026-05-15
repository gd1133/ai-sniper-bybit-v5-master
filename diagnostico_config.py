#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Diagnóstico - Validação de Configuração de Ambiente
Verifica se o sistema está configurado corretamente para execução de ordens.
"""

import os
import sys

# Tenta importar dotenv, mas continua sem ele se não estiver disponível
try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False
    print("⚠️  python-dotenv não instalado, lendo apenas variáveis de ambiente do sistema")

# Cores para terminal
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def print_header(text):
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}{text:^60}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")

def print_success(text):
    print(f"{GREEN}✅ {text}{RESET}")

def print_error(text):
    print(f"{RED}❌ {text}{RESET}")

def print_warning(text):
    print(f"{YELLOW}⚠️  {text}{RESET}")

def print_info(text):
    print(f"{BLUE}ℹ️  {text}{RESET}")

def check_env_file():
    """Verifica se o arquivo .env existe."""
    if not os.path.exists('.env'):
        print_error("Arquivo .env não encontrado!")
        print_info("Crie um arquivo .env baseado no .env.example")
        return False
    print_success("Arquivo .env encontrado")
    return True

def validate_environment():
    """Valida todas as configurações de ambiente."""

    print_header("DIAGNÓSTICO DE CONFIGURAÇÃO - AI SNIPER")

    # Carrega variáveis de ambiente se dotenv disponível
    if HAS_DOTENV:
        load_dotenv()
    else:
        print_warning("Lendo apenas variáveis de ambiente do sistema (dotenv não disponível)")

    issues = []
    warnings = []

    # 1. Verifica ENVIRONMENT
    print_info("Verificando configuração de ambiente...")
    environment = os.getenv('ENVIRONMENT', 'development').strip().lower()

    if environment == 'production':
        print_success(f"ENVIRONMENT={environment}")
    else:
        print_warning(f"ENVIRONMENT={environment} (ordens podem estar bloqueadas)")
        warnings.append("ENVIRONMENT não está em 'production'")

    # 2. Verifica ALLOW_ORDER_EXECUTION
    print_info("Verificando permissão de execução de ordens...")
    allow_exec = os.getenv('ALLOW_ORDER_EXECUTION', 'false').strip().lower()

    if allow_exec in ['true', '1', 'yes', 'on']:
        print_success(f"ALLOW_ORDER_EXECUTION={allow_exec}")
    else:
        print_error(f"ALLOW_ORDER_EXECUTION={allow_exec} - ORDENS BLOQUEADAS!")
        issues.append("ALLOW_ORDER_EXECUTION está desabilitado")

    # 3. Verifica ALLOW_REAL_TRADING
    print_info("Verificando permissão de trading real...")
    allow_real = os.getenv('ALLOW_REAL_TRADING', 'false').strip().lower()

    if allow_real in ['true', '1', 'yes', 'on']:
        print_success(f"ALLOW_REAL_TRADING={allow_real}")
    else:
        print_error(f"ALLOW_REAL_TRADING={allow_real} - TRADING REAL BLOQUEADO!")
        issues.append("ALLOW_REAL_TRADING está desabilitado")

    # 4. Verifica credenciais Bybit
    print_info("Verificando credenciais Bybit...")
    bybit_key = os.getenv('BYBIT_API_KEY', '').strip()
    bybit_secret = os.getenv('BYBIT_API_SECRET', '').strip()

    if bybit_key and bybit_secret:
        if bybit_key.startswith('YOUR_') or bybit_secret.startswith('YOUR_'):
            print_error("Credenciais Bybit não configuradas (ainda com valores de exemplo)")
            issues.append("Credenciais Bybit não configuradas")
        else:
            print_success(f"BYBIT_API_KEY configurada (length: {len(bybit_key)})")
            print_success(f"BYBIT_API_SECRET configurada (length: {len(bybit_secret)})")
    else:
        print_warning("Credenciais Bybit não encontradas (modo público)")
        warnings.append("Sem credenciais Bybit (só funciona modo público)")

    # 5. Verifica outras configurações importantes
    print_info("Verificando configurações adicionais...")

    telegram_token = os.getenv('TELEGRAM_TOKEN', '').strip()
    telegram_chat = os.getenv('TELEGRAM_CHAT_ID', '').strip()

    if telegram_token and telegram_chat:
        print_success("Telegram configurado")
    else:
        print_warning("Telegram não configurado (notificações desabilitadas)")
        warnings.append("Telegram não configurado")

    gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
    groq_key = os.getenv('GROQ_API_KEY', '').strip()

    if gemini_key or groq_key:
        print_success(f"IA configurada (Gemini: {'✅' if gemini_key else '❌'} | Groq: {'✅' if groq_key else '❌'})")
    else:
        print_warning("Chaves de IA não configuradas")
        warnings.append("Chaves de IA ausentes")

    # Resumo Final
    print_header("RESUMO DO DIAGNÓSTICO")

    if not issues and not warnings:
        print_success("SISTEMA CONFIGURADO CORRETAMENTE! ✨")
        print_info("Todas as verificações passaram.")
        print_info("Ordens SERÃO executadas quando sinais forem gerados.")
        return 0

    if issues:
        print_error(f"\n❌ {len(issues)} PROBLEMA(S) CRÍTICO(S) ENCONTRADO(S):")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")

        print(f"\n{BOLD}AÇÃO NECESSÁRIA:{RESET}")
        print("Edite o arquivo .env e configure:")
        if "ALLOW_ORDER_EXECUTION" in str(issues):
            print(f"   {YELLOW}ALLOW_ORDER_EXECUTION=true{RESET}")
        if "ALLOW_REAL_TRADING" in str(issues):
            print(f"   {YELLOW}ALLOW_REAL_TRADING=true{RESET}")
        if "ENVIRONMENT" in str(issues) or "ENVIRONMENT" in str(warnings):
            print(f"   {YELLOW}ENVIRONMENT=production{RESET}")
        if "Credenciais Bybit" in str(issues):
            print(f"   {YELLOW}BYBIT_API_KEY=sua_chave_aqui{RESET}")
            print(f"   {YELLOW}BYBIT_API_SECRET=seu_secret_aqui{RESET}")

    if warnings:
        print_warning(f"\n⚠️  {len(warnings)} AVISO(S):")
        for i, warning in enumerate(warnings, 1):
            print(f"   {i}. {warning}")

    print(f"\n{BLUE}📖 Para mais detalhes, consulte:{RESET}")
    print(f"   - RELATORIO_DIAGNOSTICO_API.md")
    print(f"   - .env.example\n")

    return 1 if issues else 0

def main():
    """Função principal."""
    try:
        if not check_env_file():
            print_info("\nCriando arquivo .env de exemplo...")
            with open('.env.example', 'r') as f:
                example_content = f.read()
            with open('.env', 'w') as f:
                f.write(example_content)
            print_success("Arquivo .env criado! Edite-o com suas credenciais.")
            return 1

        exit_code = validate_environment()

        if exit_code == 0:
            print(f"\n{GREEN}{BOLD}🎯 Sistema pronto para operar!{RESET}\n")
        else:
            print(f"\n{RED}{BOLD}🔧 Configure o sistema antes de iniciar.{RESET}\n")

        return exit_code

    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Diagnóstico interrompido pelo usuário.{RESET}")
        return 130
    except Exception as e:
        print_error(f"Erro durante diagnóstico: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
