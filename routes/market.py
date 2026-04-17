"""
Market routes
=============
Coin list / contracts  →  MEXC USDT-FUTURES
Candles (klines)       →  MEXC
Tickers                →  price_feed WS cache first, REST fallback
"""

from fastapi import APIRouter
from services.mexc_client import mexc_client
from services.mexc_price_feed import price_feed   # ← FIX: use WS cache

router = APIRouter()


# ---------------------------------------------------------------------------
# Contracts / tickers  (MEXC)
# ---------------------------------------------------------------------------

@router.get("/contracts")
async def get_contracts(limit: int = None):
    """
    All active USDT-FUTURES contracts from MEXC.
    Symbol format: BTC_USDT
    """
    data = await mexc_client.get_contracts()
    if not data:
        return {"data": [], "error": "No contract data returned from MEXC"}
    if limit:
        data = data[:limit]
    return {"data": data, "total": len(data)}


@router.get("/ticker/{symbol}")
async def get_ticker(symbol: str):
    """
    Single ticker — returns real-time price.
    Priority: WS price_feed cache (≤2s old) → REST fallback.
    Accepts BTC_USDT or BTCUSDT (auto-converts to BTC_USDT).

    FIX: Previously always made a REST call to MEXC which could be slow,
    rate-limited, or return slightly stale data. Now we hit the in-memory
    WebSocket cache first — it's updated every 1-2s with zero extra latency.
    """
    mexc_sym = symbol if "_" in symbol else (symbol[:-4] + "_USDT")

    # ── 1. Try WebSocket price feed cache (fastest, always real-time) ──
    ws_price = price_feed.get_price(mexc_sym)
    if ws_price and ws_price > 0:
        # Also subscribe to high-freq per-ticker updates for this symbol
        # so subsequent calls are even faster (1s resolution vs 2s batch).
        price_feed.watch(mexc_sym)
        return {
            "data": {
                "symbol":   mexc_sym,
                "last":     str(ws_price),
                "lastPr":   str(ws_price),
                "lastPrice": ws_price,
                "source":   "websocket",   # debug: shows which path was used
            }
        }

    # ── 2. WS cache miss (feed not started or symbol not seen yet) ──────
    #    Subscribe for next time and fall back to REST.
    price_feed.watch(mexc_sym)
    data = await mexc_client.get_ticker(mexc_sym)
    return {"data": data}


@router.get("/tickers")
async def get_all_tickers():
    """All tickers from MEXC."""
    data = await mexc_client.get_all_tickers()
    return {"data": data, "total": len(data)}


# ---------------------------------------------------------------------------
# Candles  (MEXC)
# ---------------------------------------------------------------------------

@router.get("/candles/{symbol}")
async def get_candles(symbol: str, granularity: str = "5m", limit: int = 100):
    """
    OHLCV candles from MEXC.
    Accepts BTCUSDT or BTC_USDT — auto-converts.
    """
    mexc_sym = symbol if "_" in symbol else (symbol[:-4] + "_USDT")
    data = await mexc_client.get_candles(mexc_sym, granularity, limit)
    return {"data": data, "symbol_used": mexc_sym}
