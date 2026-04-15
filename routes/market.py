from fastapi import APIRouter
from services.mexc_client import mexc_client

router = APIRouter()


@router.get("/contracts")
async def get_contracts(limit: int = None):
    data = await mexc_client.get_contracts()
    if not data:
        return {"data": [], "error": "No contract data returned from exchange"}
    if limit:
        data = data[:limit]
    return {"data": data, "total": len(data)}


@router.get("/ticker/{symbol}")
async def get_ticker(symbol: str):
    data = await mexc_client.get_ticker(symbol)
    return {"data": data}


@router.get("/tickers")
async def get_all_tickers():
    data = await mexc_client.get_all_tickers()
    return {"data": data, "total": len(data)}


@router.get("/candles/{symbol}")
async def get_candles(symbol: str, granularity: str = "5m", limit: int = 100):
    data = await mexc_client.get_candles(symbol, granularity, limit)
    return {"data": data}
