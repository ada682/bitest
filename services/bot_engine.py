"""
Bot engine — daily 20-signal scanner (no auto-trade).

Rules:
  • Every day, scan symbols one-by-one until exactly MAX_DAILY_SIGNALS
    actionable (LONG / SHORT) signals are collected.
  • "NO TRADE" results are counted silently and do NOT contribute to the
    daily quota — the bot simply moves on to the next symbol.
  • BTC_USDT, ETH_USDT, SOL_USDT are always in the pool (scanned first).
  • If the pool runs out before the quota is reached, a fresh shuffled pool
    is built from all contracts and scanning continues.
  • After the daily quota is filled, the engine sleeps until midnight then
    automatically runs a fresh batch the next day.
"""

import asyncio
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, date, timedelta
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

# How many LONG/SHORT signals to collect per day (NO TRADE doesn't count)
MAX_DAILY_SIGNALS  = int(os.getenv("MAX_DAILY_SYMBOLS", "20"))
REQUIRED_SYMBOLS   = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]

# Delay between symbols to respect MEXC rate limits
INTER_SYMBOL_DELAY = float(os.getenv("INTER_SYMBOL_DELAY", "2.0"))

# Daily state file
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
    return {"date": "", "daily_signal_count": 0, "scanned_symbols": []}


def _save_daily_state(state: dict):
    try:
        DAILY_STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.warning(f"Could not save daily state: {e}")


def _seconds_until_midnight() -> float:
    """Seconds remaining until next local midnight."""
    now      = datetime.now()
    midnight = datetime(now.year, now.month, now.day, 0, 0, 0) + timedelta(days=1)
    return max((midnight - now).total_seconds(), 60)


# ---------------------------------------------------------------------------
# BotEngine
# ---------------------------------------------------------------------------

