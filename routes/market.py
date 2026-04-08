from fastapi import APIRouter
from services.bitget_client import bitget

router = APIRouter()


@router.get("/contracts")
async def get_contracts():
    # V2: get_contracts already normalizes fields including quoteCoin
    data = await bitget.get_contracts("USDT-FUTURES")
    if not data:
        return {"data": [], "error": "No contract data returned from exchange"}
    # Filter USDT pairs only (all should be, but just in case)
    result = [c for c in data if c.get("quoteCoin") == "USDT"]
    return {"data": result}


@router.get("/ticker/{symbol}")
async def get_ticker(symbol: str):
    data = await bitget.get_ticker(symbol)
    return {"data": data}


@router.get("/candles/{symbol}")
async def get_candles(symbol: str, granularity: str = "1m", limit: int = 100):
    data = await bitget.get_candles(symbol, granularity, limit)
    return {"data": data}


@router.get("/leverage/{symbol}")
async def get_symbol_leverage(symbol: str):
    data = await bitget.get_symbol_leverage(symbol)
    return {"data": data}
