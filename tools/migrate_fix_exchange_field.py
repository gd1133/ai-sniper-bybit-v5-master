#!/usr/bin/env python3
"""
Script de migração para corrigir o campo 'exchange' em registros existentes.
Atualiza registros com exchange NULL ou vazio para 'bybit' (default).
"""
import sqlite3
import os
import sys

# Adiciona o diretório raiz ao path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database.db')


def migrate_exchange_field():
    """
    Migração para garantir que todos os registros tenham um valor válido no campo exchange.
    - Registros com exchange NULL ou vazio recebem 'bybit' como default
    - Valida que apenas 'bybit' ou 'binance' estão no banco
    """
    print("=" * 60)
    print("MIGRAÇÃO: Corrigir campo 'exchange' em registros existentes")
    print("=" * 60)
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Banco de dados não encontrado: {DB_PATH}")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # 1. Verificar se a coluna 'exchange' existe
        cur.execute("PRAGMA table_info(clientes_sniper)")
        columns = {row[1] for row in cur.fetchall()}
        
        if 'exchange' not in columns:
            print("⚠️  Coluna 'exchange' não existe. Criando...")
            cur.execute("ALTER TABLE clientes_sniper ADD COLUMN exchange TEXT DEFAULT 'bybit'")
            conn.commit()
            print("✅ Coluna 'exchange' criada com sucesso!")
        
        # 2. Contar registros com exchange NULL ou vazio
        cur.execute("""
            SELECT COUNT(*) as total 
            FROM clientes_sniper 
            WHERE exchange IS NULL OR TRIM(exchange) = ''
        """)
        null_count = cur.fetchone()[0]
        
        print(f"\n📊 Status atual:")
        cur.execute("SELECT COUNT(*) as total FROM clientes_sniper")
        total_records = cur.fetchone()[0]
        print(f"   • Total de registros: {total_records}")
        print(f"   • Registros com exchange NULL/vazio: {null_count}")
        
        if null_count > 0:
            print(f"\n🔄 Atualizando {null_count} registro(s)...")
            
            # 3. Atualizar registros NULL/vazio para 'bybit' (default)
            cur.execute("""
                UPDATE clientes_sniper
                SET exchange = 'bybit'
                WHERE exchange IS NULL OR TRIM(exchange) = ''
            """)
            updated = cur.rowcount
            conn.commit()
            
            print(f"✅ {updated} registro(s) atualizado(s) para 'bybit'")
        else:
            print("✅ Todos os registros já possuem exchange válido!")
        
        # 4. Normalizar valores para lowercase (bybit, binance)
        cur.execute("""
            UPDATE clientes_sniper
            SET exchange = LOWER(TRIM(exchange))
            WHERE exchange IS NOT NULL
        """)
        normalized = cur.rowcount
        if normalized > 0:
            conn.commit()
            print(f"✅ {normalized} registro(s) normalizado(s) para lowercase")
        
        # 5. Validar que apenas 'bybit' ou 'binance' existem
        cur.execute("""
            SELECT DISTINCT exchange 
            FROM clientes_sniper 
            WHERE exchange NOT IN ('bybit', 'binance')
        """)
        invalid = cur.fetchall()
        
        if invalid:
            print("\n⚠️  Valores inválidos encontrados:")
            for row in invalid:
                print(f"   • '{row[0]}'")
            
            # Corrigir valores inválidos para 'bybit'
            cur.execute("""
                UPDATE clientes_sniper
                SET exchange = 'bybit'
                WHERE exchange NOT IN ('bybit', 'binance')
            """)
            fixed = cur.rowcount
            conn.commit()
            print(f"✅ {fixed} valor(es) inválido(s) corrigido(s) para 'bybit'")
        
        # 6. Relatório final
        print("\n📊 Distribuição final:")
        cur.execute("""
            SELECT exchange, COUNT(*) as count
            FROM clientes_sniper
            GROUP BY exchange
            ORDER BY count DESC
        """)
        
        for row in cur.fetchall():
            exchange = row[0] or 'NULL'
            count = row[1]
            print(f"   • {exchange}: {count} registro(s)")
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ MIGRAÇÃO CONCLUÍDA COM SUCESSO!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERRO durante migração: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = migrate_exchange_field()
    sys.exit(0 if success else 1)
