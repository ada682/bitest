"""
History routes — signal-only app (no Bitget, no auto-trade).
All history comes from the persisted signals.json via bot_engine state.
"""

import json
import os
from pathlib import Path
from fastapi import APIRouter, Request

router = APIRouter()

# FIXED: use the same env var as bot_engine.py so both point to the same file.
# On Railway this resolves to /app/data/signals.json (set via SIGNALS_FILE env var).
# Locally it defaults to signals.json in the working directory.
SIGNALS_FILE = Path(os.getenv("SIGNALS_FILE", "signals.json"))


def _load_signals() -> list:
    try:
        if SIGNALS_FILE.exists():
            return json.loads(SIGNALS_FILE.read_text())
    except Exception:
        pass
    return []


def _pnl(s):
    return float(s.get("pnl_pct") or 0)


@router.get("/signals")
async def get_signal_history(limit: int = 100):
    """Return all persisted signals (newest first)."""
    signals = _load_signals()
    return {"data": signals[:limit], "total": len(signals)}


@router.get("/signals/{symbol}")
async def get_signal_history_by_symbol(symbol: str, limit: int = 100):
    """Return signals filtered by symbol."""
    signals = [s for s in _load_signals() if s.get("symbol") == symbol]
    return {"data": signals[:limit], "total": len(signals)}


@router.get("/summary")
async def get_summary_all():
    """Win/loss summary across ALL signals."""
    signals = _load_signals()

    closed   = [s for s in signals if s.get("result") in ("TP", "SL")]
    wins     = [s for s in closed  if s.get("result") == "TP"]
    losses   = [s for s in closed  if s.get("result") == "SL"]
    no_trade = [s for s in signals if s.get("status") == "NO TRADE"]
    open_sig = [s for s in signals if s.get("status") == "OPEN"]

    total_pnl = sum(_pnl(s) for s in closed)
    winrate   = round(len(wins) / len(closed) * 100, 2) if closed else 0.0
    avg_pnl   = round(total_pnl / len(closed), 4) if closed else 0.0

    return {
        "data": {
            "total_signals":  len(signals),
            "closed_trades":  len(closed),
            "open_signals":   len(open_sig),
            "no_trade_count": len(no_trade),
            "wins":           len(wins),
            "losses":         len(losses),
            "winrate":        winrate,
            "total_pnl_pct":  round(total_pnl, 4),
            "avg_pnl_pct":    avg_pnl,
        }
    }


@router.get("/summary/{symbol}")
async def get_summary_by_symbol(symbol: str):
    """Win/loss summary for a specific symbol."""
    signals = [s for s in _load_signals() if s.get("symbol") == symbol]

    closed  = [s for s in signals if s.get("result") in ("TP", "SL")]
    wins    = [s for s in closed  if s.get("result") == "TP"]
    losses  = [s for s in closed  if s.get("result") == "SL"]

    total_pnl = sum(_pnl(s) for s in closed)
    winrate   = round(len(wins) / len(closed) * 100, 2) if closed else 0.0
    avg_pnl   = round(total_pnl / len(closed), 4) if closed else 0.0

    return {
        "data": {
            "symbol":        symbol,
            "closed_trades": len(closed),
            "wins":          len(wins),
            "losses":        len(losses),
            "winrate":       winrate,
            "total_pnl_pct": round(total_pnl, 4),
            "avg_pnl_pct":   avg_pnl,
        }
    }
