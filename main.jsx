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

const AGENT_THEME = {
  gemini: { accent: 'text-sky-300', border: 'border-sky-500/30', bg: 'bg-sky-500/10', chip: 'GEMINI' },
  groq: { accent: 'text-orange-300', border: 'border-orange-500/30', bg: 'bg-orange-500/10', chip: 'GROQ' },
  analyst: { accent: 'text-emerald-300', border: 'border-emerald-500/30', bg: 'bg-emerald-500/10', chip: 'DADOS' },
  learner: { accent: 'text-violet-300', border: 'border-violet-500/30', bg: 'bg-violet-500/10', chip: 'MEMÓRIA' },
  consensus: { accent: 'text-yellow-300', border: 'border-yellow-500/30', bg: 'bg-yellow-500/10', chip: 'VEREDITO' },
};

const CandleStudyChart = ({ study }) => {
  const candles = Array.isArray(study?.candles) ? study.candles.slice(-40) : [];
  if (!candles.length) {
    return (
      <div className="h-56 flex items-center justify-center rounded-[2rem] border border-dashed border-zinc-700 bg-black/20 text-zinc-500 text-xs font-bold uppercase tracking-widest italic">
        Aguardando velas do estudo técnico...
      </div>
    );
  }
  const width = 640;
  const height = 220;
  const pad = 16;
  const highs = candles.map((c) => Number(c.h));
  const lows = candles.map((c) => Number(c.l));
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const span = Math.max(max - min, 1e-9);
  const slot = (width - pad * 2) / candles.length;
  const yOf = (price) => pad + ((max - price) / span) * (height - pad * 2);
  const entry = Number(study?.entry_price || 0);
  const fib = Number(study?.fib_618 || 0);
  const sma = Number(study?.sma_200 || 0);

  return (
    <div className="w-full overflow-hidden rounded-[2rem] border border-white/5 bg-black/30 p-4">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-56">
        {sma > 0 && <line x1={pad} x2={width - pad} y1={yOf(sma)} y2={yOf(sma)} stroke="#64748b" strokeDasharray="4 4" strokeWidth="1" />}
        {fib > 0 && <line x1={pad} x2={width - pad} y1={yOf(fib)} y2={yOf(fib)} stroke="#a78bfa" strokeDasharray="3 3" strokeWidth="1.2" />}
        {entry > 0 && <line x1={pad} x2={width - pad} y1={yOf(entry)} y2={yOf(entry)} stroke="#22c55e" strokeWidth="1.5" />}
        {candles.map((c, i) => {
          const open = Number(c.o);
          const close = Number(c.c);
          const color = close >= open ? '#22c55e' : '#ef4444';
          const x = pad + i * slot + slot * 0.5;
          const bodyTop = yOf(Math.max(open, close));
          const bodyBot = yOf(Math.min(open, close));
          const bodyH = Math.max(bodyBot - bodyTop, 1.5);
          return (
            <g key={`c-${i}`}>
              <line x1={x} x2={x} y1={yOf(Number(c.h))} y2={yOf(Number(c.l))} stroke={color} strokeWidth="1.2" />
              <rect x={x - Math.max(slot * 0.28, 2)} y={bodyTop} width={Math.max(slot * 0.56, 3)} height={bodyH} fill={color} rx="1" />
            </g>
          );
        })}
      </svg>
      <div className="mt-3 flex flex-wrap gap-3 text-[9px] font-black uppercase tracking-widest text-zinc-500">
        <span className="text-green-400">Entrada</span>
        <span className="text-violet-300">Fib 0.618</span>
        <span className="text-slate-400">SMA 200</span>
        <span>{candles.length} velas</span>
      </div>
    </div>
  );
};

