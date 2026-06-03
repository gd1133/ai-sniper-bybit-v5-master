#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Validacao: Cruzamento de Ambientes por Cliente
Verifica se as correcoes foram aplicadas corretamente no Motor Sniper V60.7
"""

import os
import sys
import re
import io

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def validate_file_contains(filepath, pattern, description):
    """Verifica se arquivo contém um padrão de texto específico"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                print(f"[OK] {description}")
                return True
            else:
                print(f"[FAIL] {description}")
                return False
    except FileNotFoundError:
        print(f"[FAIL] Arquivo nao encontrado: {filepath}")
        return False
    except Exception as e:
        print(f"[FAIL] Erro ao validar {filepath}: {e}")
        return False

def main():
    print("=" * 70)
    print("[VALIDACAO] Correcao de Cruzamento de Ambientes")
    print("=" * 70)
    print()
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    checks = []
    
    # Check 1: BybitClient recebe client_name
    print("[CHECKLIST] Validando BybitClient...")
    checks.append(validate_file_contains(
        os.path.join(base_path, 'src/broker/bybit_client.py'),
        r'def __init__\(self,.*client_name=None\)',
        "BybitClient.__init__ aceita client_name"
    ))
    
    # Check 2: BybitClient mostra logs claros
    checks.append(validate_file_contains(
        os.path.join(base_path, 'src/broker/bybit_client.py'),
        r'ambiente_tag',
        "BybitClient mostra ambiente_tag com CONTA REAL ou SIMULACAO"
    ))
    
    # Check 3: BinanceClient recebe client_name
    print("\n[CHECKLIST] Validando BinanceClient...")
    checks.append(validate_file_contains(
        os.path.join(base_path, 'src/broker/binance_client.py'),
        r'def __init__\(self,.*client_name=None\)',
        "BinanceClient.__init__ aceita client_name"
    ))
    
    # Check 4: BinanceClient mostra logs claros
    checks.append(validate_file_contains(
        os.path.join(base_path, 'src/broker/binance_client.py'),
        r'ambiente_tag',
        "BinanceClient mostra ambiente_tag com CONTA REAL ou SIMULACAO"
    ))
    
    # Check 5: Database manager tem resolve_client_testnet_flag
    print("\n[CHECKLIST] Validando Database Manager...")
    checks.append(validate_file_contains(
        os.path.join(base_path, 'src/database/manager.py'),
        r'def resolve_client_testnet_flag',
        "Database manager tem funcao resolve_client_testnet_flag()"
    ))
    
    # Check 6: Database manager suporta 'testnet'
    checks.append(validate_file_contains(
        os.path.join(base_path, 'src/database/manager.py'),
        r"VALID_ACCOUNT_MODES\s*=\s*\{.*'testnet'",
        "VALID_ACCOUNT_MODES inclui 'testnet'"
    ))
    
    # Check 7: BrokerManager lê testnet do cliente
    print("\n[CHECKLIST] Validando BrokerManager...")
    checks.append(validate_file_contains(
        os.path.join(base_path, 'main_web.py'),
        r'resolve_client_testnet_flag\(account_mode\)',
        "BrokerManager.get_broker() chama resolve_client_testnet_flag()"
    ))
    
    # Check 8: BrokerManager passa client_name ao broker
    checks.append(validate_file_contains(
        os.path.join(base_path, 'main_web.py'),
        r'client_name=client_name',
        "BrokerManager passa client_name ao instanciar broker"
    ))
    
    # Check 9: _make_broker remove hardcoded False
    print("\n[CHECKLIST] Validando _make_broker()...")
    checks.append(validate_file_contains(
        os.path.join(base_path, 'main_web.py'),
        r'testnet_override=None',
        "_make_broker() passa testnet_override=None"
    ))
    
    print()
    print("=" * 70)
    total = len(checks)
    passed = sum(checks)
    print(f"\n[RESULTADO] {passed}/{total} validacoes passaram")
    
    if passed == total:
        print("\n[SUCESSO] Todas as correcoes foram aplicadas corretamente.")
        print("\n[PROXIMO] Etapas:")
        print("   1. Inicie o servidor: python main_web.py")
        print("   2. Verifique os logs para [CONTA REAL] ou [SIMULACAO]")
        print("   3. Cada cliente deve mostrar seu ambiente correto")
        return 0
    else:
        print(f"\n[ERRO] {total - passed} validacao(oes) falharam.")
        print("\nRevise as mudancas nos arquivos listados acima.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
