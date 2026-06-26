#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Teste de Cadastro - Verifica se novo cliente é salvo corretamente com Telegram API Key
"""
import requests
import json
import sqlite3

BASE_URL = "http://127.0.0.1:5000"
DB_PATH = "database.db"

print("\n" + "="*70)
print("🧪 TESTE DE CADASTRO DE CLIENTE COM TELEGRAM API KEY")
print("="*70 + "\n")

# 1. Preparar dados do cliente
cliente_data = {
    "nome": "João Silva Teste",
    "saldo_base": 2500.0,
    "bybit_key": "test_bybit_key_123456",
    "bybit_secret": "test_bybit_secret_789abc",
    "tg_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
    "tg_api_key": "your-telegram-api-key-12345",  # ← NOVO CAMPO!
    "chat_id": "987654321",
    "is_testnet": True
}

print(f"📝 Dados do Cliente:")
for key, value in cliente_data.items():
    if "key" in key or "secret" in key or "token" in key:
        print(f"   {key}: {'*' * 10}")
    else:
        print(f"   {key}: {value}")

# 2. Enviar para backend
print(f"\n📤 Enviando para {BASE_URL}/api/vincular_cliente...")
try:
    response = requests.post(
        f"{BASE_URL}/api/vincular_cliente",
        json=cliente_data,
        timeout=10
    )
    print(f"   Status: {response.status_code}")
    print(f"   Resposta: {response.json()}")
except Exception as e:
    print(f"   ⚠️ Erro: {e}")

# 3. Verificar no banco de dados
print(f"\n🔍 Verificando banco de dados ({DB_PATH})...")
try:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Ver se cliente foi salvo
    cur.execute("SELECT * FROM clientes_sniper WHERE nome=?", ("João Silva Teste",))
    cliente = cur.fetchone()
    
    if cliente:
        print(f"   ✅ Cliente encontrado!")
        print(f"\n   📋 Dados Salvos:")
        for key in cliente.keys():
            if "key" in key or "secret" in key or "token" in key:
                print(f"      {key}: {'*' * 10}")
            else:
                print(f"      {key}: {cliente[key]}")
    else:
        print(f"   ⚠️ Cliente NÃO encontrado no banco")
    
    # Ver total de clientes
    cur.execute("SELECT COUNT(*) as cnt FROM clientes_sniper")
    total = cur.fetchone()['cnt']
    print(f"\n   Total de clientes no BD: {total}")
    
    conn.close()
except Exception as e:
    print(f"   ⚠️ Erro ao consultar BD: {e}")

print("\n" + "="*70)
print("✅ Teste concluído!")
print("="*70 + "\n")
