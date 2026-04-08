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
        {/* Sidebar — hidden on mobile, shown on lg+ */}
        <div className="hidden lg:block">
          <Sidebar />
        </div>
        <main className="flex-1 overflow-auto p-3 sm:p-4 pb-20 lg:pb-4">
          {activeTab === 'dashboard' && <Dashboard />}
          {activeTab === 'bot' && <BotControl />}
          {activeTab === 'history' && <TradeHistory />}
          {activeTab === 'market' && <Dashboard />}
        </main>
      </div>
      {/* Bottom nav — only on mobile */}
      <BottomNav />
    </div>
  )
}

function BottomNav() {
  const { activeTab, setActiveTab, botStatus } = useStore()

  const nav = [
    {
      id: 'dashboard', label: 'Dashboard',
      icon: (
        <svg width="20" height="20" viewBox="0 0 15 15" fill="none">
          <rect x="1" y="1" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.2"/>
          <rect x="8.5" y="1" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.2"/>
          <rect x="1" y="8.5" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.2"/>
          <rect x="8.5" y="8.5" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.2"/>
        </svg>
      )
    },
    {
      id: 'bot', label: 'Bot',
      icon: (
        <svg width="20" height="20" viewBox="0 0 15 15" fill="none">
          <circle cx="7.5" cy="7.5" r="5.5" stroke="currentColor" strokeWidth="1.2"/>
          <path d="M5.5 7.5L6.8 8.8L9.5 6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )
    },
    {
      id: 'history', label: 'History',
      icon: (
        <svg width="20" height="20" viewBox="0 0 15 15" fill="none">
          <path d="M1.5 7.5C1.5 4.186 4.186 1.5 7.5 1.5S13.5 4.186 13.5 7.5 10.814 13.5 7.5 13.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
          <path d="M7.5 4.5V7.5L9.5 9.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M1.5 10.5H4.5M3 12V9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
        </svg>
      )
    },
    {
      id: 'market', label: 'Market',
      icon: (
        <svg width="20" height="20" viewBox="0 0 15 15" fill="none">
          <path d="M1 11L4 7L7 9L10 4.5L14 8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )
    },
  ]

  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 bg-surface border-t border-border flex z-50">
      {nav.map(item => {
        const isActive = activeTab === item.id
        const showDot = item.id === 'bot' && botStatus === 'RUNNING'
        return (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={`flex-1 flex flex-col items-center justify-center gap-1 py-2.5 transition-all relative ${
              isActive ? 'text-accent' : 'text-muted'
            }`}
          >
            {showDot && (
              <span className="absolute top-1.5 right-1/4 w-1.5 h-1.5 bg-green-bright rounded-full" />
            )}
            {item.icon}
            <span className="text-[10px] font-mono">{item.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
