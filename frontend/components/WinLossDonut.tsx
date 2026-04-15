"use client";
import {
  ResponsiveContainer, PieChart, Pie, Cell, Tooltip,
} from "recharts";

interface Props {
  wins:   number;
  losses: number;
}

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  return (
    <div className="bg-card border border-border rounded-lg px-3 py-1.5 text-xs font-mono shadow-xl">
      <span className="text-text">{d.name}: {d.value}</span>
    </div>
  );
};

export default function WinLossDonut({ wins, losses }: Props) {
  const total = wins + losses;
  if (total === 0) {
    return (
      <div className="flex items-center justify-center h-24 text-muted text-xs font-mono">
        No closed trades
      </div>
    );
  }

  const data = [
    { name: "Wins",   value: wins },
    { name: "Losses", value: losses },
  ];

  return (
    <div className="flex items-center gap-4">
      <div className="w-20 h-20 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%" cy="50%"
              innerRadius={24} outerRadius={36}
              dataKey="value"
              strokeWidth={0}
              startAngle={90} endAngle={-270}
            >
              <Cell fill="#10B981" />
              <Cell fill="#EF4444" />
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-col gap-2 text-xs font-mono">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-success inline-block" />
          <span className="text-muted">Wins</span>
          <span className="text-text font-medium ml-1">{wins}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-danger inline-block" />
          <span className="text-muted">Losses</span>
          <span className="text-text font-medium ml-1">{losses}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-muted inline-block" />
          <span className="text-muted">Total</span>
          <span className="text-text font-medium ml-1">{total}</span>
        </div>
      </div>
    </div>
  );
}
