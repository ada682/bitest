import asyncio
import os
import time


from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from services.ws_manager import ws_manager
from services.virtual_exchange import virtual_exchange

router = APIRouter()


# ---------------------------------------------------------------------------
# PIN verification
# ---------------------------------------------------------------------------

@router.post("/verify-pin")
async def verify_pin(request: Request):
    body    = await request.json()
    entered = str(body.get("pin", "")).strip()
    correct = str(os.getenv("BOT_PIN", "")).strip()
    if not correct:
        return {"ok": True}
    return {"ok": entered == correct}


# ---------------------------------------------------------------------------
# Bot config & control
# ---------------------------------------------------------------------------

class BotConfig(BaseModel):
    symbol:   str
    tp_pct:   float = 0.004    # 0.4% take profit
    sl_pct:   float = 0.002    # 0.2% stop loss
    interval: int   = 60       # seconds between scans


@router.post("/start")
async def start_bot(config: BotConfig, request: Request):
    engine = request.app.state.bot_engine

    def listener(event, data):
        asyncio.create_task(ws_manager.broadcast(event, data))

    engine.add_listener(listener)
    result = await engine.start(config.dict())
    return result


@router.post("/stop")
async def stop_bot(request: Request):
    engine = request.app.state.bot_engine
    return await engine.stop()


@router.get("/state")
async def get_state(request: Request):
    engine = request.app.state.bot_engine
    return engine.get_state()


@router.get("/signals")
async def get_signals(request: Request, limit: int = 50):
    """Return most recent OPEN signals only."""
    engine      = request.app.state.bot_engine
    all_signals = engine.state.get("signals", [])
    open_signals = [s for s in all_signals if s.get("status") != "CLOSED"]
    return {"data": open_signals[:limit], "total": len(open_signals)}


@router.get("/stats")
async def get_stats(request: Request):
    """Return win/loss stats, winrate, balance, and total PnL."""
    engine    = request.app.state.bot_engine
    s         = engine.state
    wins      = s.get("win_count", 0)
    losses    = s.get("loss_count", 0)
    no_trade  = s.get("no_trade_count", 0)
    total_pct = s.get("total_pnl_pct", 0.0)
    total_usd = s.get("total_pnl_usdt", 0.0)
    closed    = wins + losses
    winrate   = round(wins / closed * 100, 2) if closed > 0 else 0.0

    return {
        "data": {
            "trade_count":         closed,
            "win_count":           wins,
            "loss_count":          losses,
            "no_trade_count":      no_trade,
            "winrate":             winrate,
            "total_pnl_pct":       total_pct,
            "total_pnl_usdt":      round(total_usd, 4),
            "balance":             virtual_exchange.balance,
            "leverage":            virtual_exchange.leverage,
            "entry_usdt":          virtual_exchange.entry_usdt,
            "active_signal_count": engine._active_count(),
            "max_active_signals":  int(os.getenv("MAX_ACTIVE_SIGNALS", "20")),
        }
    }


@router.post("/reset")
async def reset_stats(request: Request):
    """Reset all signal history, stats, and balance."""
    engine = request.app.state.bot_engine
    engine.reset_stats()
    await ws_manager.broadcast("reset_all", {
        "trade_count":         0,
        "win_count":           0,
        "loss_count":          0,
        "no_trade_count":      0,
        "total_pnl_pct":       0.0,
        "total_pnl_usdt":      0.0,
        "balance":             virtual_exchange.balance,
        "signals":             [],
        "active_signal_count": 0,
        "timestamp":           int(time.time() * 1000),
    })
    return {"ok": True}


# ---------------------------------------------------------------------------
# Balance endpoint (shortcut)
# ---------------------------------------------------------------------------

@router.get("/balance")
async def get_balance():
    """Current virtual balance."""
    return {"data": virtual_exchange.get_info()}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------

@router.get("/status/debug")
async def debug_status(request: Request):
    engine = request.app.state.bot_engine
    wins   = engine.state["win_count"]
    losses = engine.state["loss_count"]
    closed = wins + losses
    active = engine._active_count()
    return {
        "running":      engine.running,
        "task_exists":  engine._task is not None,
        "task_done":    engine._task.done()      if engine._task else None,
        "task_cancelled": engine._task.cancelled() if engine._task else None,
        "balance":      virtual_exchange.balance,
        "state_summary": {
            "status":              engine.state["status"],
            "trade_count":         closed,
            "win_count":           wins,
            "loss_count":          losses,
            "winrate":             round(wins / closed * 100, 2) if closed > 0 else 0.0,
            "active_signal_count": active,
            "max_active_signals":  int(os.getenv("MAX_ACTIVE_SIGNALS", "20")),
        },
    }
