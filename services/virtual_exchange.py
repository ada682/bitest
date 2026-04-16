"""
Virtual Trading System — self-contained, no real exchange API.
Tracks balance, open positions, and PnL purely via MEXC price checks.

Env vars:
  INITIAL_BALANCE   — starting equity in USDT   (default: 1000)
  TRADE_LEVERAGE    — leverage per trade         (default: 10)
  TRADE_ENTRY_USDT  — margin per trade in USDT   (default: 100)
  BALANCE_FILE      — path to persist balance    (default: balance.json)
"""

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

BALANCE_FILE     = Path(os.getenv("BALANCE_FILE",     "balance.json"))
INITIAL_BALANCE  = float(os.getenv("INITIAL_BALANCE", "1000"))
TRADE_LEVERAGE   = int(os.getenv("TRADE_LEVERAGE",    "10"))
TRADE_ENTRY_USDT = float(os.getenv("TRADE_ENTRY_USDT","100"))


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_balance() -> float:
    try:
        BALANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if BALANCE_FILE.exists():
            data = json.loads(BALANCE_FILE.read_text())
            return float(data.get("balance", INITIAL_BALANCE))
    except Exception:
        pass
    return INITIAL_BALANCE


def _save_balance(balance: float):
    try:
        BALANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BALANCE_FILE.write_text(json.dumps({
            "balance":    round(balance, 4),
            "updated_at": int(time.time() * 1000),
        }, indent=2))
    except Exception as e:
        logger.warning(f"Could not save balance: {e}")


# ---------------------------------------------------------------------------
# VirtualExchange
# ---------------------------------------------------------------------------

class VirtualExchange:
    """
    Self-managed virtual trading system.

    Rules:
    - Every actionable signal reserves TRADE_ENTRY_USDT as margin.
    - TP hit  → balance += margin * leverage * pnl_pct  (positive)
    - SL hit  → balance += margin * leverage * pnl_pct  (negative)
    - INVALIDATED → no trade was "filled" at entry price yet → balance unchanged.
    - NO TRADE → no change.

    Balance is floor-capped at 0 and persisted after every change.
    """

    def __init__(self):
        self.balance     = _load_balance()
        self.leverage    = TRADE_LEVERAGE
        self.entry_usdt  = TRADE_ENTRY_USDT

        print(
            f"VirtualExchange ready | "
            f"balance={self.balance} USDT | "
            f"leverage={self.leverage}x | "
            f"entry={self.entry_usdt} USDT/trade"
        )

    # ------------------------------------------------------------------
    # Read-only snapshot (for API responses)
    # ------------------------------------------------------------------

    def get_info(self) -> dict:
        return {
            "balance":         round(self.balance, 4),
            "initial_balance": INITIAL_BALANCE,
            "leverage":        self.leverage,
            "entry_usdt":      self.entry_usdt,
        }

    # ------------------------------------------------------------------
    # Apply TP / SL result — returns pnl_usdt
    # ------------------------------------------------------------------

    def apply_result(
        self,
        result:      str,    # "TP" | "SL"
        direction:   str,    # "LONG" | "SHORT"
        entry:       float,
        close_price: float,
    ) -> float:
        """
        Update balance based on trade result.
        Returns realized pnl in USDT (positive = profit, negative = loss).
        """
        if result not in ("TP", "SL"):
            return 0.0
        if entry <= 0:
            return 0.0

        # Use at most current balance as margin (can't over-commit)
        margin = min(self.entry_usdt, max(self.balance, 0))
        if margin <= 0:
            logger.warning("VirtualExchange: balance is 0 — trade PnL not applied")
            return 0.0

        if direction == "LONG":
            pnl_pct = (close_price - entry) / entry
        else:  # SHORT
            pnl_pct = (entry - close_price) / entry

        pnl_usdt = round(margin * self.leverage * pnl_pct, 4)

        self.balance = max(round(self.balance + pnl_usdt, 4), 0.0)
        _save_balance(self.balance)

        sign = "+" if pnl_usdt >= 0 else ""
        print(
            f"{result} | {direction} entry={entry} → {close_price} | "
            f"pnl={sign}{pnl_usdt} USDT | balance={self.balance} USDT"
        )
        logger.info(
            f"VirtualExchange {result}: direction={direction} entry={entry} "
            f"close={close_price} margin={margin} leverage={self.leverage} "
            f"pnl_usdt={pnl_usdt} balance={self.balance}"
        )
        return pnl_usdt

    # ------------------------------------------------------------------
    # Reset — restore to INITIAL_BALANCE
    # ------------------------------------------------------------------

    def reset(self):
        self.balance = INITIAL_BALANCE
        _save_balance(self.balance)
        print(f"virtualExchange: balance reset to {INITIAL_BALANCE} USDT")


# Singleton
virtual_exchange = VirtualExchange()
