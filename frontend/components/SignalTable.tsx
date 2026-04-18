"use client";
import { DecisionBadge, ResultBadge } from "./Badges";
import type { Signal } from "@/lib/types";
import clsx from "clsx";
import PosterButton from "./SignalPoster";

interface Props {
  signals:   Signal[];
  loading?:  boolean;
  leverage?: number;
  entryUsdt?: number;
  allowForClosed?: boolean;  // true on history page
}

function fmt(n?: number | null, d = 4) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: d });
}

function PnlCell({ pnl, usdt }: { pnl: number | null | undefined; usdt?: number | null }) {
  if (pnl == null) return <span className="text-muted">—</span>;
  const pos = pnl >= 0;
  return (
    <div className="flex flex-col">
      <span className={clsx("font-mono text-xs", pos ? "text-success" : "text-danger")}>
        {pos ? "+" : ""}{pnl.toFixed(4)}%
      </span>
      {usdt != null && (
        <span className={clsx("font-mono text-[10px]", pos ? "text-success/70" : "text-danger/70")}>
          {pos ? "+" : ""}{usdt.toFixed(2)}$
        </span>
      )}
    </div>
  );
}

function SlPlusBadge({ count }: { count?: number }) {
  if (!count || count === 0) return null;
  return (
    <span className="inline-flex items-center gap-0.5 text-[9px] font-mono font-medium uppercase tracking-wide text-emerald-400/90 border border-emerald-400/30 rounded px-1 py-0.5 bg-emerald-400/5">
      🛡 SL+{count > 1 ? ` ×${count}` : ""}
    </span>
  );
}

function EntryStatus({ signal }: { signal: Signal }) {
  if (signal.status === "CLOSED")      return null;
  if (signal.status === "INVALIDATED") return null;
  if (signal.status === "NO TRADE")    return null;

  if (signal.entry_hit) {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] font-mono font-medium uppercase tracking-wide text-accent">
        <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
        in trade
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[9px] font-mono font-medium uppercase tracking-wide text-warning/80">
      <span className="w-1.5 h-1.5 rounded-full bg-warning/60" />
      watching
    </span>
  );
}

