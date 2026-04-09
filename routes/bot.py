import asyncio
import os
import time

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from services.ws_manager import ws_manager

router = APIRouter()


# ---------------------------------------------------------------------------
# PIN verification
# ---------------------------------------------------------------------------

@router.post("/verify-pin")
async def verify_pin(request: Request):
    """Verify bot control PIN against BOT_PIN env variable."""
    body = await request.json()
    entered = str(body.get("pin", "")).strip()
    correct = str(os.getenv("BOT_PIN", "")).strip()

    if not correct:
        print("⚠️  BOT_PIN not set in environment. Bot is unprotected!")
        return {"ok": True}

    if entered == correct:
        return {"ok": True}

    return {"ok": False, "reason": "Wrong PIN"}


# ---------------------------------------------------------------------------
# Bot config & control
# ---------------------------------------------------------------------------

class BotConfig(BaseModel):
    symbol: str
    leverage: str
    mode: str = "MANUAL"
    manual_margin: Optional[float] = None
    tp_pct: float = 0.004
    sl_pct: float = 0.002
    volume_place: int = 3


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
# Debug / test endpoints
# ---------------------------------------------------------------------------

@router.get("/status/debug")
async def debug_status(request: Request):
    engine = request.app.state.bot_engine
    return {
        "running": engine.running,
        "task_exists": engine._task is not None,
        "task_done": engine._task.done() if engine._task else None,
        "task_cancelled": engine._task.cancelled() if engine._task else None,
        "state": engine.state,
    }


@router.get("/test-ai-direct")
async def test_ai_direct(request: Request):
    """Test AI langsung tanpa bot loop"""
    from services.bitget_client import bitget
    from services.deepseek_ai import deepseek_ai
    from utils.indicators import compute_all, format_ohlcv_text
    from services.chart_generator import generate_chart_image

    symbol = "ENJUSDT"
    candles = await bitget.get_candles(symbol, "1m", 50)
    if not candles or len(candles) < 30:
        return {"error": f"Not enough candles: {len(candles) if candles else 0}"}

    chart_b64 = generate_chart_image(candles, symbol.replace("USDT", "/USDT"), "1m")
    if not chart_b64:
        return {"error": "Failed to generate chart image"}

    indicators = compute_all(candles)
    ohlcv_text = format_ohlcv_text(candles, 30)

    try:
        result = await deepseek_ai.analyze(ohlcv_text, indicators, [chart_b64])
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}

    return {
        "symbol": symbol,
        "current_price": indicators.get("current_price"),
        "indicators": {
            "rsi": indicators.get("rsi_last"),
            "trend": indicators.get("trend"),
            "ema9": indicators.get("ema9_last"),
            "ema21": indicators.get("ema21_last"),
        },
        "ai_result": result,
    }


# ---------------------------------------------------------------------------
# Reset / UI control endpoints
# ---------------------------------------------------------------------------

@router.get("/reset-ui")
async def reset_ui(request: Request):
    """Reset UI counters dan broadcast ke semua WS clients. Bot tetap jalan."""
    engine = request.app.state.bot_engine

    engine.state["trade_count"] = 0
    engine.state["win_count"] = 0
    engine.state["loss_count"] = 0
    engine.state["total_pnl"] = 0.0
    engine.state["last_signal"] = None
    engine.state["open_position"] = None

    await ws_manager.broadcast("reset_ui", {
        "trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "total_pnl": 0.0,
        "trades": [],
        "pnl_history": [],
    })

    return {"ok": True, "message": "UI counters reset. Bot is still running."}


@router.get("/reset-ws")
async def reset_ws(request: Request):
    """Force semua WebSocket clients untuk reconnect."""
    await ws_manager.broadcast("reconnect_ws", {
        "reason": "manual_reset",
        "timestamp": int(time.time() * 1000),
    })
    return {"ok": True, "message": "Reconnect signal sent to all WS clients."}


@router.get("/reset-all")
async def reset_all(request: Request):
    """Full reset: counters + UI state + force WS reconnect."""
    engine = request.app.state.bot_engine

    engine.state["trade_count"] = 0
    engine.state["win_count"] = 0
    engine.state["loss_count"] = 0
    engine.state["total_pnl"] = 0.0
    engine.state["last_signal"] = None
    engine.state["open_position"] = None
    engine.state["last_error"] = None

    await ws_manager.broadcast("reset_all", {
        "trade_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "total_pnl": 0.0,
        "trades": [],
        "pnl_history": [],
        "last_signal": None,
        "open_position": None,
        "timestamp": int(time.time() * 1000),
    })

    await ws_manager.broadcast("reconnect_ws", {"reason": "full_reset"})

    return {"ok": True, "message": "Full reset done. Counters cleared, WS clients reconnecting."}


@router.get("/clear-trades")
async def clear_trades(request: Request):
    """Hanya clear recent trades di UI. Counters tidak berubah."""
    await ws_manager.broadcast("clear_trades", {
        "trades": [],
        "pnl_history": [],
        "timestamp": int(time.time() * 1000),
    })
    return {"ok": True, "message": "Recent trades cleared from UI."}
