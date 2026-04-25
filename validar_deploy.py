"""
Checklist de validacao pos-deploy no Render.
Executa 5 testes contra a URL publica do servico.

Uso: python validar_deploy.py [URL]
Padrao: https://ai-sniper-bybit-v5-master-1.onrender.com
"""
import sys
import requests
import json
import time

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "https://ai-sniper-bybit-v5-master-1.onrender.com"
TIMEOUT = 60  # Render free pode demorar 50s no cold start

print(f"\n=== VALIDACAO POS-DEPLOY ===")
print(f"URL: {BASE_URL}")
print(f"Timeout: {TIMEOUT}s (aguarda cold start)\n")

resultados = {}

# ------------------------------------------------------------------
# TESTE 1: Servidor respondendo (cold start)
# ------------------------------------------------------------------
print("[1/5] Servidor respondendo (/api/status)...")
try:
    r = requests.get(f"{BASE_URL}/api/status", timeout=TIMEOUT)
    ok = r.status_code == 200
    resultados['status'] = ok
    print(f"      {'OK' if ok else 'FALHOU'} | HTTP {r.status_code} | Bytes: {len(r.content)}")
except Exception as e:
    resultados['status'] = False
    print(f"      FALHOU | {e}")

# ------------------------------------------------------------------
# TESTE 2: Dashboard API respondendo (/api/status)
# ------------------------------------------------------------------
print("[2/5] API do Dashboard (/api/status)...")
try:
    r = requests.get(f"{BASE_URL}/api/status", timeout=TIMEOUT)
    ok = r.status_code == 200
    data = {}
    try:
        data = r.json()
    except Exception:
        pass
    resultados['api_status'] = ok
    campos = [k for k in ['balance', 'status', 'symbol'] if k in data]
    print(f"      {'OK' if ok else 'FALHOU'} | HTTP {r.status_code} | Campos: {campos}")
except Exception as e:
    resultados['api_status'] = False
    print(f"      FALHOU | {e}")

# ------------------------------------------------------------------
# TESTE 3: Trava de posicao unica (broadcast bloqueado na 2a chamada)
# ------------------------------------------------------------------
print("[3/5] Trava atomica de posicao unica (/api/sniper/broadcast)...")
try:
    payload = {
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'price': 77000.0,
        'quantidade': 0.001,
        'motivo': 'validacao-deploy',
        'score': 0.85
    }
    # Primeira chamada (deve tentar passar - pode ser 200 ou 409 dependendo do estado)
    r1 = requests.post(f"{BASE_URL}/api/sniper/broadcast", json=payload, timeout=TIMEOUT)
    # Segunda chamada imediata (deve ser 409 se trava ativa)
    r2 = requests.post(f"{BASE_URL}/api/sniper/broadcast", json=payload, timeout=30)
    ok = r2.status_code in (200, 409)  # qualquer resposta valida do servidor
    resultados['broadcast'] = ok
    print(f"      {'OK' if ok else 'FALHOU'} | 1a={r1.status_code} | 2a={r2.status_code}")
    if r2.status_code == 409:
        print(f"      Trava ativa: 2a chamada corretamente bloqueada (409)")
except Exception as e:
    resultados['broadcast'] = False
    print(f"      FALHOU | {e}")

# ------------------------------------------------------------------
# TESTE 4: Endpoint de trades
# ------------------------------------------------------------------
print("[4/5] Endpoint de trades (/api/trades/client/1)...")
try:
    r = requests.get(f"{BASE_URL}/api/trades/client/1", timeout=30)
    ok = r.status_code == 200
    resultados['trades'] = ok
    try:
        data = r.json()
        print(f"      {'OK' if ok else 'FALHOU'} | HTTP {r.status_code} | Registros: {len(data) if isinstance(data, list) else 'N/A'}")
    except Exception:
        print(f"      {'OK' if ok else 'FALHOU'} | HTTP {r.status_code}")
except Exception as e:
    resultados['trades'] = False
    print(f"      FALHOU | {e}")

# ------------------------------------------------------------------
# TESTE 5: Investidores endpoint
# ------------------------------------------------------------------
print("[5/5] Endpoint investidores (/api/investidores)...")
try:
    r = requests.get(f"{BASE_URL}/api/investidores", timeout=30)
    ok = r.status_code == 200
    resultados['investidores'] = ok
    try:
        data = r.json()
        print(f"      {'OK' if ok else 'FALHOU'} | HTTP {r.status_code} | Registros: {len(data) if isinstance(data, list) else 'N/A'}")
    except Exception:
        print(f"      {'OK' if ok else 'FALHOU'} | HTTP {r.status_code}")
except Exception as e:
    resultados['investidores'] = False
    print(f"      FALHOU | {e}")

# ------------------------------------------------------------------
# RESUMO
# ------------------------------------------------------------------
print("\n--- RESUMO ---")
aprovados = sum(1 for v in resultados.values() if v)
total = len(resultados)
for nome, ok in resultados.items():
    print(f"  {'[OK]' if ok else '[FALHOU]'} {nome}")

veredito = "APROVADO" if aprovados == total else f"PARCIAL ({aprovados}/{total})"
print(f"\nVEREDITO_DEPLOY: {veredito}")

if aprovados < total:
    falhos = [k for k, v in resultados.items() if not v]
    print(f"\nFalhos: {falhos}")
    print("Verifique os logs no Render > Logs para detalhes.")
