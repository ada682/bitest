import React, { useState, useRef, useEffect } from 'react'
import { useStore } from '../store/useStore'

export default function BotControl() {
  const { botStatus, config, setConfig, startBot, stopBot, statusMessage, lastError, contracts } = useStore()
  const [searchTerm, setSearchTerm] = useState('')
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const dropdownRef = useRef(null)
  
  const isRunning = botStatus === 'RUNNING'

  const handleStart = async () => {
    if (isRunning) await stopBot()
    else await startBot()
  }

  const cleanSymbol = (sym) => sym?.replace('_UMCBL', '').replace('USDT', '/USDT')
  
  // Filter contracts
  const filteredContracts = contracts.filter(c => {
    const symbol = cleanSymbol(c.symbol).toLowerCase()
    return symbol.includes(searchTerm.toLowerCase())
  })

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const selectedDisplay = cleanSymbol(config.symbol)

  return (
    <div className="panel p-4 sm:p-5 max-w-lg mx-auto lg:max-w-none">
      <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-4">Bot Configuration</div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
        {/* Symbol dengan custom dropdown */}
        <div className="sm:col-span-2" ref={dropdownRef}>
          <label className="block text-[10px] font-mono text-muted uppercase tracking-wider mb-1.5">Symbol</label>
          
          {/* Search input */}
          <input
            type="text"
            placeholder="🔍 Search pair (e.g., BTC, ETH, ENJ, SOL)..."
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value)
              setIsDropdownOpen(true)
            }}
            onFocus={() => setIsDropdownOpen(true)}
            className="w-full bg-panel border border-border rounded px-3 py-2 text-sm font-mono text-text focus:outline-none focus:border-accent mb-2"
            disabled={isRunning}
          />
          
          {/* Custom dropdown button */}
          <button
            type="button"
            onClick={() => !isRunning && setIsDropdownOpen(!isDropdownOpen)}
            disabled={isRunning}
            className="w-full bg-panel border border-border rounded px-3 py-2 text-sm font-mono text-text flex justify-between items-center hover:border-accent transition-colors"
          >
            <span>{selectedDisplay || 'Select pair...'}</span>
            <span className={`transform transition-transform ${isDropdownOpen ? 'rotate-180' : ''}`}>▼</span>
          </button>
          
          {/* Dropdown list */}
          {isDropdownOpen && !isRunning && (
            <div className="absolute z-50 mt-1 w-full max-h-60 overflow-auto bg-surface border border-border rounded shadow-lg">
              {filteredContracts.length === 0 ? (
                <div className="px-3 py-2 text-muted text-sm">No pairs found</div>
              ) : (
                filteredContracts.map(c => {
                  const displaySymbol = cleanSymbol(c.symbol)
                  const isSelected = config.symbol === c.symbol
                  return (
                    <button
                      key={c.symbol}
                      onClick={() => {
                        console.log('✅ Selected:', c.symbol)
                        setConfig({ symbol: c.symbol })
                        setIsDropdownOpen(false)
                        setSearchTerm('')
                      }}
                      className={`w-full text-left px-3 py-2 text-sm font-mono hover:bg-panel transition-colors ${
                        isSelected ? 'bg-accent/20 text-accent' : 'text-text'
                      }`}
                    >
                      {displaySymbol}
                    </button>
                  )
                })
              )}
            </div>
          )}
          
          <div className="text-[9px] font-mono text-muted mt-1">
            {filteredContracts.length} of {contracts.length} pairs
          </div>
        </div>

        {/* Leverage */}
        <div>
          <label className="block text-[10px] font-mono text-muted uppercase tracking-wider mb-1.5">Leverage</label>
          <input
            type="number"
            value={config.leverage}
            onChange={e => setConfig({ leverage: e.target.value })}
            disabled={isRunning}
            min="1" max="125"
            className="w-full bg-panel border border-border rounded px-3 py-2 text-sm font-mono text-text focus:outline-none focus:border-accent disabled:opacity-50"
          />
        </div>

        {/* Mode */}
        <div>
          <label className="block text-[10px] font-mono text-muted uppercase tracking-wider mb-1.5">Mode</label>
          <div className="flex rounded border border-border overflow-hidden">
            {['MANUAL', 'ALL_IN'].map(m => (
              <button key={m} onClick={() => !isRunning && setConfig({ mode: m })}
                className={`flex-1 py-2 text-[11px] font-mono transition-all ${
                  config.mode === m ? 'bg-accent text-white' : 'bg-panel text-muted hover:text-text'
                } ${isRunning ? 'opacity-50 cursor-not-allowed' : ''}`}>
                {m.replace('_', '-')}
              </button>
            ))}
          </div>
        </div>

        {config.mode === 'MANUAL' && (
          <div>
            <label className="block text-[10px] font-mono text-muted uppercase tracking-wider mb-1.5">Margin (USDT)</label>
            <input
              type="number"
              value={config.manual_margin}
              onChange={e => setConfig({ manual_margin: parseFloat(e.target.value) })}
              disabled={isRunning}
              className="w-full bg-panel border border-border rounded px-3 py-2 text-sm font-mono text-text focus:outline-none focus:border-accent disabled:opacity-50"
            />
          </div>
        )}

        <div>
          <label className="block text-[10px] font-mono text-muted uppercase tracking-wider mb-1.5">
            Take Profit {(config.tp_pct * 100).toFixed(2)}%
          </label>
          <input
            type="range" min="0.001" max="0.02" step="0.0005"
            value={config.tp_pct}
            onChange={e => setConfig({ tp_pct: parseFloat(e.target.value) })}
            disabled={isRunning}
            className="w-full accent-accent disabled:opacity-50"
          />
        </div>

        <div>
          <label className="block text-[10px] font-mono text-muted uppercase tracking-wider mb-1.5">
            Stop Loss {(config.sl_pct * 100).toFixed(2)}%
          </label>
          <input
            type="range" min="0.001" max="0.01" step="0.0005"
            value={config.sl_pct}
            onChange={e => setConfig({ sl_pct: parseFloat(e.target.value) })}
            disabled={isRunning}
            className="w-full accent-red-bright disabled:opacity-50"
          />
        </div>
      </div>

      <button
        onClick={handleStart}
        className={`w-full py-3 rounded font-display font-semibold text-sm tracking-wide transition-all ${
          isRunning
            ? 'bg-red-dim border border-red-dim text-red-bright hover:bg-red/20'
            : 'bg-accent hover:bg-accent-dim text-white'
        }`}
      >
        {isRunning ? 'Stop Bot' : 'Start Bot'}
      </button>

      {statusMessage && (
        <div className="mt-3 p-2.5 bg-panel rounded border border-border">
          <p className="text-[11px] font-mono text-text-faint">{statusMessage}</p>
        </div>
      )}

      {lastError && (
        <div className="mt-2 p-2.5 bg-red-dim rounded border border-red-dim">
          <p className="text-[11px] font-mono text-red-bright">{lastError}</p>
        </div>
      )}
    </div>
  )
}
