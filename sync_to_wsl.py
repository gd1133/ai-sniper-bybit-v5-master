import shutil
src = '/mnt/c/Users/Oem/Desktop/trading-bot-ia/main_web.py'
dst = '/home/dine/ai-sniper-bybit-v5-master/main_web.py'
shutil.copy2(src, dst)
with open(dst) as f:
    content = f.read()
count = content.count('_monitor_sl_tp_automatico')
print(f'Copiado OK. Ocorrencias _monitor_sl_tp: {count}')
