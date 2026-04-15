import React from 'react'
import { useStore } from '../store/useStore'

export default function Header() {
  const { botStatus, wsConnected, stats } = useStore()
  const totalPnl = stats.total_pnl_pct || 0

  return (
    <header className="flex items-center justify-between px-4 py-2 border-b border-border bg-surface">
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 bg-accent rounded flex items-center justify-center">
          <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
            <path d="M2 10L5 6L8 8L12 3" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
            <circle cx="12" cy="3" r="1.5" fill="white"/>
          </svg>
        </div>
        <span className="font-display font-semibold text-text">ScalpBot Signal</span>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden sm:flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-green-bright' : 'bg-muted'}`}
               style={wsConnected ? { animation: 'pulse-dot 2s infinite' } : {}} />
          <span className="font-mono text-[11px] text-text-faint">{wsConnected ? 'LIVE' : 'OFFLINE'}</span>
        </div>

        <div className={`flex items-center gap-1.5 px-3 py-1 rounded text-[11px] font-mono ${
          botStatus === 'RUNNING' ? 'bg-green-dim text-green-bright border border-green-dim' : 'bg-surface text-muted border border-border'
        }`}>
          {botStatus === 'RUNNING' && <div className="w-1.5 h-1.5 rounded-full bg-green-bright animate-pulse" />}
          {botStatus}
        </div>

        <div className="text-[11px] font-mono text-text-faint">
          PnL: <span className={totalPnl >= 0 ? 'text-green-bright' : 'text-red-bright'}>{totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)}%</span>
        </div>
      </div>
    </header>
  )
}
