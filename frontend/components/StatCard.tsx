"use client";
import clsx from "clsx";

interface StatCardProps {
  label:     string;
  value:     string | number;
  sub?:      string;
  color?:    "default" | "success" | "danger" | "warning" | "accent";
  loading?:  boolean;
}

const colorMap = {
  default: "text-text",
  success: "text-success",
  danger:  "text-danger",
  warning: "text-warning",
  accent:  "text-accent",
};

export default function StatCard({
  label, value, sub, color = "default", loading,
}: StatCardProps) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 flex flex-col gap-1 min-w-0">
      <span className="text-[11px] font-medium tracking-widest uppercase text-muted select-none">
        {label}
      </span>
      {loading ? (
        <div className="h-7 w-24 bg-border rounded animate-pulse mt-1" />
      ) : (
        <span className={clsx("text-2xl font-semibold leading-tight font-mono tabular-nums", colorMap[color])}>
          {value}
        </span>
      )}
      {sub && !loading && (
        <span className="text-[11px] text-muted mt-0.5">{sub}</span>
      )}
    </div>
  );
}
