#!/usr/bin/env python3
"""
🔍 DIAGNÓSTICO DE MODO DE OPERAÇÃO
===================================
Valida se o sistema está configurado para operar em modo REAL ou TESTNET.

PROBLEMA COMUM:
- Ordens aparecem no bot mas não nas exchanges
- Sistema mostra "REAL" mas envia para testnet
- Credenciais corretas mas ordens não executam

CAUSAS:
1. Variáveis de ambiente não configuradas corretamente
2. ALLOW_REAL_TRADING=false (bloqueia execução real)
3. USE_TESTNET=true (força modo testnet)

USO:
    python diagnostico_modo_real.py

SOLUÇÃO:
    Configure as variáveis no arquivo .env ou Railway:
    ALLOW_ORDER_EXECUTION=true
    ALLOW_REAL_TRADING=true
    USE_TESTNET=false  # IMPORTANTE: false para contas reais!
"""

import os
import sys


def _strict_env_bool(name, default):
    """Converte flags do Railway estritamente: apenas 'true' ativa."""
    return str(os.getenv(name, default) or default).strip().lower() == 'true'


def check_environment_variables():
    """Valida as variáveis de ambiente críticas para execução real."""
    print("=" * 70)
    print("🔍 DIAGNÓSTICO DE CONFIGURAÇÃO - MODO DE OPERAÇÃO")
    print("=" * 70)
    print()

    # Variáveis críticas
    allow_order_execution = _strict_env_bool('ALLOW_ORDER_EXECUTION', 'false')
    allow_real_trading = _strict_env_bool('ALLOW_REAL_TRADING', 'false')
    use_testnet = _strict_env_bool('USE_TESTNET', 'true')
    environment = os.getenv('ENVIRONMENT', 'development')

    print("📋 VARIÁVEIS DE AMBIENTE DETECTADAS:")
    print(f"   ENVIRONMENT = {environment}")
    print(f"   ALLOW_ORDER_EXECUTION = {os.getenv('ALLOW_ORDER_EXECUTION', '(não definido - padrão: false)')}")
    print(f"   ALLOW_REAL_TRADING = {os.getenv('ALLOW_REAL_TRADING', '(não definido - padrão: false)')}")
    print(f"   USE_TESTNET = {os.getenv('USE_TESTNET', '(não definido - padrão: true)')}")
    print()

    print("🔧 VALORES INTERPRETADOS PELO SISTEMA:")
    print(f"   ALLOW_ORDER_EXECUTION = {allow_order_execution}")
    print(f"   ALLOW_REAL_TRADING = {allow_real_trading}")
    print(f"   USE_TESTNET = {use_testnet}")
    print()

    # Credenciais
    has_bybit_key = bool(os.getenv('BYBIT_API_KEY'))
    has_bybit_secret = bool(os.getenv('BYBIT_API_SECRET'))
    has_binance_key = bool(os.getenv('BINANCE_API_KEY'))
    has_binance_secret = bool(os.getenv('BINANCE_API_SECRET'))

    print("🔑 CREDENCIAIS CONFIGURADAS:")
    print(f"   BYBIT_API_KEY: {'✅ Configurada' if has_bybit_key else '❌ Ausente'}")
    print(f"   BYBIT_API_SECRET: {'✅ Configurada' if has_bybit_secret else '❌ Ausente'}")
    print(f"   BINANCE_API_KEY: {'✅ Configurada' if has_binance_key else '❌ Ausente'}")
    print(f"   BINANCE_API_SECRET: {'✅ Configurada' if has_binance_secret else '❌ Ausente'}")
    print()

    # Análise de problemas
    print("=" * 70)
    print("🎯 ANÁLISE DE CONFIGURAÇÃO")
    print("=" * 70)
    print()

    problems = []
    warnings = []
    ok_checks = []

    # Check 1: ALLOW_ORDER_EXECUTION
    if not allow_order_execution:
        problems.append("❌ CRÍTICO: ALLOW_ORDER_EXECUTION=false - Ordens bloqueadas!")
        problems.append("   💡 SOLUÇÃO: Configure ALLOW_ORDER_EXECUTION=true")
    else:
        ok_checks.append("✅ ALLOW_ORDER_EXECUTION=true - Execução de ordens habilitada")

    # Check 2: ALLOW_REAL_TRADING
    if not allow_real_trading:
        problems.append("❌ CRÍTICO: ALLOW_REAL_TRADING=false - Trading real bloqueado!")
        problems.append("   💡 SOLUÇÃO: Configure ALLOW_REAL_TRADING=true")
    else:
        ok_checks.append("✅ ALLOW_REAL_TRADING=true - Trading real habilitado")

    # Check 3: USE_TESTNET
    if use_testnet:
        problems.append("⚠️  ATENÇÃO: USE_TESTNET=true - Sistema em modo TESTNET!")
        problems.append("   💡 SOLUÇÃO: Configure USE_TESTNET=false para usar contas reais")
        problems.append("   📝 NOTA: Ordens vão para contas de teste, não contas reais!")
    else:
        ok_checks.append("✅ USE_TESTNET=false - Modo de produção (contas reais)")

    # Check 4: Credenciais
    if not has_bybit_key or not has_bybit_secret:
        warnings.append("⚠️  BYBIT: Credenciais não configuradas (API Key/Secret)")
    else:
        ok_checks.append("✅ BYBIT: Credenciais configuradas")

    if not has_binance_key or not has_binance_secret:
        warnings.append("⚠️  BINANCE: Credenciais não configuradas (API Key/Secret)")
    else:
        ok_checks.append("✅ BINANCE: Credenciais configuradas")

    # Check 5: Combinação perigosa
    if allow_real_trading and use_testnet:
        warnings.append("⚠️  CONFIGURAÇÃO CONFLITANTE: ALLOW_REAL_TRADING=true mas USE_TESTNET=true")
        warnings.append("   Sistema vai tentar executar em testnet mesmo com permissão de trading real")

    # Exibe resultados
    if ok_checks:
        for check in ok_checks:
            print(check)
        print()

    if warnings:
        for warning in warnings:
            print(warning)
        print()

    if problems:
        for problem in problems:
            print(problem)
        print()

    # Diagnóstico final
    print("=" * 70)
    print("🎭 DIAGNÓSTICO FINAL")
    print("=" * 70)
    print()

    if not allow_order_execution:
        print("❌ SISTEMA EM MODO SEGURO - Ordens NÃO serão executadas")
        print("   O bot vai simular ordens mas não vai enviar para exchanges")
        print()
    elif not allow_real_trading:
        print("❌ TRADING REAL BLOQUEADO - Ordens NÃO serão executadas")
        print("   O sistema está bloqueado para prevenir execução acidental")
        print()
    elif use_testnet:
        print("⚠️  SISTEMA EM MODO TESTNET")
        print("   ✅ Ordens SERÃO executadas")
        print("   ⚠️  Mas APENAS em contas de teste (testnet)")
        print("   📝 Ordens NÃO aparecerão nas suas contas reais!")
        print()
        print("   🔧 Para usar contas REAIS, configure:")
        print("      USE_TESTNET=false")
        print()
    else:
        print("✅ SISTEMA CONFIGURADO PARA MODO REAL")
        print("   ✅ Execução de ordens: HABILITADA")
        print("   ✅ Trading real: HABILITADO")
        print("   ✅ Modo testnet: DESABILITADO")
        print("   🚀 Ordens serão executadas nas exchanges REAIS!")
        print()

    # Instruções de correção
    if problems:
        print("=" * 70)
        print("🔧 COMO CORRIGIR")
        print("=" * 70)
        print()
        print("1️⃣  Se usando Railway:")
        print("   • Acesse: Dashboard → Variables")
        print("   • Adicione/edite as variáveis:")
        print("     ALLOW_ORDER_EXECUTION=true")
        print("     ALLOW_REAL_TRADING=true")
        print("     USE_TESTNET=false")
        print("   • Salve e faça redeploy")
        print()
        print("2️⃣  Se usando arquivo .env local:")
        print("   • Edite o arquivo .env")
        print("   • Adicione as linhas:")
        print("     ALLOW_ORDER_EXECUTION=true")
        print("     ALLOW_REAL_TRADING=true")
        print("     USE_TESTNET=false")
        print("   • Reinicie o sistema")
        print()
        print("3️⃣  Se usando Docker/container:")
        print("   • Passe as variáveis via -e:")
        print("     docker run -e ALLOW_ORDER_EXECUTION=true \\")
        print("                -e ALLOW_REAL_TRADING=true \\")
        print("                -e USE_TESTNET=false \\")
        print("                ...")
        print()

    # Código de saída
    if problems:
        print("❌ Configuração INCORRETA - Sistema não vai operar em modo real")
        return 1
    elif warnings:
        print("⚠️  Configuração com avisos - Revise antes de operar")
        return 0
    else:
        print("✅ Configuração CORRETA - Sistema pronto para operar em modo real")
        return 0


if __name__ == '__main__':
    exit_code = check_environment_variables()
    sys.exit(exit_code)
