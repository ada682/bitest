import React, { useState } from 'react'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Cell
} from 'recharts'
import { useStore } from '../store/useStore'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  const val = payload[0].value
  const isNeg = val < 0
  return (
    <div className="bg-panel border border-border rounded px-3 py-2 text-[11px] font-mono shadow-xl">
      <div className="text-text-faint mb-1">{label}</div>
      <div className={isNeg ? 'text-red-bright' : 'text-green-bright'}>
        {isNeg ? '' : '+'}{val} USDT
      </div>
    </div>
  )
}

const CumTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-panel border border-border rounded px-3 py-2 text-[11px] font-mono shadow-xl">
      <div className="text-text-faint mb-1">{label}</div>
      <div className="text-accent">{payload[0].value} USDT</div>
    </div>
  )
}

export default function ProfitChart() {
  const { pnlHistory, trades, summary } = useStore()
  const [view, setView] = useState('cumulative')

  const hasData = pnlHistory.length > 0

  const mockData = !hasData ? Array.from({ length: 14 }, (_, i) => ({
    date: `4/${i + 1}`,
    pnl: parseFloat((Math.random() * 4 - 1.5).toFixed(3)),
    cumulative: 0,
  })).map((d, i, arr) => {
    const cum = arr.slice(0, i + 1).reduce((s, x) => s + x.pnl, 0)
    return { ...d, cumulative: parseFloat(cum.toFixed(3)) }
  }) : pnlHistory

  const data = hasData ? pnlHistory : mockData

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between mb-4">
        <span className="text-[10px] font-mono text-muted uppercase tracking-widest">Profit / Loss</span>
        <div className="flex gap-1">
          {['cumulative', 'daily'].map(v => (
            <button key={v} onClick={() => setView(v)}
              className={`px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider transition-all ${
                view === v ? 'bg-accent/15 text-accent border border-accent/25' : 'text-muted hover:text-text-faint'
              }`}>
              {v}
            </button>
          ))}
        </div>
      </div>

      {!hasData && (
        <div className="text-[10px] font-mono text-muted text-center mb-2 opacity-60">
          Preview mode — no trade data yet
        </div>
      )}

      <div className="h-40">
        {view === 'cumulative' ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="gradCum" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2563eb" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1c2333" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: '#4b5563', fontSize: 10, fontFamily: 'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#4b5563', fontSize: 10, fontFamily: 'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CumTooltip />} />
              <ReferenceLine y={0} stroke="#1c2333" />
              <Area type="monotone" dataKey="cumulative" stroke="#2563eb" strokeWidth={1.5} fill="url(#gradCum)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1c2333" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: '#4b5563', fontSize: 10, fontFamily: 'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#4b5563', fontSize: 10, fontFamily: 'IBM Plex Mono' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="#374151" />
              <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
                {data.map((entry, i) => (
                  <Cell key={i} fill={entry.pnl >= 0 ? '#16a34a' : '#dc2626'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
