import datetime
import time
import requests

API = "http://localhost:5000/api/status"
MAX_OPEN_ALERT = 5

print("MONITOR ONLINE - Ctrl+C para parar", flush=True)
last_symbol = ""
same_count = 0

while True:
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        r = requests.get(API, timeout=5)
        j = r.json() if r.ok else {}
        symbol = j.get("symbol", "---")
        conf = float(j.get("confidence", 0) or 0)
        status = j.get("status", "")
        active = j.get("active_trades", []) or []
        opp = j.get("opportunities", []) or []

        if symbol == last_symbol:
            same_count += 1
        else:
            same_count = 1
            last_symbol = symbol

        warnings = []
        if conf <= 0 and ("Radar" not in status and "MODO TESTE" not in status and "varredura" not in status.lower()):
            warnings.append("conf=0")
        if same_count >= 8 and symbol not in ["---", ""]:
            warnings.append(f"simbolo_repetido_{same_count}x")
        if len(active) >= MAX_OPEN_ALERT:
            warnings.append("max_trades_atingido")

        line = f"[{ts}] sym={symbol} conf={conf:.0f}% open={len(active)} opp={len(opp)} status={status}"
        if warnings:
            line += " | ALERTA=" + ",".join(warnings)

        print(line, flush=True)
    except Exception as e:
        print(f"[{ts}] ERRO_MONITOR: {e}", flush=True)

    time.sleep(5)
