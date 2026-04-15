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

@router.get("/positions/all")
async def get_all_history_positions(page_size: int = 100):
    """Return closed positions for ALL symbols (no symbol filter)."""
    params = {"productType": "USDT-FUTURES", "limit": str(page_size)}
    from services.bitget_client import bitget as _bitget
    resp = await _bitget.get("/api/v2/mix/position/history-position", params)
    data = resp.get("data")
    if isinstance(data, dict):
        result = data.get("list") or []
    else:
        result = data or []
    return {"data": result}


@router.get("/summary/all")
async def get_summary_all(page_size: int = 200):
    """Return win/loss summary across ALL symbols."""
    from services.bitget_client import bitget as _bitget
    params = {"productType": "USDT-FUTURES", "limit": str(page_size)}
    resp = await _bitget.get("/api/v2/mix/position/history-position", params)
    data = resp.get("data")
    positions = (data.get("list") if isinstance(data, dict) else data) or []

    def _pnl(p):
        return float(p.get("pnl") or p.get("achievedProfits") or p.get("netProfit") or 0)

    total_trades = len(positions)
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
