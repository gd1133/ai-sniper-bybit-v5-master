#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Limpeza de estrutura de pasta - Remove documentação e scripts de teste
Mantém apenas os arquivos essenciais para operação
"""
import os
import shutil

# Diretório raiz
ROOT = '.'

# Arquivos/pastas para REMOVER (documentação e testes)
CLEANUP = [
    # Documentação (não necessária em produção)
    'AGRESSIVO_CHANGELOG.md',
    'ANTI_FREEZE_FIXES.md',
    'CHECKLIST_FINAL.md',
    'CONFORMIDADE_v60.1.md',
    'DIAGRAMA_VISUAL.md',
    'DUO-IA_MASTER_v4.9_DOCUMENTATION.md',
    'EXEMPLOS_COPY_PASTE.md',
    'FINAL_STATUS_REPORT.md',
    'IMPLEMENTACAO_PNL_COMPLETA.md',
    'IMPLEMENTATION_SUMMARY.md',
    'INICIO_RAPIDO.md',
    'OPTIMIZATION_SUMMARY.md',
    'PNL_TRACKING_GUIDE.md',
    'QUICK_START.md',
    'RATE_LIMIT_OPTIMIZATION.md',
    'RATE_LIMITING_FIX.md',
    'README_IMPLEMENTACAO.md',
    'RELATÓRIO_IMPLEMENTAÇÃO.md',
    'RESUMO_FINAL_v60.1.md',
    'SALDO_TESTE_IMPLEMENTATION.md',
    'SALDO_TESTE_PRONTO.md',
    'SISTEMA_COMPLETO_RESUMO.md',
    'STARTUP_FIX_REPORT.md',
    'SUMARIO_EXECUTIVO.md',
    'TEST_MODE_GUIDE.md',
    'TEST_MODE_RUNNING.md',
    
    # Scripts de teste (não necessários em produção)
    'activate_test_mode.py',
    'check_test_config.py',
    'debug_startup.py',
    'GUIA_RAPIDO.py',
    'inspect_validator.py',
    'inspect_validator2.py',
    'patch_validator.py',
    'profile_imports.py',
    'run_system.py',
    'setup_test_balance.py',
    'test_confidence.py',
    'test_conf_long.py',
    'test_import_simple.py',
    'teste_ia_rapido.py',
    'validate_conformance.py',
    
    # Arquivos temporários
    'backend.log',
    'test_panel.html',
    'diagnostico_bd.py',
    'monitor_trades_continuo.py',
]

print("\n" + "="*60)
print("🧹 LIMPEZA DE ESTRUTURA DE PASTAS")
print("="*60 + "\n")

removed = 0
for item in CLEANUP:
    path = os.path.join(ROOT, item)
    if os.path.exists(path):
        try:
            if os.path.isfile(path):
                os.remove(path)
            else:
                shutil.rmtree(path)
            print(f"✅ Removido: {item}")
            removed += 1
        except Exception as e:
            print(f"⚠️  Erro ao remover {item}: {e}")
    else:
        print(f"⏭️  Não encontrado: {item}")

print("\n" + "="*60)
print(f"✅ Limpeza concluída! {removed} arquivos/pastas removidos")
print("="*60 + "\n")

# Listar estrutura final
print("\n📁 ESTRUTURA FINAL RECOMENDADA:\n")
print("""
trading-bot-ia/
├── 📄 index.html                   (Frontend template)
├── 📄 main.jsx                     (Dashboard React)
├── 📄 main_web.py                  (Backend Flask)
├── 📄 package.json                 (Dependências NPM)
├── 📄 requirements.txt             (Dependências Python)
├── 📄 .env                         (Variáveis de ambiente)
├── 📄 database.db                  (SQLite - Clientes + Trades)
│
├── 📁 src/                         (Código-fonte)
│   ├── __init__.py
│   ├── 📁 ai_brain/               (Cérebro IA)
│   │   ├── learning.py
│   │   └── validator.py
│   ├── 📁 broker/                 (Integração Bybit)
│   │   └── bybit_client.py
│   ├── 📁 database/               (Gerenciador BD)
│   │   └── manager.py
│   └── 📁 engine/                 (Indicadores)
│       └── indicators.py
│
├── 📁 tools/                       (Utilitários)
│   └── post_broadcast.py
│
├── 📁 data/                        (Dados locais)
│   ├── intelligence_memory.json
│   └── learning_db.json
│
└── 📁 node_modules/               (Dependências NPM)
""")

print("\n✅ Estrutura otimizada para produção!")
