"use client";
import { DecisionBadge } from "./Badges";
import type { Signal } from "@/lib/types";

function fmt(n?: number | null, digits = 4) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

function Row({ label, value, mono = true }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
      <span className="text-[11px] text-muted uppercase tracking-wide">{label}</span>
      <span className={`text-xs text-text ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}

export default function SignalPanel({ signal }: { signal: Signal | null }) {
  if (!signal) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-muted text-xs font-mono gap-2">
        <svg className="w-8 h-8 text-border" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.2}
            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
        <span>Waiting for signal…</span>
      </div>
    );
  }

  const isLong  = signal.decision === "LONG";
  const isShort = signal.decision === "SHORT";
  const isClosed = signal.status === "CLOSED";
  const isInvalidated = signal.status === "INVALIDATED";

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-text font-mono">
            {signal.symbol.replace("_USDT", "")}/USDT
          </span>
          <DecisionBadge decision={signal.decision} />
        </div>
        {signal.confidence != null && (
          <span className="text-xs font-mono text-muted">
            {signal.confidence}% conf
          </span>
        )}
      </div>

      {/* Confidence bar */}
      {signal.confidence != null && (
        <div className="w-full h-1 bg-border rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              isLong ? "bg-success" : isShort ? "bg-danger" : "bg-muted"
            }`}
            style={{ width: `${signal.confidence}%` }}
          />
        </div>
      )}

      {/* Entry hit indicator */}
      {signal.status === "OPEN" && (
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-mono ${
          signal.entry_hit
            ? "bg-accent/5 border-accent/20 text-accent"
            : "bg-warning/5 border-warning/20 text-warning/80"
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${
            signal.entry_hit ? "bg-accent animate-pulse" : "bg-warning/60"
          }`} />
          {signal.entry_hit ? "Entry hit — trade active" : "Waiting for entry…"}
        </div>
      )}

      {/* SL+ indicator */}
      {(signal.sl_plus_count ?? 0) > 0 && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-emerald-400/5 border-emerald-400/20 text-emerald-400 text-xs font-mono">
          <span className="text-base leading-none">🛡</span>
          SL moved {signal.sl_plus_count}×
          {signal.last_ai_decision === "SL+" && signal.last_ai_reason && (
            <span className="text-emerald-400/60 truncate">— {signal.last_ai_reason}</span>
          )}
        </div>
      )}

      {/* Last AI monitor decision (HOLD shown subtly, CLOSE shown more prominently) */}
      {signal.last_ai_decision && signal.last_ai_decision !== "SL+" && (
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-mono ${
          signal.last_ai_decision === "CLOSE"
            ? "bg-danger/5 border-danger/20 text-danger/80"
            : "bg-border/30 border-border/50 text-muted/70"
        }`}>
          <span className="w-1.5 h-1.5 rounded-full bg-current opacity-60" />
          AI: {signal.last_ai_decision}
          {signal.last_ai_reason && (
            <span className="opacity-60 truncate">— {signal.last_ai_reason}</span>
          )}
        </div>
      )}

      {/* Invalidated indicator */}
      {isInvalidated && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-danger/5 border-danger/20 text-danger/80 text-xs font-mono">
          <span className="w-1.5 h-1.5 rounded-full bg-danger/60" />
          Signal invalidated before entry
        </div>
      )}

      {/* Fields */}
      <div className="mt-1">
        <Row label="Symbol"  value={signal.symbol} />
        <Row label="Price"   value={`$${fmt(signal.current_price, 6)}`} />
        <Row label="Entry"   value={signal.entry ? `$${fmt(signal.entry, 6)}` : "—"} />
        <Row
          label="Take Profit"
          value={signal.tp
            ? <span className="text-success">${fmt(signal.tp, 6)}</span>
            : "—"}
        />
        <Row
          label="Stop Loss"
          value={signal.sl
            ? <span className="text-danger">${fmt(signal.sl, 6)}</span>
            : "—"}
        />
        {isClosed && signal.closed_price != null && (
          <Row
            label="Closed @"
            value={<span className="text-subtle">${fmt(signal.closed_price, 6)}</span>}
          />
        )}
        {isClosed && signal.pnl_pct != null && (
          <Row
            label="PnL"
            value={
              <div className="flex items-center gap-2">
                <span className={signal.pnl_pct >= 0 ? "text-success" : "text-danger"}>
                  {signal.pnl_pct >= 0 ? "+" : ""}{signal.pnl_pct.toFixed(4)}%
                </span>
                {signal.pnl_usdt != null && (
                  <span className={`text-[10px] ${signal.pnl_usdt >= 0 ? "text-success/70" : "text-danger/70"}`}>
                    ({signal.pnl_usdt >= 0 ? "+" : ""}{signal.pnl_usdt.toFixed(2)} USDT)
                  </span>
                )}
              </div>
            }
          />
        )}
        <Row label="Trend"   value={signal.trend   ?? "—"} mono={false} />
        <Row label="Pattern" value={signal.pattern ?? "—"} mono={false} />
      </div>

      {/* Reason */}
      {signal.reason && (
        <p className="text-[11px] text-subtle leading-relaxed bg-bg/50 rounded-lg p-3 border border-border/40 mt-1">
          {signal.reason}
        </p>
      )}

      {/* Timestamp */}
      <p className="text-[10px] text-muted/60 font-mono text-right">
        {new Date(signal.timestamp).toLocaleTimeString()}
      </p>
    </div>
  );
}
