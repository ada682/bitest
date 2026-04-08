import React from 'react'
import { useStore } from '../store/useStore'
import StatCard from '../components/StatCard'
import SignalPanel from '../components/SignalPanel'
import PositionPanel from '../components/PositionPanel'
import ProfitChart from '../components/ProfitChart'
import CandleChart from '../components/CandleChart'

export default function Dashboard() {
  const { summary, totalPnl, tradeCount, winCount, lossCount } = useStore()

  const wins = summary?.wins ?? winCount
  const losses = summary?.losses ?? lossCount
  const total = summary?.total_trades ?? tradeCount
  const winrate = total > 0 ? ((wins / total) * 100).toFixed(1) : '—'
  const realPnl = summary?.total_pnl ?? totalPnl
  const avgProfit = summary?.avg_profit ?? (total > 0 ? (realPnl / total).toFixed(4) : 0)

  return (
    <div className="flex flex-col gap-4">
      {/* Stats row — 2 cols on mobile, 5 on desktop */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 sm:gap-3">
        <StatCard
          label="Total PnL"
          value={`${realPnl >= 0 ? '+' : ''}${parseFloat(realPnl).toFixed(4)}`}
          sub="USDT"
          color={realPnl >= 0 ? 'green' : 'red'}
          mono
        />
        <StatCard label="Total Trades" value={total || 0} sub="executed" />
        <StatCard label="Win Rate" value={winrate === '—' ? '—' : `${winrate}%`}
                  color={parseFloat(winrate) >= 50 ? 'green' : 'red'} />
        <StatCard
          label="Avg Profit"
          value={`${parseFloat(avgProfit) >= 0 ? '+' : ''}${parseFloat(avgProfit).toFixed(4)}`}
          sub="per trade"
          color={parseFloat(avgProfit) >= 0 ? 'green' : 'red'}
          mono
        />
        <StatCard
          label="W / L"
          value={`${wins} / ${losses}`}
          sub="wins vs losses"
          className="col-span-2 sm:col-span-1"
        />
      </div>

      {/* Main grid — stacked on mobile, 3-col on desktop */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Charts — full width on mobile, 2 cols on desktop */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          <CandleChart />
          <ProfitChart />
        </div>

        {/* Signal + Position — full width on mobile */}
        <div className="flex flex-col gap-4">
          <SignalPanel />
          <PositionPanel />
        </div>
      </div>
    </div>
  )
}
