import React, { useEffect } from 'react'
import { useStore } from './store/useStore'
import Header from './components/header'
import Dashboard from './pages/Dashboard'

export default function App() {
  const { initWs, fetchBotState, fetchStats, fetchSignals } = useStore()

  useEffect(() => {
    initWs()
    fetchBotState()
    fetchStats()
    fetchSignals(200)
  }, [])

  return (
    <div className="flex flex-col h-screen bg-bg">
      <Header />
      <main className="flex-1 overflow-auto p-4">
        <Dashboard />
      </main>
    </div>
  )
}
