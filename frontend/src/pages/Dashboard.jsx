import React, { useEffect } from 'react'
import { useStore } from '../store/useStore'
import SignalList from '../components/SignalList'

export default function Dashboard() {
  const { stats, botStatus, statusMessage, fetchStats, fetchSignals, initWs, fetchBotState } = useStore()

  useEffect(() => {
    initWs()
    fetchBotState()
    fetchStats()
    fetchSignals(200)
    const interval = setInterval(() => {
      fetchStats()
      fetchSignals(200)
    }, 10000)
    return () => clearInterval(interval)
  }, [])

  const winrate = stats.winrate || 0
  const totalTrades = stats.trade_count || 0
  const wins = stats.win_count || 0
  const losses = stats.loss_count || 0
  const totalPnl = stats.total_pnl_pct || 0

  return (
    <div className="flex flex-col gap-5">
      {/* Header statistik */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="stat-card">
          <div className="text-[10px] font-mono text-muted uppercase">Bot Status</div>
          <div className={`text-lg font-display font-semibold ${botStatus === 'RUNNING' ? 'text-green-bright' : 'text-muted'}`}>
            {botStatus}
          </div>
          {statusMessage && <div className="text-[10px] text-text-faint mt-1">{statusMessage}</div>}
        </div>
        <div className="stat-card">
          <div className="text-[10px] font-mono text-muted uppercase">Total Trades</div>
          <div className="text-xl font-display font-semibold text-text">{totalTrades}</div>
        </div>
        <div className="stat-card">
          <div className="text-[10px] font-mono text-muted uppercase">Win Rate</div>
          <div className={`text-xl font-display font-semibold ${winrate >= 50 ? 'text-green-bright' : 'text-red-bright'}`}>
            {winrate.toFixed(1)}%
          </div>
        </div>
        <div className="stat-card">
          <div className="text-[10px] font-mono text-muted uppercase">Total PnL %</div>
          <div className={`text-xl font-display font-semibold ${totalPnl >= 0 ? 'text-green-bright' : 'text-red-bright'}`}>
            {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Daftar sinyal */}
      <div className="panel p-4">
        <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">
          Live AI Signals (LONG/SHORT)
        </div>
        <SignalList />
      </div>
    </div>
  )
}
