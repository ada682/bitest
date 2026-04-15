"use client";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from "recharts";
import type { Signal } from "@/lib/types";

interface Props {
  signals: Signal[];
}

export default function PnlChart({ signals }: Props) {
  // Only closed signals with a pnl value
  const closed = [...signals]
    .filter((s) => s.status === "CLOSED" && s.pnl_pct != null)
    .reverse(); // oldest first

  if (closed.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-muted text-xs font-mono">
        No closed signals yet
      </div>
    );
  }

  // Cumulative PnL
  let cum = 0;
  const data = closed.map((s) => {
    cum = parseFloat((cum + (s.pnl_pct ?? 0)).toFixed(4));
    return {
      name:   s.symbol.replace("_USDT", ""),
      pnl:    parseFloat((s.pnl_pct ?? 0).toFixed(4)),
      cumPnl: cum,
    };
  });

  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
      <div className="bg-card border border-border rounded-lg px-3 py-2 text-xs font-mono shadow-xl">
        <p className="text-subtle mb-1">{d.name}</p>
        <p className={d.pnl >= 0 ? "text-success" : "text-danger"}>
          Trade: {d.pnl >= 0 ? "+" : ""}{d.pnl.toFixed(4)}%
        </p>
        <p className={d.cumPnl >= 0 ? "text-success" : "text-danger"}>
          Cum: {d.cumPnl >= 0 ? "+" : ""}{d.cumPnl.toFixed(4)}%
        </p>
      </div>
    );
  };

  return (
    <ResponsiveContainer width="100%" height={160}>
      <LineChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="2 4" stroke="#1E2D45" vertical={false} />
        <XAxis
          dataKey="name"
          tick={{ fill: "#4B6280", fontSize: 10, fontFamily: "JetBrains Mono" }}
          axisLine={false} tickLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: "#4B6280", fontSize: 10, fontFamily: "JetBrains Mono" }}
          axisLine={false} tickLine={false}
          tickFormatter={(v) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`}
          width={58}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ stroke: "#1E2D45" }} />
        <ReferenceLine y={0} stroke="#1E2D45" strokeDasharray="3 3" />
        <Line
          type="monotone"
          dataKey="cumPnl"
          stroke="#1D6FD8"
          strokeWidth={1.5}
          dot={false}
          activeDot={{ r: 4, fill: "#1D6FD8", stroke: "#0B0F1A", strokeWidth: 2 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
