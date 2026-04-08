import React, { useState, useEffect } from 'react'
import { useStore } from '../store/useStore'

export default function PositionPanel() {
  const { openPosition, ticker } = useStore()
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!openPosition) return
    const t = setInterval(() => {
      setElapsed(Math.floor((Date.now() - openPosition.timestamp) / 1000))
    }, 1000)
    return () => clearInterval(t)
  }, [openPosition])

  if (!openPosition) {
    return (
      <div className="panel p-4">
        <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-4">Open Position</div>
        <div className="flex items-center justify-center py-8 text-muted text-sm">
          No open position
        </div>
      </div>
    )
  }

  // V2 uses lastPr, fallback to last
  const currentPrice = ticker ? parseFloat(ticker.lastPr || ticker.last || 0) : openPosition.entry
  const priceDiff = currentPrice - openPosition.entry
  const isLong = openPosition.direction === 'BUY'
  const unrealizedPnl = isLong ? priceDiff * parseFloat(openPosition.size) : -priceDiff * parseFloat(openPosition.size)
  const pnlColor = unrealizedPnl >= 0 ? 'text-green-bright' : 'text-red-bright'

  const formatTime = (s) => `${Math.floor(s/60).toString().padStart(2,'0')}:${(s%60).toString().padStart(2,'0')}`

  const tpDist = Math.abs((openPosition.tp - openPosition.entry) / openPosition.entry * 100)
  const slDist = Math.abs((openPosition.sl - openPosition.entry) / openPosition.entry * 100)
  const progress = Math.min(100, Math.abs(priceDiff) / Math.abs(openPosition.tp - openPosition.entry) * 100)

  const displaySymbol = openPosition.symbol?.replace('_UMCBL', '').replace('USDT', '/USDT')

  return (
    <div className={`panel p-4 border ${isLong ? 'border-green-dim' : 'border-red-dim'} ${isLong ? 'glow-green' : 'glow-red'}`}>
      <div className="flex items-center justify-between mb-4">
        <span className="text-[10px] font-mono text-muted uppercase tracking-widest">Open Position</span>
        <span className="font-mono text-[11px] text-text-faint">{formatTime(elapsed)}</span>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <div className={`px-2.5 py-1 rounded text-[11px] font-mono font-semibold ${
          isLong ? 'bg-green-dim text-green-bright border border-green-dim' : 'bg-red-dim text-red-bright border border-red-dim'
        }`}>
          {isLong ? 'LONG' : 'SHORT'}
        </div>
        <span className="font-display font-semibold text-text">{displaySymbol}</span>
        <span className="font-mono text-sm text-text-faint">x{openPosition.size}</span>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-4">
        {[
          { l: 'Entry',       v: openPosition.entry?.toFixed(4) },
          { l: 'Current',     v: currentPrice.toFixed(4) },
          { l: 'Take Profit', v: openPosition.tp?.toFixed(4), col: 'text-green-bright' },
          { l: 'Stop Loss',   v: openPosition.sl?.toFixed(4), col: 'text-red-bright' },
        ].map(({ l, v, col }) => (
          <div key={l} className="bg-panel rounded p-2">
            <div className="text-[9px] font-mono text-muted uppercase mb-1">{l}</div>
            <div className={`text-[12px] font-mono ${col || 'text-text'}`}>{v}</div>
          </div>
        ))}
      </div>

      <div className="border-t border-border pt-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] font-mono text-muted uppercase tracking-wider">Unrealized PnL</span>
          <span className={`text-sm font-mono font-semibold ${pnlColor}`}>
            {unrealizedPnl >= 0 ? '+' : ''}{unrealizedPnl.toFixed(4)} USDT
          </span>
        </div>
        <div className="h-1 bg-panel rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all duration-300 bg-accent"
               style={{ width: `${progress}%` }} />
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-[10px] font-mono text-muted">SL -{slDist.toFixed(2)}%</span>
          <span className="text-[10px] font-mono text-muted">TP +{tpDist.toFixed(2)}%</span>
        </div>
      </div>
    </div>
  )
}
