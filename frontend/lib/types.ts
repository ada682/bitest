// lib/types.ts
// Updated to match virtual exchange backend

export interface Signal {
  id:            string;
  symbol:        string;
  timestamp:     number;
  current_price: number;
  trend?:        string;
  pattern?:      string;
  decision:      "LONG" | "SHORT" | "NO TRADE";
  entry?:        number | null;
  tp?:           number | null;
  sl?:           number | null;
  invalidation?: number | null;
  reason?:       string;
  confidence?:   number | null;
  status:        "OPEN" | "CLOSED" | "NO TRADE" | "INVALIDATED";
  result?:       "TP" | "SL" | "INVALIDATED" | null;
  pnl_pct?:      number | null;
  // NEW: USDT PnL from virtual exchange
  pnl_usdt?:     number | null;
  // NEW: whether price has reached the entry level
  entry_hit?:    boolean;
  // NEW: price at which the trade was closed
  closed_price?: number | null;
  closed_at?:    number | null;
  // present in signal_closed WS event
  balance?:      number;
}

export interface BotState {
  status:             string;
  last_signal:        Signal | null;
  last_error:         string | null;
  signals:            Signal[];
  trade_count:        number;
  win_count:          number;
  loss_count:         number;
  no_trade_count:     number;
  winrate:            number;
  total_pnl_pct:      number;
  // NEW: cumulative PnL in USDT
  total_pnl_usdt:     number;
  current_symbol:     string | null;
  symbols_scanned:    number;
  // maps to max_daily_signals in the backend
  symbols_total:      number;
  scan_date:          string;
  daily_signal_count: number;
  max_daily_signals:  number;
  next_reset_in:      number;
  // NEW: current virtual balance
  balance:            number;
}

export interface WsEvent {
  event: string;
  // signal | signal_closed | signal_invalidated | balance_update |
  // reset_all | status | progress | error | signal_entry_hit
  data:  unknown;
}
