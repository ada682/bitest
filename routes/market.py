"""
Market routes
=============
Coin list / contracts  →  MEXC USDT-FUTURES
Candles (klines)       →  MEXC
Tickers                →  MEXC
"""

from fastapi import APIRouter
from services.mexc_client import mexc_client

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
    Single ticker from MEXC.
    Accepts BTC_USDT or BTCUSDT (auto-converts to BTC_USDT).
    """
    mexc_sym = symbol if "_" in symbol else (symbol[:-4] + "_USDT")
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
