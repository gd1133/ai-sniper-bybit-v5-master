#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
🔍 DIAGNÓSTICO: Teste de Configuração USE_TESTNET

Este script testa se as alterações corrigem o problema de:
- Robot operando em modo REAL quando USE_TESTNET=true deveria ser TESTNET
- Ordens aparecendo em contas reais da Bybit quando deveriam estar no testnet

Uso:
  python test_testnet_config.py
"""

import os
import sys

def test_env_config_parsing():
    """Testa se a configuração de ambiente está sendo lida corretamente"""
    print("\n" + "="*80)
    print("🧪 TESTE 1: Parsing de Configuração de Ambiente")
    print("="*80)
    
    # Test 1: USE_TESTNET=true should set use_testnet=True
    os.environ['USE_TESTNET'] = 'true'
    os.environ['ENVIRONMENT'] = 'production'
    
    try:
        from src.config.environment import is_truthy, get_environment_config
        
        result_true = is_truthy('true')
        print(f"\n✅ is_truthy('true') = {result_true}")
        assert result_true == True, "is_truthy('true') deve retornar True"
        
        result_false = is_truthy('false')
        print(f"✅ is_truthy('false') = {result_false}")
        assert result_false == False, "is_truthy('false') deve retornar False"
        
        print("\n📋 Testando get_environment_config() com USE_TESTNET=true:")
        config = get_environment_config()
        print(f"   - environment: {config.name}")
        print(f"   - use_testnet: {config.use_testnet}")
        print(f"   - allow_real_trading: {config.allow_real_trading}")
        print(f"   - allow_order_execution: {config.allow_order_execution}")
        
        if config.use_testnet:
            print(f"\n✅ CORRETO: USE_TESTNET=true foi interpretado corretamente como use_testnet=True")
        else:
            print(f"\n❌ ERRO: USE_TESTNET=true não foi interpretado corretamente!")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao testar: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def test_main_web_constants():
    """Testa se main_web.py está usando a configuração corretamente"""
    print("\n" + "="*80)
    print("🧪 TESTE 2: Constantes em main_web.py")
    print("="*80)
    
    os.environ['USE_TESTNET'] = 'true'
    os.environ['ENVIRONMENT'] = 'development'
    
    try:
        # Re-import to get fresh values
        if 'main_web' in sys.modules:
            del sys.modules['main_web']
        if 'src.config' in sys.modules:
            del sys.modules['src.config']
        if 'src.config.environment' in sys.modules:
            del sys.modules['src.config.environment']
        
        from src.config import get_environment_config
        env_config = get_environment_config()
        
        print(f"\n📋 Valores esperados:")
        print(f"   - ENV_CONFIG.use_testnet: {env_config.use_testnet}")
        print(f"   - Esperado: True (porque USE_TESTNET=true)")
        
        if env_config.use_testnet:
            print(f"\n✅ CORRETO: Configuração detectada corretamente")
            return True
        else:
            print(f"\n❌ ERRO: Configuração não foi detectada corretamente")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao testar: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*15 + "🔧 DIAGNÓSTICO: Configuração USE_TESTNET".ljust(78) + "║")
    print("║" + " "*15 + "Versão: 1.0 - Pós-correção da branch testnet".ljust(78) + "║")
    print("╚" + "="*78 + "╝")
    
    results = []
    
    # Run tests
    results.append(("Environment Config Parsing", test_env_config_parsing()))
    results.append(("Main Web Constants", test_main_web_constants()))
    
    # Summary
    print("\n" + "="*80)
    print("📊 RESUMO DOS TESTES")
    print("="*80)
    
    all_passed = True
    for test_name, result in results:
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"{status}: {test_name}")
        if not result:
            all_passed = False
    
    print("="*80)
    
    if all_passed:
        print("\n✅ TODOS OS TESTES PASSARAM!")
        print("\n🎯 PRÓXIMOS PASSOS:")
        print("   1. Configurar USE_TESTNET=true em Render para usar TESTNET")
        print("   2. Configurar USE_TESTNET=false em Render para usar contas REAIS")
        print("   3. Restart o app após alterar a configuração")
        print("   4. Verificar logs para confirmar que está usando testnet/real correto")
        print()
        return 0
    else:
        print("\n❌ ALGUNS TESTES FALHARAM!")
        print("\n⚠️  AVISO: Os problemas devem ser corrigidos antes de usar o robot")
        print()
        return 1


if __name__ == '__main__':
    sys.exit(main())