const AiAnalyzerCard = ({ agent }) => {
  const theme = AGENT_THEME[agent?.id] || AGENT_THEME.analyst;
  const assertiveness = Number(agent?.assertiveness || 0);
  return (
    <div className={`rounded-[2rem] border ${theme.border} ${theme.bg} p-6 flex flex-col gap-4 min-h-[240px]`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className={`text-[10px] font-black uppercase tracking-[0.35em] ${theme.accent}`}>{theme.chip}</div>
          <h4 className="text-lg font-black italic mt-2">{agent?.label || 'Analista'}</h4>
          <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest mt-1">{agent?.role || agent?.provider || 'IA'}</p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-black italic">{Number(agent?.score || 0).toFixed(0)}</div>
          <div className="text-[9px] font-black text-zinc-500 uppercase tracking-widest">Score • Peso {agent?.weight || 0}%</div>
        </div>
      </div>
      <p className="text-sm text-zinc-300 italic leading-relaxed flex-1">&ldquo;{agent?.motivo || 'Aguardando análise...'}&rdquo;</p>
      <div className="space-y-2">
        <div className="flex items-center justify-between text-[10px] font-black uppercase tracking-widest">
          <span className={theme.accent}>Ação {agent?.action || 'WAIT'}</span>
          <span className="text-zinc-400">Assertividade {assertiveness.toFixed(0)}%</span>
        </div>
        <div className="h-2 rounded-full bg-black/40 overflow-hidden">
          <div className="h-full bg-gradient-to-r from-emerald-500 to-lime-400" style={{ width: `${Math.max(4, Math.min(100, assertiveness))}%` }} />
        </div>
        {agent?.learning_notes ? (
          <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-wide leading-relaxed">Aprendeu: {agent.learning_notes}</p>
        ) : null}
      </div>
    </div>
  );
};

const AiDialogueFeed = ({ dialogue }) => {
  const items = Array.isArray(dialogue) ? dialogue : [];
  if (!items.length) {
    return <p className="text-sm text-zinc-500 italic">As IAs ainda não abriram o debate desta entrada.</p>;
  }
  return (
    <div className="space-y-3 max-h-[420px] overflow-y-auto pr-2">
      {items.map((msg, idx) => {
        const theme = AGENT_THEME[msg.speaker] || AGENT_THEME.consensus;
        return (
          <div key={`dlg-${idx}`} className={`rounded-2xl border ${theme.border} bg-black/25 p-4`}>
            <div className={`text-[9px] font-black uppercase tracking-[0.3em] mb-2 ${theme.accent}`}>{msg.label || msg.speaker}</div>
            <p className="text-sm text-zinc-300 leading-relaxed">{msg.text}</p>
          </div>
        );
      })}
    </div>
  );
};

// Sistema fixado em modo REAL apenas
const OPERATION_MODE_META = {
  real: {
    badge: '💼 REAL',
    label: 'CONTA REAL',
    dot: 'bg-red-500',
    shell: 'bg-red-500/10 border-red-500/30 text-red-400',
  },
};

const normalizeOperationMode = (value) => {
  // Sempre retorna 'real'
  return 'real';
};

const normalizeIsTestnet = (value) => {
  const raw = String(value ?? '').trim().toLowerCase();
  return raw === '1' || raw === 'true' || raw === 'yes' || raw === 'on';
};

const normalizeAccountMode = (value, isTestnet = false, endpointMode = '') => {
  const endpoint = String(endpointMode || '').trim().toLowerCase();
  if (endpoint === 'demo') return 'demo';
  const raw = String(value ?? '').trim().toLowerCase();
  if (raw === 'demo') return 'demo';
  if (raw === 'testnet' || normalizeIsTestnet(isTestnet ?? value)) return 'testnet';
  return 'real';
};

const getInvestorEnvMeta = (inv) => {
  const mode = normalizeAccountMode(inv?.account_mode, inv?.is_testnet, inv?.bybit_endpoint_mode);
  if (mode === 'demo') {
    return {
      label: '🧪 Conta Demo',
      className: 'bg-purple-500/15 border-purple-500/40 text-purple-200 hover:bg-purple-500/20',
    };
  }
  if (mode === 'testnet') {
    return {
      label: '🛰️ Testnet',
      className: 'bg-blue-500/10 border-blue-500/30 text-blue-300 hover:bg-blue-500/15',
    };
  }
  return {
    label: '💰 Saldo Real',
    className: 'bg-green-500/10 border-green-500/30 text-green-400 hover:bg-green-500/15',
  };
};

const normalizeInvestorRecord = (client) => {
  const endpointMode = client?.bybit_endpoint_mode || '';
  const accountMode = normalizeAccountMode(client?.account_mode, client?.is_testnet, endpointMode);
  return {
    ...client,
    banca: client?.saldo_real ?? client?.saldo_base ?? client?.banca ?? 0,
    saldo_real: client?.saldo_real,
    saldo_configurado: client?.saldo_base ?? client?.saldo_configurado ?? 0,
    balance_source: client?.balance_source ?? 'broker_real_balance',
    is_fake_balance: Boolean(client?.is_fake_balance) || String(client?.balance_source || '') === 'training_fake_balance',
    mode: accountMode === 'demo' ? 'DEMO' : accountMode === 'testnet' ? 'TESTNET' : 'REAL',
    account_mode: accountMode,
    bybit_endpoint_mode: endpointMode,
    is_testnet: accountMode !== 'real',
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
  if (!Number.isFinite(pnlPct)) return 'TP 100% da entrada • SL 50% da entrada';
  if (pnlPct >= 0) return `Faltam ${Math.max(0, 100 - pnlPct).toFixed(2)}% para TP`;
  return `Faltam ${Math.max(0, 50 - Math.abs(pnlPct)).toFixed(2)}% para SL`;
};

const canonicalizeTradeSymbol = (value) => {
  const raw = String(value || '').trim().toUpperCase().replace(/\s+/g, '');
  if (!raw) return '';
  if (raw.includes(':')) return raw;
  if (raw.includes('/')) {
    const [base, quote] = raw.split('/', 2);
    if (base && quote && quote === 'USDT') return `${base}/${quote}:${quote}`;
    return raw;
  }
  if (raw.endsWith('USDT') && raw.length > 4) return `${raw.slice(0, -4)}/USDT:USDT`;
  return raw;
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
  const [riskModeUpdating, setRiskModeUpdating] = useState(false);
  const [manualClosingSymbol, setManualClosingSymbol] = useState(null);
  const [showManualEntryModal, setShowManualEntryModal] = useState(false);
  const [manualEntryFields, setManualEntryFields] = useState({ symbol: '', side: 'buy', entry_price: '' });
  const [manualEntryAnalysis, setManualEntryAnalysis] = useState(null);
  const [manualEntryLoading, setManualEntryLoading] = useState(false);
  const [addFormFields, setAddFormFields] = useState({
    id: null, nome: '', saldo_base: 0, bybit_key: '', bybit_secret: '', tg_token: '', chat_id: '', account_mode: 'real', is_testnet: false, exchange: 'bybit', balance_source: 'broker_real_balance'
  });
  const [data, setData] = useState({
    balance: 0,  // Será atualizado do backend
    status: "Conectando ao backend...",
    symbol: "---",
    confidence: 0,
    opportunities: [],
    active_trades: [],
    trades: [],
    operation_mode: 'real',
    operation_mode_label: 'CONTA REAL',
    execution_enabled: false,
    execution_label: 'Aguardando configuração',
    last_sniper_signal: null,
    evidence: null,
    max_moedas_ativas: 1,
    risk_mode: 'conservative',
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
        const result = await fetchJson('/api/investidores', 15000);
        if (!result.ok) {
          if (mounted) setInvestidoresLoading(false);
          return;
        }
        if (mounted) {
          setInvestidores((result.json || []).map(normalizeInvestorRecord));
          setInvestidoresLoading(false);
        }
      } catch (e) {
        if (isAbortError(e)) {
          // Timeout: mantém a lista anterior (não limpa) e sinaliza carregado
          if (mounted) setInvestidoresLoading(false);
          return;
        }
        logApiError('Erro fetching /api/investidores', e);
        if (mounted) setInvestidoresLoading(false);
      }
    };

    fetchStatus();
    fetchInvestidores();
    const iv = setInterval(fetchStatus, 3000);
    const iv2 = setInterval(fetchInvestidores, 30000);
    return () => { mounted = false; clearInterval(iv); clearInterval(iv2); };
  }, []);

  const openNewInvestorModal = () => {
    setAddFormFields({ id: null, nome: '', saldo_base: 0, bybit_key: '', bybit_secret: '', tg_token: '', chat_id: '', account_mode: 'real', is_testnet: false, exchange: 'bybit', balance_source: 'broker_real_balance' });
    setAddFormMsg(null);
    setShowAddForm(true);
  };

  const openEditInvestor = async (id) => {
    try {
      console.log(`🔵 [FRONTEND] Carregando dados do cliente ID: ${id}`);
      const res = await fetch(`${API_BASE}/api/cliente/${id}`);
      if (!res.ok) {
        console.error(`❌ [FRONTEND] Erro ao buscar cliente ${id}: ${res.status}`);
        alert(`Erro ao carregar dados do investidor (status ${res.status})`);
        return;
      }
      const c = await res.json();
      console.log(`✅ [FRONTEND] Dados do cliente ${id} carregados:`, c);
      setAddFormFields({
        id: c.id,
        nome: c.nome || '',
        saldo_base: c.saldo_base || 0,
        bybit_key: c.bybit_key || '',
        bybit_secret: c.bybit_secret || '',
        tg_token: c.tg_token || '',
        chat_id: c.chat_id || '',
        account_mode: normalizeAccountMode(c.account_mode ?? c.is_testnet),
        is_testnet: normalizeIsTestnet(c.is_testnet),
        exchange: String(c.exchange || 'bybit').toLowerCase(),
        balance_source: c.balance_source || 'broker_real_balance',
      });
      setAddFormMsg(null);
      setShowAddForm(true);
    } catch (e) {
      console.error('❌ [FRONTEND] Exceção ao carregar cliente', e);
      alert('Erro ao conectar com o servidor ao carregar investidor');
    }
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

  const toggleInvestorBalanceSource = async (inv) => {
    if (!inv?.id) return;
    const current = String(inv.balance_source || 'broker_real_balance');
    const next = current === 'training_fake_balance' ? 'broker_real_balance' : 'training_fake_balance';
    try {
      const res = await fetch(`${API_BASE}/api/cliente/${inv.id}/balance-source`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ balance_source: next }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        alert(json.error || 'Erro ao alternar fonte de saldo');
        return;
      }
      if (json.client) upsertInvestor(json.client);
    } catch (e) {
      console.error(e);
      alert('Erro ao conectar com o servidor');
    }
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

  const handleRiskModeChange = async (newMode) => {
    if (riskModeUpdating || newMode === data.risk_mode) return;
    try {
      setRiskModeUpdating(true);
      const res = await fetch(`${API_BASE}/api/config/risk-mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: newMode }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        alert(json.error || 'Erro ao alternar modo de risco');
        return;
      }
      setData(prev => ({
        ...prev,
        risk_mode: json.risk_mode,
        max_moedas_ativas: json.max_moedas_ativas,
      }));
    } catch (e) {
      console.error('Erro ao alternar modo de risco', e);
      alert('Erro ao alternar modo de risco');
    } finally {
      setRiskModeUpdating(false);
    }
  };


  const handleManualCloseTrade = async (trade) => {
    const symbol = canonicalizeTradeSymbol(trade?.raw_symbol || trade?.symbol);
    const side = String(trade?.side || '').trim().toUpperCase();
    if (!symbol || trade?.isSignalCard) return;
    if (!confirm(`Fechar manualmente a operação de ${trade.symbol}?`)) return;

    try {
      setManualClosingSymbol(String(trade.symbol || symbol).toUpperCase());
      const res = await fetch(`${API_BASE}/api/trade/manual-close`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, ...(side ? { side } : {}) }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        alert(json.message || json.error || 'Erro ao fechar operação manualmente');
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

  const handleManualEntryFieldChange = (key, value) => {
    setManualEntryFields(prev => ({ ...prev, [key]: value }));
  };

  const handleGetManualEntryAnalysis = async () => {
    if (!manualEntryFields.symbol) {
      alert('Por favor, insira o símbolo do ativo (ex: BTC/USDT)');
      return;
    }

    setManualEntryLoading(true);
    setManualEntryAnalysis(null);

    try {
      const res = await fetch(`${API_BASE}/api/trade/manual-entry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: manualEntryFields.symbol,
          side: manualEntryFields.side,
          entry_price: manualEntryFields.entry_price || null,
          force_execute: false
        }),
      });

      const json = await res.json();

      if (!res.ok || !json.success) {
        alert(json.error || 'Erro ao buscar análise');
        return;
      }

      setManualEntryAnalysis(json);
    } catch (e) {
      console.error(e);
      alert('Erro ao conectar com o servidor');
    } finally {
      setManualEntryLoading(false);
    }
  };

  const handleExecuteManualEntry = async () => {
    if (!manualEntryFields.symbol) {
      alert('Por favor, insira o símbolo do ativo');
      return;
    }

    if (!confirm(`Confirma a entrada manual em ${manualEntryFields.symbol} (${manualEntryFields.side === 'buy' ? 'COMPRAR' : 'VENDER'})?`)) {
      return;
    }

    setManualEntryLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/trade/manual-entry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: manualEntryFields.symbol,
          side: manualEntryFields.side,
          entry_price: manualEntryFields.entry_price || null,
          force_execute: true
        }),
      });

      const json = await res.json();

      if (!res.ok || !json.success) {
        alert(json.error || 'Erro ao executar entrada manual');
        return;
      }

      alert('✅ Entrada manual executada com sucesso!');
      setShowManualEntryModal(false);
      setManualEntryFields({ symbol: '', side: 'buy', entry_price: '' });
      setManualEntryAnalysis(null);
      await refreshStatusSnapshot();
    } catch (e) {
      console.error(e);
      alert('Erro ao conectar com o servidor');
    } finally {
      setManualEntryLoading(false);
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


  // Lista de pessoas (alimentada pelo banco SQLite local)
  const [investidores, setInvestidores] = useState([]);
  const [investidoresLoading, setInvestidoresLoading] = useState(true);
  const currentOperationMode = normalizeOperationMode(data.operation_mode);
  const currentOperationMeta = OPERATION_MODE_META[currentOperationMode] || OPERATION_MODE_META.real;
  const formExchangeLabel = 'Bybit';
  const formIsTestnet = normalizeIsTestnet(addFormFields.is_testnet);
  const formAccountMode = normalizeAccountMode(
    addFormFields.account_mode,
    addFormFields.is_testnet,
    addFormFields.bybit_endpoint_mode,
  );
  const formIsDemoAccount = formAccountMode === 'demo' || (formIsTestnet && formAccountMode !== 'real');
  const formBalanceLabel = `Saldo sincronizado (${formIsTestnet ? (formAccountMode === 'demo' ? 'Demo' : 'Testnet') : 'Mainnet'})`;
  const formBalancePlaceholder = formIsTestnet
    ? (formAccountMode === 'demo' ? 'Será lido da Bybit Demo Trading' : 'Será lido da Bybit Testnet')
    : 'Será lido da Bybit Mainnet';

  const setInvestorEnvironment = (mode) => {
    // mode: 'real' | 'demo' | 'testnet'
    const normalized = mode === 'real' ? 'real' : (mode === 'testnet' ? 'testnet' : 'demo');
    setAddFormFields((prev) => ({
      ...prev,
      account_mode: normalized,
      is_testnet: normalized !== 'real',
      bybit_endpoint_mode: normalized === 'real' ? 'mainnet' : (normalized === 'demo' ? 'demo' : 'testnet'),
      balance_source: 'broker_real_balance',
      exchange: 'bybit',
    }));
  };

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
  const tribunalAgents = Array.isArray(evidence.agents) && evidence.agents.length
    ? evidence.agents
    : Object.entries(evidence.brains || {}).map(([id, brain]) => ({
        id,
        label: brain.label || id,
        score: brain.score || 0,
        weight: brain.weight || 0,
        action: brain.action || 'WAIT',
        motivo: brain.motivo || '',
        assertiveness: brain.assertiveness || evidence.assertiveness || 0,
        provider: brain.provider || 'local',
        role: brain.label || id,
        learning_notes: brain.learning_notes || '',
      }));
  const candleStudy = evidence.candle_study || {};
  const dialogue = evidence.dialogue || data.ai_tribunal?.dialogue || [];
  const overallAssertiveness = Number(evidence.assertiveness || data.ai_tribunal?.assertiveness || data.win_rate || 0);
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
  const statusHeadline = activeTrades.length > 0
    ? `${Math.min(activeTrades.length, 5)} SINAL${activeTrades.length > 1 ? 'S' : ''} ABERTO${activeTrades.length > 1 ? 'S' : ''}`
    : (data.opportunities?.length || 0) > 0
      ? `RADAR: ${data.opportunities?.[0]?.symbol || data.symbol || '---'}`
      : 'SCANNING MARKETS...';
  const statusSubline = activeTrades.length > 0
    ? `${monitorTrades.map((trade) => trade.symbol).slice(0, 5).join(' • ')}`
    : `RIGOR ${evidence.threshold || 60}% • ${data.risk_mode === 'aggressive' ? '5 moedas simultâneas' : '1 moeda por vez'}`;

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
           <button
             type="button"
             onClick={() => setShowManualEntryModal(true)}
             className="px-4 py-2 bg-green-500 hover:bg-green-600 text-black font-black text-xs rounded-xl uppercase tracking-wider transition-all flex items-center gap-2 shadow-lg shadow-green-500/30"
           >
             <Target size={16} />
             ENTRADA MANUAL
           </button>

           <div className={`px-4 py-1.5 rounded-full border flex items-center gap-2 ${currentOperationMeta.shell}`}>
              <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${currentOperationMeta.dot}`} />
              <span className="text-[10px] font-black uppercase italic">
                {currentOperationMeta.badge}
              </span>
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
                label={`💰 SALDO REAL (USDT)`}
                value={`$${syncedBalance.toLocaleString('pt-PT', { maximumFractionDigits: 2 })}`}
                sub={data.status || data.execution_label || data.operation_mode_label || 'Modo Produção'}
                icon={<Database size={18}/>}
                emerald
              />
              {/* Card TRADES ATIVOS com toggle conservador/agressivo */}
              <div className="bg-[#0d0e12] p-8 rounded-[2.5rem] border border-white/5 shadow-xl relative overflow-hidden group hover:border-green-500/20 transition-all">
                <div className="flex justify-between items-start mb-4">
                  <span className="text-[10px] font-black text-zinc-600 uppercase tracking-widest italic leading-none">TRADES ATIVOS</span>
                  <div className="p-3 bg-zinc-900 rounded-2xl group-hover:scale-110 transition-transform"><Database size={18}/></div>
                </div>
                <h2 className="text-4xl font-black italic tracking-tighter text-white">
                  {Math.min(data.active_trades?.length || 0, data.max_moedas_ativas || 1)}/{data.max_moedas_ativas || 1}
                </h2>
                <p className="text-[8px] font-black text-zinc-700 uppercase mt-2 tracking-widest">
                  {data.risk_mode === 'aggressive' ? '5 moedas simultâneas' : '1 moeda por vez'} • TP 100% da entrada • SL 50% da entrada
                </p>
                {/* Toggle conservador / agressivo */}
                <div className="mt-4 flex items-center gap-2">
                  <button
                    type="button"
                    disabled={riskModeUpdating}
                    onClick={() => handleRiskModeChange('conservative')}
                    className={`flex-1 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all border ${
                      data.risk_mode === 'conservative'
                        ? 'bg-green-500 text-black border-green-500'
                        : 'bg-transparent text-zinc-500 border-zinc-700 hover:border-zinc-500'
                    } ${riskModeUpdating ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    🛡️ Conserv.
                  </button>
                  <button
                    type="button"
                    disabled={riskModeUpdating}
                    onClick={() => handleRiskModeChange('aggressive')}
                    className={`flex-1 py-1.5 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all border ${
                      data.risk_mode === 'aggressive'
                        ? 'bg-orange-500 text-black border-orange-500'
                        : 'bg-transparent text-zinc-500 border-zinc-700 hover:border-zinc-500'
                    } ${riskModeUpdating ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    ⚡ Agressivo
                  </button>
                </div>
              </div>
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
                           <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mt-2">Ordem calculada dinamicamente • TP 100% da entrada • SL 50% da entrada</p>
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
                  <Search size={14} /> Veredito Institucional (Tribunal Gemini + Groq)
               </h4>
               <p className="text-2xl font-medium italic text-zinc-300">"{data.ia2_decision?.motivo || 'Aguardando debate das IAs...'}"</p>
               <div className="mt-6 flex flex-wrap gap-4 text-[10px] font-black uppercase tracking-widest text-zinc-500">
                 <span className="text-green-400">Confiança {Number(data.ia2_decision?.probabilidade || data.confidence || 0).toFixed(0)}%</span>
                 <span className="text-sky-300">Assertividade {overallAssertiveness.toFixed(0)}%</span>
                 <span>{evidence.side || data.ia2_decision?.decisao || 'SCANNER'} • {evidence.symbol || data.symbol}</span>
               </div>
            </div>

            <div className="bg-[#0d0e12] p-8 rounded-[3rem] border border-white/5">
              <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
                <h4 className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.5em] flex items-center gap-3">
                  <Activity size={14} /> Tribunal das 4 IAs — por que comprou/vendeu
                </h4>
                <button
                  type="button"
                  onClick={() => setActiveTab('evidence')}
                  className="text-[10px] font-black uppercase tracking-widest text-green-400 hover:text-green-300"
                >
                  Ver estudo completo →
                </button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                {(tribunalAgents.length ? tribunalAgents : [
                  { id: 'gemini', label: 'Gemini Estratégico', score: 0, weight: 25, action: 'WAIT', motivo: 'Aguardando ciclo do radar...', assertiveness: 0 },
                  { id: 'groq', label: 'Groq Tático', score: 0, weight: 25, action: 'WAIT', motivo: 'Aguardando ciclo do radar...', assertiveness: 0 },
                  { id: 'analyst', label: 'Analista de Dados', score: 0, weight: 30, action: 'WAIT', motivo: 'Aguardando ciclo do radar...', assertiveness: 0 },
                  { id: 'learner', label: 'Aprendizado Neural', score: 0, weight: 20, action: 'WAIT', motivo: 'Aguardando ciclo do radar...', assertiveness: 0, learning_notes: 'Sem histórico ainda' },
                ]).slice(0, 4).map((agent) => (
                  <AiAnalyzerCard key={agent.id || agent.label} agent={agent} />
                ))}
              </div>
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

        {/* ABA 2: EVIDÊNCIA — Tribunal + gráfico de velas + assertividade */}
        {activeTab === 'evidence' && (
          <div className="animate-in fade-in duration-500 space-y-8">
            <div className="bg-[#0d0e12] rounded-[3rem] border border-zinc-800 p-8 md:p-10">
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-6 mb-8">
                <div>
                  <div className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.4em] italic">Raio-X do Tribunal de IAs</div>
                  <h2 className="text-4xl font-black italic uppercase tracking-tighter mt-3">{evidence.symbol || data.symbol || '---'}</h2>
                  <p className="text-zinc-500 text-sm font-bold uppercase tracking-widest mt-2 max-w-3xl leading-relaxed italic">
                    {data.ia2_decision?.dialogue_preview || data.ia2_decision?.motivo || evidence.strategic_reason || 'O tribunal explica cada entrada com Gemini, Groq, Analista de Dados e Aprendizado Neural.'}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-3">
                  <div className="px-4 py-2 rounded-full border border-green-500/20 bg-green-500/5 text-[10px] font-black text-green-500 uppercase tracking-widest">
                    {evidence.side || 'SCANNER'} • Confiança {Number(evidence.confidence || data.confidence || 0).toFixed(0)}%
                  </div>
                  <div className="px-4 py-2 rounded-full border border-sky-500/20 bg-sky-500/5 text-[10px] font-black text-sky-300 uppercase tracking-widest">
                    Assertividade de vitória {overallAssertiveness.toFixed(0)}%
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-8">
                <div className="xl:col-span-2 space-y-4">
                  <div className="text-[10px] font-black text-zinc-600 uppercase tracking-widest">Estúdio de Velas (lógica SMC / Volume / Fib)</div>
                  <CandleStudyChart study={candleStudy} />
                  <div className="flex flex-wrap gap-2">
                    {(candleStudy.study_notes || []).map((note, idx) => (
                      <span key={`note-${idx}`} className="px-3 py-2 rounded-full border border-white/10 bg-black/30 text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                        {note}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="space-y-4">
                  <div className="text-[10px] font-black text-zinc-600 uppercase tracking-widest">Conversa das IAs</div>
                  <AiDialogueFeed dialogue={dialogue} />
                  <div className="rounded-[2rem] border border-violet-500/20 bg-violet-500/5 p-5">
                    <div className="text-[10px] font-black text-violet-300 uppercase tracking-widest mb-2">Aprendizado com outras entradas</div>
                    <p className="text-xs text-zinc-400 leading-relaxed">
                      {evidence.learning_from_history?.summary || 'O cérebro ainda está coletando histórico para calibrar a assertividade.'}
                    </p>
                    <div className="mt-4 grid grid-cols-3 gap-3 text-center">
                      <div>
                        <div className="text-xl font-black italic text-white">{evidence.learning_from_history?.sample_size || 0}</div>
                        <div className="text-[9px] font-black text-zinc-600 uppercase">Amostras</div>
                      </div>
                      <div>
                        <div className="text-xl font-black italic text-green-400">{Number(evidence.learning_from_history?.win_rate || 0).toFixed(0)}%</div>
                        <div className="text-[9px] font-black text-zinc-600 uppercase">Win rate</div>
                      </div>
                      <div>
                        <div className="text-xl font-black italic text-sky-300">{overallAssertiveness.toFixed(0)}%</div>
                        <div className="text-[9px] font-black text-zinc-600 uppercase">Assertividade</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-8">
                {(tribunalAgents.length ? tribunalAgents : []).slice(0, 4).map((agent) => (
                  <AiAnalyzerCard key={`ev-${agent.id}`} agent={agent} />
                ))}
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <div className="xl:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-6">
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
                <div className="space-y-4">
                  <h3 className="text-[10px] font-black text-zinc-600 uppercase tracking-[0.4em] px-2 italic flex items-center gap-3"><Activity size={14} className="text-green-500" /> Confluências Tactical</h3>
                  {evidenceChecks.map((item) => (
                    <CheckItem key={item.label} label={`${item.label}${item.detail ? ` • ${item.detail}` : ''}`} active={Boolean(item.active)} />
                  ))}
                  <div className="mt-4 bg-green-500/5 p-6 rounded-[2.5rem] border border-green-500/10">
                    <div className="flex items-center gap-3 mb-3">
                      <CheckCircle2 size={18} className="text-green-500" />
                      <span className="text-[10px] font-black text-zinc-200 uppercase tracking-widest">Certificação Tactical</span>
                    </div>
                    <p className="text-[9px] text-zinc-500 font-bold uppercase leading-relaxed italic">
                      TRIBUNAL GEMINI + GROQ + DADOS + MEMÓRIA • RIGOR {evidence.threshold || 60}% • ATÉ {evidence.max_positions || 5} ENTRADAS • TP 100% / SL 50% • BYBIT.
                    </p>
                  </div>
                </div>
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
                  {investidoresLoading ? (
                    [1, 2].map(i => (
                      <tr key={i} className="animate-pulse">
                        <td className="p-8"><div className="h-5 w-40 bg-zinc-800 rounded-lg mb-2"/><div className="h-3 w-24 bg-zinc-900 rounded-lg"/></td>
                        <td className="p-8"><div className="h-5 w-24 bg-zinc-800 rounded-lg"/></td>
                        <td className="p-8"><div className="h-5 w-16 bg-zinc-800 rounded-lg"/></td>
                        <td className="p-8"><div className="h-3 w-12 bg-zinc-800 rounded-lg"/></td>
                        <td className="p-8 text-right"><div className="h-5 w-16 bg-zinc-800 rounded-lg ml-auto"/></td>
                      </tr>
                    ))
                  ) : investidores.length === 0 ? (
                    <tr>
                      <td colSpan="5" className="p-12 text-center">
                        <p className="text-zinc-600 text-xs font-black uppercase tracking-widest mb-6">
                          Nenhum investidor encontrado localmente.
                        </p>
                        <p className="text-zinc-700 text-[10px] uppercase tracking-widest mb-6">
                          Adicione investidores usando o botão "Adicionar Investidor" acima.
                        </p>
                      </td>
                    </tr>
                  ) : investidores.map(inv => {
                    const envMeta = getInvestorEnvMeta(inv);
                    return (
                    <tr key={inv.id} className="hover:bg-green-500/[0.02] transition-all">
                      <td className="p-8">
                        <div className="font-black italic text-xl uppercase">{inv.nome}</div>
                        <div className="flex items-center gap-2 mt-3 flex-wrap">
                          <span className={`px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-widest ${envMeta.className}`}>
                            {envMeta.label}
                          </span>
                          {inv.auth_disabled ? (
                            <span className="px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-widest bg-red-500/10 border-red-500/30 text-red-300">
                              API inválida
                            </span>
                          ) : null}
                          <span className="px-3 py-1 rounded-full border text-[10px] font-black uppercase tracking-widest bg-yellow-500/10 border-yellow-500/30 text-yellow-300">
                            BYBIT
                          </span>
                        </div>
                      </td>
                      <td className="p-8 font-mono text-zinc-400 font-bold">${Number(inv.saldo_real ?? inv.banca ?? 0).toLocaleString()}</td>
                      <td className="p-8 font-black text-green-500 italic text-lg">{inv.pnl}</td>
                      <td className="p-8">
                        <div className="flex items-center gap-2">
                           <div className={`w-1.5 h-1.5 rounded-full ${String(inv.status || '').toLowerCase() === 'ativo' ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
                           <span className="text-[10px] font-black uppercase tracking-widest text-zinc-500">{inv.status}</span>
                        </div>
                      </td>
                      <td className="p-8 text-right">
                        <div className="flex justify-end gap-4 text-zinc-700">
                          <button onClick={() => openEditInvestor(inv.id)} className="hover:text-white transition-colors"><Settings size={18}/></button>
                          <button onClick={() => handleDeleteInvestor(inv.id)} className="hover:text-red-500 transition-colors"><Trash2 size={18}/></button>
                        </div>
                      </td>
                    </tr>
                  );})}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* FORMULÁRIO MODAL (Gestão de Pessoas) */}
      {showAddForm && (
        <div className="fixed inset-0 bg-black/95 backdrop-blur-xl z-[100] flex items-center justify-center p-6 animate-in fade-in duration-300">
          <div className="bg-[#0d0e12] w-full max-w-2xl rounded-[2rem] border border-zinc-800 shadow-2xl relative flex flex-col max-h-[92vh]">
            <div className="p-5 border-b border-white/5 flex justify-between items-center bg-zinc-900/20 flex-shrink-0">
               <div className="flex items-center gap-5">
                  <div className="w-10 h-10 bg-green-500/10 rounded-xl flex items-center justify-center text-green-500 border border-green-500/20">
                     <Users size={20}/>
                  </div>
                  <div>
                    <h3 className="text-lg font-black italic uppercase tracking-tighter">Vincular Investidor</h3>
                    <p className="text-[9px] text-zinc-500 font-bold uppercase tracking-widest">Setup de Chaves • Bybit</p>
                  </div>
               </div>
               <div className="flex items-center gap-3">
                 {addFormMsg && (
                   <div className={`px-4 py-2 rounded-lg ${addFormMsg.type === 'success' ? 'bg-green-500/10 border border-green-500/20 text-green-300' : 'bg-red-500/10 border border-red-500/20 text-red-300'}`}>
                     <small className="text-xs font-black uppercase">{addFormMsg.text}</small>
                   </div>
                 )}
                 <button onClick={() => {
                   setShowAddForm(false);
                   setAddFormMsg(null);
                   setAddFormFields({ id: null, nome: '', saldo_base: 0, bybit_key: '', bybit_secret: '', tg_token: '', chat_id: '', account_mode: 'real', is_testnet: false, exchange: 'bybit', balance_source: 'broker_real_balance' });
                 }} className="p-4 hover:bg-zinc-800 rounded-full transition-all text-zinc-500 hover:text-white"><X size={28}/></button>
               </div>
            </div>
            <form className="p-5 space-y-4 overflow-y-auto flex-1" onSubmit={async (e) => {
                e.preventDefault();
                setAddFormSaving(true);
                setAddFormMsg(null);
                  const payload = {
                    nome: addFormFields.nome,
                    bybit_key: addFormFields.bybit_key,
                    bybit_secret: addFormFields.bybit_secret,
                    tg_token: addFormFields.tg_token,
                    chat_id: addFormFields.chat_id,
                    account_mode: formIsTestnet ? (formAccountMode === 'testnet' ? 'testnet' : 'demo') : 'real',
                    is_testnet: formIsTestnet,
                    bybit_endpoint_mode: formIsTestnet
                      ? (formAccountMode === 'testnet' ? 'testnet' : 'demo')
                      : 'mainnet',
                    exchange: 'bybit',
                    balance_source: 'broker_real_balance',
                  };
                console.log('🔵 [FRONTEND] Salvando investidor:', {
                  nome: payload.nome,
                  account_mode: payload.account_mode,
                  is_testnet: payload.is_testnet,
                  bybit_endpoint_mode: payload.bybit_endpoint_mode,
                  api_base: API_BASE,
                });
                try {
                  // Se id definido, atualiza; caso contrário cria novo
                  if (addFormFields.id) {
                    console.log('🔵 [FRONTEND] Atualizando cliente existente ID:', addFormFields.id);
                    const res = await fetch(`${API_BASE}/api/cliente/${addFormFields.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                    console.log('🔵 [FRONTEND] Resposta do servidor (PUT):', res.status, res.statusText);
                     const json = await res.json();
                     console.log('🔵 [FRONTEND] JSON recebido (PUT):', json);
                     if (res.ok) {
                       if (json.client) {
                         console.log('✅ [FRONTEND] Cliente recebido do servidor:', json.client);
                         upsertInvestor(json.client);
                         setAddFormFields(prev => ({ ...prev, id: json.client.id, saldo_base: json.client.saldo_base ?? prev.saldo_base }));
                       }
                       const msgAtualiza = json.valid === false
                         ? `Salvo, mas API inválida: ${json.api_error || 'verifique as chaves'}`
                         : (json.msg || 'Investidor atualizado');
                       setAddFormMsg({ type: json.valid === false ? 'error' : 'success', text: msgAtualiza });
                        const invRes = await fetch(`${API_BASE}/api/investidores`); if (invRes.ok) setInvestidores((await invRes.json()).map(normalizeInvestorRecord));
                     } else {
                      console.error('❌ [FRONTEND] Erro na resposta do servidor:', json);
                      setAddFormMsg({ type: 'error', text: json.error || 'Erro ao atualizar' });
                    }
                  } else {
                    console.log('🔵 [FRONTEND] Criando novo cliente via /api/vincular_cliente');
                    const res = await fetch(`${API_BASE}/api/vincular_cliente`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                    console.log('🔵 [FRONTEND] Resposta do servidor (POST):', res.status, res.statusText);
                     const json = await res.json();
                     console.log('🔵 [FRONTEND] JSON recebido (POST):', json);
                     if (res.ok && json.status === 'sucesso') {
                       if (json.client) {
                         console.log('✅ [FRONTEND] Cliente criado com sucesso:', json.client);
                         upsertInvestor(json.client);
                         setAddFormFields(prev => ({ ...prev, id: json.client.id, saldo_base: json.client.saldo_base ?? prev.saldo_base }));
                       } else {
                         console.warn('⚠️ [FRONTEND] Sucesso mas sem dados do cliente na resposta');
                       }
                       const msgSalvo = json.valid === false
                         ? `Salvo, mas API inválida: ${json.api_error || 'verifique as chaves'}`
                         : (json.msg || 'Investidor salvo com sucesso');
                       setAddFormMsg({ type: json.valid === false ? 'error' : 'success', text: msgSalvo });
                        try { const invRes = await fetch(`${API_BASE}/api/investidores`); if (invRes.ok) setInvestidores((await invRes.json()).map(normalizeInvestorRecord)); } catch (e) { console.error('❌ [FRONTEND] Erro ao recarregar lista:', e); }
                     } else {
                      console.error('❌ [FRONTEND] Erro na resposta do servidor:', json);
                      setAddFormMsg({ type: 'error', text: json.msg || json.error || 'Erro ao salvar investidor' });
                    }
                  }
                } catch (err) {
                  console.error('❌ [FRONTEND] Erro de rede ou exceção ao vincular:', err);
                  const errorMsg = err.message || String(err);
                  setAddFormMsg({ type: 'error', text: `Erro de conexão: ${errorMsg}. Verifique se o servidor está acessível em ${API_BASE}` });
                }
                setAddFormSaving(false);
                // NÃO fecha automaticamente o modal — o usuário pode revisar/editar ou fechar manualmente
              }}>
               <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2 md:col-span-2">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Corretora</label>
                      <div className="px-4 py-3 rounded-2xl border bg-yellow-500/15 border-yellow-500/40 text-yellow-300 text-sm font-black uppercase italic text-center">
                        🟡 Bybit (única corretora)
                      </div>
                      <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest ml-1">
                        {formIsTestnet
                          ? 'Use chaves de testnet.bybit.com OU Demo Trading (bybit.com → Demo → API).'
                          : 'Use suas chaves da Bybit Perpetual REAIS (Mainnet).'}
                      </p>
                   </div>
                  <div className="space-y-2 md:col-span-2">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Modo da Conta</label>
                     <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                       <button
                         type="button"
                         onClick={() => setInvestorEnvironment('real')}
                         className={`px-4 py-3 rounded-2xl border text-sm font-black uppercase italic transition-all ${!formIsTestnet ? 'bg-green-500/15 border-green-500/40 text-green-300' : 'bg-black border-white/10 text-zinc-500 hover:text-white'}`}
                       >
                         💼 Conta Real
                       </button>
                       <button
                         type="button"
                         onClick={() => setInvestorEnvironment('demo')}
                         className={`px-4 py-3 rounded-2xl border text-sm font-black uppercase italic transition-all ${formIsTestnet ? 'bg-purple-500/15 border-purple-500/40 text-purple-200' : 'bg-black border-white/10 text-zinc-500 hover:text-white'}`}
                       >
                         🧪 Conta Demos
                       </button>
                      </div>
                      <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest ml-1">
                       {formIsTestnet
                         ? 'Conta Demos ativa — saldo via Bybit Testnet/Demo (api-testnet ou api-demo).'
                         : 'Conta Real ativa — saldo via Bybit Mainnet (api.bybit.com).'}
                      </p>
                   </div>
                  <div className="space-y-2 md:col-span-2">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Ambiente de Operação</label>
                      <div className="grid grid-cols-2 gap-3">
                         <button
                           type="button"
                           onClick={() => setInvestorEnvironment('real')}
                           className={`px-4 py-3 rounded-2xl border text-sm font-black uppercase italic transition-all ${!formIsTestnet ? 'bg-green-500/15 border-green-500/40 text-green-300' : 'bg-black border-white/10 text-zinc-500 hover:text-white'}`}
                         >
                           💰 Real
                         </button>
                         <button
                           type="button"
                           onClick={() => setInvestorEnvironment('demo')}
                           className={`px-4 py-3 rounded-2xl border text-sm font-black uppercase italic transition-all ${formIsTestnet ? 'bg-purple-500/15 border-purple-500/40 text-purple-200' : 'bg-black border-white/10 text-zinc-500 hover:text-white'}`}
                         >
                          🧪 Teste / Demos
                         </button>
                      </div>
                      <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest ml-1">
                       {formIsTestnet ? 'Modo Teste/Demos: o robô executará ordens no ambiente de testes da Bybit (Testnet ou Demo) com saldo da conta de teste.' : 'Modo Real: o robô executará ordens de verdade na Mainnet da corretora.'}
                      </p>
                   </div>
                  <div className="space-y-2">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Nome do Cliente</label>
                     <input value={addFormFields.nome} onChange={(e)=>handleFieldChange('nome', e.target.value)} className="w-full bg-black border border-white/10 p-3 rounded-2xl focus:border-green-500 outline-none transition-all italic" placeholder="Ex: Roberto Ferreira" required />
                  </div>
                  <div className="space-y-2">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">{formBalanceLabel}</label>
                      <input
                        value={addFormFields.saldo_base ? `Sincronizado: ${addFormFields.saldo_base}` : ''}
                        onChange={() => {}}
                        type="text"
                        disabled
                        className="w-full p-3 rounded-2xl outline-none font-mono border bg-zinc-950 border-white/5 text-zinc-500 cursor-not-allowed"
                        placeholder={formBalancePlaceholder}
                      />
                      <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest ml-1">Saldo exibido em tempo real via API Bybit V5 (UNIFIED).</p>
                   </div>
                </div>
               
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">API Key {formExchangeLabel}</label>
                    <input value={addFormFields.bybit_key} onChange={(e)=>handleFieldChange('bybit_key', e.target.value)} type="password" autoComplete="new-password" placeholder="••••••••••••" className="w-full bg-black border border-white/10 p-3 rounded-2xl focus:border-green-500 outline-none transition-all font-mono" required />
                  </div>
                  <div className="space-y-2">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">API Secret {formExchangeLabel}</label>
                    <input value={addFormFields.bybit_secret} onChange={(e)=>handleFieldChange('bybit_secret', e.target.value)} type="password" autoComplete="new-password" placeholder="••••••••••••" className="w-full bg-black border border-white/10 p-3 rounded-2xl focus:border-green-500 outline-none transition-all font-mono" required />
                  </div>
               </div>

               <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Token Telegram (Opcional)</label>
                     <input value={addFormFields.tg_token} onChange={(e)=>handleFieldChange('tg_token', e.target.value)} placeholder="Token do bot Telegram" className="w-full bg-black border border-white/10 p-3 rounded-2xl focus:border-green-500 outline-none transition-all font-mono text-sm" />
                </div>
                <div className="space-y-2">
                     <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Telegram Chat ID (Opcional)</label>
                     <input value={addFormFields.chat_id} onChange={(e)=>handleFieldChange('chat_id', e.target.value)} placeholder="Chat ID para alertas" className="w-full bg-black border border-white/10 p-3 rounded-2xl focus:border-green-500 outline-none transition-all font-mono" />
                </div>
              </div>

               <div className="flex gap-3 pt-1">
                    <button type="submit" disabled={addFormSaving} className="flex-1 bg-green-500 hover:bg-green-400 text-black font-black py-4 rounded-2xl transition-all shadow-lg shadow-green-900/30 flex items-center justify-center gap-3 uppercase italic disabled:opacity-50">
                      <Save size={18} /> {addFormSaving ? 'Salvando...' : 'Guardar Investidor'}
                    </button>
                    <button type="button" onClick={() => {
                      setShowAddForm(false);
                      setAddFormMsg(null);
                      setAddFormFields({ id: null, nome: '', saldo_base: 0, bybit_key: '', bybit_secret: '', tg_token: '', chat_id: '', account_mode: 'real', is_testnet: false, exchange: 'bybit', balance_source: 'broker_real_balance' });
                    }} className="px-5 py-4 bg-zinc-900/30 border border-white/5 rounded-2xl text-zinc-300 uppercase font-black text-sm">Fechar</button>
               </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL DE ENTRADA MANUAL */}
      {showManualEntryModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center z-50 p-4">
          <div className="bg-[#0d0e12] border border-white/10 rounded-[2.5rem] p-8 max-w-2xl w-full shadow-2xl animate-in fade-in zoom-in duration-300">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-green-500/10 rounded-2xl flex items-center justify-center">
                  <Target size={24} className="text-green-500" />
                </div>
                <div>
                  <h3 className="text-xl font-black italic tracking-tighter">ENTRADA MANUAL</h3>
                  <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest">Configure sua operação manual com análise de IA</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowManualEntryModal(false);
                  setManualEntryFields({ symbol: '', side: 'buy', entry_price: '' });
                  setManualEntryAnalysis(null);
                }}
                className="p-2 hover:bg-white/5 rounded-xl transition-all"
              >
                <X size={24} className="text-zinc-500" />
              </button>
            </div>

            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Símbolo do Ativo</label>
                <input
                  value={manualEntryFields.symbol}
                  onChange={(e) => handleManualEntryFieldChange('symbol', e.target.value.toUpperCase())}
                  placeholder="Ex: BTC/USDT, ETH/USDT"
                  className="w-full bg-black border border-white/10 p-3 rounded-2xl focus:border-green-500 outline-none transition-all text-sm"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Direção</label>
                  <select
                    value={manualEntryFields.side}
                    onChange={(e) => handleManualEntryFieldChange('side', e.target.value)}
                    className="w-full bg-black border border-white/10 p-3 rounded-2xl focus:border-green-500 outline-none transition-all text-sm"
                  >
                    <option value="buy">COMPRAR (BUY)</option>
                    <option value="sell">VENDER (SELL)</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="text-[9px] font-black text-zinc-600 uppercase tracking-widest ml-1 italic">Preço de Entrada (Opcional)</label>
                  <input
                    type="number"
                    step="any"
                    value={manualEntryFields.entry_price}
                    onChange={(e) => handleManualEntryFieldChange('entry_price', e.target.value)}
                    placeholder="Deixe vazio para usar preço de mercado"
                    className="w-full bg-black border border-white/10 p-3 rounded-2xl focus:border-green-500 outline-none transition-all text-sm"
                  />
                </div>
              </div>

              {/* Análise de IA */}
              {manualEntryAnalysis && (
                <div className="bg-zinc-900/30 border border-white/5 rounded-2xl p-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-black uppercase tracking-wider text-green-500">📊 Análise de IA</h4>
                    <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase ${
                      manualEntryAnalysis.recommendation === 'EXECUTAR'
                        ? 'bg-green-500/20 text-green-500 border border-green-500/30'
                        : 'bg-yellow-500/20 text-yellow-500 border border-yellow-500/30'
                    }`}>
                      {manualEntryAnalysis.recommendation}
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    <div className="bg-black/50 rounded-xl p-3 border border-white/5">
                      <p className="text-[9px] text-zinc-600 font-black uppercase mb-1">Groq</p>
                      <p className="text-sm font-bold">{manualEntryAnalysis.ai_analysis?.groq_decision || 'N/A'}</p>
                    </div>
                    <div className="bg-black/50 rounded-xl p-3 border border-white/5">
                      <p className="text-[9px] text-zinc-600 font-black uppercase mb-1">Gemini</p>
                      <p className="text-sm font-bold">{manualEntryAnalysis.ai_analysis?.gemini_decision || 'N/A'}</p>
                    </div>
                    <div className="bg-black/50 rounded-xl p-3 border border-white/5">
                      <p className="text-[9px] text-zinc-600 font-black uppercase mb-1">Local</p>
                      <p className="text-sm font-bold">{manualEntryAnalysis.ai_analysis?.local_decision || 'N/A'}</p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <p className="text-[9px] text-zinc-600 font-black uppercase">Confiança IA</p>
                      <p className="text-sm font-black text-green-500">{manualEntryAnalysis.ai_analysis?.confidence || 0}%</p>
                    </div>
                    <div className="w-full h-2 bg-zinc-900 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-green-500 transition-all duration-500"
                        style={{ width: `${manualEntryAnalysis.ai_analysis?.confidence || 0}%` }}
                      />
                    </div>
                  </div>

                  <div className="bg-black/50 rounded-xl p-4 border border-white/5">
                    <p className="text-[9px] text-zinc-600 font-black uppercase mb-2">Motivo</p>
                    <p className="text-xs text-zinc-300">{manualEntryAnalysis.ai_analysis?.reason || 'N/A'}</p>
                  </div>

                  {manualEntryAnalysis.tech_data && (
                    <div className="grid grid-cols-2 gap-3 pt-2">
                      <div className="bg-black/50 rounded-xl p-3 border border-white/5">
                        <p className="text-[9px] text-zinc-600 font-black uppercase mb-1">Tendência</p>
                        <p className="text-sm font-bold">{manualEntryAnalysis.tech_data.trend || 'N/A'}</p>
                      </div>
                      <div className="bg-black/50 rounded-xl p-3 border border-white/5">
                        <p className="text-[9px] text-zinc-600 font-black uppercase mb-1">RSI</p>
                        <p className="text-sm font-bold">{manualEntryAnalysis.tech_data.rsi || 'N/A'}</p>
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-3 pt-2">
                {!manualEntryAnalysis ? (
                  <button
                    type="button"
                    onClick={handleGetManualEntryAnalysis}
                    disabled={manualEntryLoading}
                    className="flex-1 bg-blue-500 hover:bg-blue-600 text-white font-black py-4 rounded-2xl transition-all shadow-lg flex items-center justify-center gap-3 uppercase italic disabled:opacity-50"
                  >
                    <Search size={18} />
                    {manualEntryLoading ? 'Analisando...' : 'Obter Análise IA'}
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={handleExecuteManualEntry}
                      disabled={manualEntryLoading}
                      className="flex-1 bg-green-500 hover:bg-green-600 text-black font-black py-4 rounded-2xl transition-all shadow-lg shadow-green-900/30 flex items-center justify-center gap-3 uppercase italic disabled:opacity-50"
                    >
                      <Target size={18} />
                      {manualEntryLoading ? 'Executando...' : 'Executar Entrada'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setManualEntryAnalysis(null)}
                      className="px-6 py-4 bg-zinc-900/30 border border-white/5 rounded-2xl text-zinc-300 uppercase font-black text-sm hover:bg-zinc-900/50 transition-all"
                    >
                      Nova Análise
                    </button>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setShowManualEntryModal(false);
                    setManualEntryFields({ symbol: '', side: 'buy', entry_price: '' });
                    setManualEntryAnalysis(null);
                  }}
                  className="px-6 py-4 bg-zinc-900/30 border border-white/5 rounded-2xl text-zinc-300 uppercase font-black text-sm hover:bg-zinc-900/50 transition-all"
                >
                  Fechar
                </button>
              </div>
            </div>
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
             Protocolo 100/50 — Bybit
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
