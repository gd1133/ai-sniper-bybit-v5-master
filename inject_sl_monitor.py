"""Insere a funcao _monitor_sl_tp_automatico no main_web.py e adiciona a thread."""
import re

FILE = r"C:\Users\Oem\Desktop\trading-bot-ia\main_web.py"

with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

# Verifica se ja existe
if "_monitor_sl_tp_automatico" in content:
    print("FUNCAO JA EXISTE - nada a fazer")
    exit(0)

MONITOR_FUNC = '''

def _monitor_sl_tp_automatico():
    """
    Monitora trades abertos e fecha automaticamente quando atingem:
    - Stop Loss: -3% (perda maxima institucional)
    - Take Profit: +6% (lucro alvo)
    Executa em background a cada 10 segundos.
    """
    SL_PCT = -3.0
    TP_PCT = 6.0

    while True:
        try:
            trades_abertos = list(central_state.get("active_trades", []))
            for trade in trades_abertos:
                trade_id = trade.get("id")
                symbol = trade.get("raw_symbol") or trade.get("symbol")
                entry_price = trade.get("entry_price", 0)
                side = trade.get("side", "buy")

                if not trade_id or not entry_price or entry_price == 0:
                    continue

                live = _get_live_price_snapshot(symbol, entry_price, side)
                pnl_pct = live.get("pnl_pct", 0.0)

                motivo = None
                if pnl_pct <= SL_PCT:
                    motivo = f"SL_AUTO -3% (real: {pnl_pct:.2f}%)"
                elif pnl_pct >= TP_PCT:
                    motivo = f"TP_AUTO +6% (real: {pnl_pct:.2f}%)"

                if motivo:
                    try:
                        conn = db._connect()
                        cur = conn.cursor()
                        cur.execute(
                            "UPDATE trades SET status=\\'closed\\', pnl_pct=?, notes=COALESCE(notes,\\'\\') || ? WHERE id=?",
                            (round(pnl_pct, 4), f" | {motivo}", trade_id)
                        )
                        conn.commit()
                        conn.close()
                        print(f"[SL/TP AUTO] trade_id={trade_id} {symbol} fechado: {motivo}")

                        tg_token = os.getenv("TELEGRAM_TOKEN")
                        tg_chat = os.getenv("TELEGRAM_CHAT_ID")
                        if tg_token and tg_chat:
                            emoji = "✅" if pnl_pct >= TP_PCT else "❌"
                            msg = (f"{emoji} *FECHAMENTO AUTOMATICO*\\n"
                                   f"Ativo: {symbol}\\n"
                                   f"PnL: {pnl_pct:.2f}%\\n"
                                   f"Motivo: {motivo}")
                            try:
                                requests.post(
                                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                                    json={"chat_id": tg_chat, "text": msg, "parse_mode": "Markdown"},
                                    timeout=5
                                )
                            except Exception:
                                pass

                        _sync_active_trades_from_db()
                    except Exception as close_err:
                        print(f"[SL/TP AUTO] Falha ao fechar trade {trade_id}: {close_err}")

        except Exception as e:
            print(f"[_monitor_sl_tp_automatico] erro: {e}")

        time.sleep(10)

'''

# Insere antes de _sync_active_trades_from_db
marker = "\ndef _sync_active_trades_from_db():"
if marker not in content:
    print(f"ERRO: marcador nao encontrado: {repr(marker[:50])}")
    exit(1)

content = content.replace(marker, MONITOR_FUNC + "\ndef _sync_active_trades_from_db():", 1)

# Adiciona a thread no bloco if __name__ == "__main__"
THREAD_MARKER = "    threading.Thread(target=sniper_worker_loop, daemon=True).start()"
THREAD_INSERT = (
    "\n\n    # Monitor SL/TP automatico (-3% stop loss / +6% take profit)\n"
    "    threading.Thread(target=_monitor_sl_tp_automatico, daemon=True).start()\n"
    '    print("   Monitor SL/TP: ATIVO (-3% SL / +6% TP)")'
)

if THREAD_MARKER in content:
    content = content.replace(
        THREAD_MARKER,
        THREAD_MARKER + THREAD_INSERT,
        1
    )
    print("Thread adicionada ao __main__")
else:
    print("AVISO: marcador da thread nao encontrado")

with open(FILE, "w", encoding="utf-8") as f:
    f.write(content)

# Verifica resultado
count = content.count("_monitor_sl_tp_automatico")
print(f"OK - funcao inserida. Ocorrencias: {count}")
