#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verificador de Configuração Railway
Valida se todas as variáveis de ambiente necessárias estão configuradas corretamente.
"""
import os
import sys
from dotenv import load_dotenv

# Carrega variáveis do .env se existir
load_dotenv()

def check_env(var_name, required=True, description=""):
    """Verifica se uma variável de ambiente está configurada."""
    value = os.getenv(var_name, "").strip()
    has_value = len(value) > 0

    status = "✅" if has_value else ("❌" if required else "⚠️")
    requirement = "OBRIGATÓRIA" if required else "OPCIONAL"

    print(f"{status} {var_name:<30} [{requirement:<12}] {description}")

    # Mostra valor (ocultado se for chave/secret)
    if has_value and not any(x in var_name.lower() for x in ['key', 'secret', 'token', 'password']):
        print(f"   └─ Valor: {value}")
    elif has_value:
        print(f"   └─ Valor: {'*' * min(len(value), 20)} (oculto)")

    return has_value

def validate_url(url, var_name):
    """Valida formato de URL."""
    if not url:
        return False

    issues = []

    # Verifica protocolo
    if not url.startswith('https://') and not url.startswith('http://'):
        issues.append("   └─ ⚠️  URL deve começar com https:// ou http://")

    # Verifica se não tem barra no final
    if url.endswith('/'):
        issues.append("   └─ ⚠️  URL não deve terminar com /")

    # Verifica se parece uma URL real
    if 'localhost' not in url and '://' in url:
        domain_part = url.split('://')[1] if '://' in url else url
        if '.' not in domain_part:
            issues.append("   └─ ⚠️  URL parece estar incompleta (falta domínio)")

    for issue in issues:
        print(issue)

    return len(issues) == 0

print("=" * 80)
print("🔍 VERIFICADOR DE CONFIGURAÇÃO RAILWAY - Motor Sniper v60.7")
print("=" * 80)
print()

# === SEÇÃO 1: CONEXÃO FRONTEND (CRÍTICO) ===
print("📡 CONEXÃO FRONTEND -> BACKEND (CRÍTICO)")
print("-" * 80)
vite_api_base = os.getenv('VITE_API_BASE', '').strip()
has_api_base = check_env('VITE_API_BASE', required=True, description="URL da API para frontend")
if has_api_base:
    validate_url(vite_api_base, 'VITE_API_BASE')
print()

# === SEÇÃO 2: AMBIENTE ===
print("🌍 CONFIGURAÇÃO DE AMBIENTE")
print("-" * 80)
check_env('ENVIRONMENT', required=True, description="production/development")
check_env('ALLOW_ORDER_EXECUTION', required=True, description="Habilita execução de ordens")
check_env('ALLOW_REAL_TRADING', required=True, description="Habilita trading real")
print()

# === SEÇÃO 3: BANCO DE DADOS ===
print("💾 BANCO DE DADOS")
print("-" * 80)
check_env('SQLITE_DB_PATH', required=True, description="Caminho do banco SQLite")
db_path = os.getenv('SQLITE_DB_PATH', '/app/data/database.db')
if '/app/data' in db_path:
    print("   └─ ✅ Caminho recomendado para Railway (/app/data)")
    print("   └─ ⚠️  IMPORTANTE: Verifique se o volume está montado em /app/data")
print()

# === SEÇÃO 4: CREDENCIAIS DE EXCHANGE ===
print("💱 CREDENCIAIS DE EXCHANGE")
print("-" * 80)
has_bybit = check_env('BYBIT_API_KEY', required=False, description="Chave API Bybit")
has_bybit_secret = check_env('BYBIT_API_SECRET', required=False, description="Secret API Bybit")

has_binance = check_env('BINANCE_API_KEY', required=False, description="Chave API Binance")
has_binance_secret = check_env('BINANCE_API_SECRET', required=False, description="Secret API Binance")

if not (has_bybit and has_bybit_secret) and not (has_binance and has_binance_secret):
    print("   └─ ❌ Configure pelo menos Bybit OU Binance (ambas chave + secret)")
elif has_bybit and has_bybit_secret:
    print("   └─ ✅ Bybit configurado")
elif has_binance and has_binance_secret:
    print("   └─ ✅ Binance configurado")
print()

# === SEÇÃO 5: INTELIGÊNCIA ARTIFICIAL ===
print("🤖 INTELIGÊNCIA ARTIFICIAL")
print("-" * 80)
has_gemini = check_env('GEMINI_API_KEY', required=True, description="Chave API Gemini (Google)")
has_groq = check_env('GROQ_API_KEY', required=True, description="Chave API Groq")
print()

# === SEÇÃO 6: NOTIFICAÇÕES (OPCIONAL) ===
print("📱 NOTIFICAÇÕES TELEGRAM (Opcional)")
print("-" * 80)
check_env('TELEGRAM_TOKEN', required=False, description="Token do bot Telegram")
check_env('TELEGRAM_CHAT_ID', required=False, description="ID do chat Telegram")
print()

# === SEÇÃO 7: AUTENTICAÇÃO 2FA (OPCIONAL) ===
print("🔐 AUTENTICAÇÃO 2FA (Opcional - deixe vazio no Railway)")
print("-" * 80)
check_env('TOTP_SECRET', required=False, description="Secret para 2FA")
check_env('TOTP_CODE', required=False, description="Código 2FA atual")
print()

# === RESUMO ===
print("=" * 80)
print("📊 RESUMO DA VALIDAÇÃO")
print("=" * 80)

errors = []
warnings = []

# Verifica críticos
if not vite_api_base:
    errors.append("❌ VITE_API_BASE não configurado - frontend não conseguirá conectar ao backend")
elif not vite_api_base.startswith('http'):
    errors.append("❌ VITE_API_BASE deve começar com https:// ou http://")

if os.getenv('ENVIRONMENT', '').lower() != 'production':
    warnings.append("⚠️  ENVIRONMENT não está como 'production'")

if os.getenv('ALLOW_ORDER_EXECUTION', '').lower() != 'true':
    warnings.append("⚠️  ALLOW_ORDER_EXECUTION não está como 'true'")

if os.getenv('ALLOW_REAL_TRADING', '').lower() != 'true':
    warnings.append("⚠️  ALLOW_REAL_TRADING não está como 'true'")

if not (has_bybit and has_bybit_secret) and not (has_binance and has_binance_secret):
    errors.append("❌ Nenhuma exchange configurada (precisa de Bybit OU Binance)")

if not has_gemini:
    errors.append("❌ GEMINI_API_KEY não configurado - IA não funcionará")

if not has_groq:
    errors.append("❌ GROQ_API_KEY não configurado - IA não funcionará")

# Mostra erros
if errors:
    print("\n❌ ERROS CRÍTICOS (devem ser corrigidos):")
    for error in errors:
        print(f"   {error}")
else:
    print("\n✅ Nenhum erro crítico encontrado!")

# Mostra avisos
if warnings:
    print("\n⚠️  AVISOS:")
    for warning in warnings:
        print(f"   {warning}")

# Verifica volume
print()
print("📦 VERIFICAÇÃO DE VOLUME (Railway)")
print("-" * 80)
print("⚠️  IMPORTANTE: Este script NÃO pode verificar se o volume está montado no Railway.")
print("    Você deve configurar manualmente no painel do Railway:")
print("    1. Vá no seu serviço > Volumes")
print("    2. Adicione volume: Mount Path = /app/data, Size = 1GB")
print("    3. Reinicie o serviço")
print()

# Status final
print("=" * 80)
if not errors:
    print("✅ CONFIGURAÇÃO VÁLIDA!")
    print()
    print("Próximos passos:")
    print("1. Se estiver no Railway, certifique-se de:")
    print("   - Configurar todas as variáveis no painel do Railway")
    print("   - Adicionar volume em /app/data")
    print("   - Reiniciar o serviço")
    print("2. Abra o dashboard e tente salvar um cliente")
    print("3. Verifique os logs no console (F12) e no Railway")
    sys.exit(0)
else:
    print("❌ CONFIGURAÇÃO INCOMPLETA")
    print()
    print("Corrija os erros acima antes de fazer deploy no Railway.")
    print("Consulte docs/GUIA_RAPIDO_RAILWAY.md para instruções detalhadas.")
    sys.exit(1)