class BotEngine:
    def __init__(self):
        self.running = False
        self.config: Dict[str, Any] = {}
        self.state = {
            "status":             "IDLE",
            "last_signal":        None,
            "last_error":         None,
            "signals":            _load_signals(),
            "trade_count":        0,
            "win_count":          0,
            "loss_count":         0,
            "no_trade_count":     0,
            "total_pnl_pct":      0.0,
            "current_symbol":     None,
            "symbols_scanned":    0,   # total symbols analysed today (incl NO TRADE)
            # Daily tracking
            "scan_date":          "",
            "daily_signal_count": 0,   # LONG/SHORT found today (quota counter)
            "daily_scanned":      [],  # symbols already scanned today
        }
        self._rebuild_counters()

        # Restore today's progress from disk so restarts don't re-count
        self._restore_daily_state()

        self._task: Optional[asyncio.Task] = None
        self._listeners: List[Callable]    = []
        self._active_signal = None          # kept for debug endpoint compat

    # ------------------------------------------------------------------
    # Rebuild counters from persisted signals
    # ------------------------------------------------------------------
    def _rebuild_counters(self):
        for s in self.state["signals"]:
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

    def _restore_daily_state(self):
        ds = _load_daily_state()
        today = date.today().isoformat()
        if ds.get("date") == today:
            self.state["scan_date"]          = today
            self.state["daily_signal_count"] = ds.get("daily_signal_count", 0)
            self.state["daily_scanned"]      = ds.get("scanned_symbols", [])
            self.state["symbols_scanned"]    = len(self.state["daily_scanned"])

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

                # ── New day: reset daily counters ────────────────────────
                if self.state["scan_date"] != today:
                    self.state["scan_date"]          = today
                    self.state["daily_signal_count"] = 0
                    self.state["daily_scanned"]      = []
                    self.state["symbols_scanned"]    = 0
                    _save_daily_state({
                        "date":               today,
                        "daily_signal_count": 0,
                        "scanned_symbols":    [],
                    })
                    print(f"[{today}] New day — collecting {MAX_DAILY_SIGNALS} signals")

                # ── Already hit quota today? sleep until midnight ─────────
                if self.state["daily_signal_count"] >= MAX_DAILY_SIGNALS:
                    secs = _seconds_until_midnight()
                    hh   = int(secs // 3600)
                    mm   = int((secs % 3600) // 60)
                    msg  = (f"Daily quota reached "
                            f"({self.state['daily_signal_count']}/{MAX_DAILY_SIGNALS} signals). "
                            f"Next run in {hh}h {mm}m.")
                    print(msg)
                    self._emit("status", msg)
                    self.state["status"] = "WAITING_NEXT_DAY"
                    await asyncio.sleep(secs)
                    self.state["status"] = "RUNNING"
                    continue

                # ── Build a fresh symbol pool (excluding already scanned) ─
                pool = await self._build_pool(exclude=set(self.state["daily_scanned"]))
                if not pool:
                    # Rare: every contract already scanned today — wait midnight
                    secs = _seconds_until_midnight()
                    print(f"Pool exhausted without reaching quota. Waiting {int(secs)}s.")
                    self._emit("status", "All symbols scanned — waiting next day.")
                    self.state["status"] = "WAITING_NEXT_DAY"
                    await asyncio.sleep(secs)
                    self.state["status"] = "RUNNING"
                    continue

                # ── Scan pool until quota is filled ──────────────────────
                for symbol in pool:
                    if not self.running:
                        break
                    if self.state["daily_signal_count"] >= MAX_DAILY_SIGNALS:
                        break

                    found = await self._cycle(symbol)

                    # Mark symbol as scanned regardless of result
                    self.state["daily_scanned"].append(symbol)
                    self.state["symbols_scanned"] += 1

                    # Persist progress so restarts resume correctly
                    _save_daily_state({
                        "date":               today,
                        "daily_signal_count": self.state["daily_signal_count"],
                        "scanned_symbols":    self.state["daily_scanned"],
                    })

                    if found:
                        progress = (f"Signal {self.state['daily_signal_count']}"
                                    f"/{MAX_DAILY_SIGNALS} collected.")
                        self._emit("progress", {
                            "daily_signal_count": self.state["daily_signal_count"],
                            "max_daily_signals":  MAX_DAILY_SIGNALS,
                            "symbols_scanned":    self.state["symbols_scanned"],
                        })
                        print(f"  📊 {progress}")

                    await asyncio.sleep(INTER_SYMBOL_DELAY)

                # ── If quota not yet reached, outer loop rebuilds pool ────
                # (outer `while self.running` continues; pool will exclude
                #  already-scanned symbols so we pick fresh ones)

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
    # Build a shuffled symbol pool, required coins first
    # ------------------------------------------------------------------
    async def _build_pool(self, exclude: set = None) -> List[str]:
        exclude = exclude or set()
        self._emit("status", "Fetching contract list from MEXC…")
        try:
            contracts = await mexc_client.get_contracts()
        except Exception as e:
            logger.error(f"Failed to fetch contracts: {e}")
            self._emit("error", f"Contract fetch error: {e}")
            # Fallback: return required symbols not yet scanned
            return [s for s in REQUIRED_SYMBOLS if s not in exclude]

        all_symbols = [c["symbol"] for c in contracts]

        mandatory = [s for s in REQUIRED_SYMBOLS
                     if s in all_symbols and s not in exclude]
        pool      = [s for s in all_symbols
                     if s not in REQUIRED_SYMBOLS and s not in exclude]
        random.shuffle(pool)

        return mandatory + pool

    # ------------------------------------------------------------------
    # One analysis cycle for a single symbol.
    # Returns True if an actionable signal (LONG/SHORT) was found,
    # False if result was NO TRADE or an error occurred.
    # ------------------------------------------------------------------
    async def _cycle(self, symbol: str) -> bool:
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
            return False

        # 2. Current price
        try:
            ticker        = await mexc_client.get_ticker(symbol)
            current_price = float(ticker.get("lastPr", ticker.get("last", 0)) or 0)
        except Exception:
            tf_any        = next(iter(candles_by_tf.values()))
            current_price = float(tf_any[-1][4])

        if current_price <= 0:
            return False

        # 3. AI analysis
        try:
            signal = await deepseek_ai.analyze(symbol, candles_by_tf)
        except Exception as e:
            logger.error(f"AI error for {symbol}: {e}")
            return False

        decision = signal.get("decision", "NO TRADE")

        # 4a. NO TRADE — count silently, do NOT increment daily quota
        if decision == "NO TRADE":
            self.state["no_trade_count"] += 1
            print(f"  → NO TRADE (not counted toward daily quota)")
            return False   # ← caller will fetch the next symbol

        # 4b. Actionable signal — save, broadcast, increment quota
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

        self.state["last_signal"]        = signal_record
        self.state["trade_count"]       += 1
        self.state["daily_signal_count"] += 1   # ← counts toward quota

        self._emit("signal", signal_record)
        print(f"  ✅ {decision} @ {current_price} | TP={signal.get('tp')} "
              f"SL={signal.get('sl')} | conf={signal.get('confidence')}% "
              f"[{self.state['daily_signal_count']}/{MAX_DAILY_SIGNALS} today]")

        # 5. Monitor TP/SL in the background
        asyncio.create_task(self._monitor_signal(sig_id))

        return True   # ← signal found, quota incremented

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
            "winrate":            winrate,
            "scan_date":          self.state["scan_date"],
            "daily_signal_count": self.state["daily_signal_count"],
            "max_daily_signals":  MAX_DAILY_SIGNALS,
            "next_reset_in":      int(_seconds_until_midnight()),
        }

    def reset_stats(self):
        self.state.update({
            "signals":            [],
            "trade_count":        0,
            "win_count":          0,
            "loss_count":         0,
            "no_trade_count":     0,
            "total_pnl_pct":      0.0,
            "last_signal":        None,
            "last_error":         None,
            "symbols_scanned":    0,
            "daily_signal_count": 0,
            "scan_date":          "",   # force fresh pick next cycle
            "daily_scanned":      [],
        })
        _save_signals([])
        _save_daily_state({"date": "", "daily_signal_count": 0, "scanned_symbols": []})


bot_engine = BotEngine()
