#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DIAGNÓSTICO COMPLETO: Por que as ordens não aparecem na Bybit/Binance?

Este script verifica TODOS os pontos críticos do fluxo de execução:
1. Variáveis de ambiente (ALLOW_ORDER_EXECUTION, ALLOW_REAL_TRADING, USE_TESTNET)
2. Modo de operação do sistema
3. Configuração de credenciais
4. Endpoints usados (testnet vs produção)
5. Fluxo de execução completo

Uso: python diagnostico_execucao_ordens.py
"""

import os
import sys
from dotenv import load_dotenv

# Cores para output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(text):
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}{text.center(80)}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")

def print_success(text):
    print(f"{GREEN}✅ {text}{RESET}")

def print_error(text):
    print(f"{RED}❌ {text}{RESET}")

def print_warning(text):
    print(f"{YELLOW}⚠️  {text}{RESET}")

def print_info(text):
    print(f"ℹ️  {text}")

def _strict_env_bool(name, default):
    """Mesma lógica usada no main_web.py"""
    return str(os.getenv(name, default) or default).strip().lower() == 'true'

def main():
    print_header("DIAGNÓSTICO COMPLETO DE EXECUÇÃO DE ORDENS")

    # Carrega variáveis de ambiente
    load_dotenv()

    problems = []
    warnings = []
    ok_checks = []

    # ==============================================
    # 1. VERIFICAÇÃO DE VARIÁVEIS DE AMBIENTE
    # ==============================================
    print_header("1. VARIÁVEIS DE AMBIENTE CRÍTICAS")

    allow_order_execution = _strict_env_bool('ALLOW_ORDER_EXECUTION', 'false')
    allow_real_trading = _strict_env_bool('ALLOW_REAL_TRADING', 'false')
    use_testnet = _strict_env_bool('USE_TESTNET', 'false')

    print_info("Valores RAW (arquivo .env):")
    print(f"   ALLOW_ORDER_EXECUTION = {os.getenv('ALLOW_ORDER_EXECUTION', '(não definido - padrão: false)')}")
    print(f"   ALLOW_REAL_TRADING = {os.getenv('ALLOW_REAL_TRADING', '(não definido - padrão: false)')}")
    print(f"   USE_TESTNET = {os.getenv('USE_TESTNET', '(não definido - padrão: false)')}")

    print_info("\nValores INTERPRETADOS (após conversão booleana):")
    print(f"   ALLOW_ORDER_EXECUTION = {allow_order_execution}")
    print(f"   ALLOW_REAL_TRADING = {allow_real_trading}")
    print(f"   USE_TESTNET = {use_testnet}")

    # Check 1: ALLOW_ORDER_EXECUTION
    if not allow_order_execution:
        problems.append("❌ CRÍTICO: ALLOW_ORDER_EXECUTION=false - Ordens bloqueadas!")
        problems.append("   💡 SOLUÇÃO: Configure ALLOW_ORDER_EXECUTION=true no Railway")
    else:
        ok_checks.append("✅ ALLOW_ORDER_EXECUTION=true - Execução de ordens habilitada")

    # Check 2: ALLOW_REAL_TRADING
    if not allow_real_trading:
        problems.append("❌ CRÍTICO: ALLOW_REAL_TRADING=false - Trading real bloqueado!")
        problems.append("   💡 SOLUÇÃO: Configure ALLOW_REAL_TRADING=true no Railway")
    else:
        ok_checks.append("✅ ALLOW_REAL_TRADING=true - Trading real habilitado")

    # Check 3: USE_TESTNET
    if use_testnet:
        warnings.append("⚠️  ATENÇÃO: USE_TESTNET=true - Sistema em modo TESTNET!")
        warnings.append("   💡 As ordens VÃO PARA CONTAS DE TESTE, não para contas reais!")
        warnings.append("   💡 SOLUÇÃO: Configure USE_TESTNET=false para usar contas reais")
        warnings.append("")
        warnings.append("   🔍 ENDPOINTS USADOS:")
        warnings.append("      Bybit: https://api-testnet.bybit.com (TESTNET)")
        warnings.append("      Binance: https://testnet.binancefuture.com (TESTNET)")
    else:
        ok_checks.append("✅ USE_TESTNET=false - Modo de produção (contas reais)")
        ok_checks.append("   🔍 ENDPOINTS USADOS:")
        ok_checks.append("      Bybit: https://api.bybit.com (PRODUÇÃO)")
        ok_checks.append("      Binance: https://fapi.binance.com (PRODUÇÃO)")

    # ==============================================
    # 2. VERIFICAÇÃO DE CREDENCIAIS
    # ==============================================
    print_header("2. CREDENCIAIS DAS EXCHANGES")

    bybit_api_key = os.getenv('BYBIT_API_KEY', '').strip()
    bybit_api_secret = os.getenv('BYBIT_API_SECRET', '').strip()

    if bybit_api_key and bybit_api_key != 'YOUR_BYBIT_API_KEY':
        print_success(f"Bybit API Key configurada: {bybit_api_key[:8]}...")
    else:
        print_error("Bybit API Key NÃO configurada ou usando valor de exemplo")
        problems.append("❌ Credenciais Bybit inválidas ou não configuradas")

    if bybit_api_secret and bybit_api_secret != 'YOUR_BYBIT_API_SECRET':
        print_success(f"Bybit API Secret configurada: {bybit_api_secret[:8]}...")
    else:
        print_error("Bybit API Secret NÃO configurada ou usando valor de exemplo")
        problems.append("❌ Credenciais Bybit inválidas ou não configuradas")

    # ==============================================
    # 3. VERIFICAÇÃO DE CONFLITOS
    # ==============================================
    print_header("3. VERIFICAÇÃO DE CONFLITOS DE CONFIGURAÇÃO")

    # Conflito: ALLOW_REAL_TRADING=true mas USE_TESTNET=true
    if allow_real_trading and use_testnet:
        warnings.append("⚠️  CONFIGURAÇÃO CONFLITANTE: ALLOW_REAL_TRADING=true mas USE_TESTNET=true")
        warnings.append("   💡 As ordens serão enviadas para TESTNET, não para contas reais!")
        warnings.append("   💡 Você quer operar com dinheiro real? Configure USE_TESTNET=false")

    # ==============================================
    # 4. RESUMO E DIAGNÓSTICO
    # ==============================================
    print_header("4. RESUMO DO DIAGNÓSTICO")

    if ok_checks:
        print(f"{GREEN}✅ CONFIGURAÇÕES CORRETAS:{RESET}")
        for check in ok_checks:
            print(f"   {check}")

    if warnings:
        print(f"\n{YELLOW}⚠️  AVISOS:{RESET}")
        for warning in warnings:
            print(f"   {warning}")

    if problems:
        print(f"\n{RED}❌ PROBLEMAS ENCONTRADOS:{RESET}")
        for problem in problems:
            print(f"   {problem}")

    # ==============================================
    # 5. DIAGNÓSTICO FINAL E CAUSA RAIZ
    # ==============================================
    print_header("5. DIAGNÓSTICO FINAL - POR QUE AS ORDENS NÃO APARECEM?")

    if not allow_order_execution or not allow_real_trading:
        print_error("CAUSA RAIZ IDENTIFICADA:")
        print("   As ordens NÃO estão sendo enviadas para a exchange!")
        print("   O sistema está BLOQUEANDO a execução devido às flags de segurança.")
        print("")
        print("   O que está acontecendo:")
        print("   1. O robô processa os sinais normalmente ✅")
        print("   2. Envia notificação para o Telegram ✅")
        print("   3. Mostra a ordem na interface web ✅")
        print(f"   4. Bloqueia a execução real na exchange ❌")
        print("")
        print(f"{RED}   SOLUÇÃO IMEDIATA:{RESET}")
        print(f"   Configure no Railway:")
        print(f"      ALLOW_ORDER_EXECUTION=true")
        print(f"      ALLOW_REAL_TRADING=true")
        if use_testnet:
            print(f"      USE_TESTNET=false")

    elif use_testnet:
        print_warning("CAUSA RAIZ IDENTIFICADA:")
        print("   As ordens ESTÃO sendo enviadas, mas para contas de TESTE!")
        print("   O sistema está em modo TESTNET.")
        print("")
        print("   O que está acontecendo:")
        print("   1. O robô processa os sinais normalmente ✅")
        print("   2. Envia a ordem para a exchange ✅")
        print("   3. A ordem vai para: https://api-testnet.bybit.com ⚠️")
        print("   4. A ordem NÃO aparece na conta real porque foi para TESTNET ⚠️")
        print("")
        print(f"{YELLOW}   SOLUÇÃO IMEDIATA:{RESET}")
        print(f"   Configure no Railway:")
        print(f"      USE_TESTNET=false")
        print("")
        print("   Depois de mudar para false, as ordens irão para:")
        print("   - Bybit: https://api.bybit.com (PRODUÇÃO)")
        print("   - Binance: https://fapi.binance.com (PRODUÇÃO)")

    else:
        print_success("CONFIGURAÇÃO ESTÁ CORRETA!")
        print("   Todas as flags estão configuradas para execução real.")
        print("")
        print("   Se as ordens ainda não aparecem, verifique:")
        print("   1. As credenciais API estão corretas?")
        print("   2. As API Keys têm permissão de 'Trade Orders'?")
        print("   3. Há saldo suficiente na conta?")
        print("   4. O IP do servidor está na whitelist? (Bybit exige)")
        print("")
        print("   Para verificar IP do servidor:")
        print("      curl https://seu-dominio.railway.app/api/server-ip")

    # ==============================================
    # 6. INSTRUÇÕES PASSO A PASSO
    # ==============================================
    print_header("6. INSTRUÇÕES PASSO A PASSO PARA CORRIGIR")

    print("1. Acesse o Railway: https://railway.app")
    print("2. Selecione seu projeto")
    print("3. Vá em 'Variables'")
    print("4. Configure:")
    if not allow_order_execution:
        print(f"   {YELLOW}ALLOW_ORDER_EXECUTION=true{RESET}")
    if not allow_real_trading:
        print(f"   {YELLOW}ALLOW_REAL_TRADING=true{RESET}")
    if use_testnet:
        print(f"   {YELLOW}USE_TESTNET=false{RESET}")
    print("5. Clique em 'Deploy' ou espere o redeploy automático")
    print("6. Verifique os logs após o deploy")
    print("")
    print("Você deve ver no log:")
    print(f"   {GREEN}✅ AMBIENTE CONFIGURADO PARA EXECUÇÃO REAL{RESET}")
    print(f"   {GREEN}✅ ALLOW_ORDER_EXECUTION=true{RESET}")
    print(f"   {GREEN}✅ ALLOW_REAL_TRADING=true{RESET}")
    print(f"   {GREEN}✅ USE_TESTNET=false{RESET}")

    # ==============================================
    # 7. CÓDIGO DE SAÍDA
    # ==============================================
    print("")
    if problems:
        print(f"{RED}❌ DIAGNÓSTICO CONCLUÍDO COM PROBLEMAS{RESET}")
        return 1
    elif warnings:
        print(f"{YELLOW}⚠️  DIAGNÓSTICO CONCLUÍDO COM AVISOS{RESET}")
        return 0
    else:
        print(f"{GREEN}✅ DIAGNÓSTICO CONCLUÍDO - CONFIGURAÇÃO OK{RESET}")
        return 0

if __name__ == '__main__':
    sys.exit(main())
