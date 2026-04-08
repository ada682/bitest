import React from 'react'

export default function StatCard({ label, value, sub, color, mono }) {
  const colorMap = {
    green: 'text-green-bright',
    red: 'text-red-bright',
    blue: 'text-accent',
    default: 'text-text',
  }

  return (
    <div className="stat-card">
      <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-2">{label}</div>
      <div className={`text-xl font-display font-semibold ${colorMap[color] || colorMap.default} ${mono ? 'font-mono' : ''}`}>
        {value}
      </div>
      {sub && <div className="text-[11px] text-text-faint mt-1">{sub}</div>}
    </div>
  )
}