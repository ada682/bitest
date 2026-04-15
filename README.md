# CryptoSignals — MEXC Futures AI Scanner

Real-time AI signal scanner for all MEXC perpetual futures.
Signals are **global** — stored in `signals.json` on the backend so every
visitor sees the same live results the moment they open the page.

---

## Architecture

```
backend/   FastAPI (Python) — deploys on Railway / Render / VPS
frontend/  Next.js (TypeScript) — deploys on Vercel
```

---

## Backend Setup

### 1. Install dependencies
```bash
pip install fastapi uvicorn httpx python-dotenv
```

### 2. Environment variables (`.env`)
```
DEEPSEEK_API_KEY=sk-...
BOT_PIN=1234                  # optional PIN to protect start/stop
MEXC_API_KEY=                 # not needed for public market data
MEXC_SECRET_KEY=              # not needed for public market data
INTER_SYMBOL_DELAY=2.0        # seconds between each symbol analysis
SIGNALS_FILE=signals.json     # path to persistence file
```

### 3. Run locally
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Deploy to Railway
1. Push `backend/` folder to a GitHub repo
2. Create a new Railway project → "Deploy from GitHub"
3. Add environment variables in Railway dashboard
4. Railway auto-detects Python and deploys

---

## Frontend Setup (Vercel)

### 1. Environment variables
Create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=https://your-backend.up.railway.app
NEXT_PUBLIC_WS_URL=wss://your-backend.up.railway.app
```

### 2. Deploy to Vercel
```bash
cd frontend
npx vercel
```
Or connect the `frontend/` folder directly in Vercel dashboard.

Add the two env vars in **Vercel → Project Settings → Environment Variables**.

---

## MEXC API Endpoints Used (all public, no auth needed)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/contract/detail` | Fetch all active USDT-perp contracts |
| `GET /api/v1/contract/ticker` | Live price for a symbol |
| `GET /api/v1/contract/kline/{symbol}` | OHLCV candles |

Kline interval mapping:
| Bot TF | MEXC interval |
|---|---|
| 5m  | Min5  |
| 15m | Min15 |
| 30m | Min30 |
| 1h  | Min60 |
| 4h  | Hour4 |

---

## How the Global Signal Feed Works

1. Backend bot scans ALL MEXC futures symbols continuously
2. Each signal is appended to `signals.json` on the server
3. On startup, `bot_engine.py` loads `signals.json` into memory
4. When a new user hits the frontend, `fetchBotState()` returns the full
   signal history immediately — no need to wait for the bot to run
5. New signals arrive in real-time via WebSocket `/api/bot/ws`

---

## TP / SL Monitoring

After each LONG/SHORT signal is emitted, `bot_engine.py` spawns a
background `_monitor_signal` task that:
- Polls the live MEXC ticker every 10 seconds
- Marks the signal `CLOSED` with `result: "TP"` or `"SL"` when hit
- Updates `win_count`, `loss_count`, `total_pnl_pct`
- Persists the updated signal to `signals.json`
- Broadcasts `signal_closed` over WebSocket so the frontend updates live

Win rate and cumulative PnL in the dashboard are derived entirely from
these closed signal records.
