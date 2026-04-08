import React from 'react'
import { useStore } from '../store/useStore'

function ConfidenceBar({ value }) {
  const color = value >= 80 ? '#22c55e' : value >= 60 ? '#f59e0b' : '#ef4444'
  return (
    <div className="mt-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] font-mono text-muted uppercase tracking-wider">Confidence</span>
        <span className="text-[11px] font-mono" style={{ color }}>{value}%</span>
      </div>
      <div className="h-1 bg-panel rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500" 
             style={{ width: `${value}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}

export default function SignalPanel() {
  const { lastSignal, statusMessage } = useStore()

  const isLong = lastSignal?.decision === 'BUY'
  const isShort = lastSignal?.decision === 'SELL'
  const isActive = isLong || isShort

  return (
    <div className="panel p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono text-muted uppercase tracking-widest">AI Signal</span>
        {lastSignal && (
          <span className="text-[10px] font-mono text-text-faint">
            {new Date(lastSignal.timestamp).toLocaleTimeString()}
          </span>
        )}
      </div>

      {lastSignal ? (
        <>
          <div className={`flex items-center justify-center py-3 rounded-md border text-sm font-display font-semibold tracking-wider ${
            isLong
              ? 'bg-green-dim border-green-dim text-green-bright'
              : isShort
              ? 'bg-red-dim border-red-dim text-red-bright'
              : 'bg-panel border-border text-muted'
          }`}>
            {isLong ? 'LONG' : isShort ? 'SHORT' : 'NO TRADE'}
          </div>

          {isActive && (
            <div className="grid grid-cols-3 gap-2">
              {[
                { l: 'Entry', v: lastSignal.entry },
                { l: 'Take Profit', v: lastSignal.tp },
                { l: 'Stop Loss', v: lastSignal.sl },
              ].map(({ l, v }) => (
                <div key={l} className="bg-panel rounded p-2">
                  <div className="text-[9px] font-mono text-muted uppercase tracking-wider mb-1">{l}</div>
                  <div className="text-[12px] font-mono text-text">
                    {typeof v === 'number' ? v.toFixed(4) : v}
                  </div>
                </div>
              ))}
            </div>
          )}

          <ConfidenceBar value={lastSignal.confidence || 0} />

          {lastSignal.reason && (
            <p className="text-[11px] text-text-faint leading-relaxed border-t border-border pt-3">
              {lastSignal.reason}
            </p>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center py-8 gap-2">
          <div className="text-muted text-sm">No signal yet</div>
          {statusMessage && (
            <p className="text-[11px] font-mono text-text-faint text-center">{statusMessage}</p>
          )}
        </div>
      )}
    </div>
  )
}