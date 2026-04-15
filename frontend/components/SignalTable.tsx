"use client";
import { DecisionBadge, ResultBadge } from "./Badges";
import type { Signal } from "@/lib/types";
import clsx from "clsx";

interface Props {
  signals:  Signal[];
  loading?: boolean;
}

function fmt(n?: number | null, d = 4) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: d });
}

function PnlCell({ pnl }: { pnl: number | null | undefined }) {
  if (pnl == null) return <span className="text-muted">—</span>;
  const pos = pnl >= 0;
  return (
    <span className={clsx("font-mono", pos ? "text-success" : "text-danger")}>
      {pos ? "+" : ""}{pnl.toFixed(4)}%
    </span>
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
  { key: "status",   label: "Status",   w: "w-20"  },
  { key: "result",   label: "Result",   w: "w-16"  },
  { key: "pnl",      label: "PnL",      w: "w-20"  },
];

export default function SignalTable({ signals, loading }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="border-b border-border">
            {COLS.map((c) => (
              <th
                key={c.key}
                className={clsx(
                  "text-left py-2.5 px-3 text-[10px] font-medium uppercase tracking-widest text-muted whitespace-nowrap",
                  c.w,
                )}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && (
            Array.from({ length: 6 }).map((_, i) => (
              <tr key={i} className="border-b border-border/40">
                {COLS.map((c) => (
                  <td key={c.key} className="py-3 px-3">
                    <div className="h-3 bg-border/60 rounded animate-pulse" style={{ width: "70%" }} />
                  </td>
                ))}
              </tr>
            ))
          )}

          {!loading && signals.length === 0 && (
            <tr>
              <td colSpan={COLS.length} className="py-12 text-center text-muted font-mono text-xs">
                No signals yet. Start the bot to begin scanning.
              </td>
            </tr>
          )}

          {!loading && signals.map((s) => (
            <tr
              key={s.id}
              className="signal-row border-b border-border/30 transition-colors duration-100"
            >
              {/* Time */}
              <td className="py-2.5 px-3 font-mono text-muted whitespace-nowrap">
                {new Date(s.timestamp).toLocaleString("en-US", {
                  month: "2-digit", day: "2-digit",
                  hour: "2-digit", minute: "2-digit", hour12: false,
                })}
              </td>

              {/* Pair */}
              <td className="py-2.5 px-3 font-mono font-medium text-text whitespace-nowrap">
                {s.symbol.replace("_USDT", "")}<span className="text-muted">/USDT</span>
              </td>

              {/* Signal */}
              <td className="py-2.5 px-3">
                <DecisionBadge decision={s.decision} />
              </td>

              {/* Entry */}
              <td className="py-2.5 px-3 font-mono text-subtle">
                {s.entry ? `$${fmt(s.entry, 6)}` : `$${fmt(s.current_price, 6)}`}
              </td>

              {/* TP */}
              <td className="py-2.5 px-3 font-mono text-success/80">
                {s.tp ? `$${fmt(s.tp, 6)}` : "—"}
              </td>

              {/* SL */}
              <td className="py-2.5 px-3 font-mono text-danger/80">
                {s.sl ? `$${fmt(s.sl, 6)}` : "—"}
              </td>

              {/* Confidence */}
              <td className="py-2.5 px-3 font-mono text-muted">
                {s.confidence != null ? `${s.confidence}%` : "—"}
              </td>

              {/* Status */}
              <td className="py-2.5 px-3">
                <span className={clsx(
                  "text-[10px] font-mono uppercase",
                  s.status === "OPEN"     && "text-warning",
                  s.status === "CLOSED"   && "text-subtle",
                  s.status === "NO TRADE" && "text-muted/60",
                )}>
                  {s.status}
                </span>
              </td>

              {/* Result */}
              <td className="py-2.5 px-3">
                <ResultBadge result={s.result} />
                {!s.result && s.status !== "NO TRADE" && (
                  <span className="text-[10px] font-mono text-muted/50">—</span>
                )}
              </td>

              {/* PnL */}
              <td className="py-2.5 px-3">
                <PnlCell pnl={s.pnl_pct} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
