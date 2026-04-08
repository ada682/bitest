from fastapi import APIRouter
from services.bitget_client import bitget

router = APIRouter()


@router.get("/positions/{symbol}")
async def get_history_positions(symbol: str, page_size: int = 50):
    data = await bitget.get_history_positions(symbol, "USDT", page_size)
    return {"data": data}


@router.get("/pnl/{symbol}")
async def get_pnl_history(symbol: str, page_size: int = 100):
    data = await bitget.get_account_bill(symbol, "USDT", page_size=page_size)
    return {"data": data}


@router.get("/summary/{symbol}")
async def get_summary(symbol: str):
    positions = await bitget.get_history_positions(symbol, "USDT", 200)

    total_trades = len(positions)
    wins = [p for p in positions if float(p.get("achievedProfits", 0)) > 0]
    losses = [p for p in positions if float(p.get("achievedProfits", 0)) < 0]
    total_pnl = sum(float(p.get("achievedProfits", 0)) for p in positions)
    winrate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
    avg_profit = total_pnl / total_trades if total_trades > 0 else 0

    return {
        "data": {
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "total_pnl": round(total_pnl, 4),
            "winrate": round(winrate, 2),
            "avg_profit": round(avg_profit, 4),
        }
    }