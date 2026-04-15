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
