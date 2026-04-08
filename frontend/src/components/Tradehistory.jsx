import React from 'react'
import { useStore } from '../store/useStore'

export default function TradeHistory() {
  const { trades } = useStore()

  return (
    <div className="panel">
      <div className="px-4 py-3 border-b border-border">
        <span className="text-[10px] font-mono text-muted uppercase tracking-widest">Recent Trades</span>
      </div>
      <div className="overflow-auto max-h-[calc(100vh-200px)]">
        {trades.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-muted text-sm">No trades recorded</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px]">
              <thead>
                <tr className="border-b border-border">
                  {['Side','Symbol','Size','Entry','Exit','PnL','Time'].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-[9px] font-mono text-muted uppercase tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => {
                  const pnl = parseFloat(t.achievedProfits || 0)
                  const isWin = pnl > 0
                  return (
                    <tr key={i} className="border-b border-border/50 hover:bg-panel/60 transition-colors">
                      <td className="px-3 py-2">
                        <span className={`text-[10px] font-mono font-medium ${
                          t.holdSide === 'long' ? 'text-green-bright' : 'text-red-bright'
                        }`}>
                          {t.holdSide?.toUpperCase() || '—'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-[11px] font-mono text-text-faint whitespace-nowrap">
                        {t.symbol?.replace('_UMCBL', '')}
                      </td>
                      <td className="px-3 py-2 text-[11px] font-mono text-text-faint">{t.openDealCount || '—'}</td>
                      <td className="px-3 py-2 text-[11px] font-mono text-text-faint whitespace-nowrap">
                        {parseFloat(t.averageOpenPrice || 0).toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-[11px] font-mono text-text-faint whitespace-nowrap">
                        {parseFloat(t.averageClosePrice || 0).toFixed(2)}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`text-[11px] font-mono font-medium ${isWin ? 'text-green-bright' : 'text-red-bright'}`}>
                          {pnl >= 0 ? '+' : ''}{pnl.toFixed(4)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-[10px] font-mono text-muted whitespace-nowrap">
                        {t.ctime ? new Date(Number(t.ctime)).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
