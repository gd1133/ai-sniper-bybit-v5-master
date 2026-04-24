#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SINAL SNIPER BROADCAST - Envia sinal de operação ao backend
"""
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

# Dados do sinal que o usuário forneceu
sinal = {
    "symbol": "BTC/USDT:USDT",
    "side": "VENDER",
    "entry_price": 74486.1,
    "confidence": 70,
    "reason": "Confluência 70% detectada - Gemini: 70 | Groq: 70 | Local: 70"
}

print("\n" + "="*70)
print("🚀 ENVIANDO SINAL SNIPER BROADCAST")
print("="*70)
print(f"\n📦 Ativo: {sinal['symbol']}")
print(f"📈 Lado: {sinal['side']}")
print(f"🎯 Entrada: ${sinal['entry_price']:.2f}")
print(f"🧠 Confiança: {sinal['confidence']}%")
print(f"📝 Razão: {sinal['reason']}\n")

try:
    response = requests.post(
        f"{BASE_URL}/api/sniper/broadcast",
        json=sinal,
        timeout=10
    )
    
    print(f"Status: {response.status_code}")
    result = response.json()
    print(f"\n✅ Resposta do Backend:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    print("\n" + "="*70)
    print("✅ SINAL EXECUTADO COM SUCESSO!")
    print("="*70)
    print("\n📊 Verifique o dashboard em http://localhost:5173")
    print("   - Moeda deve aparecer: BTC/USDT")
    print("   - Confiança: 70%")
    print("   - Saldo deve estar atualizado")
    print()
    
except Exception as e:
    print(f"❌ Erro ao enviar sinal: {e}")
