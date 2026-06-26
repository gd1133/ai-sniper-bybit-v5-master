import requests

payload = {'symbol':'BTC/USDT','side':'COMPRAR','price':30000,'res_ia':{'probabilidade':75,'motivo':'Teste via API'}}
resp = requests.post('http://127.0.0.1:5000/api/test_broadcast', json=payload, timeout=10)
print(resp.status_code)
print(resp.text)
