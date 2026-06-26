from dotenv import load_dotenv
load_dotenv()
from pybit.unified_trading import HTTP
from src.config import get_bybit_base_url, get_bybit_credentials, resolve_use_testnet

print("Testando conexao Bybit do WSL...")
use_testnet = resolve_use_testnet()
api_key, api_secret = get_bybit_credentials()
s = HTTP(
    testnet=use_testnet,
    api_key=api_key,
    api_secret=api_secret,
    recv_window=20000
)
r = None
s.endpoint = get_bybit_base_url(use_testnet)
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
