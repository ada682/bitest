from fastapi import APIRouter
from services.mexc_client import mexc_client

router = APIRouter()


@router.get("/positions")
async def get_positions():
    """Open positions from MEXC (requires API key)."""
    data = await mexc_client.get_positions()
    return {"data": data}


@router.get("/contracts")
async def get_contracts():
    """List all active USDT-perp contracts."""
    data = await mexc_client.get_contracts()
    return {"data": data, "total": len(data)}
