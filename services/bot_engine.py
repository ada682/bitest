"""
Bot engine — daily 20-signal scanner (no auto-trade).

Rules:
  • Every day, scan symbols in parallel batches until exactly MAX_DAILY_SIGNALS
    actionable (LONG / SHORT) signals are collected.
  • Batch size = number of available DeepSeek tokens (1–3).
    Each coin in a batch is analyzed by its own dedicated token simultaneously.
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
CANDLE_LIMIT = 150

SIGNALS_FILE = Path(os.getenv("SIGNALS_FILE", "signals.json"))
MAX_SIGNALS  = 500   # keep last N actionable signals on disk

# How many LONG/SHORT signals to collect per day (NO TRADE doesn't count)
MAX_DAILY_SIGNALS  = int(os.getenv("MAX_DAILY_SYMBOLS", "20"))
REQUIRED_SYMBOLS   = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]

# Delay between batches to respect MEXC rate limits
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


def _save_signals(open_signals: list):
    """
    Save open signals to disk while preserving closed signals already on disk.
    This ensures closed signals are never lost when the in-memory list is trimmed.
    """
    try:
        existing = []
        if SIGNALS_FILE.exists():
            existing = json.loads(SIGNALS_FILE.read_text())

        # Build a map from disk (all signals)
        sig_map = {s["id"]: s for s in existing}

        # Overlay current open signals (updates any that changed)
        for s in open_signals:
            sig_map[s["id"]] = s

        # Sort newest-first and trim
        final = sorted(sig_map.values(), key=lambda x: -x.get("timestamp", 0))
        SIGNALS_FILE.write_text(json.dumps(final[:MAX_SIGNALS], indent=2))
    except Exception as e:
        logger.warning(f"Could not save signals file: {e}")


def _save_closed_signal(signal: dict):
    """
    Persist a single closed signal to disk (upsert by id).
    Called right before removing the signal from the in-memory open list.
    """
    try:
        existing = []
        if SIGNALS_FILE.exists():
            existing = json.loads(SIGNALS_FILE.read_text())
        sig_map = {s["id"]: s for s in existing}
        sig_map[signal["id"]] = signal
        final = sorted(sig_map.values(), key=lambda x: -x.get("timestamp", 0))
        SIGNALS_FILE.write_text(json.dumps(final[:MAX_SIGNALS], indent=2))
    except Exception as e:
        logger.warning(f"Could not save closed signal: {e}")


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
            # Only OPEN signals kept in memory; closed ones live on disk only
            "signals":            [],
            "trade_count":        0,
            "win_count":          0,
            "loss_count":         0,
            "no_trade_count":     0,
            "total_pnl_pct":      0.0,
            "current_symbol":     None,
            "symbols_scanned":    0,
            # Daily tracking
            "scan_date":          "",
            "daily_signal_count": 0,
            "daily_scanned":      [],
        }
        self._rebuild_counters()
        self._restore_daily_state()

        self._task: Optional[asyncio.Task] = None
        self._listeners: List[Callable]    = []
        self._active_signal = None

    # ------------------------------------------------------------------
    # Rebuild counters from persisted signals
    # ------------------------------------------------------------------
    def _rebuild_counters(self):
        """
        Rebuild win/loss counters and restore open signals from disk.
        trade_count = only closed trades (TP or SL), matching WR denominator.
        INVALIDATED signals are excluded from all counters.
        """
        all_signals = _load_signals()
        for s in all_signals:
            result = s.get("result")
            status = s.get("status")
            if result == "TP":
                self.state["trade_count"] += 1
                self.state["win_count"]   += 1
                self.state["total_pnl_pct"] = round(
                    self.state["total_pnl_pct"] + (s.get("pnl_pct") or 0), 4)
            elif result == "SL":
                self.state["trade_count"] += 1
                self.state["loss_count"]  += 1
                self.state["total_pnl_pct"] = round(
                    self.state["total_pnl_pct"] + (s.get("pnl_pct") or 0), 4)
            elif status == "OPEN":
                # Restore only genuine open signals (not invalidated ones)
                self.state["signals"].append(s)

        self.state["signals"] = self.state["signals"][:MAX_SIGNALS]

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

        n_workers = max(len(deepseek_ai.clients), 1)
        print(f"[BotEngine] Parallel workers: {n_workers} (DeepSeek tokens loaded)")

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
                    print(f"[{today}] New day — collecting {MAX_DAILY_SIGNALS} signals "
                          f"({n_workers} coins/batch)")

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
                    secs = _seconds_until_midnight()
                    print(f"Pool exhausted without reaching quota. Waiting {int(secs)}s.")
                    self._emit("status", "All symbols scanned — waiting next day.")
                    self.state["status"] = "WAITING_NEXT_DAY"
                    await asyncio.sleep(secs)
                    self.state["status"] = "RUNNING"
                    continue

                # ── Scan pool in parallel batches ─────────────────────────
                i = 0
                while i < len(pool):
                    if not self.running:
                        break
                    if self.state["daily_signal_count"] >= MAX_DAILY_SIGNALS:
                        break

                    batch = pool[i:i + n_workers]
                    i += n_workers

                    print(f"\n[Batch] Analysing {len(batch)} coins in parallel: "
                          f"{', '.join(batch)}")
                    self._emit("status", f"Batch: {', '.join(batch)}")

                    # Step 1: Fetch candles + ticker for all symbols in parallel
                    market_tasks = [
                        asyncio.create_task(self._fetch_market_data(sym))
                        for sym in batch
                    ]
                    market_results = await asyncio.gather(*market_tasks, return_exceptions=True)

                    # Step 2: Build AI analysis items
                    ai_items   = []
                    skip_syms  = []

                    for sym, mresult in zip(batch, market_results):
                        if isinstance(mresult, Exception) or mresult is None:
                            print(f"  {sym}: market data error — skip")
                            skip_syms.append(sym)
                            continue
                        candles_by_tf, current_price = mresult
                        if not candles_by_tf or current_price <= 0:
                            print(f"  {sym}: insufficient data — skip")
                            skip_syms.append(sym)
                            continue
                        ai_items.append((sym, candles_by_tf, current_price))

                    for sym in skip_syms:
                        self._mark_scanned(sym, today)

                    if not ai_items:
                        await asyncio.sleep(INTER_SYMBOL_DELAY)
                        continue

                    # Step 3: Run AI analysis in parallel
                    ai_items = ai_items[:n_workers]

                    print(f"  Sending {len(ai_items)} AI requests in parallel…")
                    ai_batch = [(sym, tfs) for sym, tfs, _ in ai_items]
                    signals  = await deepseek_ai.analyze_batch(ai_batch)

                    # Step 4: Process each result
                    for (sym, candles_by_tf, current_price), signal in zip(ai_items, signals):
                        found = self._process_signal(sym, current_price, signal, today)
                        self._mark_scanned(sym, today)

                        if found:
                            progress = (f"Signal {self.state['daily_signal_count']}"
                                        f"/{MAX_DAILY_SIGNALS} collected.")
                            self._emit("progress", {
                                "daily_signal_count": self.state["daily_signal_count"],
                                "max_daily_signals":  MAX_DAILY_SIGNALS,
                                "symbols_scanned":    self.state["symbols_scanned"],
                            })
                            print(f"  📊 {progress}")

                            if self.state["daily_signal_count"] >= MAX_DAILY_SIGNALS:
                                break

                    await asyncio.sleep(INTER_SYMBOL_DELAY)

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
    # Fetch candles + ticker for a single symbol (used in parallel)
    # ------------------------------------------------------------------
    async def _fetch_market_data(self, symbol: str):
        candles_by_tf: Dict[str, list] = {}
        for tf in TIMEFRAMES:
            try:
                candles = await mexc_client.get_candles(symbol, tf, CANDLE_LIMIT)
                if candles and len(candles) >= 5:
                    candles_by_tf[tf] = candles
            except Exception as e:
                logger.debug(f"  {symbol}/{tf} fetch error: {e}")

        if not candles_by_tf:
            return None

        try:
            ticker        = await mexc_client.get_ticker(symbol)
            current_price = float(ticker.get("lastPr", ticker.get("last", 0)) or 0)
        except Exception:
            tf_any        = next(iter(candles_by_tf.values()))
            current_price = float(tf_any[-1][4])

        if current_price <= 0:
            return None

        return candles_by_tf, current_price

    # ------------------------------------------------------------------
    # Mark a symbol as scanned and persist daily state
    # ------------------------------------------------------------------
    def _mark_scanned(self, symbol: str, today: str):
        if symbol not in self.state["daily_scanned"]:
            self.state["daily_scanned"].append(symbol)
        self.state["symbols_scanned"] += 1
        _save_daily_state({
            "date":               today,
            "daily_signal_count": self.state["daily_signal_count"],
            "scanned_symbols":    self.state["daily_scanned"],
        })

    # ------------------------------------------------------------------
    # Process one AI signal result
    # Returns True if actionable (LONG/SHORT), False if NO TRADE
    # ------------------------------------------------------------------
    def _process_signal(self, symbol: str, current_price: float,
                        signal: dict, today: str) -> bool:
        self.state["current_symbol"] = symbol
        decision = signal.get("decision", "NO TRADE")

        if decision == "NO TRADE":
            self.state["no_trade_count"] += 1
            print(f"  {symbol} → NO TRADE (not counted toward daily quota)")
            return False

        # Actionable signal
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
            "invalidation":  signal.get("invalidation"),
            "reason":        signal.get("reason"),
            "confidence":    signal.get("confidence"),
            "status":        "OPEN",
            "result":        None,
            "pnl_pct":       None,
            "closed_at":     None,
            "closed_price":  None,
            # FIX BUG 2: track whether price has reached entry yet
            "entry_hit":     False,
        }

        self.state["signals"].insert(0, signal_record)
        self.state["signals"] = self.state["signals"][:MAX_SIGNALS]
        _save_signals(self.state["signals"])

        # FIX BUG 2: validate TP/SL are on the correct side of entry.
        # If AI returns inverted values (tp < entry for LONG, or tp > entry for SHORT),
        # reject the signal to prevent instant false-wins.
        _entry = signal_record.get("entry") or current_price
        _tp    = signal_record.get("tp")
        _sl    = signal_record.get("sl")
        if _entry and _tp and _sl:
            try:
                e, t, s = float(_entry), float(_tp), float(_sl)
                invalid_long  = (decision == "LONG"  and not (t > e > s))
                invalid_short = (decision == "SHORT" and not (t < e < s))
                if invalid_long or invalid_short:
                    print(f"  ⚠️  {symbol} {decision} REJECTED — invalid TP/SL direction: "
                          f"entry={e} tp={t} sl={s}")
                    self.state["signals"] = [
                        x for x in self.state["signals"] if x["id"] != sig_id
                    ]
                    _save_signals(self.state["signals"])
                    return False
            except (TypeError, ValueError):
                pass  # non-numeric values — let _monitor_signal handle

        self.state["last_signal"]        = signal_record
        # FIX BUG 1: don't increment trade_count here anymore;
        # trade_count only counts closed trades (TP/SL) for accurate WR
        self.state["daily_signal_count"] += 1

        self._emit("signal", signal_record)
        print(f"  ✅ {symbol} {decision} @ {current_price} | "
              f"TP={signal.get('tp')} SL={signal.get('sl')} | "
              f"conf={signal.get('confidence')}% "
              f"[{self.state['daily_signal_count']}/{MAX_DAILY_SIGNALS} today]")

        asyncio.create_task(self._monitor_signal(sig_id))
        return True

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
            return [s for s in REQUIRED_SYMBOLS if s not in exclude]

        all_symbols = [c["symbol"] for c in contracts]

        mandatory = [s for s in REQUIRED_SYMBOLS
                     if s in all_symbols and s not in exclude]
        pool      = [s for s in all_symbols
                     if s not in REQUIRED_SYMBOLS and s not in exclude]
        random.shuffle(pool)

        return mandatory + pool

    # ------------------------------------------------------------------
    # Monitor a signal until TP / SL / timeout
    # ------------------------------------------------------------------
    async def _monitor_signal(self, sig_id: str):
        signal = self._find_signal(sig_id)
        if not signal:
            return

        symbol    = signal["symbol"]
        direction = signal["decision"]
        entry     = float(signal.get("entry") or signal.get("current_price") or 0)
        tp        = signal.get("tp")
        sl        = signal.get("sl")
        inv_price = signal.get("invalidation")

        if not tp or not sl:
            return

        max_duration = 60 * 60 * 8   # 8 hours
        start        = time.time()

        # FIX BUG 2: gate — only start monitoring TP/SL after entry is hit
        entry_hit = False

        while time.time() - start < max_duration:
            await asyncio.sleep(10)
            if not self.running:
                break

            # Re-fetch signal in case it was removed (invalidated)
            signal = self._find_signal(sig_id)
            if not signal:
                break

            try:
                ticker = await mexc_client.get_ticker(symbol)
                price  = float(ticker.get("lastPr", ticker.get("last", 0)) or 0)
            except Exception:
                continue

            if price <= 0:
                continue

            # ── Cek invalidasi (auto-hapus signal) ──────────────────────
            if inv_price and inv_price > 0:
                inv_hit = (
                    (direction == "LONG"  and price <= inv_price) or
                    (direction == "SHORT" and price >= inv_price)
                )
                if inv_hit:
                    # FIX BUG 1: save signal as INVALIDATED on disk BEFORE
                    # removing from memory — prevents zombie OPEN signals in history.
                    signal["status"]       = "INVALIDATED"
                    signal["result"]       = "INVALIDATED"
                    signal["closed_at"]    = int(time.time() * 1000)
                    signal["closed_price"] = price
                    _save_closed_signal(signal)

                    self.state["signals"] = [
                        s for s in self.state["signals"] if s["id"] != sig_id
                    ]
                    self.state["daily_signal_count"] = max(0, self.state["daily_signal_count"] - 1)
                    self._emit("signal_invalidated", {
                        "id":        sig_id,
                        "symbol":    symbol,
                        "price":     price,
                        "inv_price": inv_price,
                        "direction": direction,
                        "timestamp": int(time.time() * 1000),
                    })
                    print(f"  ❌ Signal {sig_id} ({symbol} {direction}) "
                          f"INVALIDATED @ {price} | inv_level={inv_price}")
                    break

            # ── FIX BUG 2: wait for price to reach entry first ───────────
            if not entry_hit:
                if entry <= 0:
                    # No valid entry price from AI — skip gate
                    entry_hit = True
                elif direction == "LONG"  and price >= entry:
                    entry_hit = True
                    signal["entry_hit"] = True
                    print(f"  📍 {sig_id} ({symbol} LONG) entry hit @ {price}")
                elif direction == "SHORT" and price <= entry:
                    entry_hit = True
                    signal["entry_hit"] = True
                    print(f"  📍 {sig_id} ({symbol} SHORT) entry hit @ {price}")
                else:
                    # Price hasn't reached entry yet — keep waiting
                    continue
                # FIX BUG 2B: skip TP/SL check in the SAME tick entry is hit.
                # Prevents a phantom win when price barely touches entry and TP
                # is already satisfied (usually due to inverted AI levels).
                continue

            # ── Cek TP / SL ─────────────────────────────────────────────
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

                # FIX BUG 1: increment trade_count only on close
                self.state["trade_count"] += 1
                if hit == "TP":
                    self.state["win_count"] += 1
                else:
                    self.state["loss_count"] += 1
                self.state["total_pnl_pct"] = round(
                    self.state["total_pnl_pct"] + pnl_pct, 4)

                # FIX BUG 3: persist closed signal BEFORE removing from memory
                _save_closed_signal(signal)

                # Remove from in-memory open list → no longer shows in recent signals
                self.state["signals"] = [
                    s for s in self.state["signals"] if s["id"] != sig_id
                ]

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
        wins   = self.state["win_count"]
        losses = self.state["loss_count"]
        closed = wins + losses
        # FIX BUG 1: winrate = wins / (wins + losses), not wins / trade_count
        winrate = round(wins / closed * 100, 2) if closed > 0 else 0.0
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
            "scan_date":          "",
            "daily_scanned":      [],
        })
        _save_signals([])
        _save_daily_state({"date": "", "daily_signal_count": 0, "scanned_symbols": []})


bot_engine = BotEngine()
