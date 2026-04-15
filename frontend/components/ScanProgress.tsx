"use client";

interface Props {
  scanned: number;
  total:   number;
  symbol?: string | null;
  visible: boolean;
}

export default function ScanProgress({ scanned, total, symbol, visible }: Props) {
  if (!visible || total === 0) return null;
  const pct = Math.round((scanned / total) * 100);

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] font-medium uppercase tracking-widest text-muted">
          Scanning All MEXC Pairs
        </span>
        <span className="text-xs font-mono text-subtle">
          {scanned} / {total}
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full h-1.5 bg-border rounded-full overflow-hidden mb-2">
        <div
          className="h-full bg-accent rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      {symbol && (
        <p className="text-[11px] font-mono text-muted/70">
          Analysing: <span className="text-subtle">{symbol}</span>
        </p>
      )}
    </div>
  );
}
