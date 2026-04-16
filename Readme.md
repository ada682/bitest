# cryptosignals

ai-powered futures signal scanner untuk mexc perpetual. bot ini scan semua pair usdt setiap hari, analisa pakai deepseek ai (3 token parallel), dan kirim sinyal long/short berdasarkan pola void & wick imbalance. tidak auto-trade — purely signal generation.

## kenapa bikin ini?

gue butuh scanner yang bisa kasih sinyal teknikal murni tanpa noise indicator. deepseek bisa baca struktur candle, void, sama imbalance jauh lebih akurat daripada indikator biasa. plus, gue pengen punya history sinyal yang bisa di-review ulang buat evaluasi strategi.

## fitur utama

- **daily 20 signals** — setiap hari bot kumpulin tepat 20 sinyal actionable (long/short). no trade di-skip.
- **parallel ai analysis** — 3 token deepseek jalan barengan, masing-masing nanganin 1 coin. batch processing.
- **invalidation system** — setiap sinyal punya level invalidation. kalau kena, sinyal auto-dihapus dari memori.
- **real-time dashboard** — websocket live update, chart pnl, winrate, sama progress scanning.

## tech stack

**backend**
- fastapi (python)
- websocket buat real-time update
- deepseek ai (wasm pow solver)
- mexc api (public endpoints)

**frontend**
- next.js 14 (app router)
- tailwind css
- recharts buat charting
- websocket client

## cara jalanin local

### backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # atau venv\Scripts\activate di windows
pip install -r requirements.txt
