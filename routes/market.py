"""
Market routes
=============
Coin list / tickers  →  Bitget USDT-FUTURES v2
Candles (klines)     →  MEXC (better free data)
"""

from fastapi import APIRouter

from services.bitget_client import bitget_client, mexc_to_bitget, bitget_to_mexc
from services.mexc_client   import mexc_client

router = APIRouter()


# ---------------------------------------------------------------------------
# Contracts / tickers  (Bitget)
# ---------------------------------------------------------------------------

@router.get("/contracts")
async def get_contracts(limit: int = None):
    """
    All active USDT-FUTURES contracts from Bitget.
    Each item includes both 'symbol' (BTCUSDT) and 'mexcSymbol' (BTC_USDT).
    """
    data = await bitget_client.get_contracts()
    if not data:
        return {"data": [], "error": "No contract data returned from Bitget"}
    if limit:
        data = data[:limit]
    return {"data": data, "total": len(data)}


@router.get("/ticker/{symbol}")
async def get_ticker(symbol: str):
    """
    Single ticker.
    Accepts BTCUSDT or BTC_USDT — always queries MEXC (cheapest live price).
    """
    mexc_sym = symbol if "_" in symbol else bitget_to_mexc(symbol)
    data = await mexc_client.get_ticker(mexc_sym)
    return {"data": data}


@router.get("/tickers")
async def get_all_tickers():
    """All tickers from MEXC (fast, no auth needed)."""
    data = await mexc_client.get_all_tickers()
    return {"data": data, "total": len(data)}


# ---------------------------------------------------------------------------
# Candles  (MEXC)
# ---------------------------------------------------------------------------

@router.get("/candles/{symbol}")
async def get_candles(symbol: str, granularity: str = "5m", limit: int = 100):
    """
    OHLCV candles from MEXC.
    Accepts BTCUSDT (Bitget) or BTC_USDT (MEXC) — auto-converts.
    """
    mexc_sym = symbol if "_" in symbol else bitget_to_mexc(symbol)
    data = await mexc_client.get_candles(mexc_sym, granularity, limit)
    return {"data": data, "symbol_used": mexc_sym}
