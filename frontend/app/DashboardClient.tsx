"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import type { Signal, BotState, WsEvent } from "@/lib/types";

import Sidebar      from "@/components/Sidebar";
import Header       from "@/components/Header";
import StatCard     from "@/components/StatCard";
import SignalPanel  from "@/components/SignalPanel";
import SignalTable  from "@/components/SignalTable";
import PnlChart     from "@/components/PnlChart";
import WinLossDonut from "@/components/WinLossDonut";
import BalanceCard  from "@/components/BalanceCard";
import ScanProgress from "@/components/ScanProgress";
import LiveTicker   from "@/components/LiveTicker";
import { useWebSocket } from "@/hooks/useWebSocket";
import {
  fetchBotState, startBot, stopBot, resetStats,
} from "@/lib/api";

type View = "dashboard" | "history";

const EMPTY_STATE: Partial<BotState> = {
  status:           "IDLE",
  trade_count:      0,
  win_count:        0,
  loss_count:       0,
  no_trade_count:   0,
  winrate:          0,
  total_pnl_pct:    0,
  total_pnl_usdt:   0,
  signals:          [],
  current_symbol:   null,
  symbols_scanned:  0,
  symbols_total:    0,
  balance:          0,
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

interface VirtualBalance {
  balance:         number;
  initial_balance: number;
  leverage:        number;
  entry_usdt:      number;
}

export default function DashboardClient() {
  const [view,            setView]            = useState<View>("dashboard");
  const [state,           setState]           = useState<Partial<BotState>>(EMPTY_STATE);
  const [loading,         setLoading]         = useState(true);
  const [closedSigs,      setClosedSigs]      = useState<Signal[]>([]);
  const [historyLoading,  setHistoryLoading]  = useState(false);
  const [sidebarOpen,     setSidebarOpen]     = useState(false);
  // Virtual exchange balance (realtime)
  const [vBalance,        setVBalance]        = useState<VirtualBalance>({
    balance: 0, initial_balance: 0, leverage: 10, entry_usdt: 100,
  });
  const flashRef = useRef<Set<string>>(new Set());

  // ── Initial load: bot state + balance ──────────────────────────────
  useEffect(() => {
    fetchBotState()
      .then((s) => {
        setState(s);
        // Seed balance from state if available
        if (s.balance != null) {
          setVBalance((prev) => ({ ...prev, balance: s.balance ?? 0 }));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));

    // Also fetch full virtual balance info
    fetch(`${API_BASE}/api/bot/balance`)
      .then((r) => r.json())
      .then((json) => {
        if (json.data) setVBalance(json.data as VirtualBalance);
      })
      .catch(() => {});
  }, []);

  // ── Fetch closed signal history ─────────────────────────────────────
  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res  = await fetch(`${API_BASE}/api/history/signals?limit=500`);
      const json = await res.json();
      const all: Signal[] = json.data ?? [];
      setClosedSigs(
        all.filter((s) => s.status === "CLOSED" || s.result === "TP" || s.result === "SL")
      );
    } catch {
      // silently fail
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (view === "history") fetchHistory();
  }, [view, fetchHistory]);

  // ── WebSocket event handler ─────────────────────────────────────────
  const handleWs = useCallback((msg: WsEvent) => {

    // New open signal
    if (msg.event === "signal") {
      const sig = msg.data as Signal;
      setState((prev) => {
        const signals = [sig, ...(prev.signals ?? [])].slice(0, 500);
        return {
          ...prev,
          last_signal:    sig,
          signals,
          trade_count:    (prev.trade_count    ?? 0) + (sig.decision !== "NO TRADE" ? 1 : 0),
          no_trade_count: (prev.no_trade_count ?? 0) + (sig.decision === "NO TRADE" ? 1 : 0),
        };
      });
      flashRef.current.add(sig.id);
      setTimeout(() => flashRef.current.delete(sig.id), 700);
    }

    // Signal entry hit update (entry_hit flipped to true)
    if (msg.event === "signal_entry_hit") {
      const { id } = msg.data as { id: string };
      setState((prev) => ({
        ...prev,
        signals: (prev.signals ?? []).map((s) =>
          s.id === id ? { ...s, entry_hit: true } : s
        ),
      }));
    }

    // Signal closed (TP or SL)
    if (msg.event === "signal_closed") {
      const closed = msg.data as Signal & { balance?: number };

      setState((prev) => {
        const signals = (prev.signals ?? []).filter((s) => s.id !== closed.id);
        const wins    = (prev.win_count  ?? 0) + (closed.result === "TP" ? 1 : 0);
        const losses  = (prev.loss_count ?? 0) + (closed.result === "SL" ? 1 : 0);
        const total   = wins + losses;
        return {
          ...prev,
          signals,
          win_count:      wins,
          loss_count:     losses,
          winrate:        total > 0 ? parseFloat((wins / total * 100).toFixed(2)) : 0,
          total_pnl_pct:  parseFloat(((prev.total_pnl_pct  ?? 0) + (closed.pnl_pct  ?? 0)).toFixed(4)),
          total_pnl_usdt: parseFloat(((prev.total_pnl_usdt ?? 0) + (closed.pnl_usdt ?? 0)).toFixed(4)),
        };
      });

      // Update balance from the closed event payload
      if (closed.balance != null) {
        setVBalance((prev) => ({ ...prev, balance: closed.balance! }));
      }

      // Push to history list
      setClosedSigs((prev) => {
        const exists = prev.some((s) => s.id === closed.id);
        if (exists) return prev.map((s) => s.id === closed.id ? closed : s);
        return [closed, ...prev];
      });
    }

    // Signal invalidated before entry
    if (msg.event === "signal_invalidated") {
      const { id } = msg.data as { id: string; symbol: string; price: number; timestamp: number };
      setState((prev) => ({
        ...prev,
        signals: (prev.signals ?? []).filter((s) => s.id !== id),
      }));
    }

    // Balance update from virtual exchange
    if (msg.event === "balance_update") {
      const info = msg.data as VirtualBalance;
      setVBalance(info);
      setState((prev) => ({ ...prev, balance: info.balance }));
    }

    // Bot status message (quota reached, waiting, etc.)
    if (msg.event === "status") {
      // Could surface a toast/notification here if desired
    }

    // Daily progress
    if (msg.event === "progress") {
      const { daily_signal_count, max_daily_signals, symbols_scanned } =
        msg.data as { daily_signal_count: number; max_daily_signals: number; symbols_scanned: number };
      setState((prev) => ({
        ...prev,
        symbols_scanned,
        daily_signal_count,
        symbols_total: max_daily_signals,
      }));
    }

    // Full reset
    if (msg.event === "reset_all") {
      setState((prev) => ({ ...prev, ...EMPTY_STATE, status: prev.status ?? "IDLE" }));
      setClosedSigs([]);
      setVBalance((prev) => ({ ...prev, balance: prev.initial_balance }));
    }
  }, []);

  useWebSocket(handleWs);

  const handleStart = useCallback(async () => {
    await startBot({ interval: 300 });
    setState((p) => ({ ...p, status: "RUNNING" }));
  }, []);

  const handleStop = useCallback(async () => {
    await stopBot();
    setState((p) => ({ ...p, status: "IDLE" }));
  }, []);

  const handleReset = useCallback(async () => {
    await resetStats();
    setState((p) => ({ ...EMPTY_STATE, status: p.status ?? "IDLE" }));
    setClosedSigs([]);
    // Refetch balance after reset
    fetch(`${API_BASE}/api/bot/balance`)
      .then((r) => r.json())
      .then((json) => { if (json.data) setVBalance(json.data); })
      .catch(() => {});
  }, []);

  const signals  = state.signals ?? [];
  const running  = state.status  === "RUNNING";
  const pnlColor = (state.total_pnl_pct ?? 0) >= 0 ? "success" : "danger";

  // PnL % from initial balance
  const pnlBalancePct = vBalance.initial_balance > 0
    ? ((vBalance.balance - vBalance.initial_balance) / vBalance.initial_balance * 100)
    : 0;

  return (
    <div className="flex min-h-screen bg-bg">
      <Sidebar
        active={view}
        onChange={setView}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex-1 flex flex-col lg:ml-56 min-w-0">
        <Header
          status={state.status ?? "IDLE"}
          currentSymbol={state.current_symbol}
          scanned={state.symbols_scanned}
          total={state.symbols_total}
          onStart={handleStart}
          onStop={handleStop}
          onReset={handleReset}
          running={running}
          onMenuToggle={() => setSidebarOpen((o) => !o)}
        />

        <LiveTicker signals={signals} />

        {/* ——— DASHBOARD VIEW ——— */}
        {view === "dashboard" && (
          <div className="flex-1 p-3 sm:p-6 flex flex-col gap-4 sm:gap-5 overflow-auto">

            <ScanProgress
              scanned={state.symbols_scanned ?? 0}
              total={state.symbols_total     ?? 0}
              symbol={state.current_symbol}
              visible={running}
            />

            {/* ── Balance card (full width on mobile, left-aligned on desktop) ── */}
            <BalanceCard
              balance={vBalance.balance}
              initialBalance={vBalance.initial_balance}
              leverage={vBalance.leverage}
              entryUsdt={vBalance.entry_usdt}
              pnlUsdt={state.total_pnl_usdt ?? 0}
              pnlPct={pnlBalancePct}
              loading={loading}
            />

            {/* Stat cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 sm:gap-3">
              <StatCard
                label="Total Trades"
                value={state.trade_count ?? 0}
                loading={loading}
              />
              <StatCard
                label="Win Rate"
                value={`${(state.winrate ?? 0).toFixed(1)}%`}
                sub={`${state.win_count ?? 0}W / ${state.loss_count ?? 0}L`}
                color={(state.winrate ?? 0) >= 50 ? "success" : "danger"}
                loading={loading}
              />
              <StatCard
                label="W / L Ratio"
                value={
                  (state.loss_count ?? 0) > 0
                    ? ((state.win_count ?? 0) / (state.loss_count ?? 0)).toFixed(2)
                    : (state.win_count ?? 0) > 0 ? "∞" : "—"
                }
                loading={loading}
              />
              <StatCard
                label="Cum. PnL %"
                value={`${(state.total_pnl_pct ?? 0) >= 0 ? "+" : ""}${(state.total_pnl_pct ?? 0).toFixed(4)}%`}
                color={pnlColor}
                loading={loading}
              />
              <StatCard
                label="No Trade"
                value={state.no_trade_count ?? 0}
                sub="filtered"
                loading={loading}
                className="col-span-2 sm:col-span-1"
              />
            </div>

            {/* Main layout */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-5">

              {/* Signal table */}
              <div className="lg:col-span-2 bg-card border border-border rounded-xl overflow-hidden">
                <div className="px-4 sm:px-5 py-3.5 border-b border-border flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-text">Open Signals</h2>
                  <div className="flex items-center gap-3">
                    <span className="text-[11px] font-mono text-warning">
                      {signals.filter((s) => s.entry_hit).length} in trade
                    </span>
                    <span className="text-[11px] font-mono text-muted">
                      {signals.filter((s) => !s.entry_hit && s.decision !== "NO TRADE").length} watching
                    </span>
                  </div>
                </div>
                <SignalTable
                  signals={signals.slice(0, 30)}
                  loading={loading}
                  leverage={vBalance.leverage} 
                />
              </div>

              {/* Right panel */}
              <div className="flex flex-col gap-4 sm:gap-5">

                {/* Latest AI signal */}
                <div className="bg-card border border-border rounded-xl p-4 sm:p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-sm font-semibold text-text">Latest Signal</h2>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-accent/10 text-accent border border-accent/20 uppercase tracking-wide">
                      AI
                    </span>
                  </div>
                  <SignalPanel signal={state.last_signal ?? null} />
                </div>

                {/* W/L donut */}
                <div className="bg-card border border-border rounded-xl p-4 sm:p-5">
                  <h2 className="text-sm font-semibold text-text mb-4">W/L Distribution</h2>
                  <WinLossDonut
                    wins={state.win_count   ?? 0}
                    losses={state.loss_count ?? 0}
                  />
                </div>
              </div>
            </div>

            {/* PnL chart */}
            <div className="bg-card border border-border rounded-xl p-4 sm:p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-text">Cumulative PnL</h2>
                <div className="flex items-center gap-3">
                  <span className={`text-xs font-mono ${pnlColor === "success" ? "text-success" : "text-danger"}`}>
                    {(state.total_pnl_pct ?? 0) >= 0 ? "+" : ""}
                    {(state.total_pnl_pct ?? 0).toFixed(4)}%
                  </span>
                  <span className={`text-xs font-mono ${(state.total_pnl_usdt ?? 0) >= 0 ? "text-success" : "text-danger"}`}>
                    {(state.total_pnl_usdt ?? 0) >= 0 ? "+" : ""}
                    {(state.total_pnl_usdt ?? 0).toFixed(2)} USDT
                  </span>
                </div>
              </div>
              <PnlChart signals={closedSigs} />
            </div>
          </div>
        )}

        {/* ——— HISTORY VIEW ——— */}
        {view === "history" && (
          <div className="flex-1 p-3 sm:p-6 overflow-auto">
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <div className="px-4 sm:px-5 py-4 border-b border-border flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-0 sm:justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-text">Signal History</h2>
                  <p className="text-[11px] text-muted mt-0.5">
                    Closed signals — {closedSigs.length} resolved
                  </p>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono">
                  <span className="text-success">{state.win_count ?? 0} TP</span>
                  <span className="text-danger">{state.loss_count ?? 0} SL</span>
                  <span className="text-muted">{state.no_trade_count ?? 0} skipped</span>
                  <button
                    onClick={fetchHistory}
                    disabled={historyLoading}
                    className="text-muted/60 hover:text-muted transition-colors disabled:opacity-40"
                    title="Refresh history"
                  >
                    <svg className={`w-3.5 h-3.5 ${historyLoading ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </button>
                </div>
              </div>

              {closedSigs.length > 0 && (
                <div className="px-4 sm:px-5 py-4 border-b border-border">
                  <PnlChart signals={closedSigs} />
                </div>
              )}

              <SignalTable
                signals={closedSigs}
                loading={historyLoading}
                leverage={vBalance.leverage}  
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
