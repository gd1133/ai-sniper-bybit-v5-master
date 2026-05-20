# 🚀 Quick Start - API Tester

## TL;DR - Teste Rápido

```bash
# Instalar dependências
pip install python-dotenv ccxt pybit requests

# Testar tudo
python api_tester.py
```

Se todos os testes passarem ✅, você está pronto para ligar o robô!

## O que este script faz?

O `api_tester.py` é como um **check-up médico** para o seu robô de trading:

- 🔍 **Diagnóstico**: Verifica se tudo está funcionando
- ⚡ **Rápido**: Executa em menos de 30 segundos
- 🎨 **Visual**: Usa cores para facilitar a leitura
- 📊 **Completo**: Testa API, saldo, conectividade e IP

## Quando usar?

✅ **USE ANTES DE**:
- Ligar o robô pela primeira vez
- Fazer deploy em um novo servidor
- Adicionar/atualizar API Keys
- Trocar de testnet para produção

❌ **NÃO PRECISA USAR**:
- Durante operação normal do robô
- Para monitorar ordens (use o dashboard)
- Para fechar posições (use `fechar_posicao.py`)

## Exemplos de Uso

### Teste Completo (Recomendado)

```bash
python api_tester.py
```

Testa **Bybit** e **Binance** automaticamente.

### Teste Específico

```bash
# Só Bybit
python api_tester.py --bybit

# Só Binance
python api_tester.py --binance
```

Útil quando você só usa uma exchange.

### Teste Detalhado

```bash
python api_tester.py --full
```

Inclui testes adicionais:
- Dados de mercado (preços, volume)
- Order book (livro de ofertas)
- Validação extra de conectividade

## Interpretando Resultados

### ✅ Tudo OK

```
✅ Autenticação bem-sucedida!
✅ Saldo Total: $1,234.56 USDT
✅ 🎉 TODOS OS TESTES PASSARAM!
```

**Ação**: Nada! Pode ligar o robô.

### ⚠️ Avisos

```
⚠️ Saldo disponível baixo (< $10 USDT)
⚠️ Modo TESTNET ativo
```

**Ação**: Verifique se é intencional. Ajuste se necessário.

### ❌ Erros

```
❌ API Key não configurada
❌ Falha na autenticação (retCode: 10003)
```

**Ação**: Corrija o problema antes de continuar. Veja seção de troubleshooting.

## Troubleshooting Rápido

### "API Key não configurada"

**Problema**: Arquivo `.env` não existe ou está vazio.

**Solução**:
```bash
cp .env.example .env
# Edite .env com suas credenciais reais
```

### "Erro 10003: Chave de API inválida"

**Problema**: Credenciais incorretas ou 2FA ativo.

**Solução**:
1. Copie a API Key novamente (sem espaços)
2. Desative 2FA na API Key (não na conta!)
3. Regenere a chave se necessário

### "Modo TESTNET ativo"

**Problema**: `USE_TESTNET=true` mas você quer usar contas reais.

**Solução**:
```bash
# No arquivo .env
USE_TESTNET=false
```

### "Saldo disponível baixo"

**Problema**: Menos de $10 USDT na conta.

**Solução**:
- Deposite mais fundos, ou
- Ajuste `RISK_PER_TRADE_PCT` no `.env`

## Estrutura de Testes

O script executa os seguintes testes em sequência:

```
1. ⚙️  Configuração do Sistema
   ├─ ALLOW_ORDER_EXECUTION
   ├─ ALLOW_REAL_TRADING
   └─ USE_TESTNET

2. 🟡 Bybit
   ├─ Credenciais
   ├─ Conectividade
   ├─ Autenticação
   ├─ Saldo (USDT)
   ├─ Dados de Mercado (--full)
   └─ IP Whitelisting

3. 🟠 Binance
   ├─ Credenciais
   ├─ Conectividade
   ├─ Autenticação
   ├─ Saldo (USDT)
   ├─ Dados de Mercado
   └─ Order Book (--full)

4. 📊 Resumo Final
   └─ Status de cada exchange
```

## Testnet vs Produção

### Modo Testnet (Seguro) 🛡️

```bash
USE_TESTNET=true
```

- ✅ Não usa dinheiro real
- ✅ Ideal para testes
- ❌ Ordens não aparecem na conta real

**Endpoints**:
- Bybit: `https://api-testnet.bybit.com`
- Binance: `https://testnet.binancefuture.com`

### Modo Produção (Real) 💰

```bash
USE_TESTNET=false
```

- ⚠️ Usa dinheiro real
- ✅ Ordens aparecem na conta
- ⚠️ Configure SL/TP corretamente!

**Endpoints**:
- Bybit: `https://api.bybit.com`
- Binance: `https://fapi.binance.com`

## Próximos Passos

Após todos os testes passarem:

```bash
# 1. Configurar variáveis de ambiente
# Edite .env com:
ALLOW_ORDER_EXECUTION=true
ALLOW_REAL_TRADING=true
USE_TESTNET=false

# 2. Iniciar o robô
python main_web.py

# 3. Acessar dashboard
# http://localhost:5000
```

## Arquivos Relacionados

- `api_tester.py` - Este script
- `docs/API_TESTER_GUIA.md` - Documentação completa
- `diagnostico_config.py` - Valida variáveis de ambiente
- `diagnostico_modo_real.py` - Verifica modo testnet vs produção
- `.env` - Suas credenciais (nunca compartilhe!)

## Perguntas Frequentes

### O script modifica algo?

**Não.** O script é 100% read-only. Ele apenas:
- Lê variáveis de ambiente
- Faz requisições de consulta
- Mostra resultados

Não cria ordens, não altera saldo, não modifica configurações.

### Preciso rodar toda vez?

**Não.** Rode apenas quando:
- Configurar algo novo
- Houver problemas de conectividade
- Antes de um deploy importante

### Posso usar em produção?

**Sim!** É seguro rodar em qualquer ambiente. Ele não executa ordens nem altera nada.

### E se eu só usar Bybit?

Use `python api_tester.py --bybit` para testar apenas Bybit.

### E se não tiver credenciais Binance?

O script continua e testa apenas Bybit. Avisos serão mostrados, mas não é erro.

## Suporte

Para mais informações:

- 📖 **Guia Completo**: `docs/API_TESTER_GUIA.md`
- 🔧 **Diagnóstico**: `python diagnostico_config.py`
- 📚 **Documentação**: `docs/DOCUMENTACAO_COMPLETA.md`
- 🐛 **Issues**: https://github.com/gd1133/ai-sniper-bybit-v5-master/issues

---

**💡 Dica Pro**: Execute `python api_tester.py --full` antes de cada deploy importante. Assim você garante que tudo está funcionando perfeitamente!
