from fastapi import APIRouter
from services.bitget_client import bitget

router = APIRouter()


@router.get("/contracts")
async def get_contracts():
    # V2: productType = 'USDT-FUTURES'
    data = await bitget.get_contracts("USDT-FUTURES")
    if not data:
        return {"data": [], "error": "No contract data returned from exchange"}
    result = [
        {
            "symbol": c.get("symbol"),
            "baseCoin": c.get("baseVolume"),
            "quoteCoin": "USDT",
            "lastPrice": c.get("lastPr"),
            "volume24h": c.get("usdtVolume"),
        }
        for c in data
        if isinstance(c, dict)
    ]
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
