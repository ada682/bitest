from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from services.mexc_client import mexc_client

router = APIRouter()


@router.get("/account/{symbol}")
async def get_account(symbol: str):
    data = await mexc_client.get_account(symbol)  # Need to implement this
    return {"data": data}


@router.get("/positions")
async def get_positions():
    data = await mexc_client.get_positions()
    return {"data": data}


class LeverageRequest(BaseModel):
    symbol: str
    leverage: str
    hold_side: str = "long"


@router.post("/leverage")
async def set_leverage(req: LeverageRequest):
    # MEXC may handle leverage differently
    result = await mexc_client.set_leverage(req.symbol, req.leverage)
    return {"result": result}
