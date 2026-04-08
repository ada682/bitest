import React from 'react'
import { useStore } from '../store/useStore'

const nav = [
  { id: 'dashboard', label: 'Dashboard', icon: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
      <rect x="1" y="1" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.2"/>
      <rect x="8.5" y="1" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.2"/>
      <rect x="1" y="8.5" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.2"/>
      <rect x="8.5" y="8.5" width="5.5" height="5.5" rx="1" stroke="currentColor" strokeWidth="1.2"/>
    </svg>
  )},
  { id: 'bot', label: 'Bot Control', icon: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
      <circle cx="7.5" cy="7.5" r="5.5" stroke="currentColor" strokeWidth="1.2"/>
      <path d="M5.5 7.5L6.8 8.8L9.5 6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )},
  { id: 'history', label: 'Trade History', icon: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
      <path d="M1.5 7.5C1.5 4.186 4.186 1.5 7.5 1.5S13.5 4.186 13.5 7.5 10.814 13.5 7.5 13.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
      <path d="M7.5 4.5V7.5L9.5 9.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M1.5 10.5H4.5M3 12V9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
    </svg>
  )},
  { id: 'market', label: 'Market', icon: (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
      <path d="M1 11L4 7L7 9L10 4.5L14 8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )},
]

export default function Sidebar() {
  const { activeTab, setActiveTab, botStatus } = useStore()

  return (
    <aside className="w-48 bg-surface border-r border-border flex flex-col shrink-0">
      <nav className="flex flex-col gap-0.5 p-2 mt-1">
        {nav.map(item => (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-all text-left ${
              activeTab === item.id
                ? 'bg-accent/10 text-accent border border-accent/20'
                : 'text-text-faint hover:text-text hover:bg-panel'
            }`}
          >
            {item.icon}
            <span className="font-sans">{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="mt-auto p-3 border-t border-border">
        <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-2">System</div>
        <div className="flex items-center gap-2 text-[11px] font-mono">
          <div className={`w-1.5 h-1.5 rounded-full ${botStatus === 'RUNNING' ? 'bg-green-bright' : 'bg-muted'}`} />
          <span className="text-text-faint">{botStatus === 'RUNNING' ? 'Active' : 'Standby'}</span>
        </div>
      </div>
    </aside>
  )
}