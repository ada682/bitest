export interface Signal {
  id:            string;
  symbol:        string;
  timestamp:     number;
  current_price: number;
  trend?:        string;
  pattern?:      string;
  decision:      "LONG" | "SHORT" | "NO TRADE";
  entry?:        number;
  tp?:           number;
  sl?:           number;
  reason?:       string;
  confidence?:   number;
  status:        "OPEN" | "CLOSED" | "NO TRADE";
  result?:       "TP" | "SL" | null;
  pnl_pct?:      number | null;
  closed_at?:    number | null;
  closed_price?: number | null;
}

export interface BotStats {
  trade_count:    number;
  win_count:      number;
  loss_count:     number;
  no_trade_count: number;
  winrate:        number;
  total_pnl_pct:  number;
}

export interface BotState extends BotStats {
  status:          string;
  last_signal:     Signal | null;
  last_error:      string | null;
  signals:         Signal[];
  current_symbol:  string | null;
  symbols_scanned: number;
  symbols_total:   number;
}

export type WsEvent =
  | { event: "signal";        data: Signal }
  | { event: "signal_closed"; data: Signal }
  | { event: "status";        data: string }
  | { event: "error";         data: string }
  | { event: "reset_all";     data: Partial<BotStats> };
