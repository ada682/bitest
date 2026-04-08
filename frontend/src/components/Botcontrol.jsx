import React from 'react'
import { useStore } from '../store/useStore'

export default function BotControl() {
  const { botStatus, config, setConfig, startBot, stopBot, statusMessage, lastError, contracts } = useStore()
  const isRunning = botStatus === 'RUNNING'

  const handleStart = async () => {
    if (isRunning) await stopBot()
    else await startBot()
  }

  return (
    <div className="panel p-4 sm:p-5 max-w-lg mx-auto lg:max-w-none">
      <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-4">Bot Configuration</div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
        {/* Symbol */}
        <div className="sm:col-span-2">
          <label className="block text-[10px] font-mono text-muted uppercase tracking-wider mb-1.5">Symbol</label>
          <select
            value={config.symbol}
            onChange={e => setConfig({ symbol: e.target.value })}
            disabled={isRunning}
            className="w-full bg-panel border border-border rounded px-3 py-2 text-sm font-mono text-text focus:outline-none focus:border-accent disabled:opacity-50"
          >
            {contracts.length > 0 ? contracts.slice(0, 30).map(c => (
              <option key={c.symbol} value={c.symbol}>{c.symbol?.replace('_UMCBL','')}</option>
            )) : (
              <option value="BTCUSDT_UMCBL">BTCUSDT</option>
            )}
          </select>
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

        {/* Manual margin */}
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

        {/* TP % */}
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

        {/* SL % */}
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

      {/* Start / Stop */}
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
