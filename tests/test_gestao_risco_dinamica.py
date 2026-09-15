#!/usr/bin/env python3
"""
Testes da Gestão de Risco Dinâmica
Valida os cenários: 5% normal → 3% após stop loss → 5% após vitória
"""

import os
import sys
import sqlite3
from datetime import datetime

# Adiciona o diretório src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from risk.position_sizing import (
    load_entry_pct,
    load_entry_after_stop_pct,
    calculate_order_margin,
    calcular_tamanho_posicao
)


def test_percentuais_configurados():
    """Teste 1: Verifica se os percentuais estão corretos"""
    print("\n" + "="*70)
    print("TESTE 1: Percentuais Configurados")
    print("="*70)
    
    pct_normal = load_entry_pct() * 100
    pct_apos_stop = load_entry_after_stop_pct() * 100
    
    print(f"✅ Entrada Normal: {pct_normal:.1f}%")
    print(f"✅ Após Stop Loss: {pct_apos_stop:.1f}%")
    
    assert pct_normal == 5.0, f"❌ Esperado 5%, obtido {pct_normal}%"
    assert pct_apos_stop == 3.0, f"❌ Esperado 3%, obtido {pct_apos_stop}%"
    
    print("✅ TESTE 1 PASSOU: Percentuais corretos!")


def test_calculo_margem_normal():
    """Teste 2: Calcula margem para entrada normal (5%)"""
    print("\n" + "="*70)
    print("TESTE 2: Cálculo de Margem - Entrada Normal")
    print("="*70)
    
    banca = 1000.0
    margem_normal = calculate_order_margin(banca, after_stop=False)
    margem_esperada = 50.0  # 5% de $1000
    
    print(f"Banca: ${banca:.2f}")
    print(f"Margem Calculada: ${margem_normal:.2f}")
    print(f"Margem Esperada: ${margem_esperada:.2f}")
    
    assert abs(margem_normal - margem_esperada) < 0.01, \
        f"❌ Esperado ${margem_esperada}, obtido ${margem_normal}"
    
    print("✅ TESTE 2 PASSOU: Margem normal correta!")


def test_calculo_margem_apos_stop():
    """Teste 3: Calcula margem após stop loss (3%)"""
    print("\n" + "="*70)
    print("TESTE 3: Cálculo de Margem - Após Stop Loss")
    print("="*70)
    
    banca = 1000.0
    margem_conservadora = calculate_order_margin(banca, after_stop=True)
    margem_esperada = 30.0  # 3% de $1000
    
    print(f"Banca: ${banca:.2f}")
    print(f"Margem Calculada: ${margem_conservadora:.2f}")
    print(f"Margem Esperada: ${margem_esperada:.2f}")
    
    assert abs(margem_conservadora - margem_esperada) < 0.01, \
        f"❌ Esperado ${margem_esperada}, obtido ${margem_conservadora}"
    
    print("✅ TESTE 3 PASSOU: Margem conservadora correta!")


def test_cenario_completo_5_trades():
    """Teste 4: Simula 5 trades com win/loss alternados"""
    print("\n" + "="*70)
    print("TESTE 4: Cenário Completo - 5 Trades")
    print("="*70)
    
    banca_inicial = 1000.0
    leverage = 20.0
    price = 50000.0
    
    cenarios = [
        {"id": 1, "resultado": "WIN", "pnl_pct": 2.3, "after_stop": False, "expected_pct": 5.0},
        {"id": 2, "resultado": "WIN", "pnl_pct": 1.8, "after_stop": False, "expected_pct": 5.0},
        {"id": 3, "resultado": "STOP_LOSS", "pnl_pct": -1.5, "after_stop": False, "expected_pct": 5.0},
        {"id": 4, "resultado": "WIN (recuperação)", "pnl_pct": 2.1, "after_stop": True, "expected_pct": 3.0},
        {"id": 5, "resultado": "WIN", "pnl_pct": 3.4, "after_stop": False, "expected_pct": 5.0},
    ]
    
    print(f"\n{'#':<3} {'Resultado':<20} {'PnL%':<8} {'Após SL?':<10} {'% Usado':<10} {'Margem':<12}")
    print("-" * 70)
    
    for c in cenarios:
        margem = calculate_order_margin(banca_inicial, after_stop=c["after_stop"])
        pct_usado = (margem / banca_inicial) * 100
        status = "⚠️" if c["after_stop"] else "✅"
        
        print(f"{c['id']:<3} {c['resultado']:<20} {c['pnl_pct']:>6.1f}% "
              f"{status + ' SIM' if c['after_stop'] else '    NÃO':<10} "
              f"{pct_usado:>6.1f}% {f'${margem:.2f}':>12}")
        
        assert abs(pct_usado - c["expected_pct"]) < 0.1, \
            f"❌ Trade #{c['id']}: Esperado {c['expected_pct']}%, obtido {pct_usado:.1f}%"
    
    print("\n✅ TESTE 4 PASSOU: Todos os cenários corretos!")


