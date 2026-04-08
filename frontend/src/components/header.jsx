import React from 'react'
import { useStore } from '../store/useStore'

export default function Header() {
  const { botStatus, wsConnected, ticker, config } = useStore()

  return (
    <header className="flex items-center justify-between px-6 py-3 border-b border-border bg-surface sticky top-0 z-50">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-accent rounded flex items-center justify-center">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 10L5 6L8 8L12 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="12" cy="3" r="1.5" fill="white"/>
            </svg>
          </div>
          <span className="font-display font-semibold text-text text-[15px] tracking-tight">ScalpBot</span>
        </div>

        <div className="h-4 w-px bg-border" />

        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-text-faint">{config.symbol.replace('_UMCBL','')}</span>
          {ticker && (
            <span className="font-mono text-[12px] text-text font-medium">
              {parseFloat(ticker.last || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-green-bright' : 'bg-muted'}`} 
               style={wsConnected ? { animation: 'pulse-dot 2s infinite' } : {}} />
          <span className="font-mono text-[11px] text-text-faint">{wsConnected ? 'CONNECTED' : 'OFFLINE'}</span>
        </div>

        <div className="h-4 w-px bg-border" />

        <div className={`flex items-center gap-2 px-3 py-1 rounded text-[11px] font-mono font-medium ${
          botStatus === 'RUNNING' 
            ? 'bg-green-dim border border-green-dim text-green-bright' 
            : 'bg-surface border border-border text-muted'
        }`}>
          {botStatus === 'RUNNING' && (
            <div className="dot w-1.5 h-1.5 rounded-full bg-green-bright" style={{ animation: 'pulse-dot 2s infinite' }} />
          )}
          {botStatus}
        </div>
      </div>
    </header>
  )
}