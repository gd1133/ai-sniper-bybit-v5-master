from dotenv import load_dotenv
load_dotenv()
import os
from pybit.unified_trading import HTTP

print("Testando conexao Bybit do WSL...")
s = HTTP(
    testnet=False,
    api_key=os.getenv("BYBIT_API_KEY"),
    api_secret=os.getenv("BYBIT_API_SECRET"),
    recv_window=20000
)
r = s.get_wallet_balance(accountType="UNIFIED", coin="USDT")
code = r.get("retCode")
msg = r.get("retMsg")
print(f"retCode: {code} | retMsg: {msg}")
if code == 0:
    lista = r.get("result", {}).get("list", [])
    saldo = lista[0].get("totalWalletBalance", "?") if lista else "?"
    print(f"Saldo USDT: {saldo}")
    print("SUCESSO - IP do WSL NAO esta bloqueado pela Bybit!")
else:
    print("FALHOU - Verificar chave ou regiao")
