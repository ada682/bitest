import { create } from 'zustand'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || ''

export const useStore = create((set, get) => ({
  botStatus: 'IDLE',
  signals: [],           // semua sinyal (LONG/SHORT/NO TRADE)
  stats: {
    trade_count: 0,
    win_count: 0,
    loss_count: 0,
    no_trade_count: 0,
    total_pnl_pct: 0,
    winrate: 0,
  },
  statusMessage: '',
  lastError: null,
  wsConnected: false,
  ws: null,

  initWs: () => {
    const wsUrl = (API || 'http://localhost:8000')
      .replace('http://', 'ws://')
      .replace('https://', 'wss://')
    const ws = new WebSocket(`${wsUrl}/api/bot/ws`)
    ws.onopen = () => set({ wsConnected: true })
    ws.onclose = () => {
      set({ wsConnected: false })
      setTimeout(() => get().initWs(), 3000)
    }
    ws.onmessage = (e) => {
      try {
        const { event, data } = JSON.parse(e.data)
        if (event === 'status') set({ statusMessage: data })
        else if (event === 'signal') {
          // sinyal baru, masukkan ke awal array
          set(state => ({ signals: [data, ...state.signals] }))
          get().fetchStats() // refresh statistik
        }
        else if (event === 'signal_closed') {
          // update sinyal yang sudah closed (TP/SL)
          set(state => ({
            signals: state.signals.map(s =>
              s.id === data.id ? { ...s, ...data } : s
            )
          }))
          get().fetchStats()
        }
        else if (event === 'error') set({ lastError: data })
        else if (event === 'reset_all') {
          set({ signals: [], stats: { trade_count:0, win_count:0, loss_count:0, no_trade_count:0, total_pnl_pct:0, winrate:0 } })
        }
      } catch (err) { console.error(err) }
    }
    set({ ws })
  },

  fetchStats: async () => {
    try {
      const res = await axios.get(`${API}/api/bot/stats`)
      set({ stats: res.data.data })
    } catch (e) { console.error(e) }
  },

  fetchSignals: async (limit = 100) => {
    try {
      const res = await axios.get(`${API}/api/bot/signals`, { params: { limit } })
      set({ signals: res.data.data })
    } catch (e) { console.error(e) }
  },

  fetchBotState: async () => {
    try {
      const res = await axios.get(`${API}/api/bot/state`)
      set({ botStatus: res.data.status })
    } catch {}
  },
}))
