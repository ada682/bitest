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
import ScanProgress from "@/components/ScanProgress";
import LiveTicker   from "@/components/LiveTicker";
import { useWebSocket } from "@/hooks/useWebSocket";
import {
  fetchBotState, startBot, stopBot, resetStats,
} from "@/lib/api";

type View = "dashboard" | "history";

const EMPTY_STATE: Partial<BotState> = {
  status:          "IDLE",
  trade_count:     0,
  win_count:       0,
  loss_count:      0,
  no_trade_count:  0,
  winrate:         0,
  total_pnl_pct:   0,
  signals:         [],
  current_symbol:  null,
  symbols_scanned: 0,
  symbols_total:   0,
};

export default function DashboardClient() {
  const [view,    setView]    = useState<View>("dashboard");
  const [state,   setState]   = useState<Partial<BotState>>(EMPTY_STATE);
  const [loading, setLoading] = useState(true);
  const flashRef              = useRef<Set<string>>(new Set());

  // Load state on mount (provides global signals immediately)
  useEffect(() => {
    fetchBotState()
      .then((s) => setState(s))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // WebSocket handler
  const handleWs = useCallback((msg: WsEvent) => {
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

    if (msg.event === "signal_closed") {
      const closed = msg.data as Signal;
      setState((prev) => {
        const signals = (prev.signals ?? []).map((s) =>
          s.id === closed.id ? closed : s
        );
        const wins    = (prev.win_count  ?? 0) + (closed.result === "TP" ? 1 : 0);
        const losses  = (prev.loss_count ?? 0) + (closed.result === "SL" ? 1 : 0);
        const total   = wins + losses;
        return {
          ...prev,
          signals,
          win_count:      wins,
          loss_count:     losses,
          winrate:        total > 0 ? parseFloat((wins / total * 100).toFixed(2)) : 0,
          total_pnl_pct:  parseFloat(((prev.total_pnl_pct ?? 0) + (closed.pnl_pct ?? 0)).toFixed(4)),
        };
      });
    }

    if (msg.event === "status") {
      setState((prev) => ({
        ...prev,
        status: prev.status === "RUNNING" ? "RUNNING" : prev.status,
      }));
    }

    if (msg.event === "reset_all") {
      setState((prev) => ({ ...prev, ...EMPTY_STATE, status: prev.status ?? "IDLE" }));
    }
  }, []);

  useWebSocket(handleWs);

  // Controls
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
  }, []);

  const signals    = state.signals      ?? [];
  const running    = state.status       === "RUNNING";
  const closedSigs = signals.filter((s) => s.status === "CLOSED");
  const pnlColor   = (state.total_pnl_pct ?? 0) >= 0 ? "success" : "danger";

  return (
    <div className="flex min-h-screen bg-bg">
      <Sidebar active={view} onChange={setView} />

      {/* Main area */}
      <div className="flex-1 flex flex-col ml-56">
        <Header
          status={state.status ?? "IDLE"}
          currentSymbol={state.current_symbol}
          scanned={state.symbols_scanned}
          total={state.symbols_total}
          onStart={handleStart}
          onStop={handleStop}
          running={running}
        />

        <LiveTicker signals={signals} />

        {/* ——————————————————— DASHBOARD VIEW ——————————————————— */}
        {view === "dashboard" && (
          <div className="flex-1 p-6 flex flex-col gap-5 overflow-auto">

            {/* Scan progress */}
            <ScanProgress
              scanned={state.symbols_scanned ?? 0}
              total={state.symbols_total     ?? 0}
              symbol={state.current_symbol}
              visible={running}
            />

            {/* Stat cards */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
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
                label="Cum. PnL"
                value={`${(state.total_pnl_pct ?? 0) >= 0 ? "+" : ""}${(state.total_pnl_pct ?? 0).toFixed(4)}%`}
                color={pnlColor}
                loading={loading}
              />
              <StatCard
                label="No Trade"
                value={state.no_trade_count ?? 0}
                sub="filtered signals"
                loading={loading}
              />
            </div>

            {/* Main 2-col layout */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

              {/* Left: recent signals table */}
              <div className="lg:col-span-2 bg-card border border-border rounded-xl overflow-hidden">
                <div className="px-5 py-3.5 border-b border-border flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-text">Recent Signals</h2>
                  <span className="text-[11px] font-mono text-muted">
                    {signals.filter((s) => s.decision !== "NO TRADE").length} actionable
                  </span>
                </div>
                <SignalTable
                  signals={signals.slice(0, 30)}
                  loading={loading}
                />
              </div>

              {/* Right: AI signal + W/L donut */}
              <div className="flex flex-col gap-5">

                {/* Latest AI signal */}
                <div className="bg-card border border-border rounded-xl p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-sm font-semibold text-text">Latest Signal</h2>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-accent/10 text-accent border border-accent/20 uppercase tracking-wide">
                      AI
                    </span>
                  </div>
                  <SignalPanel signal={state.last_signal ?? null} />
                </div>

                {/* W/L distribution */}
                <div className="bg-card border border-border rounded-xl p-5">
                  <h2 className="text-sm font-semibold text-text mb-4">W/L Distribution</h2>
                  <WinLossDonut
                    wins={state.win_count   ?? 0}
                    losses={state.loss_count ?? 0}
                  />
                </div>
              </div>
            </div>

            {/* PnL chart */}
            <div className="bg-card border border-border rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-text">Cumulative PnL</h2>
                <span className={`text-xs font-mono ${pnlColor === "success" ? "text-success" : "text-danger"}`}>
                  {(state.total_pnl_pct ?? 0) >= 0 ? "+" : ""}
                  {(state.total_pnl_pct ?? 0).toFixed(4)}%
                </span>
              </div>
              <PnlChart signals={signals} />
            </div>
          </div>
        )}

        {/* ——————————————————— HISTORY VIEW ——————————————————— */}
        {view === "history" && (
          <div className="flex-1 p-6 overflow-auto">
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <div className="px-5 py-4 border-b border-border flex items-center justify-between">
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
                </div>
              </div>

              {/* PnL summary */}
              {closedSigs.length > 0 && (
                <div className="px-5 py-4 border-b border-border">
                  <PnlChart signals={signals} />
                </div>
              )}

              <SignalTable
                signals={signals.filter((s) => s.status === "CLOSED")}
                loading={loading}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
