from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.bitget_client import bitget_client, mexc_to_bitget
from services.bitget_ws     import bitget_ws

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class OpenOrderBody(BaseModel):
    symbol:      str               # BTCUSDT  OR  BTC_USDT  (auto-converted)
    side:        str               # 'buy' | 'sell'
    size:        str               # contract quantity
    price:       str               # limit entry price
    tp_price:    Optional[str] = None
    sl_price:    Optional[str] = None
    leverage:    int              = 10
    margin_mode: str              = "isolated"  # 'isolated' | 'crossed'


class ClosePositionBody(BaseModel):
    symbol:    str     # BTCUSDT
    hold_side: str     # 'long' | 'short'
    size:      str = "0"   # 0 = full position


class TpSlBody(BaseModel):
    symbol:        str
    plan_type:     str   # 'profit_loss' | 'pos_profit' | 'pos_loss'
    trigger_price: str
    hold_side:     str   # 'long' | 'short'
    size:          str = "0"


class CancelOrderBody(BaseModel):
    symbol:   str
    order_id: str


def _normalise_symbol(symbol: str) -> str:
    """Accept BTC_USDT or BTCUSDT — always return BTCUSDT."""
    return symbol.replace("_", "")


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------

@router.get("/balance")
async def get_balance():
    """Demo account USDT balance."""
    data = await bitget_client.get_account_balance()
    return {"data": data}


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

@router.get("/positions")
async def get_positions(symbol: str = None):
    """
    Open positions from Bitget Demo (REST).
    For real-time subscribe to the /api/bot/ws WebSocket and listen for
    'positions_update' events.
    """
    sym  = _normalise_symbol(symbol) if symbol else None
    data = await bitget_client.get_open_positions(sym)
    return {"data": data, "total": len(data)}


# ---------------------------------------------------------------------------
# Open order (limit + preset TP/SL)
# ---------------------------------------------------------------------------

@router.post("/open")
async def open_order(body: OpenOrderBody):
    """
    Place a limit order on Bitget Demo with optional preset TP/SL.

    Example:
    {
        "symbol":   "BTCUSDT",
        "side":     "buy",
        "size":     "0.01",
        "price":    "65000",
        "tp_price": "67000",
        "sl_price": "64000",
        "leverage": 10
    }
    """
    symbol = _normalise_symbol(body.symbol)

    # Set leverage first (best-effort)
    hold_side = "long" if body.side == "buy" else "short"
    await bitget_client.set_leverage(symbol, body.leverage, hold_side)

    result = await bitget_client.place_order(
        symbol      = symbol,
        side        = body.side,
        trade_side  = "open",
        size        = body.size,
        price       = body.price,
        tp_price    = body.tp_price,
        sl_price    = body.sl_price,
        margin_mode = body.margin_mode,
        leverage    = body.leverage,
    )

    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("msg", "Order failed"))

    return {"data": result}


# ---------------------------------------------------------------------------
# Close position (market)
# ---------------------------------------------------------------------------

@router.post("/close")
async def close_position(body: ClosePositionBody):
    """
    Close an existing position (market order).

    {
        "symbol":    "BTCUSDT",
        "hold_side": "long",
        "size":      "0"       // 0 = close entire position
    }
    """
    symbol = _normalise_symbol(body.symbol)
    result = await bitget_client.close_position(symbol, body.hold_side, body.size)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("msg", "Close failed"))
    return {"data": result}


# ---------------------------------------------------------------------------
# Set / update TP or SL on existing position
# ---------------------------------------------------------------------------

@router.post("/tpsl")
async def set_tpsl(body: TpSlBody):
    """
    Place a TP/SL order on an existing position.
    plan_type:
      'profit_loss'  — set both TP and SL in one call (use two separate calls for each)
      'pos_profit'   — take profit only
      'pos_loss'     — stop loss only
    """
    symbol = _normalise_symbol(body.symbol)
    result = await bitget_client.place_tpsl(
        symbol        = symbol,
        plan_type     = body.plan_type,
        trigger_price = body.trigger_price,
        hold_side     = body.hold_side,
        size          = body.size,
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("msg", "TP/SL failed"))
    return {"data": result}


# ---------------------------------------------------------------------------
# Cancel order
# ---------------------------------------------------------------------------

@router.post("/cancel")
async def cancel_order(body: CancelOrderBody):
    symbol = _normalise_symbol(body.symbol)
    result = await bitget_client.cancel_order(symbol, body.order_id)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("msg", "Cancel failed"))
    return {"data": result}


# ---------------------------------------------------------------------------
# Order history
# ---------------------------------------------------------------------------

@router.get("/orders/history")
async def get_order_history(
    symbol:     str = None,
    limit:      int = 50,
    start_time: str = None,
    end_time:   str = None,
):
    """
    Closed / filled order history from Bitget Demo.
    symbol: optional filter, e.g. 'BTCUSDT'
    start_time / end_time: Unix ms strings
    """
    sym  = _normalise_symbol(symbol) if symbol else None
    data = await bitget_client.get_order_history(sym, limit, start_time, end_time)
    return {"data": data, "total": len(data)}


# ---------------------------------------------------------------------------
# Contracts list
# ---------------------------------------------------------------------------

@router.get("/contracts")
async def get_contracts(limit: int = None):
    """All active USDT-FUTURES contracts from Bitget."""
    data = await bitget_client.get_contracts()
    if limit:
        data = data[:limit]
    return {"data": data, "total": len(data)}


# ---------------------------------------------------------------------------
# WebSocket snapshot (latest cached data from private WS)
# ---------------------------------------------------------------------------

@router.get("/ws/snapshot")
async def ws_snapshot():
    """
    Return the latest position + order snapshot cached from the
    Bitget private WebSocket connection.
    Useful as initial state before subscribing to live WS events.
    """
    return {
        "data": {
            "positions": bitget_ws.positions,
            "orders":    bitget_ws.orders,
        }
    }


# ---------------------------------------------------------------------------
# Leverage setter (standalone)
# ---------------------------------------------------------------------------

@router.post("/leverage")
async def set_leverage_endpoint(
    symbol:    str,
    leverage:  int,
    hold_side: str = "long",
):
    symbol = _normalise_symbol(symbol)
    result = await bitget_client.set_leverage(symbol, leverage, hold_side)
    return {"data": result}
