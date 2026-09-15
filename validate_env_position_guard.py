#!/usr/bin/env python3
"""
Script de Validação de Variáveis de Ambiente
AI Sniper V5 - PositionGuard + Trade Learning

Uso:
    python3 validate_env_position_guard.py
    python3 validate_env_position_guard.py --verbose
"""

import os
import sys
from typing import Dict, List, Tuple

# ==================== CORES PARA TERMINAL ====================
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

# ==================== CONFIGURAÇÕES ESPERADAS ====================
REQUIRED_ENV_VARS = {
    # PositionGuard - Escada de Lucro
    "POSITION_GUARD_LEVEL1_TRIGGER_PCT": {
        "default": "1.8",
        "description": "ROI% para ativar Nível 1 (saída parcial)",
        "category": "PositionGuard"
    },
    "POSITION_GUARD_LEVEL1_PARTIAL_FRACTION": {
        "default": "0.40",
        "description": "Fração da posição a sair no Nível 1 (40%)",
        "category": "PositionGuard"
    },
    "POSITION_GUARD_LEVEL2_TRIGGER_PCT": {
        "default": "3.5",
        "description": "ROI% para ativar Nível 2 (trailing stop)",
        "category": "PositionGuard"
    },
    "POSITION_GUARD_TRAIL_ATR_MULT": {
        "default": "1.5",
        "description": "Multiplicador do ATR para trailing stop",
        "category": "PositionGuard"
    },
    "POSITION_GUARD_FEE_BUFFER_PCT": {
        "default": "0.12",
        "description": "Buffer de taxa para evitar saídas prematuras",
        "category": "PositionGuard"
    },
    
    # Trade Learning - Aprendizado Local
    "TRADE_LEARNING_MIN_SAMPLE": {
        "default": "8",
        "description": "Mínimo de trades históricos para aplicar learning",
        "category": "Trade Learning"
    },
    "TRADE_LEARNING_LOW_WIN_MODE": {
        "default": "reduce",
        "description": "Modo para baixa win-rate: 'reduce' ou 'discard'",
        "category": "Trade Learning"
    }
}

# ==================== FUNÇÕES DE VALIDAÇÃO ====================

def check_env_var(var_name: str, config: Dict) -> Tuple[bool, str, str]:
    """
    Verifica se uma variável de ambiente está configurada.
    
    Returns:
        (is_set, current_value, expected_default)
    """
    current_value = os.getenv(var_name)
    expected_default = config["default"]
    
    if current_value is not None:
        return (True, current_value, expected_default)
    else:
        return (False, None, expected_default)

