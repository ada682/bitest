"""
Bot engine — daily 20-symbol scanner (no auto-trade).

Rules:
  • Every day, pick exactly MAX_DAILY_SYMBOLS symbols to analyse.
  • BTC_USDT, ETH_USDT, SOL_USDT are ALWAYS included.
  • The remaining slots are filled with a random sample from the full pool.
  • "NO TRADE" results are counted but NEVER saved or emitted to the frontend.
  • After the daily batch finishes, the engine sleeps until midnight (local time)
    then automatically runs a fresh random batch the next day.
"""

import asyncio
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.mexc_client import mexc_client
from services.deepseek_ai import deepseek_ai
from utils.indicators import format_ohlcv_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIMEFRAMES   = ["5m", "15m", "30m", "1h", "4h"]
CANDLE_LIMIT = 60

SIGNALS_FILE = Path(os.getenv("SIGNALS_FILE", "signals.json"))
MAX_SIGNALS  = 500   # keep last N actionable signals on disk

# Daily limit & mandatory coins
MAX_DAILY_SYMBOLS  = int(os.getenv("MAX_DAILY_SYMBOLS", "20"))
REQUIRED_SYMBOLS   = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]

# Delay between symbols to respect MEXC rate limits
INTER_SYMBOL_DELAY = float(os.getenv("INTER_SYMBOL_DELAY", "2.0"))

