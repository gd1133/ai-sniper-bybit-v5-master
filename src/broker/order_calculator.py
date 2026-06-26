"""
╔══════════════════════════════════════════════════════════════════╗
║           CALCULADORA DE ORDENS DINÂMICA v1.0                    ║
║        Baseada em Limites Mínimos da Exchange (CCXT)             ║
╚══════════════════════════════════════════════════════════════════╝

Sistema de cálculo de ordens que respeita os limites ESTRITOS da corretora:
  - market["limits"]["amount"]["min"] → Lote mínimo de contratos
  - market["limits"]["cost"]["min"] → Nocional mínimo em USDT

REMOVE completamente o modelo de "5% da banca" ou percentuais fixos.
CALCULA a quantidade exata para atingir o valor mínimo aceito pela exchange.
"""

from decimal import Decimal, ROUND_UP, InvalidOperation
from typing import Tuple, Optional


class OrderCalculator:
    """
    Calculadora de ordens baseada nos limites dinâmicos da corretora.

    Elimina o uso de percentuais fixos (5%, 15%, etc.) da banca do investidor.
    Busca dinamicamente as regras da moeda e calcula a quantidade EXATA para
    que a ordem atinja o valor mínimo absoluto aceito pela corretora.
    """

    # Margens de segurança por corretora (em USDT)
    SAFETY_MARGINS = {
        'binance': 0.50,  # Binance exige ~$5 USDT, usamos $5.50
        'bybit': 0.50,    # Bybit exige ~$5 USDT (alguns pares $2), usamos margem de $0.50
    }

    DEFAULT_MIN_NOTIONAL = 5.0  # Valor padrão se não conseguir carregar da API
    DEFAULT_MIN_AMOUNT = 0.001  # Quantidade padrão

    def __init__(self, exchange_name: str = 'bybit'):
        """
        Inicializa a calculadora para uma exchange específica.

        Args:
            exchange_name: Nome da exchange ('bybit' ou 'binance')
        """
        self.exchange_name = exchange_name.lower()
        self.safety_margin = self.SAFETY_MARGINS.get(self.exchange_name, 0.50)

    def calculate_minimum_order_qty(
        self,
        exchange_instance,
        symbol: str,
        current_price: float,
    ) -> Tuple[float, dict]:
        """
        Calcula a quantidade mínima de contratos para uma ordem válida.

        Esta função:
        1. Carrega dinamicamente os limites do mercado via exchange.load_markets()
        2. Extrai market["limits"]["amount"]["min"] e market["limits"]["cost"]["min"]
        3. Calcula a quantidade necessária para atingir o nocional mínimo
        4. Adiciona margem de segurança conforme a exchange
        5. Aplica precisão usando CCXT amount_to_precision

        Args:
            exchange_instance: Instância do CCXT exchange (ex: ccxt.bybit())
            symbol: Par de negociação (ex: 'BTC/USDT:USDT')
            current_price: Preço atual do ativo

        Returns:
            Tuple (quantidade_final, metadata) onde metadata contém:
                - min_amount: Quantidade mínima em contratos
                - min_cost: Nocional mínimo em USDT
                - calculated_cost: Valor nocional calculado
                - precision: Precisão da quantidade
                - safety_margin: Margem de segurança aplicada
        """
        if current_price <= 0:
            raise ValueError(f"Preço inválido para {symbol}: {current_price}")

        # PASSO 1: Carrega limites dinâmicos da corretora
        try:
            exchange_instance.load_markets()
            market = exchange_instance.market(symbol)
            limits = market.get('limits', {})

            # Extrai limites mínimos
            min_amount = limits.get('amount', {}).get('min', self.DEFAULT_MIN_AMOUNT)
            min_cost = limits.get('cost', {}).get('min', self.DEFAULT_MIN_NOTIONAL)

            # Precisão da quantidade
            precision = market.get('precision', {})
            amount_precision = precision.get('amount', 4)
            # 🔧 PROTEÇÃO CRÍTICA: Converte para int para evitar TypeError em .scaleb()
            amount_precision = int(amount_precision) if amount_precision is not None else 4

            print(f"   📊 [{self.exchange_name.upper()} LIMITS] {symbol}:")
            print(f"      • min_amount: {min_amount} contratos")
            print(f"      • min_cost: {min_cost} USDT")
            print(f"      • amount_precision: {amount_precision}")

        except Exception as e:
            print(f"⚠️ [ORDER CALC] Erro ao carregar limites do mercado: {e}")
            print(f"   Usando valores padrão: min_amount={self.DEFAULT_MIN_AMOUNT}, min_cost={self.DEFAULT_MIN_NOTIONAL}")
            min_amount = self.DEFAULT_MIN_AMOUNT
            min_cost = self.DEFAULT_MIN_NOTIONAL
            amount_precision = 4

        # PASSO 2: Calcula quantidade mínima para satisfazer nocional mínimo
        try:
            # Adiciona margem de segurança ao nocional mínimo
            target_cost = Decimal(str(min_cost)) + Decimal(str(self.safety_margin))

            # Calcula quantidade necessária: qty = target_cost / price
            min_qty_for_notional = target_cost / Decimal(str(current_price))

            # PASSO 3: Usa o MAIOR entre min_amount e min_qty_for_notional
            required_qty = max(Decimal(str(min_amount)), min_qty_for_notional)

            # PASSO 4: Arredonda para cima respeitando precisão da exchange
            # 🔧 PROTEÇÃO CRÍTICA: amount_precision deve ser int para .scaleb() retornar Decimal correto
            step = Decimal('1').scaleb(-int(amount_precision))
            quantized = required_qty.quantize(step, rounding=ROUND_UP)

            # PASSO 5: Valida que o nocional ainda atende o mínimo após arredondamento
            calculated_cost = float(quantized) * current_price

            if calculated_cost < min_cost:
                # Se caiu abaixo do mínimo, arredonda para cima até atingir
                quantized = (Decimal(str(min_cost + self.safety_margin)) / Decimal(str(current_price))).quantize(
                    step, rounding=ROUND_UP
                )
                calculated_cost = float(quantized) * current_price

            # PASSO 6: Aplica amount_to_precision do CCXT
            final_qty = float(quantized)
            try:
                if hasattr(exchange_instance, 'amount_to_precision'):
                    final_qty = float(exchange_instance.amount_to_precision(symbol, final_qty))
            except Exception as precision_err:
                print(f"⚠️ [CCXT PRECISION] Erro ao aplicar amount_to_precision: {precision_err}")

            # Recalcula nocional final
            final_cost = final_qty * current_price

            # Metadados para auditoria
            metadata = {
                'min_amount': float(min_amount),
                'min_cost': float(min_cost),
                'calculated_cost': round(final_cost, 2),
                'precision': amount_precision,
                'safety_margin': self.safety_margin,
                'exchange': self.exchange_name,
            }

            print(f"   ✅ [ORDER CALC] Quantidade calculada:")
            print(f"      • qty: {final_qty}")
            print(f"      • notional: ${final_cost:.2f} USDT")
            print(f"      • min_required: ${min_cost:.2f} USDT")
            print(f"      • safety_margin: ${self.safety_margin:.2f} USDT")

            return final_qty, metadata

        except (InvalidOperation, ValueError, ZeroDivisionError) as calc_err:
            raise ValueError(f"Erro no cálculo da quantidade mínima: {calc_err}")

    def calculate_order_qty_from_balance(
        self,
        exchange_instance,
        symbol: str,
        current_price: float,
        balance: float,
        risk_multiplier: float = 1.0,
    ) -> Tuple[float, dict]:
        """
        Calcula quantidade de ordem considerando o saldo disponível.

        Se o saldo permitir, usa um múltiplo do valor mínimo.
        Caso contrário, usa apenas o valor mínimo absoluto.

        Args:
            exchange_instance: Instância do CCXT exchange
            symbol: Par de negociação
            current_price: Preço atual do ativo
            balance: Saldo disponível em USDT
            risk_multiplier: Multiplicador de risco (ex: 1.5x, 2x o mínimo)

        Returns:
            Tuple (quantidade_final, metadata)
        """
        # Primeiro calcula a quantidade mínima absoluta
        min_qty, metadata = self.calculate_minimum_order_qty(
            exchange_instance, symbol, current_price
        )

        min_cost = metadata['calculated_cost']

        # Verifica se o saldo permite usar um múltiplo do mínimo
        if balance > (min_cost * risk_multiplier):
            # Calcula quantidade baseada no multiplicador
            target_cost = min_cost * risk_multiplier
            multiplied_qty = target_cost / current_price

            # Aplica precisão CCXT
            try:
                if hasattr(exchange_instance, 'amount_to_precision'):
                    multiplied_qty = float(exchange_instance.amount_to_precision(symbol, multiplied_qty))
            except Exception:
                pass

            final_cost = multiplied_qty * current_price
            metadata['calculated_cost'] = round(final_cost, 2)
            metadata['risk_multiplier'] = risk_multiplier

            print(f"   💰 [ORDER CALC] Saldo permite {risk_multiplier}x do mínimo:")
            print(f"      • qty: {multiplied_qty}")
            print(f"      • notional: ${final_cost:.2f} USDT")

            return multiplied_qty, metadata
        else:
            # Saldo insuficiente para multiplicador, usa apenas o mínimo
            print(f"   ⚠️ [ORDER CALC] Saldo (${balance:.2f}) insuficiente para {risk_multiplier}x mínimo")
            print(f"      Usando quantidade mínima absoluta: {min_qty}")
            metadata['risk_multiplier'] = 1.0
            return min_qty, metadata


def sanitize_numeric_string(value: str) -> str:
    """
    Limpa strings numéricas para evitar erros de conversão decimal.

    Remove espaços, troca vírgulas por pontos, remove caracteres inválidos.
    Trata o erro 'decimal.ConversionSyntax' mencionado nos requisitos.
    """
    if not isinstance(value, str):
        return str(value)

    # Remove espaços, tabulações, quebras de linha
    cleaned = value.strip().replace(' ', '').replace('\t', '').replace('\n', '').replace('\r', '')

    # Troca vírgula por ponto (formato decimal brasileiro vs inglês)
    cleaned = cleaned.replace(',', '.')

    # Remove caracteres não numéricos exceto ponto e sinal negativo
    allowed_chars = set('0123456789.-')
    cleaned = ''.join(c for c in cleaned if c in allowed_chars)

    return cleaned
