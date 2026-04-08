import React, { useEffect } from 'react'
import { useStore } from './store/useStore'
import Header from './components/header'
import Sidebar from './components/sidebar'
import Dashboard from './pages/Dashboard'
import BotControl from './components/Botcontrol'
import TradeHistory from './components/Tradehistory'

export default function App() {
  const { activeTab, initWs, fetchBotState, fetchContracts, fetchTicker, fetchCandles, fetchTrades } = useStore()

  useEffect(() => {
    initWs()
    fetchBotState()
    fetchContracts()
    fetchTrades()
    const interval = setInterval(() => {
      fetchTicker()
      fetchCandles()
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="flex flex-col h-screen bg-bg">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-auto p-4">
          {activeTab === 'dashboard' && <Dashboard />}
          {activeTab === 'bot' && <BotControl />}
          {activeTab === 'history' && <TradeHistory />}
        </main>
      </div>
    </div>
  )
}