# Daily state file — remembers which date we last ran so restarts don't re-scan
DAILY_STATE_FILE = Path(os.getenv("DAILY_STATE_FILE", "daily_state.json"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_signals() -> list:
    try:
        if SIGNALS_FILE.exists():
            return json.loads(SIGNALS_FILE.read_text())[:MAX_SIGNALS]
    except Exception as e:
        logger.warning(f"Could not load signals file: {e}")
    return []


def _save_signals(signals: list):
    try:
        SIGNALS_FILE.write_text(json.dumps(signals[:MAX_SIGNALS], indent=2))
    except Exception as e:
        logger.warning(f"Could not save signals file: {e}")


def _load_daily_state() -> dict:
    try:
        if DAILY_STATE_FILE.exists():
            return json.loads(DAILY_STATE_FILE.read_text())
    except Exception:
        pass
    return {"date": "", "symbols": []}


def _save_daily_state(state: dict):
    try:
        DAILY_STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.warning(f"Could not save daily state: {e}")


def _seconds_until_midnight() -> float:
    """Seconds remaining until next local midnight."""
    now = datetime.now()
    midnight = datetime(now.year, now.month, now.day, 0, 0, 0)
    # tomorrow's midnight
    from datetime import timedelta
    midnight += timedelta(days=1)
    return max((midnight - now).total_seconds(), 60)


# ---------------------------------------------------------------------------
# BotEngine
# ---------------------------------------------------------------------------

class BotEngine:
    def __init__(self):
        self.running = False
        self.config: Dict[str, Any] = {}
        self.state = {
            "status":           "IDLE",
            "last_signal":      None,
            "last_error":       None,
            "signals":          _load_signals(),
            "trade_count":      0,
            "win_count":        0,
            "loss_count":       0,
            "no_trade_count":   0,
            "total_pnl_pct":    0.0,
            "current_symbol":   None,
            "symbols_scanned":  0,
            "symbols_total":    0,
            # Daily tracking
            "scan_date":        "",
            "daily_symbols":    [],
        }
        self._rebuild_counters()

        self._task: Optional[asyncio.Task] = None
        self._listeners: List[Callable]    = []

    # ------------------------------------------------------------------
    # Rebuild counters from persisted (actionable) signals
    # ------------------------------------------------------------------
    def _rebuild_counters(self):
        for s in self.state["signals"]:
            # All signals in file are LONG/SHORT (NO TRADE never saved)
            self.state["trade_count"] += 1
            result = s.get("result")
            if result == "TP":
                self.state["win_count"] += 1
                self.state["total_pnl_pct"] = round(
                    self.state["total_pnl_pct"] + (s.get("pnl_pct") or 0), 4)
            elif result == "SL":
                self.state["loss_count"] += 1
                self.state["total_pnl_pct"] = round(
                    self.state["total_pnl_pct"] + (s.get("pnl_pct") or 0), 4)

    # ------------------------------------------------------------------
    # Listener management
    # ------------------------------------------------------------------
    def add_listener(self, fn: Callable):
        if fn not in self._listeners:
            self._listeners.append(fn)

    def _emit(self, event: str, data: Any):
        for fn in self._listeners:
            try:
                fn(event, data)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------
    async def start(self, config: dict):
        if self.running:
            return {"ok": False, "reason": "Bot already running"}
        self.config  = config
        self.running = True
        self.state["status"] = "RUNNING"
        self._task = asyncio.create_task(self._loop())
        return {"ok": True}

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        self.state["status"] = "IDLE"
        return {"ok": True}

    async def shutdown(self):
        await self.stop()
        await mexc_client.close()
        await deepseek_ai.close()

    # ------------------------------------------------------------------
    # Main loop  —  daily rhythm
    # ------------------------------------------------------------------
    async def _loop(self):
        logger.info("Bot scanner loop started")
        print("Bot scanner loop started")
        await asyncio.sleep(2)

        while self.running:
            try:
                today = date.today().isoformat()

                if self.state["scan_date"] != today:
                    # ── New day: build a fresh symbol list ───────────────
                    symbols = await self._pick_daily_symbols()
                    self.state["scan_date"]    = today
                    self.state["daily_symbols"] = symbols
                    _save_daily_state({"date": today, "symbols": symbols})
                    print(f"[{today}] Daily batch: {symbols}")
                else:
                    # Restarted mid-day — reuse today's list
                    symbols = self.state["daily_symbols"]
                    print(f"[{today}] Resuming today's batch: {symbols}")

                # ── Scan the selected symbols ─────────────────────────
                self.state["symbols_total"]   = len(symbols)
                self.state["symbols_scanned"] = 0

                for symbol in symbols:
                    if not self.running:
                        break
                    await self._cycle(symbol)
                    self.state["symbols_scanned"] += 1
                    await asyncio.sleep(INTER_SYMBOL_DELAY)

                # ── Sleep until midnight for next day's batch ─────────
                secs = _seconds_until_midnight()
                hh   = int(secs // 3600)
                mm   = int((secs % 3600) // 60)
                msg  = f"Daily scan done ({len(symbols)} symbols). Next run in {hh}h {mm}m."
                print(msg)
                self._emit("status", msg)
                self.state["status"] = "WAITING_NEXT_DAY"

                await asyncio.sleep(secs)
                self.state["status"] = "RUNNING"

            except asyncio.CancelledError:
                print("Scanner loop cancelled")
                break
            except Exception as e:
                print(f"Loop error: {e}")
                import traceback; traceback.print_exc()
                self.state["last_error"] = str(e)
                self._emit("error", str(e))
                await asyncio.sleep(30)

        self.state["status"] = "IDLE"
        print("Scanner loop ended")

    # ------------------------------------------------------------------
    # Build the daily symbol list
    # ------------------------------------------------------------------
    async def _pick_daily_symbols(self) -> List[str]:
        self._emit("status", "Fetching contract list from MEXC…")
        try:
            contracts = await mexc_client.get_contracts()
        except Exception as e:
            logger.error(f"Failed to fetch contracts: {e}")
            self._emit("error", f"Contract fetch error: {e}")
            return REQUIRED_SYMBOLS[:]

        all_symbols = [c["symbol"] for c in contracts]

        # Mandatory coins (filter to those actually listed on MEXC)
        mandatory = [s for s in REQUIRED_SYMBOLS if s in all_symbols]

        # Pool = everything else
        pool = [s for s in all_symbols if s not in mandatory]
        random.shuffle(pool)

        remaining_slots = max(MAX_DAILY_SYMBOLS - len(mandatory), 0)
        selected = mandatory + pool[:remaining_slots]

        # Shuffle the final list so mandatory coins aren't always first
        random.shuffle(selected)
        return selected

    # ------------------------------------------------------------------
    # One analysis cycle for a single symbol
    # ------------------------------------------------------------------
    async def _cycle(self, symbol: str):
        self.state["current_symbol"] = symbol
        self._emit("status", f"Analysing {symbol}…")
        print(f"--- {symbol} ---")

        # 1. Fetch candles
        candles_by_tf: Dict[str, list] = {}
        for tf in TIMEFRAMES:
            try:
                candles = await mexc_client.get_candles(symbol, tf, CANDLE_LIMIT)
                if candles and len(candles) >= 5:
                    candles_by_tf[tf] = candles
            except Exception as e:
                print(f"  {tf} fetch error: {e}")

        if not candles_by_tf:
            return

        # 2. Current price
        try:
            ticker        = await mexc_client.get_ticker(symbol)
            current_price = float(ticker.get("lastPr", ticker.get("last", 0)) or 0)
        except Exception:
            tf_any        = next(iter(candles_by_tf.values()))
            current_price = float(tf_any[-1][4])

        if current_price <= 0:
            return

        # 3. AI analysis
        try:
            signal = await deepseek_ai.analyze(symbol, candles_by_tf)
        except Exception as e:
            logger.error(f"AI error for {symbol}: {e}")
            return

        decision = signal.get("decision", "NO TRADE")

        # 4a. NO TRADE — count silently, never touch the frontend
        if decision == "NO TRADE":
            self.state["no_trade_count"] += 1
            print(f"  → NO TRADE (skipped)")
            return

        # 4b. Actionable signal — save & broadcast
        sig_id = str(uuid.uuid4())[:8]
        signal_record = {
            "id":            sig_id,
            "symbol":        symbol,
            "timestamp":     int(time.time() * 1000),
            "current_price": current_price,
            "trend":         signal.get("trend"),
            "pattern":       signal.get("pattern"),
            "decision":      decision,
            "entry":         signal.get("entry"),
            "tp":            signal.get("tp"),
            "sl":            signal.get("sl"),
            "reason":        signal.get("reason"),
            "confidence":    signal.get("confidence"),
            "status":        "OPEN",
            "result":        None,
            "pnl_pct":       None,
            "closed_at":     None,
            "closed_price":  None,
        }

        self.state["signals"].insert(0, signal_record)
        self.state["signals"] = self.state["signals"][:MAX_SIGNALS]
        _save_signals(self.state["signals"])

        self.state["last_signal"] = signal_record
        self.state["trade_count"] += 1

        self._emit("signal", signal_record)
        print(f"  ✅ {decision} @ {current_price} | TP={signal.get('tp')} SL={signal.get('sl')} | conf={signal.get('confidence')}%")

        # 5. Monitor TP/SL in the background
        asyncio.create_task(self._monitor_signal(sig_id))

    # ------------------------------------------------------------------
    # Monitor a signal until TP / SL / timeout
    # ------------------------------------------------------------------
    async def _monitor_signal(self, sig_id: str):
        signal = self._find_signal(sig_id)
        if not signal:
            return

        symbol    = signal["symbol"]
        direction = signal["decision"]
        entry     = signal.get("entry") or signal.get("current_price")
        tp        = signal.get("tp")
        sl        = signal.get("sl")

        if not tp or not sl:
            return

        max_duration = 60 * 60 * 8   # 8 hours
        start        = time.time()

        while time.time() - start < max_duration:
            await asyncio.sleep(10)
            if not self.running:
                break
            try:
                ticker = await mexc_client.get_ticker(symbol)
                price  = float(ticker.get("lastPr", ticker.get("last", 0)) or 0)
            except Exception:
                continue

            hit = None
            if direction == "LONG":
                if price >= tp:   hit = "TP"
                elif price <= sl: hit = "SL"
            elif direction == "SHORT":
                if price <= tp:   hit = "TP"
                elif price >= sl: hit = "SL"

            if hit:
                pnl_pct = 0.0
                if entry and entry > 0:
                    pnl_pct = round(
                        (price - entry) / entry * 100 if direction == "LONG"
                        else (entry - price) / entry * 100, 4
                    )

                signal["status"]       = "CLOSED"
                signal["result"]       = hit
                signal["pnl_pct"]      = pnl_pct
                signal["closed_at"]    = int(time.time() * 1000)
                signal["closed_price"] = price

                if hit == "TP":
                    self.state["win_count"] += 1
                else:
                    self.state["loss_count"] += 1
                self.state["total_pnl_pct"] = round(
                    self.state["total_pnl_pct"] + pnl_pct, 4)

                _save_signals(self.state["signals"])
                self._emit("signal_closed", signal)
                print(f"  Signal {sig_id} closed: {hit} @ {price} | PnL: {pnl_pct}%")
                break

    def _find_signal(self, sig_id: str) -> Optional[Dict]:
        for s in self.state["signals"]:
            if s["id"] == sig_id:
                return s
        return None

    # ------------------------------------------------------------------
    # State / Stats
    # ------------------------------------------------------------------
    def get_state(self) -> dict:
        trades  = self.state["trade_count"]
        wins    = self.state["win_count"]
        winrate = round(wins / trades * 100, 2) if trades > 0 else 0.0
        return {
            **self.state,
            "winrate": winrate,
            # Expose daily info
            "scan_date":     self.state["scan_date"],
            "daily_symbols": self.state["daily_symbols"],
            "next_reset_in": int(_seconds_until_midnight()),
        }

    def reset_stats(self):
        self.state.update({
            "signals":          [],
            "trade_count":      0,
            "win_count":        0,
            "loss_count":       0,
            "no_trade_count":   0,
            "total_pnl_pct":    0.0,
            "last_signal":      None,
            "last_error":       None,
            "symbols_scanned":  0,
            "scan_date":        "",   # force fresh pick next cycle
            "daily_symbols":    [],
        })
        _save_signals([])
        _save_daily_state({"date": "", "symbols": []})


bot_engine = BotEngine()
