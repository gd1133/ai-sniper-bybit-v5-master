import React, { useState, useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { 
  LayoutDashboard, 
  FileSearch, 
  Users, 
  Zap, 
  TrendingUp, 
  TrendingDown,
  Target, 
  Database, 
  Activity,
  ShieldCheck,
  Search,
  X,
  Save,
  CheckCircle2,
  Trash2,
  Settings
} from 'lucide-react';

const getApiBase = () => {
  const configuredBase = import.meta.env.VITE_API_BASE?.trim();
  if (configuredBase) return configuredBase.replace(/\/$/, '');
  if (typeof window !== 'undefined') return window.location.origin;
  return 'http://localhost:5000';
};

const API_BASE = getApiBase();

const CLIENT_STATUS_STYLE = {
  ativo:     { dot: 'bg-green-500 animate-pulse', text: 'text-green-500' },
  erro_api:  { dot: 'bg-red-500',                 text: 'text-red-400'   },
};
const CLIENT_STATUS_STYLE_DEFAULT = { dot: 'bg-zinc-500', text: 'text-zinc-500' };

const OPERATION_MODE_META = {
  paper: {
    badge: '🧪 PAPER',
    label: 'PAPER TRADING',
    dot: 'bg-yellow-500',
    shell: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-500',
  },
  testnet: {
    badge: '🛰️ TESTNET',
    label: 'BYBIT TESTNET',
    dot: 'bg-blue-400',
    shell: 'bg-blue-500/10 border-blue-500/30 text-blue-300',
  },
  real: {
    badge: '💼 REAL',
    label: 'CONTA REAL',
    dot: 'bg-green-500',
    shell: 'bg-green-500/10 border-green-500/30 text-green-400',
  },
};

const normalizeOperationMode = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'test') return 'paper';
  return ['paper', 'testnet', 'real'].includes(normalized) ? normalized : 'paper';
};

const normalizeAccountMode = (value) => {
  const normalized = String(value || '').trim().toLowerCase();
  if (['testnet', 'real'].includes(normalized)) return normalized;
  if (value === true || value === 1 || value === '1' || value === 'true') return 'testnet';
  if (value === false || value === 0 || value === '0' || value === 'false') return 'real';
  return 'testnet';
};

const normalizeInvestorRecord = (client) => {
  const accountMode = normalizeAccountMode(client?.account_mode ?? client?.is_testnet);
  return {
    ...client,
    banca: client?.saldo_real ?? client?.saldo_base ?? client?.banca ?? 0,
    saldo_real: client?.saldo_real,
    saldo_configurado: client?.saldo_base ?? client?.saldo_configurado ?? 0,
    mode: accountMode.toUpperCase(),
    account_mode: accountMode,
    storage_source: String(client?.storage_source || client?.source || 'local').toUpperCase(),
    pnl: client?.pnl ?? '+0.0%',
  };
};

const formatEntryPrice = (value) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return '--';

  return numeric.toLocaleString('en-US', {
    minimumFractionDigits: numeric < 1 ? 3 : 2,
    maximumFractionDigits: numeric < 1 ? 6 : 2,
  });
};

const formatSignedPercent = (value) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '--';
  return `${numeric >= 0 ? '+' : ''}${numeric.toFixed(2)}%`;
};

