"use client";
import clsx from "clsx";

interface StatCardProps {
  label:      string;
  value:      string | number;
  sub?:       string;
  color?:     "default" | "success" | "danger" | "warning" | "accent";
  loading?:   boolean;
  className?: string;
}

const colorMap = {
  default: "text-text",
  success: "text-success",
  danger:  "text-danger",
  warning: "text-warning",
  accent:  "text-accent",
};

export default function StatCard({
  label, value, sub, color = "default", loading, className,
}: StatCardProps) {
  return (
    <div className={clsx("bg-card border border-border rounded-xl p-3 sm:p-4 flex flex-col gap-1 min-w-0", className)}>
      <span className="text-[10px] sm:text-[11px] font-medium tracking-widest uppercase text-muted select-none truncate">
        {label}
      </span>
      {loading ? (
        <div className="h-6 sm:h-7 w-20 bg-border rounded animate-pulse mt-1" />
      ) : (
        <span className={clsx("text-xl sm:text-2xl font-semibold leading-tight font-mono tabular-nums", colorMap[color])}>
          {value}
        </span>
      )}
      {sub && !loading && (
        <span className="text-[10px] sm:text-[11px] text-muted mt-0.5 truncate">{sub}</span>
      )}
    </div>
  );
}
