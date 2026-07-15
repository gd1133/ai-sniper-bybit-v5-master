# Documentação Técnica: Motor Sniper V60.7 🚀

Esta documentação descreve as regras de negócio, arquitetura de proteção e gerenciamento de risco do sistema de trading automatizado de alta frequência integrado com a API da Bybit V5.

---

## 1. Arquitetura de Decisão: O Triplo Cérebro

O robô opera através de uma estrutura de decisão em camadas para garantir que nenhuma operação seja aberta sem uma confluência de dados de alta probabilidade:

* **Cérebro 1 (Mapeamento de Estrutura - SMC):** Analisa quebras de estrutura de mercado (BOS/CHoCH) e identifica blocos de ordens institucionais (*Order Blocks*) em tempos gráficos de 15m e 1h.
* **Cérebro 2 (Volume & Fluxo):** Monitora picos de volume financeiro real (*Volume Clímax*) e analisa o desequilíbrio dinâmico do livro de ordens (mínimo de 60% de dominância de um lado do livro nas primeiras 20 profundidades).
* **Cérebro 3 (Decisão Soberana & Contingência):** Consolida os dados e aprova a execução. Em caso de falha de conexão ou limites de requisição (*Rate Limit*) das IAs auxiliares, o Cérebro 3 assume o controle de forma autônoma utilizando indicadores matemáticos puramente locais para evitar o travamento do robô.

---

## 2. Protocolo Rígido de Gerenciamento de Risco

Para evitar a quebra de capital das contas conectadas, o robô deve seguir as seguintes diretrizes matemáticas obrigatórias em cada operação:

### A. Seleção do Modo de Margem
* **Proibição Absoluta:** É terminantemente proibido operar em modo de Margem Cruzada (*Cross Margin*).
* **Padrão Exigido:** Toda e qualquer operação deve ser executada em **Margem Isolada (*Isolated Margin*)**. O robô força esta configuração via API antes de transmitir a ordem principal (`set_isolated_margin` → CCXT `set_margin_mode('isolated', symbol, {'leverage': 20})`, com fallback `pybit switch_margin_mode(tradeMode=1)`).

### B. Tamanho do Lote Dinâmico (Fórmula dos 3%)
A margem utilizada em cada trade deve ser equivalente a exatamente **3%** do saldo real disponível na carteira do investidor:

$$\text{Margem Isolada} = \text{Saldo da Conta} \times 0.03$$
$$\text{Tamanho Nominal} = \text{Margem Isolada} \times 20 \text{ (Alavancagem)}$$
$$\text{Lote Final} = \frac{\text{Tamanho Nominal}}{\text{Preço Atual do Ativo}}$$

O lote é arredondado usando as regras de precisão (Step Size / minOrderQty) da corretora, respeitando o teto de tolerância de 7.5% da banca.

### C. Parâmetros de Saída de Emergência
* **Take Profit (TP):** Configurado na corretora para garantir **+100% de ROI** sobre a margem separada.
* **Stop Loss (SL):** Configurado na corretora para limitar a perda em exatamente **-50% de ROI** sobre a margem separada. No caso de 20x de alavancagem, o SL é acionado quando o preço do ativo mover **2.5%** contra a direção de entrada.
* **Vínculo à Ordem Principal:** TP e SL são enviados **dentro dos parâmetros da própria ordem de mercado** (`takeProfit`/`stopLoss`, `tpslMode=Full`), e não em requisições separadas. A rota `set_trading_stop` só é usada como fallback caso o TP/SL inline seja rejeitado.

---

## 3. Segurança Contra Sobrecarga e Duplicação (Anti-Overtrading)

* **Trava de Ativo Único:** O robô só pode manter **uma única posição aberta por par de moedas**. Sinais adicionais para um ativo já posicionado são descartados. Antes de cada compra, o robô chama `has_open_position(symbol)` (`get_positions`/`fetch_positions`) e **aborta imediatamente** se já houver qualquer quantidade aberta no par.
* **Mutex / Lock de Concorrência:** O loop de varredura do radar reserva a trava do par (`SNIPER_SIGNAL_RESERVATIONS`) assim que o sinal é aprovado e **só a libera após a confirmação de retorno da API** (dentro de `_process_client_orders_background`). Isso evita a criação de ordens fantasmas duplicadas por atraso de rede (latência). A verificação `_can_open_new_signal` considera tanto as posições abertas no banco quanto as reservas em processamento.

---

## 4. Conta Real (100%)

O sistema opera exclusivamente em **conta real (mainnet)**. Não há paper trading, testnet, demo ou saldo fictício. Todos os saldos e posições exibidos e processados são lidos diretamente das APIs reais da Bybit/Binance.
