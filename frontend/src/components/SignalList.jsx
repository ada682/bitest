import React, { useState } from 'react'
import { useStore } from '../store/useStore'

function SignalCard({ signal }) {
  const [expanded, setExpanded] = useState(false)
  const isLong = signal.decision === 'LONG'
  const isShort = signal.decision === 'SHORT'
  const isNoTrade = signal.decision === 'NO TRADE'
  const isClosed = signal.status === 'CLOSED'
  const resultColor = signal.result === 'TP' ? 'text-green-bright' : 'text-red-bright'

  return (
    <div className="bg-panel border border-border rounded-lg p-3 hover:border-accent/30 transition-all">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span className="font-mono font-semibold text-text">{signal.symbol}</span>
          <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${
            isLong ? 'bg-green-dim text-green-bright border border-green-dim' :
            isShort ? 'bg-red-dim text-red-bright border border-red-dim' :
            'bg-panel text-muted border border-border'
          }`}>
            {signal.decision}
          </span>
          {isClosed && (
            <span className={`text-[10px] font-mono ${resultColor}`}>
              {signal.result} ({signal.pnl_pct >= 0 ? '+' : ''}{signal.pnl_pct}%)
            </span>
          )}
        </div>
        <div className="text-[10px] font-mono text-muted">
          {new Date(signal.timestamp).toLocaleString()}
        </div>
      </div>

      <div className="mt-2 text-[11px] text-text-faint">
        <span>Entry: {signal.entry?.toFixed(4)}</span>
        {signal.tp && <span className="ml-3">TP: {signal.tp.toFixed(4)}</span>}
        {signal.sl && <span className="ml-3">SL: {signal.sl.toFixed(4)}</span>}
      </div>

      {signal.reason && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 text-[10px] font-mono text-accent hover:underline"
        >
          {expanded ? 'Hide reason' : 'Show reason'}
        </button>
      )}

      {expanded && signal.reason && (
        <p className="mt-2 text-[11px] text-text-faint border-t border-border pt-2">
          {signal.reason}
        </p>
      )}
    </div>
  )
}

export default function SignalList() {
  const { signals } = useStore()

  if (!signals.length) {
    return (
      <div className="panel p-8 text-center text-muted">
        No signals yet. Start the bot to see AI trade ideas.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 max-h-[70vh] overflow-y-auto pr-1">
      {signals.map(signal => (
        <SignalCard key={signal.id} signal={signal} />
      ))}
    </div>
  )
}
