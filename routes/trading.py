from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from services.bitget_client import bitget

router = APIRouter()


@router.get("/account/{symbol}")
async def get_account(symbol: str):
    data = await bitget.get_account(symbol)
    return {"data": data}


@router.get("/positions")
async def get_positions():
    data = await bitget.get_positions()
    return {"data": data}


class LeverageRequest(BaseModel):
    symbol: str
    leverage: str
    hold_side: str = "long"


@router.post("/leverage")
async def set_leverage(req: LeverageRequest):
    result_long = await bitget.set_leverage(req.symbol, req.leverage, "USDT", "long")
    result_short = await bitget.set_leverage(req.symbol, req.leverage, "USDT", "short")
    return {"long": result_long, "short": result_short}