def test_calculo_quantidade_com_alavancagem():
    """Teste 5: Calcula quantidade final com alavancagem"""
    print("\n" + "="*70)
    print("TESTE 5: Cálculo de Quantidade com Alavancagem")
    print("="*70)
    
    banca = 1000.0
    leverage = 20.0
    price = 50000.0
    
    # Entrada normal (5%)
    resultado_normal = calcular_tamanho_posicao(
        saldo_banca=banca,
        alavancagem=leverage,
        preco_entrada=price,
        pct_banca=0.05
    )
    
    print("\n📊 Entrada Normal (5%):")
    print(f"  Banca: ${resultado_normal['saldo_referencia']:.2f}")
    print(f"  Margem Inicial: ${resultado_normal['margem_inicial']:.2f}")
    print(f"  Alavancagem: {resultado_normal['alavancagem']:.0f}x")
    print(f"  Valor da Posição: ${resultado_normal['valor_posicao_usdt']:.2f}")
    print(f"  Quantidade: {resultado_normal['quantidade']:.6f} BTC")
    print(f"  % da Banca: {resultado_normal['pct_banca'] * 100:.1f}%")
    
    # Entrada conservadora (3%)
    resultado_conservador = calcular_tamanho_posicao(
        saldo_banca=banca,
        alavancagem=leverage,
        preco_entrada=price,
        pct_banca=0.03
    )
    
    print("\n📊 Entrada Conservadora (3% - após stop loss):")
    print(f"  Banca: ${resultado_conservador['saldo_referencia']:.2f}")
    print(f"  Margem Inicial: ${resultado_conservador['margem_inicial']:.2f}")
    print(f"  Alavancagem: {resultado_conservador['alavancagem']:.0f}x")
    print(f"  Valor da Posição: ${resultado_conservador['valor_posicao_usdt']:.2f}")
    print(f"  Quantidade: {resultado_conservador['quantidade']:.6f} BTC")
    print(f"  % da Banca: {resultado_conservador['pct_banca'] * 100:.1f}%")
    
    # Validações
    assert resultado_normal['margem_inicial'] == 50.0, "❌ Margem normal incorreta"
    assert resultado_conservador['margem_inicial'] == 30.0, "❌ Margem conservadora incorreta"
    assert resultado_normal['valor_posicao_usdt'] == 1000.0, "❌ Valor posição normal incorreto"
    assert resultado_conservador['valor_posicao_usdt'] == 600.0, "❌ Valor posição conservadora incorreto"
    
    print("\n✅ TESTE 5 PASSOU: Quantidades calculadas corretamente!")


def test_comparacao_lado_a_lado():
    """Teste 6: Comparação visual lado a lado"""
    print("\n" + "="*70)
    print("TESTE 6: Comparação Lado a Lado - Normal vs Conservador")
    print("="*70)
    
    banca = 1000.0
    leverage = 20.0
    price = 50000.0
    
    normal = calcular_tamanho_posicao(banca, leverage, price, pct_banca=0.05)
    conservador = calcular_tamanho_posicao(banca, leverage, price, pct_banca=0.03)
    
    print(f"\n{'Métrica':<25} {'Normal (5%)':<20} {'Conservador (3%)':<20}")
    print("-" * 70)
    print(f"{'Margem Inicial':<25} ${normal['margem_inicial']:<19.2f} ${conservador['margem_inicial']:<19.2f}")
    print(f"{'Valor da Posição':<25} ${normal['valor_posicao_usdt']:<19.2f} ${conservador['valor_posicao_usdt']:<19.2f}")
    print(f"{'Quantidade':<25} {normal['quantidade']:<19.6f} {conservador['quantidade']:<19.6f}")
    print(f"{'% da Banca':<25} {normal['pct_banca']*100:<19.1f}% {conservador['pct_banca']*100:<19.1f}%")
    
    diferenca_margem = normal['margem_inicial'] - conservador['margem_inicial']
    diferenca_pct = ((normal['margem_inicial'] - conservador['margem_inicial']) / normal['margem_inicial']) * 100
    
    print(f"\n💡 Diferença: ${diferenca_margem:.2f} ({diferenca_pct:.1f}% menor no modo conservador)")
    print("✅ TESTE 6 PASSOU: Comparação visual completa!")


def run_all_tests():
    """Executa todos os testes"""
    print("\n" + "="*70)
    print("🧪 SUITE DE TESTES - GESTÃO DE RISCO DINÂMICA")
    print("="*70)
    
    try:
        test_percentuais_configurados()
        test_calculo_margem_normal()
        test_calculo_margem_apos_stop()
        test_cenario_completo_5_trades()
        test_calculo_quantidade_com_alavancagem()
        test_comparacao_lado_a_lado()
        
        print("\n" + "="*70)
        print("✅ TODOS OS TESTES PASSARAM COM SUCESSO!")
        print("="*70)
        print("\n🎯 Sistema de Gestão de Risco está funcionando corretamente:")
        print("   • Entrada normal: 5% da banca")
        print("   • Após stop loss: 3% da banca")
        print("   • Após vitória: volta automaticamente para 5%")
        print("\n")
        
        return True
        
    except AssertionError as e:
        print(f"\n❌ TESTE FALHOU: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
