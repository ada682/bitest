import React, { useMemo } from 'react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from 'recharts'
import { useStore } from '../store/useStore'

const CandleTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  return (
    <div className="bg-panel border border-border rounded px-3 py-2 text-[11px] font-mono shadow-xl">
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {['O','H','L','C'].map((k, i) => (
          <React.Fragment key={k}>
            <span className="text-muted">{k}</span>
            <span className="text-text text-right">{[d.open,d.high,d.low,d.close][i]?.toFixed(2)}</span>
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}

function CandlestickBar(props) {
  const { x, width, payload, yAxisMap } = props
  if (!payload) return null

  const { open, close, high, low } = payload
  const isUp = close >= open
  const color = isUp ? '#22c55e' : '#ef4444'

  const scale = yAxisMap?.[0]?.scale
  if (!scale) return null

  const highY = scale(high)
  const lowY = scale(low)
  const openY = scale(open)
  const closeY = scale(close)
  const bodyY = Math.min(openY, closeY)
  const bodyHeight = Math.max(Math.abs(openY - closeY), 1)
  const cx = x + width / 2

  return (
    <g>
      <line x1={cx} y1={highY} x2={cx} y2={lowY} stroke={color} strokeWidth={0.8} />
      <rect x={x + 1} y={bodyY} width={Math.max(width - 2, 1)} height={bodyHeight} fill={color} />
    </g>
  )
}

export default function CandleChart() {
  const { candles, config } = useStore()

  const displaySymbol = config.symbol.replace('_UMCBL', '').replace('USDT', '/USDT')

  const data = useMemo(() => {
    if (!candles?.length) return []
    return candles.slice(-60).map(c => ({
      // V2 candle: [ts, open, high, low, close, baseVol, quoteVol]
      time: new Date(Number(c[0])).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' }),
      open:   parseFloat(c[1]),
      high:   parseFloat(c[2]),
      low:    parseFloat(c[3]),
      close:  parseFloat(c[4]),
      volume: parseFloat(c[5]),
    }))
  }, [candles])

  const [minPrice, maxPrice] = useMemo(() => {
    if (!data.length) return [0, 1]
    const lows  = data.map(d => d.low)
    const highs = data.map(d => d.high)
    const pad   = (Math.max(...highs) - Math.min(...lows)) * 0.05
    return [Math.min(...lows) - pad, Math.max(...highs) + pad]
  }, [data])

  if (!data.length) {
    return (
      <div className="panel p-4">
        <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">
          {displaySymbol} — 1m
        </div>
        <div className="flex items-center justify-center h-52 text-muted text-sm">
          Waiting for market data...
        </div>
      </div>
    )
  }

  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-mono text-muted uppercase tracking-widest">
          {displaySymbol} — 1m
        </span>
        <span className="text-[11px] font-mono text-text-faint">
          {data[data.length - 1]?.close?.toLocaleString('en-US', { minimumFractionDigits: 2 })}
        </span>
      </div>

      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1c2333" vertical={false} />
            <XAxis
              dataKey="time"
              tick={{ fill: '#4b5563', fontSize: 9, fontFamily: 'IBM Plex Mono' }}
              axisLine={false} tickLine={false}
              interval={Math.floor(data.length / 6)}
            />
            <YAxis
              domain={[minPrice, maxPrice]}
              tick={{ fill: '#4b5563', fontSize: 9, fontFamily: 'IBM Plex Mono' }}
              axisLine={false} tickLine={false}
              tickFormatter={v => v.toFixed(0)}
            />
            <Tooltip content={<CandleTooltip />} />
            <Bar dataKey="close" shape={<CandlestickBar />} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
