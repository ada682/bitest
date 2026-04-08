from fastapi import APIRouter
from services.bitget_client import bitget

router = APIRouter()


@router.get("/contracts")
async def get_contracts():
    data = await bitget.get_contracts("umcbl")
    # Filter active contracts only
    result = [
        {
            "symbol": c.get("symbol"),
            "baseCoin": c.get("baseCoin"),
            "quoteCoin": c.get("quoteCoin"),
            "minTradeNum": c.get("minTradeNum"),
            "volumePlace": c.get("volumePlace"),
            "pricePlace": c.get("pricePlace"),
            "maxLeverage": c.get("maxLeverage"),
        }
        for c in data
        if c.get("quoteCoin") == "USDT"
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
