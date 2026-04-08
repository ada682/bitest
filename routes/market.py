from fastapi import APIRouter
from services.bitget_client import bitget

router = APIRouter()


@router.get("/contracts")
async def get_contracts(limit: int = None):
    data = await bitget.get_contracts("USDT-FUTURES")
    if not data:
        return {"data": [], "error": "No contract data returned from exchange"}
    
    # Filter USDT pairs only
    result = [c for c in data if c.get("quoteCoin") == "USDT"]
    
    # Optional limit
    if limit:
        result = result[:limit]
    
    return {
        "data": result,
        "total": len(result),
        "message": f"Returning {len(result)} pairs"
    }


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


@router.get("/balance/{symbol}")
async def get_balance(symbol: str):
    """Get futures account balance for a specific symbol"""
    data = await bitget.get_futures_account(symbol)
    return {"data": data}


@router.get("/balances")
async def get_all_balances():
    """Get all futures account balances"""
    data = await bitget.get_all_futures_accounts()
    return {"data": data}