// Mobile card view
function SignalCard({ s, leverage, entryUsdt, allowForClosed }: { s: Signal; leverage: number; entryUsdt?: number; allowForClosed?: boolean }) {
  return (
    <div className="px-4 py-3 border-b border-border/30 last:border-0">
      {/* Top row: symbol + badges | PnL + Poster icon */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-mono font-medium text-text">
            {s.symbol.replace("_USDT", "")}<span className="text-muted">/USDT</span>
          </span>
          <DecisionBadge decision={s.decision} />
          {s.result && <ResultBadge result={s.result} />}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <PnlCell pnl={s.pnl_pct} usdt={s.pnl_usdt} />
          <PosterButton signal={s} leverage={leverage} entryUsdt={entryUsdt} allowForClosed={allowForClosed} />
        </div>
      </div>

      {/* Price grid */}
      <div className="grid grid-cols-3 gap-x-3 gap-y-1 text-[11px]">
        <div>
          <span className="text-muted block">Entry</span>
          <span className="font-mono text-subtle">
            {s.entry ? `$${fmt(s.entry, 6)}` : `$${fmt(s.current_price, 6)}`}
          </span>
        </div>
        <div>
          <span className="text-muted block">TP</span>
          <span className="font-mono text-success/80">{s.tp ? `$${fmt(s.tp, 6)}` : "—"}</span>
        </div>
        <div>
          <span className="text-muted block">SL</span>
          <span className="font-mono text-danger/80">{s.sl ? `$${fmt(s.sl, 6)}` : "—"}</span>
        </div>
      </div>

      {s.status === "CLOSED" && s.closed_price != null && (
        <div className="mt-1 text-[10px] font-mono text-muted/60">
          closed @ ${fmt(s.closed_price, 6)}
        </div>
      )}

      {/* Bottom row: status + confidence | timestamp */}
      <div className="flex items-center justify-between mt-2 text-[10px] font-mono text-muted/60">
        <div className="flex items-center gap-2">
          <span className={clsx(
            s.status === "OPEN"        && "text-warning",
            s.status === "CLOSED"      && "text-subtle",
            s.status === "NO TRADE"    && "text-muted/50",
            s.status === "INVALIDATED" && "text-danger/60",
          )}>
            {s.status}
          </span>
          <EntryStatus signal={s} />
          <SlPlusBadge count={s.sl_plus_count} />
          {s.confidence != null ? (
            <span className="text-muted/50">{s.confidence}% conf</span>
          ) : null}
        </div>
        <span>
          {new Date(s.timestamp).toLocaleString("en-US", {
            month: "2-digit", day: "2-digit",
            hour: "2-digit", minute: "2-digit", hour12: false,
          })}
        </span>
      </div>
    </div>
  );
}

const COLS = [
  { key: "time",     label: "Time",     w: "w-24"  },
  { key: "symbol",   label: "Pair",     w: "w-28"  },
  { key: "decision", label: "Signal",   w: "w-20"  },
  { key: "entry",    label: "Entry",    w: "w-24"  },
  { key: "tp",       label: "TP",       w: "w-24"  },
  { key: "sl",       label: "SL",       w: "w-24"  },
  { key: "conf",     label: "Conf.",    w: "w-14"  },
  { key: "status",   label: "Status",   w: "w-28"  },
  { key: "result",   label: "Result",   w: "w-16"  },
  { key: "pnl",      label: "PnL",      w: "w-24"  },
  { key: "poster",   label: "",         w: "w-20"  },  // ← new
];

export default function SignalTable({ signals, loading, leverage = 50, entryUsdt = 20, allowForClosed = false }: Props) {
  if (loading) {
    return (
      <div>
        <div className="sm:hidden">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="px-4 py-3 border-b border-border/30">
              <div className="flex justify-between mb-2">
                <div className="h-4 w-24 bg-border rounded animate-pulse" />
                <div className="h-4 w-16 bg-border rounded animate-pulse" />
              </div>
              <div className="grid grid-cols-3 gap-3">
                {[0,1,2].map(j => <div key={j} className="h-8 bg-border/60 rounded animate-pulse" />)}
              </div>
            </div>
          ))}
        </div>
        <div className="hidden sm:block overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="border-b border-border">
                {COLS.map((c) => (
                  <th key={c.key} className={clsx("text-left py-2.5 px-3 text-[10px] font-medium uppercase tracking-widest text-muted whitespace-nowrap", c.w)}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-b border-border/40">
                  {COLS.map((c) => (
                    <td key={c.key} className="py-3 px-3">
                      <div className="h-3 bg-border/60 rounded animate-pulse" style={{ width: "70%" }} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (signals.length === 0) {
    return (
      <div className="py-12 text-center text-muted font-mono text-xs">
        No signals yet. Start the bot to begin scanning.
      </div>
    );
  }

  return (
    <>
      {/* Mobile card list */}
      <div className="sm:hidden">
        {signals.map((s) => <SignalCard key={s.id} s={s} leverage={leverage} allowForClosed={allowForClosed} />)}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b border-border">
              {COLS.map((c) => (
                <th key={c.key} className={clsx("text-left py-2.5 px-3 text-[10px] font-medium uppercase tracking-widest text-muted whitespace-nowrap", c.w)}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {signals.map((s) => (
              <tr
                key={s.id}
                className={clsx(
                  "signal-row border-b border-border/30 transition-colors duration-100",
                  s.entry_hit && s.status === "OPEN" && "bg-accent/[0.03]",
                )}
              >
                <td className="py-2.5 px-3 font-mono text-muted whitespace-nowrap">
                  {new Date(s.timestamp).toLocaleString("en-US", {
                    month: "2-digit", day: "2-digit",
                    hour: "2-digit", minute: "2-digit", hour12: false,
                  })}
                </td>
                <td className="py-2.5 px-3 font-mono font-medium text-text whitespace-nowrap">
                  {s.symbol.replace("_USDT", "")}<span className="text-muted">/USDT</span>
                </td>
                <td className="py-2.5 px-3"><DecisionBadge decision={s.decision} /></td>
                <td className="py-2.5 px-3 font-mono text-subtle">
                  {s.entry ? `$${fmt(s.entry, 6)}` : `$${fmt(s.current_price, 6)}`}
                </td>
                <td className="py-2.5 px-3 font-mono text-success/80">{s.tp ? `$${fmt(s.tp, 6)}` : "—"}</td>
                <td className="py-2.5 px-3 font-mono text-danger/80">{s.sl ? `$${fmt(s.sl, 6)}` : "—"}</td>
                <td className="py-2.5 px-3 font-mono text-muted">{s.confidence != null ? `${s.confidence}%` : "—"}</td>
                <td className="py-2.5 px-3">
                  <div className="flex flex-col gap-0.5">
                    <span className={clsx("text-[10px] font-mono uppercase",
                      s.status === "OPEN"        && "text-warning",
                      s.status === "CLOSED"      && "text-subtle",
                      s.status === "NO TRADE"    && "text-muted/60",
                      s.status === "INVALIDATED" && "text-danger/60",
                    )}>
                      {s.status}
                    </span>
                    <EntryStatus signal={s} />
                    <SlPlusBadge count={s.sl_plus_count} />
                    {s.status === "CLOSED" && s.closed_price != null && (
                      <span className="text-[9px] font-mono text-muted/50">
                        @ ${fmt(s.closed_price, 6)}
                      </span>
                    )}
                  </div>
                </td>
                <td className="py-2.5 px-3">
                  {s.result ? (
                    <ResultBadge result={s.result} />
                  ) : s.status !== "NO TRADE" ? (
                    <span className="text-[10px] font-mono text-muted/50">—</span>
                  ) : null}
                </td>
                <td className="py-2.5 px-3">
                  <PnlCell pnl={s.pnl_pct} usdt={s.pnl_usdt} />
                </td>

                {/* ── POSTER BUTTON — only visible for in-trade rows ── */}
                <td className="py-2.5 px-3">
                  <PosterButton signal={s} leverage={leverage} entryUsdt={entryUsdt} allowForClosed={allowForClosed} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
