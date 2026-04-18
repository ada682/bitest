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
  result?:       "TP" | "SL" | "AI_CLOSE" | "INVALIDATED" | "TIMEOUT" | null;
  pnl_pct?:      number | null;
  pnl_usdt?:     number | null;
  entry_hit?:    boolean;
  closed_price?: number | null;
  closed_at?:    number | null;
  close_reason?: string | null;

  // SL+ — stop loss trailing by AI monitor
  sl_plus_count?:   number;                  // how many times SL has been moved
  sl_plus_history?: SlPlusMove[];            // full audit trail of each move

  // AI monitor decisions (updated live via signal_ai_update WS event)
  last_ai_decision?: "HOLD" | "CLOSE" | "SL+" | null;
  last_ai_reason?:   string | null;
  last_ai_at?:       number | null;          // ms timestamp of last AI check

  // present in signal_closed WS event
  balance?: number;
}

export interface SlPlusMove {
  from:  number;   // old SL price
  to:    number;   // new SL price
  price: number;   // market price at the time of the move
  at:    number;   // ms timestamp
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
  total_pnl_usdt:     number;
  current_symbol:     string | null;
  symbols_scanned:    number;
  symbols_total:      number;
  // legacy fields (kept for backward compat)
  scan_date?:          string;
  daily_signal_count?: number;
  max_daily_signals?:  number;
  next_reset_in?:      number;
  // current virtual balance
  balance:            number;
  // active signal cap info
  active_signal_count?: number;
  max_active_signals?:  number;
}

export interface WsEvent {
  event:
    | "signal"
    | "signal_closed"
    | "signal_invalidated"
    | "signal_entry_hit"
    | "signal_ai_update"
    | "signal_sl_updated"   // ← new: SL moved by AI
    | "balance_update"
    | "reset_all"
    | "status"
    | "progress"
    | "price_tick"
    | "error";
  data: unknown;
}

// Payload shape for signal_sl_updated WS event
export interface SlUpdatedPayload {
  id:        string;
  symbol:    string;
  direction: "LONG" | "SHORT";
  old_sl:    number;
  new_sl:    number;
  price:     number;
  reason:    string;
  timestamp: number;
}

// Payload shape for signal_ai_update WS event
export interface AiUpdatePayload {
  id:        string;
  symbol:    string;
  decision:  "HOLD" | "CLOSE" | "SL+";
  reason:    string;
  new_sl:    number | null;
  timestamp: number;
}
