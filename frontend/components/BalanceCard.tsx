"use client";
import clsx from "clsx";

interface BalanceCardProps {
  balance:        number;
  initialBalance: number;
  leverage:       number;
  entryUsdt:      number;
  pnlUsdt:        number;
  pnlPct:         number;
  loading?:       boolean;
}

export default function BalanceCard({
  balance, initialBalance, leverage, entryUsdt,
  pnlUsdt, pnlPct, loading,
}: BalanceCardProps) {
  const isProfit = pnlUsdt >= 0;
  const barWidth = initialBalance > 0
    ? Math.min(Math.abs((balance / initialBalance) * 100), 200)
    : 0;
  const barColor = balance >= initialBalance ? "bg-success" : "bg-danger";

  return (
    <div className="bg-card border border-border rounded-xl p-4 sm:p-5">
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-0 sm:justify-between">

        {/* Left — balance */}
        <div className="flex items-center gap-4 sm:gap-6">
          <div>
            <p className="text-[10px] sm:text-[11px] font-medium tracking-widest uppercase text-muted mb-1">
              Virtual Balance
            </p>
            {loading ? (
              <div className="h-8 w-32 bg-border rounded animate-pulse" />
            ) : (
              <div className="flex items-baseline gap-2">
                <span className="text-2xl sm:text-3xl font-semibold font-mono text-text tabular-nums">
                  {balance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
                <span className="text-sm text-muted font-mono">USDT</span>
              </div>
            )}
            {/* Balance bar vs initial */}
            {!loading && initialBalance > 0 && (
              <div className="mt-2 flex items-center gap-2">
                <div className="w-32 sm:w-48 h-1 bg-border rounded-full overflow-hidden">
                  <div
                    className={clsx("h-full rounded-full transition-all duration-700", barColor)}
                    style={{ width: `${Math.min(barWidth, 100)}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-muted">
                  initial: {initialBalance.toFixed(0)} USDT
                </span>
              </div>
            )}
          </div>

          {/* Divider */}
          <div className="hidden sm:block h-10 w-px bg-border" />

          {/* PnL USDT */}
          <div className="hidden sm:block">
            <p className="text-[10px] sm:text-[11px] font-medium tracking-widest uppercase text-muted mb-1">
              Realized PnL
            </p>
            {loading ? (
              <div className="h-7 w-24 bg-border rounded animate-pulse" />
            ) : (
              <div className="flex flex-col">
                <span className={clsx(
                  "text-xl font-semibold font-mono tabular-nums",
                  isProfit ? "text-success" : "text-danger",
                )}>
                  {isProfit ? "+" : ""}{pnlUsdt.toFixed(2)} USDT
                </span>
                <span className={clsx(
                  "text-[11px] font-mono mt-0.5",
                  isProfit ? "text-success/70" : "text-danger/70",
                )}>
                  {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}% vs initial
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Right — settings */}
        <div className="flex items-center gap-3 sm:gap-4">
          {/* Mobile PnL */}
          <div className="sm:hidden flex flex-col">
            <p className="text-[10px] uppercase tracking-widest text-muted">PnL</p>
            {loading ? (
              <div className="h-5 w-20 bg-border rounded animate-pulse" />
            ) : (
              <span className={clsx("text-sm font-semibold font-mono", isProfit ? "text-success" : "text-danger")}>
                {isProfit ? "+" : ""}{pnlUsdt.toFixed(2)} USDT
              </span>
            )}
          </div>

          {/* Leverage badge */}
          <div className="flex flex-col items-center">
            <p className="text-[10px] uppercase tracking-widest text-muted mb-1">Leverage</p>
            <span className="px-2.5 py-1 rounded-lg bg-accent/10 border border-accent/20 text-accent text-sm font-mono font-semibold">
              {leverage}×
            </span>
          </div>

          {/* Entry size */}
          <div className="flex flex-col items-center">
            <p className="text-[10px] uppercase tracking-widest text-muted mb-1">Per Trade</p>
            <span className="px-2.5 py-1 rounded-lg bg-border/60 text-subtle text-sm font-mono font-semibold">
              {entryUsdt} USDT
            </span>
          </div>

          {/* Notional */}
          <div className="flex flex-col items-center">
            <p className="text-[10px] uppercase tracking-widest text-muted mb-1">Notional</p>
            <span className="px-2.5 py-1 rounded-lg bg-border/60 text-subtle text-sm font-mono font-semibold">
              {(entryUsdt * leverage).toFixed(0)} USDT
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
