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
    symbol: 'BTCUSDT_UMCBL',
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
          get().fetchSummary()
        }
        else if (event === 'error') set({ lastError: data })
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
      set({ contracts: res.data.data || [] })
    } catch {}
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
    const { config } = get()
    try {
      const res = await axios.get(`${API}/api/history/summary/${config.symbol}`)
      set({ summary: res.data.data })
    } catch {}
  },

  fetchTrades: async () => {
    const { config } = get()
    try {
      const res = await axios.get(`${API}/api/history/positions/${config.symbol}`, { params: { page_size: 50 } })
      const trades = res.data.data || []
      set({ trades })
      const dailyMap = {}
      trades.forEach(t => {
        if (!t.ctime) return
        const d = new Date(Number(t.ctime))
        const key = `${d.getMonth()+1}/${d.getDate()}`
        dailyMap[key] = (dailyMap[key] || 0) + parseFloat(t.achievedProfits || 0)
      })
      const pnlHistory = Object.entries(dailyMap).slice(-14).map(([date, pnl]) => ({ date, pnl: parseFloat(pnl.toFixed(4)), cumulative: 0 }))
      let cum = 0
      pnlHistory.forEach(d => { cum += d.pnl; d.cumulative = parseFloat(cum.toFixed(4)) })
      set({ pnlHistory })
    } catch {}
  },
}))