const formatDollar = (value) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '$0.00';
  return `$${numeric.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const hasLivePrice = (trade) => Number(trade?.current_price || 0) > 0;

const getTradeTone = (trade) => {
  if (typeof trade?.is_favorable === 'boolean') return trade.is_favorable;

  const entry = Number(trade?.entry_price || 0);
  const current = Number(trade?.current_price || 0);
  const side = String(trade?.side || '').toUpperCase();
  if (!entry || !current) return false;
  return side === 'VENDER' || side === 'SELL' ? current <= entry : current >= entry;
};

const getTradeRelationLabel = (trade) => {
  const entry = Number(trade?.entry_price || 0);
  const current = Number(trade?.current_price || 0);
  if (!entry || !current) return 'Aguardando preço ao vivo';
  if (current > entry) return 'Acima da entrada';
  if (current < entry) return 'Abaixo da entrada';
  return 'Na entrada';
};

const getTradeStatusLabel = (trade) => {
  if (!hasLivePrice(trade)) return trade?.isSignalCard ? 'ENTRADA CONFIRMADA' : 'AGUARDANDO PREÇO';
  const pnlPct = Number(trade?.pnl_pct || 0);
  if (pnlPct > 0) return 'EM LUCRO';
  if (pnlPct < 0) return 'EM PERDA';
  return trade?.isSignalCard ? 'ENTRADA CONFIRMADA' : 'NA ENTRADA';
};

const getTradeStatusClasses = (trade) => {
  const pnlPct = Number(trade?.pnl_pct || 0);
  if (pnlPct > 0) return 'bg-green-500/10 border-green-500/30 text-green-400';
  if (pnlPct < 0) return 'bg-red-500/10 border-red-500/30 text-red-400';
  return 'bg-zinc-800 border-white/10 text-zinc-300';
};

const getTradeProgressPercent = (trade) => {
  const pnlPct = Number(trade?.pnl_pct || 0);
  if (!Number.isFinite(pnlPct)) return 0;
  if (pnlPct >= 0) return Math.max(0, Math.min(100, pnlPct));
  return Math.max(0, Math.min(100, (Math.abs(pnlPct) / 3) * 100));
};

const getTradeProgressText = (trade) => {
  if (!hasLivePrice(trade)) return 'Aguardando preço ao vivo';
  const pnlPct = Number(trade?.pnl_pct || 0);
  if (!Number.isFinite(pnlPct)) return 'TP 100% • SL 3%';
  if (pnlPct >= 0) return `Faltam ${Math.max(0, 100 - pnlPct).toFixed(2)}% para TP`;
  return `Faltam ${Math.max(0, 3 - Math.abs(pnlPct)).toFixed(2)}% para SL`;
};

/**
 * MOTOR SNIPER v60.7 - SaaS EDITION
 * Visual Proof Framework • Emerald Design
 */

const App = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [showAddForm, setShowAddForm] = useState(false);
  const [addFormMsg, setAddFormMsg] = useState(null);
  const [addFormSaving, setAddFormSaving] = useState(false);
  const [modeUpdating, setModeUpdating] = useState(false);
  const [manualClosingSymbol, setManualClosingSymbol] = useState(null);
  const [addFormFields, setAddFormFields] = useState({
    id: null, nome: '', saldo_base: 0, bybit_key: '', bybit_secret: '', tg_token: '', chat_id: '', account_mode: 'testnet'
  });
  const [data, setData] = useState({
    balance: 0,  // Será atualizado do backend
    status: "Conectando ao backend...",
    symbol: "---",
    confidence: 0,
    opportunities: [],
    active_trades: [],
    trades: [],
    test_balance: 0,
    test_mode: false,
    operation_mode: 'paper',
    operation_mode_label: 'PAPER TRADING',
    execution_enabled: false,
    execution_label: 'Sem ordens reais',
    last_sniper_signal: null,
    evidence: null,
    ia2_decision: { 
      motivo: "Aguardando conexão com o servidor..."
    }
  });

  // Polling do backend para manter o dashboard atualizado
  useEffect(() => {
    let mounted = true;
    let lastApiErrorLogAt = 0;
    console.log('Dashboard Iniciado - Conectando em:', API_BASE);

    const isAbortError = (err) => {
      const message = String(err?.message || '').toLowerCase();
      return err?.name === 'AbortError' || message.includes('aborted');
    };

    const logApiError = (label, err) => {
      const now = Date.now();
      if (now - lastApiErrorLogAt > 8000) {
        console.error(label, err);
        lastApiErrorLogAt = now;
      }
    };

    const fetchJson = async (path, timeoutMs = 12000) => {
      const ctrl = new AbortController();
      const timeoutId = setTimeout(() => ctrl.abort('timeout'), timeoutMs);
      try {
        const res = await fetch(`${API_BASE}${path}`, { signal: ctrl.signal });
        if (!res.ok) {
          return { ok: false, status: res.status, json: null };
        }
        const json = await res.json();
        return { ok: true, status: res.status, json };
      } finally {
        clearTimeout(timeoutId);
      }
    };

    const fetchStatus = async () => {
      try {
        const result = await fetchJson('/api/status');
        if (!result.ok) {
          if (mounted) {
            setData(prev => ({
              ...prev,
              status: `Backend offline (${result.status || 'sem resposta'})`
            }));
          }
          return;
        }
        const json = result.json;
        if (mounted) {
          setData(prev => ({
            ...prev,
            ...json,
            balance: json.balance ?? json.test_balance ?? 0,
            test_balance: json.test_balance ?? 0,
            test_mode: json.test_mode ?? false,
            operation_mode: normalizeOperationMode(json.operation_mode ?? json.mode),
            operation_mode_label: json.operation_mode_label ?? prev.operation_mode_label,
            execution_enabled: json.execution_enabled ?? prev.execution_enabled,
            execution_label: json.execution_label ?? prev.execution_label,
          }));
        }
      } catch (e) {
        if (isAbortError(e)) return;
        logApiError('Erro Total na API:', e);
        if (mounted) {
          setData(prev => ({
            ...prev,
            status: 'Backend offline (conexão recusada)'
          }));
        }
      }
    };

  const fetchInvestidores = async () => {
      try {
        const result = await fetchJson('/api/investidores');
        if (!result.ok) return;
        if (mounted) setInvestidores((result.json || []).map(normalizeInvestorRecord));
      } catch (e) {
        if (isAbortError(e)) return;
        logApiError('Erro fetching /api/investidores', e);
      }
    };

    fetchStatus();
    fetchInvestidores();
    const iv = setInterval(fetchStatus, 3000);
    const iv2 = setInterval(fetchInvestidores, 30000);
    return () => { mounted = false; clearInterval(iv); clearInterval(iv2); };
  }, []);

  const openNewInvestorModal = () => {
    setAddFormFields({ id: null, nome: '', saldo_base: 0, bybit_key: '', bybit_secret: '', tg_token: '', chat_id: '', account_mode: 'testnet' });
    setAddFormMsg(null);
    setShowAddForm(true);
  };

  const openEditInvestor = async (id) => {
    try {
      const res = await fetch(`${API_BASE}/api/cliente/${id}`);
      if (!res.ok) return;
      const c = await res.json();
      setAddFormFields({
        id: c.id,
        nome: c.nome || '',
        saldo_base: c.saldo_base || 0,
        bybit_key: c.bybit_key || '',
        bybit_secret: c.bybit_secret || '',
        tg_token: c.tg_token || '',
        chat_id: c.chat_id || '',
        account_mode: normalizeAccountMode(c.account_mode ?? c.is_testnet)
      });
      setAddFormMsg(null);
      setShowAddForm(true);
    } catch (e) { console.error('Erro ao carregar cliente', e); }
  };

  const handleDeleteInvestor = async (id) => {
    if (!confirm('Confirmar remoção do investidor? Esta ação é irreversível.')) return;
    try {
      const res = await fetch(`${API_BASE}/api/cliente/${id}`, { method: 'DELETE' });
      const json = await res.json();
      if (res.ok) {
        setInvestidores(prev => prev.filter(i => i.id !== id));
        alert(json.msg || 'Removido');
      } else {
        alert(json.error || 'Erro ao remover');
      }
    } catch (e) { console.error(e); alert('Erro ao remover'); }
  };

  const refreshStatusSnapshot = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/status`);
      if (!res.ok) return;
      const json = await res.json();
      setData(prev => ({
        ...prev,
        ...json,
        balance: json.balance ?? json.test_balance ?? 0,
        test_balance: json.test_balance ?? 0,
        test_mode: json.test_mode ?? false,
        operation_mode: normalizeOperationMode(json.operation_mode ?? json.mode),
        operation_mode_label: json.operation_mode_label ?? prev.operation_mode_label,
        execution_enabled: json.execution_enabled ?? prev.execution_enabled,
        execution_label: json.execution_label ?? prev.execution_label,
      }));
    } catch (e) {
      console.error('Erro ao atualizar status', e);
    }
  };

  const handleOperationModeChange = async (mode) => {
    if (modeUpdating || normalizeOperationMode(mode) === currentOperationMode) return;
    try {
      setModeUpdating(true);
      const res = await fetch(`${API_BASE}/api/mode/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        alert(json.error || json.message || 'Erro ao alternar modo');
        return;
      }
      await refreshStatusSnapshot();
    } catch (e) {
      console.error('Erro ao alternar modo operacional', e);
      alert('Erro ao alternar modo operacional');
    } finally {
      setModeUpdating(false);
    }
  };

  const handleManualCloseTrade = async (trade) => {
    const symbol = trade?.raw_symbol || trade?.symbol;
    if (!symbol || trade?.isSignalCard) return;
    if (!confirm(`Fechar manualmente a operação de ${trade.symbol}?`)) return;

    try {
      setManualClosingSymbol(String(trade.symbol || symbol).toUpperCase());
      const res = await fetch(`${API_BASE}/api/trade/manual-close`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        alert(json.error || 'Erro ao fechar operação manualmente');
        return;
      }
      await refreshStatusSnapshot();
    } catch (e) {
      console.error(e);
      alert('Erro ao fechar operação manualmente');
    } finally {
      setManualClosingSymbol(null);
    }
  };

  const handleFieldChange = (key, value) => setAddFormFields(prev => ({ ...prev, [key]: value }));
  const upsertInvestor = (client) => {
    if (!client?.id) return;
    setInvestidores(prev => {
      const normalized = normalizeInvestorRecord(client);
      const existingIndex = prev.findIndex(inv => Number(inv.id) === Number(client.id));
      if (existingIndex === -1) return [normalized, ...prev];
      const next = [...prev];
      next[existingIndex] = { ...next[existingIndex], ...normalized };
      return next;
    });
  };

  // Lista de pessoas (será alimentada pelo banco local futuramente)
  const [investidores, setInvestidores] = useState([]);
  const currentOperationMode = normalizeOperationMode(data.operation_mode);
  const currentOperationMeta = OPERATION_MODE_META[currentOperationMode] || OPERATION_MODE_META.paper;
  const formAccountMode = normalizeAccountMode(addFormFields.account_mode);
  const formBalanceLabel = formAccountMode === 'testnet' ? 'Saldo sincronizado da Testnet' : 'Saldo sincronizado da Conta Real';
  const formBalancePlaceholder = formAccountMode === 'testnet' ? 'Será lido da Bybit Testnet' : 'Será lido da Bybit Real';

  // Métricas live derivadas dos trades abertos (atualiza cards do topo em tempo real)
  const activeTrades = data.active_trades || [];
  const openWinningTrades = activeTrades.filter(t => Number(t?.pnl_pct || 0) > 0).length;
  const openLosingTrades = activeTrades.filter(t => Number(t?.pnl_pct || 0) < 0).length;
  const totalWinningTrades = Number(data.winning_trades || 0) + openWinningTrades;
  const totalLosingTrades = Number(data.losing_trades || 0) + openLosingTrades;
  const totalClosedAndOpen = totalWinningTrades + totalLosingTrades;
  const liveWinRate = totalClosedAndOpen > 0 ? (totalWinningTrades / totalClosedAndOpen) * 100 : 0;

  const unrealizedPnl = activeTrades.reduce((acc, trade) => {
    const entryValue = Number(trade?.entry || 0);
    const pnlPct = Number(trade?.pnl_pct || 0);
    if (!entryValue || !Number.isFinite(entryValue) || !Number.isFinite(pnlPct)) return acc;
    return acc + (entryValue * pnlPct) / 100;
  }, 0);

  const realizedPnl = Number(data.pnl_total || 0);
  const totalPnlLive = realizedPnl + unrealizedPnl;
  const syncedBalance = Number(data.balance ?? 0);
  const currentBalanceLive = syncedBalance + unrealizedPnl;
  const latestSignal = data.last_sniper_signal;
  const evidence = data.evidence || {};
  const signalAlreadyListed = latestSignal && activeTrades.some((trade) => (
    String(trade?.symbol || '').toUpperCase() === String(latestSignal?.symbol || '').toUpperCase()
    && String(trade?.side || '').toUpperCase() === String(latestSignal?.side || '').toUpperCase()
  ));
  const monitorTrades = activeTrades.length > 0
    ? activeTrades.slice(0, 5).map((trade) => ({ ...trade, isSignalCard: false }))
    : latestSignal && !signalAlreadyListed
      ? [{
          id: `signal-${latestSignal.received_at || latestSignal.symbol}`,
          symbol: latestSignal.symbol,
          side: latestSignal.side,
          entry_price: latestSignal.entry_price,
          current_price: latestSignal.current_price,
          price_change_pct: latestSignal.price_change_pct,
          pnl_pct: latestSignal.pnl_pct ?? 0,
          confidence: latestSignal.confidence,
          trend: latestSignal.trend,
          is_favorable: latestSignal.is_favorable,
          isSignalCard: true,
          client_count: 0,
          open_pnl_value: 0,
          entry: 0,
        }]
      : [];
  const monitorSlots = [...monitorTrades, ...Array.from({ length: Math.max(0, 5 - monitorTrades.length) }, (_, idx) => ({ id: `empty-${idx}`, empty: true }))];
  const recentClosedTrades = (data.trades || []).filter((trade) => String(trade?.status || '').toLowerCase() === 'closed').slice(0, 5);
  const evidenceChecks = evidence.checks || [];
  const evidenceBrains = evidence.brains || {};
  const statusHeadline = activeTrades.length > 0
    ? `${Math.min(activeTrades.length, 5)} SINAL${activeTrades.length > 1 ? 'S' : ''} ABERTO${activeTrades.length > 1 ? 'S' : ''}`
    : (data.opportunities?.length || 0) > 0
      ? `RADAR: ${data.opportunities?.[0]?.symbol || data.symbol || '---'}`
      : 'SCANNING MARKETS...';
  const statusSubline = activeTrades.length > 0
    ? `${monitorTrades.map((trade) => trade.symbol).slice(0, 5).join(' • ')}`
    : `RIGOR ${evidence.threshold || 60}% • ${evidence.position_mode || '5 moedas diferentes'}`;

  return (
    <div className="min-h-screen bg-[#050505] text-white font-sans selection:bg-green-500/30">
      
      {/* HEADER INTEGRADO (Dashboard | Evidência | Gestão) */}
      <header className="border-b border-white/5 bg-[#0a0b0d] px-8 py-4 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-green-500 rounded-lg flex items-center justify-center shadow-lg shadow-green-500/40">
            <Zap size={24} className="text-black fill-current" />
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tighter italic">
              MOTOR <span className="text-green-500 uppercase">SNIPER v60.7</span>
            </h1>
            <p className="text-[8px] text-zinc-500 font-bold tracking-[0.3em] uppercase">Triplo Cérebro • Cloud Brain Active</p>
          </div>
        </div>

        <nav className="flex bg-black p-1 rounded-xl border border-white/10">
          <TabButton active={activeTab === 'dashboard'} onClick={() => setActiveTab('dashboard')} icon={<LayoutDashboard size={16}/>} label="DASHBOARD" />
          <TabButton active={activeTab === 'evidence'} onClick={() => setActiveTab('evidence')} icon={<FileSearch size={16}/>} label="EVIDÊNCIA" />
          <TabButton active={activeTab === 'gestao'} onClick={() => setActiveTab('gestao')} icon={<Users size={16}/>} label="GESTÃO" />
        </nav>

        <div className="hidden md:flex items-center gap-4">
           <div className={`px-4 py-1.5 rounded-full border flex items-center gap-2 ${currentOperationMeta.shell}`}>
              <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${currentOperationMeta.dot}`} />
              <span className="text-[10px] font-black uppercase italic">
                {currentOperationMeta.badge}
              </span>
           </div>

           <div className="flex bg-black p-1 rounded-xl border border-white/10">
             {['paper', 'testnet', 'real'].map((mode) => (
               <button
                 key={mode}
                 type="button"
                 disabled={modeUpdating}
                 onClick={() => handleOperationModeChange(mode)}
                 className={`px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${
                   currentOperationMode === mode
                     ? 'bg-green-500 text-black'
                     : 'text-zinc-500 hover:text-white hover:bg-white/5'
                 } ${modeUpdating ? 'opacity-50 cursor-not-allowed' : ''}`}
               >
                 {OPERATION_MODE_META[mode].badge}
               </button>
             ))}
           </div>
           
           <div className="bg-zinc-900/50 px-4 py-1.5 rounded-full border border-green-500/20 flex items-center gap-2">
              <div className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
              <span className="text-[10px] font-black text-green-500 uppercase italic">{data.execution_label || data.status || 'Conectando...'}</span>
           </div>
        </div>
      </header>

      <main className="p-8 max-w-[1800px] mx-auto">
        
        {/* ABA 1: DASHBOARD (Igual ao seu print) */}
        {activeTab === 'dashboard' && (
          <div className="animate-in fade-in duration-500 space-y-8">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              <KpiCard 
                label={currentOperationMode === 'paper' ? "🧪 SALDO PAPER (USDT)" : `💰 SALDO ${currentOperationMode === 'testnet' ? 'TESTNET' : 'REAL'} (USDT)`} 
                value={`$${(currentOperationMode === 'paper' ? currentBalanceLive : syncedBalance).toLocaleString('pt-PT', { maximumFractionDigits: 2 })}`}
                sub={currentOperationMode === 'paper'
                  ? `Base: $${syncedBalance.toLocaleString('pt-PT', { maximumFractionDigits: 2 })} • Aberto: $${unrealizedPnl.toLocaleString('pt-PT', { maximumFractionDigits: 2 })}`
                  : (data.status || data.execution_label || data.operation_mode_label || 'Modo Produção')}
                icon={<Database size={18}/>} 
                emerald 
              />
              <KpiCard label="TRADES ATIVOS" value={`${Math.min(data.active_trades?.length || 0, 5)}/5`} sub="5 moedas diferentes • Ordem 15% da banca • TP 100% • SL 3%" icon={<Database size={18}/>} />
              <KpiCard label="RADAR LIVE" value={data.symbol || "---"} sub="TOP VOLUME BYBIT" icon={<Activity size={18}/>} highlight={data.confidence >= 60} />
              <KpiCard label="IA CONFIANÇA" value={`${data.confidence}%`} progress={data.confidence} icon={<ShieldCheck size={18}/>} emerald={data.confidence >= 60} highlight={data.confidence >= 60} />
            </div>

            {/* 📊 CARDS DE P&L */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              <KpiCard 
                label="📈 P&L TOTAL (USDT)" 
                value={`${totalPnlLive >= 0 ? '+' : ''}$${totalPnlLive.toLocaleString('pt-PT', { maximumFractionDigits: 2 })}`}
                sub={`Realizado: $${realizedPnl.toLocaleString('pt-PT', { maximumFractionDigits: 2 })} • Aberto: $${unrealizedPnl.toLocaleString('pt-PT', { maximumFractionDigits: 2 })}`}
                icon={<TrendingUp size={18}/>} 
                emerald={totalPnlLive >= 0}
              />
              <KpiCard 
                label="✅ TRADES VENCEDORES" 
                value={`${totalWinningTrades}`}
                sub={`${liveWinRate.toFixed(1)}% de Taxa de Acerto`}
                icon={<CheckCircle2 size={18}/>} 
              />
              <KpiCard 
                label="❌ TRADES PERDEDORES" 
                value={`${totalLosingTrades}`}
                sub={`${(100 - liveWinRate).toFixed(1)}% de Perdas`}
                icon={<Trash2 size={18}/>} 
              />
              <KpiCard 
                label="💰 SALDO ATUAL" 
                value={`$${currentBalanceLive.toLocaleString('pt-PT', { maximumFractionDigits: 2 })}`}
                sub={`Base: $${syncedBalance.toLocaleString('pt-PT', { maximumFractionDigits: 2 })} • Variação aberta: $${unrealizedPnl.toLocaleString('pt-PT', { maximumFractionDigits: 2 })}`}
                icon={<Database size={18}/>} 
                emerald={currentBalanceLive >= syncedBalance}
              />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2 bg-[#0d0e12] rounded-[2.5rem] border border-white/5 p-10">
                <div className="flex justify-between items-center mb-8">
                   <h3 className="text-xs font-black text-zinc-500 uppercase tracking-[0.3em] italic flex items-center gap-3">
                      <TrendingUp size={16} className="text-green-500" /> Monitor Sniper Multi-Ativo
                   </h3>
                   <span className="text-[10px] font-black text-zinc-600 uppercase tracking-widest">{Math.min(data.active_trades?.length || 0, 5)}/5 ativos</span>
                </div>
                 <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                   {monitorSlots.map((trade, idx) => trade.empty ? (
                     <div key={trade.id} className="bg-black/20 border border-dashed border-white/10 rounded-[2rem] p-6 min-h-[210px] flex flex-col justify-between">
                       <div className="flex items-center justify-between">
                         <span className="text-[10px] font-black uppercase tracking-widest text-zinc-600">Slot {idx + 1}</span>
                         <span className="text-[10px] font-black uppercase tracking-widest text-zinc-700">Livre</span>
                       </div>
                       <div className="text-center py-6">
                         <div className="w-12 h-12 mx-auto rounded-2xl bg-zinc-900 flex items-center justify-center text-zinc-700 mb-4"><Zap size={18} /></div>
                         <p className="text-lg font-black italic text-zinc-700">AGUARDANDO MOEDA</p>
                           <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mt-2">Cada ordem usa 15% da banca • TP 100% • SL 3%</p>
                       </div>
                       <div className="h-2 rounded-full bg-zinc-900" />
                     </div>
                   ) : (
                     <div key={trade.id} className={`rounded-[2rem] border p-6 min-h-[210px] flex flex-col justify-between transition-all ${trade.isSignalCard ? 'bg-green-500/[0.03] border-green-500/20' : 'bg-zinc-900/30 border-white/5 hover:bg-zinc-900/50'}`}>
                       <div className="flex items-start justify-between gap-4">
                         <div className="flex items-center gap-4">
                           <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${getTradeTone(trade) ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                             {getTradeTone(trade) ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
                           </div>
                           <div>
                             <div className="flex items-center gap-2 flex-wrap">
                               <h4 className="text-2xl font-black italic">{trade.symbol}</h4>
                               <span className={`px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-widest ${getTradeStatusClasses(trade)}`}>
                                 {getTradeStatusLabel(trade)}
                               </span>
                             </div>
                              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mt-2">
                                {trade.side} • ENTRADA ${formatEntryPrice(trade.entry_price ?? trade.entry)} • AGORA {hasLivePrice(trade) ? `$${formatEntryPrice(trade.current_price)}` : '--'}
                              </p>
                             <p className="text-[10px] font-bold uppercase tracking-widest mt-2 text-zinc-400">
                               {trade.client_count > 0 ? `${trade.client_count} conta(s) nesta moeda` : 'Sinal aguardando execucao'}
                             </p>
                           </div>
                          </div>
                          <div className="text-right">
                            <p className={`text-3xl font-black italic ${getTradeTone(trade) ? 'text-green-500' : 'text-red-500'}`}>
                              {hasLivePrice(trade) ? formatSignedPercent(trade.pnl_pct || 0) : '--'}
                            </p>
                            <p className={`text-sm font-black ${getTradeTone(trade) ? 'text-green-400' : 'text-red-400'}`}>
                              {formatDollar(trade.open_pnl_value || 0)}
                            </p>
                         </div>
                       </div>

                        <div className="space-y-3">
                         <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-widest">
                           <span className="text-zinc-500">{getTradeRelationLabel(trade)}</span>
                           <span className={getTradeTone(trade) ? 'text-green-500' : 'text-red-500'}>{getTradeProgressText(trade)}</span>
                         </div>
                         <div className="h-2 rounded-full bg-black/50 overflow-hidden">
                           <div
                             className={`h-full rounded-full transition-all ${getTradeTone(trade) ? 'bg-green-500' : 'bg-red-500'}`}
                             style={{ width: `${getTradeProgressPercent(trade)}%` }}
                           />
                         </div>
                          <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest">
                            <span className="text-zinc-500">
                              {trade.isSignalCard ? `Confiança ${trade.confidence || 0}%` : `Margem ${formatDollar(trade.entry || 0)}`}
                            </span>
                             <span className={getTradeTone(trade) ? 'text-green-500' : 'text-red-500'}>
                               {hasLivePrice(trade) ? formatSignedPercent(trade.price_change_pct || 0) : '--'}
                             </span>
                          </div>
                          {!trade.isSignalCard && (
                            <button
                              type="button"
                              onClick={() => handleManualCloseTrade(trade)}
                              disabled={manualClosingSymbol === String(trade.symbol || '').toUpperCase()}
                              className="w-full rounded-2xl border border-green-500/30 bg-green-500/10 px-4 py-3 text-[10px] font-black uppercase tracking-widest text-green-400 transition-all hover:bg-green-500/15 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {manualClosingSymbol === String(trade.symbol || '').toUpperCase() ? 'Saindo...' : 'Sair manual'}
                            </button>
                          )}
                        </div>
                      </div>
                   ))}
                 </div>
              </div>

              <div className="bg-[#0d0e12] rounded-[2.5rem] border border-white/5 p-10 flex flex-col items-center justify-center text-center relative overflow-hidden">
                <div className="absolute top-6 right-6 text-[8px] font-black text-zinc-600 tracking-widest uppercase">Escada: 60/70/80</div>
                <div className="w-48 h-48 rounded-full border-[6px] border-zinc-900 flex items-center justify-center relative mb-8">
                   <div className="absolute inset-0 rounded-full border-[6px] border-green-500 border-t-transparent animate-spin-slow opacity-20" />
                    <Zap size={60} className="text-green-500 fill-current drop-shadow-[0_0_20px_rgba(34,197,94,0.5)]" />
                </div>
                <h3 className="text-xl font-black italic mb-2 uppercase">{statusHeadline}</h3>
                <p className="text-[8px] text-zinc-600 font-bold uppercase tracking-widest leading-loose">{statusSubline}</p>
              </div>
            </div>

            <div className="bg-[#0d0e12] p-10 rounded-[3rem] border border-white/5">
               <h4 className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.5em] mb-4 flex items-center gap-3">
                  <Search size={14} /> Veredito Institucional (Cloud Mode)
               </h4>
               <p className="text-2xl font-medium italic text-zinc-300">"{data.ia2_decision.motivo}"</p>
            </div>

            <div className="bg-[#0d0e12] p-10 rounded-[3rem] border border-white/5">
              <div className="flex items-center justify-between mb-6">
                <h4 className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.5em] flex items-center gap-3">
                  <Target size={14} /> Top Oportunidades do Ciclo
                </h4>
                <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">
                  {data.opportunities?.length || 0} ativas
                </span>
              </div>

              {data.opportunities && data.opportunities.length > 0 ? (
                <div className="space-y-3">
                  {data.opportunities.map((op, idx) => (
                    <div key={`${op.symbol}-${idx}`} className="bg-zinc-900/30 border border-white/5 rounded-2xl p-4 flex items-center justify-between">
                      <div>
                        <p className="text-lg font-black italic text-white">{op.symbol}</p>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                          {op.decisao} • {op.probabilidade}% • Score {op.score}
                        </p>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-green-500 mt-1">
                          Dinheiro Forte {op.money_flow_score || 0} • Fluxo {op.money_flow_side || 'WAIT'} • Volume x{op.volume_ratio || 0}
                        </p>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mt-1">
                          Lucro Histórico {formatDollar(op.profit_total || 0)} • Win Rate {Number(op.win_rate || 0).toFixed(1)}% • Base {op.sample_size || 0}
                        </p>
                        <p className="text-xs text-zinc-400 mt-1">{op.motivo}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs font-black uppercase text-zinc-500">Rank</p>
                        <p className="text-2xl font-black italic text-green-500">#{idx + 1}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-zinc-500 text-sm italic">Sem oportunidades ranqueadas neste ciclo.</p>
              )}
            </div>
          </div>
        )}

        {/* ABA 2: EVIDÊNCIA (Igual ao seu print) */}
        {activeTab === 'evidence' && (
          <div className="animate-in fade-in duration-500 grid grid-cols-1 lg:grid-cols-4 gap-8">
            <div className="lg:col-span-3 space-y-6">
              <div className="bg-[#0d0e12] min-h-[550px] rounded-[3rem] border border-zinc-800 border-dashed p-10 flex flex-col">
                 <div className="flex items-start justify-between gap-6">
                   <div className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.4em] italic">Raio-X Triplo Cérebro</div>
                   <div className="px-4 py-2 rounded-full border border-green-500/20 bg-green-500/5 text-[10px] font-black text-green-500 uppercase tracking-widest">
                     {evidence.side || 'SCANNER'} • {Number(evidence.confidence || 0).toFixed(0)}%
                   </div>
                 </div>

                 <div className="flex-1 flex flex-col items-center justify-center text-center">
                    <div className="w-20 h-20 bg-zinc-900 rounded-3xl flex items-center justify-center mb-6 border border-white/5">
                       <FileSearch size={40} className="text-zinc-700" />
                    </div>
                    <h2 className="text-4xl font-black italic uppercase tracking-tighter mb-4">{evidence.symbol || data.symbol || '---'}</h2>
                    <p className="text-zinc-500 text-sm font-bold uppercase tracking-widest text-center max-w-2xl leading-relaxed italic">
                       {data.ia2_decision?.motivo || evidence.strategic_reason || 'O Framework Tactical gera evidências matemáticas baseadas na lógica de cloud.'}
                    </p>
                    <div className="mt-10 px-12 py-4 bg-green-500 text-black font-black rounded-2xl shadow-xl shadow-green-900/20 uppercase text-xs tracking-widest">
                      Evidência Tática • Rigor {evidence.threshold || 60}%
                    </div>
                 </div>

                 <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-6">
                   {Object.entries(evidenceBrains).map(([key, brain]) => (
                     <div key={key} className="bg-black/20 p-6 rounded-[2rem] border border-white/5">
                       <div className="text-[10px] font-black text-zinc-600 uppercase tracking-widest">{brain.label}</div>
                       <div className="flex items-end justify-between mt-5">
                         <div className="text-4xl font-black italic text-white">{brain.score ?? 0}</div>
                         <div className="text-[10px] font-black text-green-500 uppercase tracking-widest">Peso {brain.weight}%</div>
                       </div>
                     </div>
                   ))}
                 </div>

                 <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                   <div className="bg-black/20 p-6 rounded-[2rem] border border-white/5">
                     <div className="text-[10px] font-black text-zinc-600 uppercase tracking-widest mb-4">Entradas em aberto</div>
                     <div className="space-y-3">
                       {monitorTrades.length > 0 ? monitorTrades.map((trade) => (
                         <div key={`evidence-open-${trade.id}`} className="flex items-center justify-between gap-4 p-4 rounded-2xl border border-white/5 bg-zinc-950/40">
                           <div>
                             <div className="text-sm font-black italic">{trade.symbol}</div>
                             <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">{trade.side} • Entrada {formatDollar(trade.entry_price ?? trade.entry)}</div>
                           </div>
                           <div className="text-right">
                             <div className={`text-sm font-black ${getTradeTone(trade) ? 'text-green-500' : 'text-red-500'}`}>{formatDollar(trade.current_price || trade.entry_price || trade.entry)}</div>
                             <div className={`text-[10px] font-bold uppercase tracking-widest ${getTradeTone(trade) ? 'text-green-500' : 'text-red-500'}`}>{formatSignedPercent(trade.pnl_pct || trade.price_change_pct || 0)}</div>
                           </div>
                         </div>
                       )) : <p className="text-sm text-zinc-500 italic">Sem entradas abertas no momento.</p>}
                     </div>
                   </div>

                   <div className="bg-black/20 p-6 rounded-[2rem] border border-white/5">
                     <div className="text-[10px] font-black text-zinc-600 uppercase tracking-widest mb-4">Lucro e perda recente</div>
                     <div className="space-y-3">
                       {recentClosedTrades.length > 0 ? recentClosedTrades.map((trade) => {
                         const profit = Number(trade?.profit || 0);
                         return (
                           <div key={`evidence-closed-${trade.id}`} className="flex items-center justify-between gap-4 p-4 rounded-2xl border border-white/5 bg-zinc-950/40">
                             <div>
                               <div className="text-sm font-black italic">{String(trade?.pair || '---').split(':')[0]}</div>
                               <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">{trade?.side || '---'} • {trade?.closed_at || 'Sem data'}</div>
                             </div>
                             <div className={`text-sm font-black ${profit >= 0 ? 'text-green-500' : 'text-red-500'}`}>{formatDollar(profit)}</div>
                           </div>
                         );
                       }) : <p className="text-sm text-zinc-500 italic">Ainda não há fechamentos para exibir.</p>}
                     </div>
                   </div>
                 </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-[#0d0e12] p-8 rounded-[2.5rem] border border-white/5">
                  <span className="text-[10px] font-black text-zinc-600 uppercase tracking-widest flex items-center gap-3 mb-4"><TrendingUp size={14} className="text-green-500" /> Logica Neural</span>
                  <p className="text-xs text-zinc-400 italic leading-relaxed">{evidence.local_reason || 'Aguardando leitura do Motor Matemático.'}</p>
                </div>
                <div className="bg-[#0d0e12] p-8 rounded-[2.5rem] border border-white/5">
                  <span className="text-[10px] font-black text-zinc-600 uppercase tracking-widest flex items-center gap-3 mb-4"><ShieldCheck size={14} className="text-blue-500" /> Critica de Risco</span>
                  <p className="text-xs text-zinc-400 italic leading-relaxed">{evidence.tactical_reason || evidence.strategic_reason || 'Aguardando crítica do Radar Tático.'}</p>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.4em] mb-6 px-2 italic flex items-center gap-3"><Activity size={14} className="text-green-500" /> Confluências Tactical</h3>
              {evidenceChecks.map((item) => (
                <CheckItem key={item.label} label={`${item.label}${item.detail ? ` • ${item.detail}` : ''}`} active={Boolean(item.active)} />
              ))}
              
               <div className="mt-12 bg-green-500/5 p-8 rounded-[3rem] border border-green-500/10">
                  <div className="flex items-center gap-3 mb-4">
                     <CheckCircle2 size={20} className="text-green-500" />
                     <span className="text-[10px] font-black text-zinc-200 uppercase tracking-widest">Certificação Tactical</span>
                  </div>
                  <p className="text-[9px] text-zinc-500 font-bold uppercase leading-relaxed italic">
                     TRIPLO CÉREBRO COM RIGOR DE {evidence.threshold || 60}% • ATÉ {evidence.max_positions || 5} ENTRADAS SIMULTÂNEAS, SEM REPETIR MOEDA • ORDEM 15% DA BANCA • TP 100% E SL 3%.
                  </p>
               </div>
            </div>
          </div>
        )}

        {/* ABA 3: GESTÃO DE PESSOAS (NOVIDADE SaaS) */}
        {activeTab === 'gestao' && (
          <div className="animate-in slide-in-from-bottom-6 duration-700">
            <div className="flex flex-col md:flex-row justify-between items-end mb-12 gap-6">
              <div>
                <h2 className="text-4xl font-black italic tracking-tighter uppercase mb-2">Gestão SaaS de Investidores</h2>
                <p className="text-zinc-500 text-sm font-bold uppercase tracking-widest">Armazenamento de chaves API e banca dinâmica na nuvem.</p>
              </div>
              <button 
                onClick={openNewInvestorModal}
                className="bg-green-500 hover:bg-green-400 text-black font-black px-10 py-5 rounded-3xl flex items-center gap-3 transition-all transform active:scale-95 shadow-2xl shadow-green-900/30 uppercase text-xs tracking-widest"
              >
                + Novo Investidor
              </button>
            </div>

            <div className="bg-[#0d0e12] rounded-[3rem] border border-white/5 overflow-hidden shadow-2xl">
              <table className="w-full text-left">
                <thead className="bg-zinc-950 text-zinc-600 text-[9px] font-black uppercase tracking-[0.3em] border-b border-white/5">
                  <tr>
                    <th className="p-8">Investidor</th>
                    <th className="p-8">Saldo USDT</th>
                    <th className="p-8">PNL Ciclo</th>
                    <th className="p-8">Status</th>
                    <th className="p-8 text-right">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {investidores.map(inv => (
                    <tr key={inv.id} className="hover:bg-green-500/[0.02] transition-all">
                      <td className="p-8">
                        <div className="font-black italic text-xl uppercase">{inv.nome}</div>
                        <div className="flex items-center gap-2 mt-3 flex-wrap">
                          <span className={`px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-widest ${String(inv.account_mode || inv.mode || 'TESTNET').toUpperCase() === 'REAL' ? 'bg-green-500/10 border-green-500/30 text-green-400' : 'bg-blue-500/10 border-blue-500/30 text-blue-300'}`}>
                            {String(inv.account_mode || inv.mode || 'TESTNET').toUpperCase() === 'REAL' ? 'Conta Real' : 'Conta Testnet'}
                          </span>
                          <span className={`px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-widest ${String(inv.storage_source || 'LOCAL').toUpperCase() === 'SUPABASE' ? 'bg-blue-500/10 border-blue-500/30 text-blue-300' : 'bg-zinc-800 border-white/10 text-zinc-300'}`}>
                            {String(inv.storage_source || 'LOCAL').toUpperCase()}
                          </span>
                        </div>
                      </td>
                      <td className="p-8 font-mono text-zinc-400 font-bold">${Number(inv.saldo_real ?? inv.banca ?? 0).toLocaleString()}</td>
                      <td className="p-8 font-black text-green-500 italic text-lg">{inv.pnl}</td>
                      <td className="p-8">
                        <div className="flex items-center gap-2">
                           <div className={`w-1.5 h-1.5 rounded-full ${(CLIENT_STATUS_STYLE[inv.status] || CLIENT_STATUS_STYLE_DEFAULT).dot}`} />
                           <span className={`text-[10px] font-black uppercase tracking-widest ${(CLIENT_STATUS_STYLE[inv.status] || CLIENT_STATUS_STYLE_DEFAULT).text}`}>{inv.status}</span>
                        </div>
                      </td>
                      <td className="p-8 text-right">
                        <div className="flex justify-end gap-4 text-zinc-700">
                          <button onClick={() => openEditInvestor(inv.id)} className="hover:text-white transition-colors"><Settings size={18}/></button>
                          <button onClick={() => handleDeleteInvestor(inv.id)} className="hover:text-red-500 transition-colors"><Trash2 size={18}/></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* FORMULÁRIO MODAL (Gestão de Pessoas) */}
      {showAddForm && (
        <div className="fixed inset-0 bg-black/95 backdrop-blur-xl z-[100] flex items-center justify-center p-6 animate-in fade-in duration-300">
          <div className="bg-[#0d0e12] w-full max-w-2xl rounded-[4rem] border border-zinc-800 shadow-2xl relative overflow-hidden">
            <div className="p-10 border-b border-white/5 flex justify-between items-center bg-zinc-900/20">
               <div className="flex items-center gap-5">
                  <div className="w-14 h-14 bg-green-500/10 rounded-2xl flex items-center justify-center text-green-500 border border-green-500/20">
                     <Users size={28}/>
                  </div>
                  <div>
                    <h3 className="text-2xl font-black italic uppercase tracking-tighter">Vincular Investidor</h3>
                    <p className="text-[9px] text-zinc-500 font-bold uppercase tracking-widest">Setup de Chaves e Banca Institucional</p>
                  </div>
               </div>
               <div className="flex items-center gap-3">
                 {addFormMsg && (
                   <div className={`px-4 py-2 rounded-lg ${addFormMsg.type === 'success' ? 'bg-green-500/10 border border-green-500/20 text-green-300' : 'bg-red-500/10 border border-red-500/20 text-red-300'}`}>
                     <small className="text-xs font-black uppercase">{addFormMsg.text}</small>
                   </div>
                 )}
                 <button onClick={() => { setShowAddForm(false); setAddFormMsg(null); }} className="p-4 hover:bg-zinc-800 rounded-full transition-all text-zinc-500 hover:text-white"><X size={28}/></button>
               </div>
            </div>
            <form className="p-12 space-y-8" onSubmit={async (e) => {
                e.preventDefault();
                setAddFormSaving(true);
                setAddFormMsg(null);
                const payload = {
                  nome: addFormFields.nome,
                  saldo_base: parseFloat(addFormFields.saldo_base) || 0,
                  bybit_key: addFormFields.bybit_key,
                  bybit_secret: addFormFields.bybit_secret,
                  tg_token: addFormFields.tg_token,
                  chat_id: addFormFields.chat_id,
                  account_mode: formAccountMode,
                  is_testnet: formAccountMode === 'testnet'
                };
                try {
                  // Se id definido, atualiza; caso contrário cria novo
                  if (addFormFields.id) {
                    const res = await fetch(`${API_BASE}/api/cliente/${addFormFields.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                     const json = await res.json();
                     if (res.ok) {
                       if (json.client) {
                         upsertInvestor(json.client);
                         setAddFormFields(prev => ({ ...prev, id: json.client.id, saldo_base: json.client.saldo_base ?? prev.saldo_base }));
                       }
                       const msgAtualiza = json.valid === false
                         ? `Salvo, mas API inválida: ${json.api_error || 'verifique as chaves'}`
                         : (json.msg || 'Investidor atualizado');
                       setAddFormMsg({ type: json.valid === false ? 'error' : 'success', text: msgAtualiza });
                        const invRes = await fetch(`${API_BASE}/api/investidores`); if (invRes.ok) setInvestidores((await invRes.json()).map(normalizeInvestorRecord));
                     } else {
                      setAddFormMsg({ type: 'error', text: json.error || 'Erro ao atualizar' });
                    }
                  } else {
                    const res = await fetch(`${API_BASE}/api/vincular_cliente`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                     const json = await res.json();
                     if (res.ok && json.status === 'sucesso') {
                       if (json.client) {
                         upsertInvestor(json.client);
                         setAddFormFields(prev => ({ ...prev, id: json.client.id, saldo_base: json.client.saldo_base ?? prev.saldo_base }));
                       }
                       const msgSalvo = json.valid === false
                         ? `Salvo, mas API inválida: ${json.api_error || 'verifique as chaves'}`
                         : (json.msg || 'Investidor salvo com sucesso');
                       setAddFormMsg({ type: json.valid === false ? 'error' : 'success', text: msgSalvo });
                        try { const invRes = await fetch(`${API_BASE}/api/investidores`); if (invRes.ok) setInvestidores((await invRes.json()).map(normalizeInvestorRecord)); } catch (e) { }
                     } else {
                      setAddFormMsg({ type: 'error', text: json.msg || json.error || 'Erro ao salvar investidor' });
                    }
                  }
                } catch (err) { console.error('Erro ao vincular', err); setAddFormMsg({ type: 'error', text: String(err) }); }
                setAddFormSaving(false);
                // NÃO fecha automaticamente o modal — o usuário pode revisar/editar ou fechar manualmente
              }}>
               <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="space-y-3 md:col-span-2">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Modo da Conta</label>
                      <div className="grid grid-cols-2 gap-4">
                         <button
                           type="button"
                           onClick={() => handleFieldChange('account_mode', 'testnet')}
                           className={`px-5 py-4 rounded-[1.5rem] border text-sm font-black uppercase italic transition-all ${formAccountMode === 'testnet' ? 'bg-blue-500/15 border-blue-500/40 text-blue-300' : 'bg-black border-white/10 text-zinc-500 hover:text-white'}`}
                         >
                           🛰️ Conta Testnet
                         </button>
                         <button
                           type="button"
                           onClick={() => handleFieldChange('account_mode', 'real')}
                           className={`px-5 py-4 rounded-[1.5rem] border text-sm font-black uppercase italic transition-all ${formAccountMode === 'real' ? 'bg-green-500/15 border-green-500/40 text-green-300' : 'bg-black border-white/10 text-zinc-500 hover:text-white'}`}
                         >
                           💼 Conta Real
                         </button>
                      </div>
                      <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest ml-1">
                        {formAccountMode === 'testnet'
                          ? 'A conta testnet valida chaves sandbox e sincroniza saldo da Bybit Testnet.'
                          : 'A conta real valida chaves reais e sincroniza saldo da Bybit Real.'}
                      </p>
                   </div>
                  <div className="space-y-3">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Nome do Cliente</label>
                     <input value={addFormFields.nome} onChange={(e)=>handleFieldChange('nome', e.target.value)} className="w-full bg-black border border-white/10 p-5 rounded-[1.5rem] focus:border-green-500 outline-none transition-all italic text-lg" placeholder="Ex: Roberto Ferreira" required />
                  </div>
                  <div className="space-y-3">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">{formBalanceLabel}</label>
                      <input
                        value={addFormFields.saldo_base ? `Sincronizado: ${addFormFields.saldo_base}` : ''}
                        onChange={() => {}}
                        type="text"
                        disabled
                        className="w-full p-5 rounded-[1.5rem] outline-none transition-all font-mono text-lg border bg-zinc-950 border-white/5 text-zinc-500 cursor-not-allowed"
                        placeholder={formBalancePlaceholder}
                      />
                      <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest ml-1">
                        O saldo aparece depois que a chave for validada e salva.
                      </p>
                   </div>
                </div>
               
               <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="space-y-3">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">API Key Bybit</label>
                    <input value={addFormFields.bybit_key} onChange={(e)=>handleFieldChange('bybit_key', e.target.value)} type="password" autoComplete="new-password" placeholder="••••••••••••" className="w-full bg-black border border-white/10 p-5 rounded-[1.5rem] focus:border-green-500 outline-none transition-all font-mono" required />
                  </div>
                  <div className="space-y-3">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">API Secret Bybit</label>
                    <input value={addFormFields.bybit_secret} onChange={(e)=>handleFieldChange('bybit_secret', e.target.value)} type="password" autoComplete="new-password" placeholder="••••••••••••" className="w-full bg-black border border-white/10 p-5 rounded-[1.5rem] focus:border-green-500 outline-none transition-all font-mono" required />
                  </div>
               </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div className="space-y-3">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Token Telegram (Opcional)</label>
                     <input value={addFormFields.tg_token} onChange={(e)=>handleFieldChange('tg_token', e.target.value)} placeholder="Preencha so se quiser receber sinais no Telegram" className="w-full bg-black border border-white/10 p-5 rounded-[1.5rem] focus:border-green-500 outline-none transition-all font-mono text-sm" />
                </div>
                {/* API Key Telegram removed: use only Bot Token + Chat ID */}
                <div />
              </div>

               <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-end">
                  <div className="space-y-3">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Telegram Chat ID (Opcional)</label>
                     <input value={addFormFields.chat_id} onChange={(e)=>handleFieldChange('chat_id', e.target.value)} placeholder="Preencha junto com o token se quiser alertas" className="w-full bg-black border border-white/10 p-5 rounded-[1.5rem] focus:border-green-500 outline-none transition-all font-mono" />
                     <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest ml-1 mt-2">
                       Telegram e opcional. Sem esses campos, o cliente opera so com a API da corretora.
                     </p>
                  </div>
                  <div className="flex gap-4 items-center">
                    <button type="submit" disabled={addFormSaving} className="flex-1 bg-green-500 hover:bg-green-400 text-black font-black py-6 rounded-[1.5rem] text-lg transition-all shadow-2xl shadow-green-900/30 flex items-center justify-center gap-4 uppercase italic disabled:opacity-50">
                      <Save size={20} /> {addFormSaving ? 'Salvando...' : 'Guardar Investidor'}
                    </button>
                    <button type="button" onClick={() => { setShowAddForm(false); setAddFormMsg(null); }} className="px-6 py-4 bg-zinc-900/30 border border-white/5 rounded-[1.5rem] text-zinc-300 uppercase font-black">Fechar</button>
                  </div>
               </div>
            </form>
          </div>
        </div>
      )}

      {/* FOOTER ELITE */}
      <footer className="fixed bottom-0 left-0 right-0 bg-[#0a0b0d]/90 backdrop-blur-md border-t border-white/5 px-10 py-4 flex justify-between items-center z-40">
        <div className="flex gap-10">
          <div className="flex items-center gap-3 text-[10px] font-black text-green-500 uppercase tracking-widest italic">
             <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.8)]"/>
             Motor Sniper Ativo
          </div>
          <div className="flex items-center gap-3 text-[10px] font-black text-zinc-500 uppercase tracking-widest italic">
             <ShieldCheck size={14} className="text-zinc-600"/>
             Protocolo 100/3 Verificado
           </div>
         </div>
         <p className="text-[9px] font-black text-zinc-700 uppercase tracking-[0.5em] italic">Motor Sniper v60.7 &copy; 2026</p>
       </footer>
    </div>
  );
};

// --- SUB-COMPONENTES DE DESIGN ---

const TabButton = ({ active, onClick, icon, label }) => (
  <button 
    onClick={onClick} 
    className={`flex items-center gap-3 px-8 py-3 rounded-xl transition-all uppercase text-[10px] font-black italic tracking-widest ${active ? 'bg-green-500 text-black shadow-lg shadow-green-900/20' : 'text-zinc-600 hover:bg-white/5 hover:text-zinc-300'}`}
  >
    {icon} {label}
  </button>
);

const KpiCard = ({ label, value, sub, icon, emerald, progress, highlight }) => (
  <div className={`bg-[#0d0e12] p-8 rounded-[2.5rem] border transition-all shadow-xl relative overflow-hidden group hover:border-green-500/20 transition-all ${highlight ? 'border-green-500/50 shadow-[0_0_25px_rgba(34,197,94,0.3)]' : 'border-white/5'}`}>
    <div className="flex justify-between items-start mb-6">
      <span className="text-[10px] font-black text-zinc-600 uppercase tracking-widest italic leading-none">{label}</span>
      <div className={`p-3 bg-zinc-900 rounded-2xl group-hover:scale-110 transition-transform ${highlight ? 'text-green-500' : ''}`}>{icon}</div>
    </div>
    <h2 className={`text-4xl font-black italic tracking-tighter ${emerald || highlight ? 'text-green-500' : 'text-white'}`}>{value}</h2>
    {sub && <p className="text-[8px] font-black text-zinc-700 uppercase mt-3 tracking-widest">{sub}</p>}
    {progress !== undefined && (
      <div className="mt-6 w-full h-1 bg-zinc-900 rounded-full overflow-hidden">
        <div className="h-full bg-green-500 transition-all duration-1000" style={{ width: `${progress}%` }} />
      </div>
    )}
  </div>
);

const CheckItem = ({ label, active }) => (
  <div className={`flex items-center justify-between p-6 rounded-[1.8rem] border transition-all duration-500 ${active ? 'bg-green-500/5 border-green-500/30 shadow-[0_0_15px_rgba(34,197,94,0.05)]' : 'bg-zinc-900/20 border-white/5 opacity-40'}`}>
    <span className={`text-[10px] font-black uppercase italic ${active ? 'text-green-500' : 'text-zinc-600'}`}>{label}</span>
    {active ? <CheckCircle2 size={18} className="text-green-500" /> : <div className="w-4 h-4 rounded-full border-2 border-zinc-800" />}
  </div>
);

export default App;
// Montagem do App no DOM (entrypoint Vite)
const rootEl = document.getElementById('root');
if (rootEl) {
  ReactDOM.createRoot(rootEl).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
} else {
  console.error('Elemento #root não encontrado — verifique o index.html');
}
