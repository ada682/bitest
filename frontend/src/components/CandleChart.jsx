import React, { useRef, useEffect } from 'react'
import { createChart } from 'lightweight-charts'
import { useStore } from '../store/useStore'

export default function CandleChart() {
  const { candles, config } = useStore()
  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)

  const displaySymbol = config.symbol.replace('_UMCBL', '').replace('USDT', '/USDT')

  useEffect(() => {
    if (!chartContainerRef.current || !candles?.length) return

    // Buat chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#0d1117' },
        textColor: '#e2e8f0',
      },
      grid: {
        vertLines: { color: '#1c2333' },
        horzLines: { color: '#1c2333' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 200,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    })

    // Candlestick series
    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    })

    // Format data
    const chartData = candles.slice(-60).map(c => ({
      time: Math.floor(Number(c[0]) / 1000), // Unix timestamp in seconds
      open: parseFloat(c[1]),
      high: parseFloat(c[2]),
      low: parseFloat(c[3]),
      close: parseFloat(c[4]),
    }))

    candlestickSeries.setData(chartData)
    
    chart.timeScale().fitContent()

    chartRef.current = chart

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      if (chartRef.current) {
        chartRef.current.remove()
      }
    }
  }, [candles])

  if (!candles?.length) {
    return (
      <div className="panel p-4">
        <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">
          {displaySymbol} — 1m
        </div>
        <div className="flex items-center justify-center h-52 text-muted text-sm">
          Loading market data...
        </div>
      </div>
    )
  }

  return (
    <div className="panel p-4">
      <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">
        {displaySymbol} — 1m
      </div>
      <div ref={chartContainerRef} style={{ height: '200px', width: '100%' }} />
    </div>
  )
}
