import React, { useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useStore } from '../store/useStore'

export default function CandleChart() {
  const { candles, config } = useStore()

  const displaySymbol = config.symbol.replace('_UMCBL', '').replace('USDT', '/USDT')

  const data = useMemo(() => {
    if (!candles?.length) return []
    
    console.log('Candles received:', candles.length) // Debug
    
    return candles.slice(-60).map(c => ({
      time: new Date(Number(c[0])).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' }),
      price: parseFloat(c[4]), // close price
      high: parseFloat(c[2]),
      low: parseFloat(c[3]),
    }))
  }, [candles])

  if (!data.length) {
    return (
      <div className="panel p-4">
        <div className="text-center py-12 text-muted">Loading chart data...</div>
      </div>
    )
  }

  return (
    <div className="panel p-4">
      <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">
        {displaySymbol} — 1m
      </div>
      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1c2333" />
            <XAxis dataKey="time" tick={{ fill: '#4b5563', fontSize: 9 }} />
            <YAxis domain={['auto', 'auto']} tick={{ fill: '#4b5563', fontSize: 9 }} />
            <Tooltip />
            <Line type="monotone" dataKey="price" stroke="#2563eb" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
