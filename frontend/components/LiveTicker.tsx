"use client";
import type { Signal } from "@/lib/types";
import clsx from "clsx";

interface Props { signals: Signal[] }

export default function LiveTicker({ signals }: Props) {
  const recent = signals
    .filter((s) => s.decision !== "NO TRADE")
    .slice(0, 12);

  if (recent.length === 0) return null;

  return (
    <div className="bg-surface border-b border-border overflow-hidden">
      <div className="flex items-center gap-0">
        <span className="shrink-0 px-2 sm:px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-accent bg-accent/10 border-r border-border">
          Live
        </span>
        <div className="overflow-x-auto flex items-center gap-3 sm:gap-4 px-3 sm:px-4 py-1.5 scrollbar-none">
          {recent.map((s) => (
            <span
              key={s.id}
              className="flex items-center gap-1 sm:gap-1.5 whitespace-nowrap text-[10px] sm:text-[11px] font-mono shrink-0"
            >
              <span className="text-subtle">{s.symbol.replace("_USDT", "")}</span>
              <span className={clsx("font-semibold", s.decision === "LONG" ? "text-success" : "text-danger")}>
                {s.decision}
              </span>
              {s.confidence && (
                <span className="text-muted/60 hidden sm:inline">{s.confidence}%</span>
              )}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
