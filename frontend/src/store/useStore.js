import { create } from 'zustand'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || ''

export const useStore = create((set, get) => ({
  botStatus: 'IDLE',
  openPosition: null,
  lastSignal: null,
  lastError: null,
  statusMessage: '',
  tradeCount: 0,
  winCount: 0,
  lossCount: 0,
  totalPnl: 0,
  config: {
    symbol: 'BTCUSDT',
    leverage: '10',
    mode: 'MANUAL',
    manual_margin: 10,
    tp_pct: 0.004,
    sl_pct: 0.002,
    volume_place: 3,
  },
  contracts: [],
  ticker: null,
  candles: [],
  trades: [],
  summary: null,
  pnlHistory: [],
  activeTab: 'dashboard',
  wsConnected: false,
  ws: null,
  futuresBalance: {
    available: "0",
    locked: "0",
    equity: "0",
    usdtEquity: "0",
    unrealizedPL: "0",
    loading: false,
  },

  setConfig: (updates) => set(state => ({ config: { ...state.config, ...updates } })),
  setActiveTab: (tab) => set({ activeTab: tab }),

  initWs: () => {
    const wsUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8000')
      .replace('http://', 'ws://')
      .replace('https://', 'wss://')
    const ws = new WebSocket(`${wsUrl}/api/bot/ws`)
    ws.onopen = () => set({ wsConnected: true })
    ws.onclose = () => { set({ wsConnected: false }); setTimeout(() => get().initWs(), 3000) }
    ws.onmessage = (e) => {
      try {
        const { event, data } = JSON.parse(e.data)
        if (event === 'status') set({ statusMessage: data })
        else if (event === 'signal') set({ lastSignal: data })
        else if (event === 'position_open') set({ openPosition: data })
        else if (event === 'position_close') {
          set(state => ({ openPosition: null, tradeCount: state.tradeCount + 1, totalPnl: state.totalPnl + (data.pnl || 0) }))
          get().fetchTrades()
          get().fetchSummary()
        }
        else if (event === 'position_update') {
          set(state => ({
            openPosition: state.openPosition
              ? { ...state.openPosition, unrealized_pnl: data.unrealized_pnl, mark_price: data.mark_price }
              : state.openPosition,
            futuresBalance: { ...state.futuresBalance, unrealizedPL: String(data.unrealized_pnl) }
          }))
        }
        else if (event === 'error') set({ lastError: data })
        // --- Reset events from backend ---
        else if (event === 'reset_ui' || event === 'reset_all') {
          set({
            tradeCount: 0,
            winCount: 0,
            lossCount: 0,
            totalPnl: 0,
            trades: [],
            pnlHistory: [],
            lastSignal: null,
            openPosition: null,
            lastError: null,
            statusMessage: '',
            summary: null,
          })
          if (event === 'reset_all') {
            ws.close()
            setTimeout(() => get().initWs(), 500)
          }
        }
        else if (event === 'clear_trades') {
          set({ trades: [], pnlHistory: [] })
        }
        else if (event === 'reconnect_ws') {
          ws.close()
          setTimeout(() => get().initWs(), 1000)
        }
      } catch {}
    }
    set({ ws })
  },

  startBot: async () => {
    const { config } = get()
    try {
      const res = await axios.post(`${API}/api/bot/start`, config)
      if (res.data.ok) set({ botStatus: 'RUNNING', lastError: null })
      return res.data
    } catch (e) { set({ lastError: e.message }) }
  },

  stopBot: async () => {
    try {
      await axios.post(`${API}/api/bot/stop`)
      set({ botStatus: 'IDLE' })
    } catch (e) { set({ lastError: e.message }) }
  },

  fetchBotState: async () => {
    try {
      const res = await axios.get(`${API}/api/bot/state`)
      const d = res.data
      set({ botStatus: d.status, openPosition: d.open_position, lastSignal: d.last_signal, tradeCount: d.trade_count, winCount: d.win_count, lossCount: d.loss_count, totalPnl: d.total_pnl })
    } catch {}
  },

  fetchContracts: async () => {
    try {
      const res = await axios.get(`${API}/api/market/contracts`)
      const contracts = res.data.data || []
      console.log('📊 Total contracts fetched:', contracts.length)
      set({ contracts })
      
      const { config, contracts: c } = get()
      const found = c.find(x => x.symbol === config.symbol)
      if (!found && c.length > 0) {
        set(state => ({ config: { ...state.config, symbol: c[0].symbol } }))
      }
    } catch (err) {
      console.error('Failed to fetch contracts:', err)
    }
  },

  fetchTicker: async () => {
    const { config } = get()
    try {
      const res = await axios.get(`${API}/api/market/ticker/${config.symbol}`)
      set({ ticker: res.data.data })
    } catch {}
  },

  fetchCandles: async () => {
    const { config } = get()
    try {
      const res = await axios.get(`${API}/api/market/candles/${config.symbol}`, { params: { granularity: '1m', limit: 100 } })
      set({ candles: res.data.data || [] })
    } catch {}
  },

  fetchSummary: async () => {
    try {
      const res = await axios.get(`${API}/api/history/summary/all`)
      set({ summary: res.data.data })
    } catch {}
  },

  fetchTrades: async () => {
    try {
      const res = await axios.get(`${API}/api/history/positions/all`, { params: { page_size: 100 } })
      const trades = res.data.data || []
      set({ trades })
      // Build daily PnL chart — use correct field names from Bitget V2
      const dailyMap = {}
      trades.forEach(t => {
        const ts = t.ctime || t.uTime || t.createTime
        if (!ts) return
        const d = new Date(Number(ts))
        const key = `${d.getMonth()+1}/${d.getDate()}`
        const pnl = parseFloat(t.pnl ?? t.netProfit ?? t.achievedProfits ?? 0)
        dailyMap[key] = (dailyMap[key] || 0) + pnl
      })
      const pnlHistory = Object.entries(dailyMap).slice(-14).map(([date, pnl]) => ({ date, pnl: parseFloat(pnl.toFixed(4)), cumulative: 0 }))
      let cum = 0
      pnlHistory.forEach(d => { cum += d.pnl; d.cumulative = parseFloat(cum.toFixed(4)) })
      set({ pnlHistory })
    } catch {}
  },

  fetchFuturesBalance: async () => {
    const { config } = get()
    set(state => ({ futuresBalance: { ...state.futuresBalance, loading: true } }))
    try {
      const res = await axios.get(`${API}/api/market/balance/${config.symbol}`)
      const data = res.data.data || {}
      set(state => ({
        futuresBalance: {
          available: data.available || "0",
          locked: data.locked || "0",
          equity: data.accountEquity || data.equity || "0",
          usdtEquity: data.usdtEquity || "0",
          unrealizedPL: data.unrealizedPL || "0",
          loading: false,
        }
      }))
    } catch (err) {
      console.error("Failed to fetch balance:", err)
      set(state => ({ futuresBalance: { ...state.futuresBalance, loading: false } }))
    }
  },
}))
