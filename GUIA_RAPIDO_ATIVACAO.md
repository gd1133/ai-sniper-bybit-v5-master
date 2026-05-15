# 🚀 GUIA RÁPIDO - ATIVAÇÃO DE ORDENS REAIS

## ⚡ PROBLEMA IDENTIFICADO

**Sintoma**: API conectada ✅ | Saldo visível ✅ | Mas ordens NÃO executam ❌

**Causa**: Sistema em modo desenvolvimento (segurança ativa)

---

## ✅ SOLUÇÃO EM 3 PASSOS

### 1️⃣ EDITAR ARQUIVO `.env`

Abra o arquivo `.env` e adicione/edite estas linhas:

```bash
# Ativar modo produção
ENVIRONMENT=production

# Permitir execução de ordens
ALLOW_ORDER_EXECUTION=true

# Permitir trading em conta real
ALLOW_REAL_TRADING=true
```

### 2️⃣ VALIDAR CONFIGURAÇÃO

Execute o script de diagnóstico:

```bash
python diagnostico_config.py
```

**Deve mostrar:**
```
✅ ENVIRONMENT=production
✅ ALLOW_ORDER_EXECUTION=true
✅ ALLOW_REAL_TRADING=true
✅ BYBIT_API_KEY configurada
✅ BYBIT_API_SECRET configurada

🎯 Sistema pronto para operar!
```

### 3️⃣ REINICIAR SISTEMA

**Railway/Cloud:**
- Edite as variáveis no painel
- Clique em "Deploy"

**Local:**
```bash
# Pare o servidor (Ctrl+C)
python main_web.py
```

---

## 🔍 VERIFICAR API NA BYBIT

1. Acesse: https://www.bybit.com/app/user/api-management
2. Encontre sua chave API
3. Verifique permissões:
   - ✅ **Read Position** (ler posições)
   - ✅ **Trade Orders** (executar ordens)
4. Desative **2FA na API Key** (se estiver ativo)
5. Configure **IP Whitelist** (opcional, mais seguro)

---

## 📋 CHECKLIST DE VALIDAÇÃO

- [ ] Arquivo `.env` editado com as 3 variáveis
- [ ] Script `diagnostico_config.py` executado com sucesso
- [ ] API da Bybit com permissões corretas
- [ ] Sistema reiniciado
- [ ] Logs mostram "EXECUÇÃO REAL" ou "ORDEM EXECUTADA"

---

## 🎯 CONFIRMAR FUNCIONAMENTO

Após reiniciar, os logs devem mostrar:

```
[SISTEMA] Iniciando em modo: production
💼 CONTA REAL: Ordens reais ativas
🚀 [EXECUÇÃO REAL] cliente - buy 0.0050 BTCUSDT
✅ [ORDEM EXECUTADA] ID: 12345678
```

**NÃO deve mais aparecer:**
```
🔒 [ORDENS BLOQUEADAS]
```

---

## ⚠️ SEGURANÇA

- Comece com valores PEQUENOS para testar
- Use IP Whitelist na API se possível
- Nunca compartilhe suas chaves de API
- Mantenha 2FA ativo na CONTA (não na API Key)

---

## 📞 SUPORTE

**Documentação completa**: `RELATORIO_DIAGNOSTICO_API.md`

**Script de diagnóstico**: `python diagnostico_config.py`

**Arquivo de exemplo**: `.env.example`

---

**Atualizado em**: 15/05/2026
