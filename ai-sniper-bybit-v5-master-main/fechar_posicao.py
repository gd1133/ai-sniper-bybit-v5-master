#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script para fechar posição aberta e testar lógica de símbolo"""

import sqlite3
import os
import json
from src.database import manager as db

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

def fechar_posicoes_abertas():
    """Fecha todas as posições abertas para teste"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Busca posições abertas
        cur.execute("SELECT * FROM trades WHERE status='open'")
        trades_abertos = cur.fetchall()
        
        if not trades_abertos:
            print("❌ Nenhuma posição aberta")
            conn.close()
            return
        
        print(f"📊 Encontradas {len(trades_abertos)} posições abertas")
        
        for trade in trades_abertos:
            trade_id = trade['id']
            pair = trade['pair']
            profit = trade['profit']
            
            # Atualiza para fechado com profit simples
            cur.execute(
                "UPDATE trades SET status='closed', profit=?, pnl_pct=? WHERE id=?",
                (100.0, 5.0, trade_id)
            )
            print(f"✅ Fechada posição #{trade_id}: {pair} → +$100 USDT")
        
        conn.commit()
        conn.close()
        
        print("\n" + "="*60)
        print("✅ TODAS AS POSIÇÕES FECHADAS COM SUCESSO!")
        print("="*60)
        print("\n🔄 Dashboard agora mostrará:")
        print("  - symbol: '---' (sem posição aberta)")
        print("  - confidence: 0 (sem análise)")
        print("  - balance: ATUALIZADO com novo P&L")
        
    except Exception as e:
        print(f"❌ Erro ao fechar posições: {e}")

if __name__ == "__main__":
    print("="*60)
    print("🔄 FECHANDO POSIÇÕES ABERTAS")
    print("="*60)
    fechar_posicoes_abertas()