def validate_all_env_vars(verbose: bool = False) -> Tuple[List[str], List[str]]:
    """
    Valida todas as variáveis de ambiente necessárias.
    
    Returns:
        (list_of_ok_vars, list_of_missing_vars)
    """
    ok_vars = []
    missing_vars = []
    
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}🔍 VALIDAÇÃO DE VARIÁVEIS DE AMBIENTE{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")
    
    # Agrupar por categoria
    categories = {}
    for var_name, config in REQUIRED_ENV_VARS.items():
        category = config["category"]
        if category not in categories:
            categories[category] = []
        categories[category].append((var_name, config))
    
    # Validar por categoria
    for category, vars_list in categories.items():
        print(f"{Colors.BOLD}{Colors.BLUE}📦 {category}{Colors.END}")
        print(f"{'-'*70}")
        
        for var_name, config in vars_list:
            is_set, current_value, expected_default = check_env_var(var_name, config)
            
            if is_set:
                ok_vars.append(var_name)
                status = f"{Colors.GREEN}✅ OK{Colors.END}"
                
                if verbose:
                    print(f"{status} {Colors.BOLD}{var_name}{Colors.END}")
                    print(f"   └─ Valor: {Colors.GREEN}{current_value}{Colors.END}")
                    print(f"   └─ Padrão: {expected_default}")
                    print(f"   └─ Descrição: {config['description']}")
                else:
                    value_display = current_value if len(current_value) <= 20 else current_value[:17] + "..."
                    print(f"{status} {Colors.BOLD}{var_name}{Colors.END} = {Colors.GREEN}{value_display}{Colors.END}")
            else:
                missing_vars.append(var_name)
                status = f"{Colors.RED}❌ FALTANDO{Colors.END}"
                
                if verbose:
                    print(f"{status} {Colors.BOLD}{var_name}{Colors.END}")
                    print(f"   └─ Valor esperado: {Colors.YELLOW}{expected_default}{Colors.END}")
                    print(f"   └─ Descrição: {config['description']}")
                else:
                    print(f"{status} {Colors.BOLD}{var_name}{Colors.END} (esperado: {Colors.YELLOW}{expected_default}{Colors.END})")
        
        print()
    
    return (ok_vars, missing_vars)

def print_summary(ok_vars: List[str], missing_vars: List[str]):
    """Imprime o resumo final da validação."""
    total = len(REQUIRED_ENV_VARS)
    ok_count = len(ok_vars)
    missing_count = len(missing_vars)
    
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}📊 RESUMO DA VALIDAÇÃO{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")
    
    print(f"Total de variáveis esperadas: {Colors.BOLD}{total}{Colors.END}")
    print(f"Configuradas corretamente: {Colors.GREEN}{Colors.BOLD}{ok_count}{Colors.END}")
    print(f"Faltando: {Colors.RED}{Colors.BOLD}{missing_count}{Colors.END}\n")
    
    if missing_count == 0:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ SUCESSO! Todas as variáveis estão configuradas.{Colors.END}\n")
        print(f"{Colors.GREEN}✅ PositionGuard está pronto para uso.{Colors.END}")
        print(f"{Colors.GREEN}✅ Trade Learning está pronto para uso.{Colors.END}\n")
        return True
    else:
        print(f"{Colors.RED}{Colors.BOLD}⚠️  ATENÇÃO! Variáveis faltando:{Colors.END}\n")
        for var_name in missing_vars:
            config = REQUIRED_ENV_VARS[var_name]
            print(f"{Colors.YELLOW}  • {var_name}{Colors.END} = {config['default']}")
        print(f"\n{Colors.YELLOW}📝 Adicione as variáveis faltando no painel Environment do Render.{Colors.END}\n")
        return False

def print_render_instructions(missing_vars: List[str]):
    """Imprime instruções específicas para o Render.com."""
    if not missing_vars:
        return
    
    print(f"{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}📋 INSTRUÇÕES PARA RENDER.COM{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")
    
    print(f"1. Acesse o painel do seu serviço no Render.com")
    print(f"2. Navegue até a aba {Colors.BOLD}'Environment'{Colors.END}")
    print(f"3. Clique em {Colors.BOLD}'+ Add variable'{Colors.END}")
    print(f"4. Adicione cada variável abaixo:\n")
    
    for var_name in missing_vars:
        config = REQUIRED_ENV_VARS[var_name]
        print(f"{Colors.YELLOW}Variável:{Colors.END} {Colors.BOLD}{var_name}{Colors.END}")
        print(f"{Colors.YELLOW}Valor:{Colors.END} {config['default']}")
        print(f"{Colors.YELLOW}Descrição:{Colors.END} {config['description']}\n")
    
    print(f"5. Clique em {Colors.BOLD}'Save Changes'{Colors.END}")
    print(f"6. Aguarde o deploy automático concluir (~3-5min)")
    print(f"7. Execute este script novamente para validar\n")

def check_database_table():
    """Verifica se a tabela trade_learning existe no banco."""
    try:
        import sqlite3
        
        # Tentar paths comuns
        db_paths = [
            "/opt/render/project/src/data/database.db",
            "/home/ubuntu/ai_sniper_v5/data/database.db",
            "./data/database.db",
            "../data/database.db"
        ]
        
        db_path = None
        for path in db_paths:
            if os.path.exists(path):
                db_path = path
                break
        
        if not db_path:
            print(f"{Colors.YELLOW}⚠️  Banco de dados não encontrado (será criado no primeiro uso){Colors.END}\n")
            return
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar se a tabela trade_learning existe
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='trade_learning'
        """)
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            print(f"{Colors.GREEN}✅ Tabela 'trade_learning' encontrada no banco de dados{Colors.END}\n")
        else:
            print(f"{Colors.YELLOW}⚠️  Tabela 'trade_learning' ainda não criada (será criada no primeiro trade){Colors.END}\n")
    
    except Exception as e:
        print(f"{Colors.YELLOW}⚠️  Não foi possível verificar o banco: {e}{Colors.END}\n")

# ==================== MAIN ====================

def main():
    """Função principal."""
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    
    # Validar variáveis de ambiente
    ok_vars, missing_vars = validate_all_env_vars(verbose=verbose)
    
    # Imprimir resumo
    success = print_summary(ok_vars, missing_vars)
    
    # Se houver variáveis faltando, mostrar instruções
    if not success:
        print_render_instructions(missing_vars)
    else:
        # Verificar banco de dados (bonus)
        check_database_table()
    
    # Exit code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
