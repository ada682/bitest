"""
Virtual Trading routes
=======================
Replaces Bitget API routes with a self-managed virtual trading system.
All balance & PnL tracking is done internally — no real exchange involved.

Endpoints:
  GET  /balance          — current virtual balance + settings
  GET  /positions        — currently open (monitored) signals
  GET  /history          — closed trades from signals.json
  POST /reset-balance    — reset balance to INITIAL_BALANCE
  GET  /settings         — show leverage / entry size from env
"""

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request
from services.virtual_exchange import virtual_exchange, INITIAL_BALANCE

router = APIRouter()

SIGNALS_FILE = Path(os.getenv("SIGNALS_FILE", "signals.json"))


def _load_closed_signals() -> list:
    try:
        if SIGNALS_FILE.exists():
            signals = json.loads(SIGNALS_FILE.read_text())
            return [s for s in signals if s.get("result") in ("TP", "SL")]
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------

@router.get("/balance")
async def get_balance():
    """Virtual account balance and trading settings."""
    return {"data": virtual_exchange.get_info()}


# ---------------------------------------------------------------------------
# Open positions (from bot engine state)
# ---------------------------------------------------------------------------

@router.get("/positions")
async def get_positions(request: Request):
    """
    Return currently open (monitored) signals as virtual positions.
    These are signals where entry has been hit but TP/SL hasn't yet.
    """
    engine  = request.app.state.bot_engine
    signals = engine.state.get("signals", [])
    open_s  = [s for s in signals if s.get("status") == "OPEN"]

    positions = []
    for s in open_s:
        entry = float(s.get("entry") or s.get("current_price") or 0)
        positions.append({
            "id":           s["id"],
            "symbol":       s["symbol"],
            "direction":    s["decision"],     # LONG | SHORT
            "entry":        entry,
            "tp":           s.get("tp"),
            "sl":           s.get("sl"),
            "invalidation": s.get("invalidation"),
            "entry_hit":    s.get("entry_hit", False),
            "confidence":   s.get("confidence"),
            "opened_at":    s.get("timestamp"),
            "margin_usdt":  virtual_exchange.entry_usdt,
            "leverage":     virtual_exchange.leverage,
        })

    return {"data": positions, "total": len(positions)}


# ---------------------------------------------------------------------------
# Trade history (closed trades)
# ---------------------------------------------------------------------------

@router.get("/history")
async def get_trade_history(limit: int = 50):
    """Closed trades (TP / SL) from signal history."""
    closed = _load_closed_signals()
    return {"data": closed[:limit], "total": len(closed)}


# ---------------------------------------------------------------------------
# Settings (read-only)
# ---------------------------------------------------------------------------

@router.get("/settings")
async def get_settings():
    """Show current trading settings (set via .env)."""
    return {
        "data": {
            "initial_balance": INITIAL_BALANCE,
            "leverage":        virtual_exchange.leverage,
            "entry_usdt":      virtual_exchange.entry_usdt,
            "note": (
                "Set INITIAL_BALANCE, TRADE_LEVERAGE, TRADE_ENTRY_USDT "
                "in your Railway environment variables."
            ),
        }
    }


# ---------------------------------------------------------------------------
# Reset balance
# ---------------------------------------------------------------------------

@router.post("/reset-balance")
async def reset_balance():
    """Reset virtual balance to INITIAL_BALANCE (from env)."""
    virtual_exchange.reset()
    return {"ok": True, "balance": virtual_exchange.balance}
