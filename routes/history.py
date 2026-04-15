from fastapi import APIRouter
from services.mexc_client import mexc_client

router = APIRouter()


@router.get("/positions/{symbol}")
async def get_history_positions(symbol: str, page_size: int = 50):
    # MEXC history endpoint - implement if needed
    data = await mexc_client.get_history_positions(symbol, page_size)
    return {"data": data}


@router.get("/pnl/{symbol}")
async def get_pnl_history(symbol: str, page_size: int = 100):
    data = await mexc_client.get_pnl_history(symbol, page_size)
    return {"data": data}


@router.get("/summary/{symbol}")
async def get_summary(symbol: str):
    positions = await mexc_client.get_history_positions(symbol, 200)
    
    total_trades = len(positions)
    def _pnl(p):
        return float(p.get("pnl") or p.get("achievedProfits") or p.get("netProfit") or 0)
    
    wins = [p for p in positions if _pnl(p) > 0]
    losses = [p for p in positions if _pnl(p) < 0]
    total_pnl = sum(_pnl(p) for p in positions)
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
