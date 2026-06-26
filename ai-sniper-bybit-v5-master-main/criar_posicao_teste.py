#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Script para criar posição de teste compatível com a imagem"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

def criar_posicao_teste():
    """Cria posição aberta com lucro simulado"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        cur = conn.cursor()
        
        # Limpa posições abertas anteriores
        cur.execute("DELETE FROM trades WHERE status='open'")
        
        # Cria nova posição aberta (MOVR/USDT:USDT)
        cur.execute("""
            INSERT INTO trades 
            (client_id, pair, side, pnl_pct, profit, closed_at, notes, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            1,                                    # client_id
            "MOVR/USDT:USDT",                    # pair (exatamente como na imagem)
            "VENDER",                             # side
            52.24,                                # pnl_pct (lucro %)
            326.122,                              # profit (lucro em $)
            datetime.now().strftime("%d/%m %H:%M"),
            "POSIÇÃO ATIVA: MOVR VENDER @ 2.382 | P&L: +52.24%",
            "open",                               # status OPEN
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        print("="*60)
        print("✅ POSIÇÃO DE TESTE CRIADA COM SUCESSO!")
        print("="*60)
        print("\n📊 Dados da posição:")
        print("  Moeda: MOVR/USDT:USDT")
        print("  Lado: VENDER")
        print("  Lucro: +52.24%")
        print("  Profit: $326.122")
        print("  Status: OPEN (ativo)")
        print("\n💡 O dashboard mostrará:")
        print("  - Moeda: MOVR/USDT")
        print("  - Lucro: +52.24%")
        print("  - Saldo: $1026.122 (700 + 326.122)")
        print("  - Trades Ativos: 1/3")
        
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    criar_posicao_teste()
