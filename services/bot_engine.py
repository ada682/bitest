"""
Bot engine — perpetual signal scanner.

Data sources:
  • Symbol pool  →  MEXC USDT-FUTURES (get_contracts)
  • Candles      →  MEXC (best free kline data)
  • AI analysis  →  DeepSeek

Logic change (v2):
  - No more daily quota. Instead we maintain a MAX_ACTIVE_SIGNALS cap on
    CONCURRENT open signals.
  - Whenever an open signal closes (TP / SL / INVALIDATED), the active count
    drops below the cap and the scanner immediately picks a new coin.
  - NO TRADE results never count toward the cap.
  - The scanner keeps a "scanned but not yet producing signal" exclusion set
    that resets whenever the symbol pool is exhausted (so we cycle through
    coins forever without double-scanning within one pass).
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

from services.mexc_client      import mexc_client
from services.virtual_exchange import virtual_exchange
from services.qwen_ai          import qwen_ai
from services.mexc_price_feed  import price_feed          # ← WS price feed
from services.position_ai      import position_ai, MONITOR_INTERVAL
from utils.indicators          import format_ohlcv_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIMEFRAMES   = ["5m", "15m", "30m", "1h", "4h"]
CANDLE_LIMIT = 150
TIMEFRAMES_MONITOR = ["5m", "15m", "1h", "4h"]   # TFs used for hold/close AI

SIGNALS_FILE = Path(os.getenv("SIGNALS_FILE", "signals.json"))
MAX_SIGNALS  = 500

# NEW: concurrent open-signal cap (replaces MAX_DAILY_SIGNALS)
MAX_ACTIVE_SIGNALS = int(os.getenv("MAX_ACTIVE_SIGNALS", "20"))

REQUIRED_SYMBOLS   = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]   # MEXC format
INTER_SYMBOL_DELAY = float(os.getenv("INTER_SYMBOL_DELAY", "2.0"))

# Self-ping keepalive (for Railway free tier — prevents sleep)
KEEPALIVE_URL      = os.getenv("KEEPALIVE_URL", "")          # e.g. https://your-app.up.railway.app/api/health
KEEPALIVE_INTERVAL = int(os.getenv("KEEPALIVE_INTERVAL", "240"))  # seconds (4 min)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_signals() -> list:
    try:
        SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if SIGNALS_FILE.exists():
            data = json.loads(SIGNALS_FILE.read_text())
            print(f"📂 Loaded {len(data)} signals from {SIGNALS_FILE.absolute()}")
            return data[:MAX_SIGNALS]
    except Exception as e:
        logger.warning(f"Could not load signals file: {e}")
        print(f"❌ Failed to load signals: {e}")
    return []


def _save_signals(open_signals: list):
    try:
        SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if SIGNALS_FILE.exists():
            existing = json.loads(SIGNALS_FILE.read_text())
        sig_map = {s["id"]: s for s in existing}
        for s in open_signals:
            sig_map[s["id"]] = s
        final = sorted(sig_map.values(), key=lambda x: -x.get("timestamp", 0))
        SIGNALS_FILE.write_text(json.dumps(final[:MAX_SIGNALS], indent=2))
        print(f"✅ Signals saved | total: {len(final[:MAX_SIGNALS])}")
    except Exception as e:
        logger.warning(f"Could not save signals file: {e}")


def _save_closed_signal(signal: dict):
    try:
        SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if SIGNALS_FILE.exists():
            existing = json.loads(SIGNALS_FILE.read_text())
        sig_map = {s["id"]: s for s in existing}
        sig_map[signal["id"]] = signal
        final = sorted(sig_map.values(), key=lambda x: -x.get("timestamp", 0))
        SIGNALS_FILE.write_text(json.dumps(final[:MAX_SIGNALS], indent=2))
        print(f"✅ Closed signal saved: {signal['id']} | result: {signal.get('result')}")
    except Exception as e:
        logger.warning(f"Could not save closed signal: {e}")


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
            "signals":            [],
            "trade_count":        0,
            "win_count":          0,
            "loss_count":         0,
            "no_trade_count":     0,
            "total_pnl_pct":      0.0,
            "total_pnl_usdt":     0.0,
            "current_symbol":     None,
            "symbols_scanned":    0,
            # active signal count (replaces daily_signal_count)
            "active_signal_count": 0,
        }
        self._rebuild_counters()

        self._task:       Optional[asyncio.Task] = None
        self._ka_task:    Optional[asyncio.Task] = None   # keepalive
        self._listeners:  List[Callable]         = []

        # Per-pass exclusion set — reset when pool is exhausted
        self._pass_scanned: set = set()

    # ------------------------------------------------------------------
    # Rebuild counters from disk
    # ------------------------------------------------------------------
    def _rebuild_counters(self):
        all_signals = _load_signals()
        for s in all_signals:
            result = s.get("result")
            status = s.get("status")
            if result == "TP":
                self.state["trade_count"] += 1
                self.state["win_count"]   += 1
                self.state["total_pnl_pct"]   = round(
                    self.state["total_pnl_pct"]  + (s.get("pnl_pct") or 0), 4)
                self.state["total_pnl_usdt"]  = round(
                    self.state["total_pnl_usdt"] + (s.get("pnl_usdt") or 0), 4)
            elif result == "SL":
                self.state["trade_count"] += 1
                self.state["loss_count"]  += 1
                self.state["total_pnl_pct"]   = round(
                    self.state["total_pnl_pct"]  + (s.get("pnl_pct") or 0), 4)
                self.state["total_pnl_usdt"]  = round(
                    self.state["total_pnl_usdt"] + (s.get("pnl_usdt") or 0), 4)
            elif status == "OPEN":
                self.state["signals"].append(s)

        self.state["signals"] = self.state["signals"][:MAX_SIGNALS]
        self.state["active_signal_count"] = len(self.state["signals"])

    # ------------------------------------------------------------------
    # Listeners
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
    # Active signal count (thread-safe helper)
    # ------------------------------------------------------------------
    def _active_count(self) -> int:
        return sum(1 for s in self.state["signals"] if s.get("status") == "OPEN")

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------
    async def start(self, config: dict):
        if self.running:
            return {"ok": False, "reason": "Bot already running"}

        await price_feed.start()
        self.config  = config
        self.running = True
        self.state["status"] = "RUNNING"
        self._task = asyncio.create_task(self._loop())

        # Start keepalive ping if URL configured
        if KEEPALIVE_URL:
            self._ka_task = asyncio.create_task(self._keepalive_loop())
            print(f"🏓 Keepalive ping started → {KEEPALIVE_URL} every {KEEPALIVE_INTERVAL}s")
        else:
            print("⚠️  KEEPALIVE_URL not set — Railway may sleep. Set it in env vars.")

        return {"ok": True}

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        if self._ka_task:
            self._ka_task.cancel()
        self.state["status"] = "IDLE"
        return {"ok": True}

    async def shutdown(self):
        await self.stop()
        await price_feed.stop()
        await mexc_client.close()
        await qwen_ai.close()
        await position_ai.close()   # ← position monitor AI

    # ------------------------------------------------------------------
    # Keepalive loop — ping self to prevent Railway free-tier sleep
    # ------------------------------------------------------------------
    async def _keepalive_loop(self):
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            while self.running:
                try:
                    await asyncio.sleep(KEEPALIVE_INTERVAL)
                    r = await client.get(KEEPALIVE_URL)
                    print(f"🏓 Keepalive ping → {r.status_code}")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"🏓 Keepalive ping failed: {e}")

    # ------------------------------------------------------------------
    # Main loop — perpetual, cap-based
    # ------------------------------------------------------------------
    async def _loop(self):
        logger.info("Bot scanner loop started")
        print("Bot scanner loop started")

        n_workers = max(len(qwen_ai.clients), 1)
        print(f"[BotEngine] Parallel workers: {n_workers}")

        await asyncio.sleep(2)

        while self.running:
            try:
                active = self._active_count()

                # ── Already at cap → wait a bit then re-check ──────────
                if active >= MAX_ACTIVE_SIGNALS:
                    self.state["status"] = "MONITORING"
                    self._emit("status",
                        f"At cap ({active}/{MAX_ACTIVE_SIGNALS} active signals). "
                        "Waiting for a signal to close…"
                    )
                    await asyncio.sleep(10)
                    continue

                slots_needed = MAX_ACTIVE_SIGNALS - active
                print(f"\n[Loop] Active={active}/{MAX_ACTIVE_SIGNALS} — scanning for {slots_needed} more signal(s)")

                # ── Build pool excluding already-scanned this pass ──────
                pool = await self._build_pool(exclude=self._pass_scanned)

                if not pool:
                    # All symbols scanned this pass — reset exclusion set
                    print("[Loop] Pass exhausted — resetting scanned set for next pass")
                    self._pass_scanned = set()
                    await asyncio.sleep(5)
                    continue

                self.state["status"] = "RUNNING"
                i = 0
                while i < len(pool) and self.running:
                    # Re-check cap each iteration (a signal may have closed)
                    if self._active_count() >= MAX_ACTIVE_SIGNALS:
                        break

                    batch = pool[i:i + n_workers]
                    i    += n_workers

                    print(f"\n[Batch] {', '.join(batch)}")
                    self._emit("status", f"Scanning: {', '.join(batch)}")

                    market_tasks = [
                        asyncio.create_task(self._fetch_market_data(sym))
                        for sym in batch
                    ]
                    market_results = await asyncio.gather(*market_tasks, return_exceptions=True)

                    ai_items  = []
                    skip_syms = []

                    for sym, mresult in zip(batch, market_results):
                        if isinstance(mresult, Exception) or mresult is None:
                            skip_syms.append(sym)
                            continue
                        candles_by_tf, current_price = mresult
                        if not candles_by_tf or current_price <= 0:
                            skip_syms.append(sym)
                            continue
                        ai_items.append((sym, candles_by_tf, current_price))

                    for sym in skip_syms:
                        self._pass_scanned.add(sym)

                    if not ai_items:
                        await asyncio.sleep(INTER_SYMBOL_DELAY)
                        continue

                    ai_items = ai_items[:n_workers]
                    print(f"  Sending {len(ai_items)} AI requests in parallel…")
                    signals  = await qwen_ai.analyze_batch(ai_items)

                    for (sym, candles_by_tf, current_price), signal in zip(ai_items, signals):
                        found = self._process_signal(sym, current_price, signal)
                        self._pass_scanned.add(sym)

                        if found:
                            self._emit("progress", {
                                "active_signal_count": self._active_count(),
                                "max_active_signals":  MAX_ACTIVE_SIGNALS,
                                "symbols_scanned":     self.state["symbols_scanned"],
                            })
                            if self._active_count() >= MAX_ACTIVE_SIGNALS:
                                break

                    await asyncio.sleep(INTER_SYMBOL_DELAY)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Bot loop error: {e}", exc_info=True)
                self.state["last_error"] = str(e)
                self._emit("error", str(e))
                await asyncio.sleep(30)

        logger.info("Bot scanner loop ended")

    # ------------------------------------------------------------------
    # Fetch candles + ticker (MEXC)
    # ------------------------------------------------------------------
    async def _fetch_market_data(self, symbol: str):
        """symbol is MEXC format e.g. BTC_USDT"""
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
    # Build symbol pool from MEXC
    # ------------------------------------------------------------------
    async def _build_pool(self, exclude: set = None) -> List[str]:
        exclude = exclude or set()
        self._emit("status", "Fetching contract list from MEXC…")
        try:
            contracts = await mexc_client.get_contracts()
        except Exception as e:
            logger.error(f"Failed to fetch MEXC contracts: {e}")
            self._emit("error", f"Contract fetch error: {e}")
            return [s for s in REQUIRED_SYMBOLS if s not in exclude]

        all_symbols = [c["symbol"] for c in contracts if c.get("symbol")]
        mandatory   = [s for s in REQUIRED_SYMBOLS
                       if s in all_symbols and s not in exclude]
        pool        = [s for s in all_symbols
                       if s not in REQUIRED_SYMBOLS and s not in exclude]
        random.shuffle(pool)

        return mandatory + pool

    # ------------------------------------------------------------------
    # Process one AI signal
    # ------------------------------------------------------------------
    def _process_signal(self, symbol: str, current_price: float,
                        signal: dict) -> bool:
        """symbol is MEXC format (BTC_USDT) throughout the engine."""
        self.state["current_symbol"] = symbol
        self.state["symbols_scanned"] += 1

        decision = signal.get("decision", "NO TRADE")

        if decision == "NO TRADE":
            self.state["no_trade_count"] += 1
            print(f"  {symbol} → NO TRADE")
            return False

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
            "pnl_usdt":      None,
            "closed_at":     None,
            "closed_price":  None,
            "entry_hit":     False,
        }

        # Validate TP/SL direction before accepting
        _entry = signal_record.get("entry") or current_price
        _tp    = signal_record.get("tp")
        _sl    = signal_record.get("sl")
        if _entry and _tp and _sl:
            try:
                e, t, s = float(_entry), float(_tp), float(_sl)
                invalid_long  = (decision == "LONG"  and not (t > e > s))
                invalid_short = (decision == "SHORT" and not (t < e < s))
                if invalid_long or invalid_short:
                    print(f"  ⚠️  {symbol} {decision} REJECTED — invalid TP/SL: "
                          f"entry={e} tp={t} sl={s}")
                    return False
            except (TypeError, ValueError):
                pass

        self.state["signals"].insert(0, signal_record)
        self.state["signals"] = self.state["signals"][:MAX_SIGNALS]
        _save_signals(self.state["signals"])

        self.state["last_signal"]         = signal_record
        self.state["active_signal_count"] = self._active_count()
        self._emit("signal", signal_record)

        print(
            f"  ✅ {symbol} {decision} @ {current_price} | "
            f"TP={signal.get('tp')} SL={signal.get('sl')} | "
            f"conf={signal.get('confidence')}% "
            f"[active {self._active_count()}/{MAX_ACTIVE_SIGNALS}]"
        )

        # Spawn price monitor
        price_feed.watch(symbol)
        asyncio.create_task(self._monitor_signal(sig_id))

        return True

    # ------------------------------------------------------------------
    # Price monitor — WS price feed + AI hold/close
    # ------------------------------------------------------------------
    async def _monitor_signal(self, sig_id: str):
        """
        Monitor one open signal until TP / SL / AI_CLOSE / INVALIDATED / timeout.

        Flow after entry hit (Alpha Arena-style):
          Every MONITOR_INTERVAL seconds → fetch fresh candles → ask position_ai
          to HOLD or CLOSE.  Retries until valid response (sequential token rotation).
          TP / SL price checks still run every price tick in parallel.

        Timeout fix:
          Previously the task ended leaving signal status = "OPEN" with no monitor.
          Now: timeout → INVALIDATED (result="TIMEOUT") → releases the active slot.
        """
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
            price_feed.unwatch(symbol)
            return

        tp_f  = float(tp)
        sl_f  = float(sl)
        inv_f = float(inv_price) if inv_price else None

        # Capture original open analysis so position_ai has full context
        original_analysis = {
            "trend":      signal.get("trend"),
            "pattern":    signal.get("pattern"),
            "reason":     signal.get("reason"),
            "confidence": signal.get("confidence"),
        }

        max_duration        = 60 * 60 * 8   # 8 hours hard cap
        start               = time.time()
        entry_hit           = (entry <= 0)   # treat as already hit if no entry given
        PRICE_TICK_INTERVAL = 3              # seconds between price_tick events
        _last_tick_emit     = start
        _last_ai_check      = 0.0            # will be set when entry is hit

        _start_price = float(signal.get("current_price") or entry)
        if entry > 0:
            _pullback_entry = (
                _start_price > entry if direction == "LONG" else _start_price < entry
            )
        else:
            _pullback_entry = False

        print(
            f"  🔍 {sig_id} monitor start (WS) | direction={direction} "
            f"entry={entry} start_price={_start_price} pullback={_pullback_entry}"
        )

        # ─── main monitoring loop ─────────────────────────────────────
        while time.time() - start < max_duration:
            if not self.running:
                break

            signal = self._find_signal(sig_id)
            if not signal or signal.get("status") == "CLOSED":
                break

            # ── Get current price (WS feed, REST fallback) ─────────────
            price = await price_feed.wait_for_price(symbol, timeout=5.0)
            if not price or price <= 0:
                try:
                    ticker = await mexc_client.get_ticker(symbol)
                    price  = float(ticker.get("lastPr", ticker.get("last", 0)) or 0)
                except Exception:
                    continue
                if price <= 0:
                    continue

            signal["current_price"] = price

            # ── Emit price tick for frontend ────────────────────────────
            now_t = time.time()
            if now_t - _last_tick_emit >= PRICE_TICK_INTERVAL:
                self._emit("price_tick", {
                    "id":        sig_id,
                    "symbol":    symbol,
                    "price":     price,
                    "entry_hit": entry_hit,
                    "timestamp": int(now_t * 1000),
                })
                _last_tick_emit = now_t

            # ── Invalidation check (before entry) ──────────────────────
            if inv_f and not entry_hit:
                inv_hit = (
                    (direction == "LONG"  and price <= inv_f) or
                    (direction == "SHORT" and price >= inv_f)
                )
                if inv_hit:
                    signal.update({
                        "status":       "INVALIDATED",
                        "result":       "INVALIDATED",
                        "closed_at":    int(time.time() * 1000),
                        "closed_price": price,
                        "pnl_usdt":     0.0,
                        "pnl_pct":      0.0,
                    })
                    _save_closed_signal(signal)
                    self.state["signals"] = [
                        s for s in self.state["signals"] if s["id"] != sig_id
                    ]
                    self.state["active_signal_count"] = self._active_count()
                    self._emit("signal_invalidated", {
                        "id":        sig_id,
                        "symbol":    symbol,
                        "price":     price,
                        "timestamp": int(time.time() * 1000),
                    })
                    self._emit("balance_update", virtual_exchange.get_info())
                    print(f"  ❌ {sig_id} INVALIDATED @ {price}"
                          f" [active {self._active_count()}/{MAX_ACTIVE_SIGNALS}]")
                    price_feed.unwatch(symbol)
                    break

            # ── Entry gate ─────────────────────────────────────────────
            if not entry_hit:
                if direction == "LONG":
                    touched = price <= entry if _pullback_entry else price >= entry
                else:
                    touched = price >= entry if _pullback_entry else price <= entry

                if touched:
                    entry_hit      = True
                    signal["entry_hit"] = True
                    _last_ai_check = time.time()   # start AI interval from entry
                    mode_label     = "pullback" if _pullback_entry else "breakout"
                    print(f"  📍 {sig_id} entry HIT ({direction} {mode_label}) @ {price}")
                else:
                    continue
                continue

            # ── TP / SL price check (every tick, after entry) ──────────
            hit = None
            if direction == "LONG":
                if price >= tp_f:   hit = "TP"
                elif price <= sl_f: hit = "SL"
            elif direction == "SHORT":
                if price <= tp_f:   hit = "TP"
                elif price >= sl_f: hit = "SL"

            if hit:
                close_p  = tp_f if hit == "TP" else sl_f
                pnl_pct  = round(
                    (close_p - entry) / entry * 100 if direction == "LONG"
                    else (entry - close_p) / entry * 100, 4
                ) if entry > 0 else 0.0
                # Use pnl_pct (not hit label) to determine win/loss —
                # after SL+, sl_f may be above entry so SL hit = profit
                ve_label = "TP" if pnl_pct >= 0 else "SL"
                pnl_usdt = virtual_exchange.apply_result(ve_label, direction, entry, close_p)

                signal.update({
                    "status":       "CLOSED",
                    "result":       hit,          # keep "TP"/"SL" as the trigger label
                    "pnl_pct":      pnl_pct,
                    "pnl_usdt":     pnl_usdt,
                    "closed_at":    int(time.time() * 1000),
                    "closed_price": close_p,
                })
                self.state["trade_count"] += 1
                # Win = positive pnl (covers SL+ hit above entry)
                if pnl_pct >= 0:
                    self.state["win_count"] += 1
                else:
                    self.state["loss_count"] += 1
                self.state["total_pnl_pct"]  = round(
                    self.state["total_pnl_pct"] + pnl_pct, 4)
                self.state["total_pnl_usdt"] = round(
                    self.state["total_pnl_usdt"] + pnl_usdt, 4)

                _save_closed_signal(signal)
                self.state["signals"] = [
                    s for s in self.state["signals"] if s["id"] != sig_id
                ]
                self.state["active_signal_count"] = self._active_count()
                self._emit("signal_closed", {**signal, "balance": virtual_exchange.balance})
                self._emit("balance_update", virtual_exchange.get_info())
                print(
                    f"  Signal {sig_id} {hit} @ {close_p} | "
                    f"pnl={pnl_pct}% / {pnl_usdt:+.4f} USDT | "
                    f"balance={virtual_exchange.balance} USDT | "
                    f"active {self._active_count()}/{MAX_ACTIVE_SIGNALS}"
                )
                price_feed.unwatch(symbol)
                break

            # ── AI Hold/Close check — every MONITOR_INTERVAL seconds ────
            if (
                entry_hit
                and position_ai.enabled
                and (time.time() - _last_ai_check) >= MONITOR_INTERVAL
            ):
                _last_ai_check = time.time()
                print(f"  🤖 {sig_id} AI hold/close check ({symbol} {direction} @ {entry})…")

                try:
                    candles_by_tf: dict = {}
                    for tf in TIMEFRAMES_MONITOR:
                        try:
                            candles = await mexc_client.get_candles(symbol, tf, 100)
                            if candles and len(candles) >= 5:
                                candles_by_tf[tf] = candles
                        except Exception as e:
                            logger.debug(f"  {sig_id} candle fetch {tf}: {e}")

                    if not candles_by_tf:
                        print(f"  🤖 {sig_id} no candle data — skipping AI check")
                        continue

                    ai_result = await position_ai.decide_with_retry(
                        symbol             = symbol,
                        direction          = direction,
                        entry              = entry,
                        tp                 = tp_f,
                        sl                 = sl_f,
                        current_price      = price,
                        candles_by_tf      = candles_by_tf,
                        leverage           = virtual_exchange.leverage,
                        margin_usdt        = virtual_exchange.entry_usdt,
                        original_analysis  = original_analysis,
                        sl_plus_history    = signal.get("sl_plus_history") or [],
                    )

                    signal["last_ai_decision"] = ai_result.get("decision")
                    signal["last_ai_reason"]   = ai_result.get("reason")
                    signal["last_ai_at"]       = int(time.time() * 1000)

                    self._emit("signal_ai_update", {
                        "id":        sig_id,
                        "symbol":    symbol,
                        "decision":  ai_result.get("decision"),
                        "reason":    ai_result.get("reason"),
                        "new_sl":    ai_result.get("new_sl"),
                        "timestamp": int(time.time() * 1000),
                    })

                    # ── SL+ — move stop loss to lock profit ────────────
                    if ai_result.get("decision") == "SL+":
                        new_sl = ai_result.get("new_sl")
                        if new_sl and float(new_sl) > 0:
                            old_sl = sl_f
                            new_sl_f = float(new_sl)

                            # Extra guard: must improve the SL (closer to price)
                            sl_improves = (
                                (direction == "LONG"  and new_sl_f > old_sl) or
                                (direction == "SHORT" and new_sl_f < old_sl)
                            )
                            if sl_improves:
                                sl_f              = new_sl_f
                                signal["sl"]      = new_sl_f
                                signal["sl_plus_count"] = signal.get("sl_plus_count", 0) + 1
                                signal["sl_plus_history"] = signal.get("sl_plus_history", [])
                                signal["sl_plus_history"].append({
                                    "from":  old_sl,
                                    "to":    new_sl_f,
                                    "price": price,
                                    "at":    int(time.time() * 1000),
                                })
                                _save_signals(self.state["signals"])
                                self._emit("signal_sl_updated", {
                                    "id":        sig_id,
                                    "symbol":    symbol,
                                    "direction": direction,
                                    "old_sl":    old_sl,
                                    "new_sl":    new_sl_f,
                                    "price":     price,
                                    "reason":    ai_result.get("reason"),
                                    "timestamp": int(time.time() * 1000),
                                })
                                print(
                                    f"  🛡️  {sig_id} SL+ | {direction} "
                                    f"SL moved {old_sl} → {new_sl_f} "
                                    f"(price={price}) | {ai_result.get('reason')}"
                                )
                            else:
                                print(
                                    f"  ⚠️  {sig_id} SL+ rejected — "
                                    f"new_sl={new_sl_f} doesn't improve current sl={old_sl} "
                                    f"for {direction}"
                                )
                        else:
                            print(f"  ⚠️  {sig_id} SL+ had no valid new_sl — ignoring")

                    elif ai_result.get("decision") == "CLOSE":
                        pnl_pct = round(
                            (price - entry) / entry * 100 if direction == "LONG"
                            else (entry - price) / entry * 100, 4
                        ) if entry > 0 else 0.0

                        ve_label = "TP" if pnl_pct >= 0 else "SL"
                        pnl_usdt = virtual_exchange.apply_result(
                            ve_label, direction, entry, price
                        )

                        signal.update({
                            "status":       "CLOSED",
                            "result":       "AI_CLOSE",
                            "pnl_pct":      pnl_pct,
                            "pnl_usdt":     pnl_usdt,
                            "closed_at":    int(time.time() * 1000),
                            "closed_price": price,
                            "close_reason": ai_result.get("reason", "AI decided to close"),
                        })
                        self.state["trade_count"] += 1
                        if pnl_pct >= 0:
                            self.state["win_count"] += 1
                        else:
                            self.state["loss_count"] += 1
                        self.state["total_pnl_pct"]  = round(
                            self.state["total_pnl_pct"] + pnl_pct, 4)
                        self.state["total_pnl_usdt"] = round(
                            self.state["total_pnl_usdt"] + pnl_usdt, 4)

                        _save_closed_signal(signal)
                        self.state["signals"] = [
                            s for s in self.state["signals"] if s["id"] != sig_id
                        ]
                        self.state["active_signal_count"] = self._active_count()
                        self._emit("signal_closed", {
                            **signal,
                            "balance": virtual_exchange.balance,
                        })
                        self._emit("balance_update", virtual_exchange.get_info())
                        print(
                            f"  🤖 {sig_id} AI_CLOSE @ {price} | "
                            f"pnl={pnl_pct}% / {pnl_usdt:+.4f} USDT | "
                            f"reason: {ai_result.get('reason')} | "
                            f"balance={virtual_exchange.balance} USDT | "
                            f"active {self._active_count()}/{MAX_ACTIVE_SIGNALS}"
                        )
                        price_feed.unwatch(symbol)
                        break

                    else:
                        print(
                            f"  🤖 {sig_id} AI says HOLD "
                            f"({ai_result.get('reason', 'no reason given')})"
                        )

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(
                        f"  {sig_id} AI position check exception: {e}", exc_info=True
                    )

        # ─── Loop ended — bot stopped, signal closed, or 8h timeout ──────
        if self.running:
            signal = self._find_signal(sig_id)
            if signal and signal.get("status") == "OPEN":
                # FIX: previously "staying OPEN" with NO active monitor task
                # → signal would never close, slot permanently occupied.
                # Now: INVALIDATED with result=TIMEOUT → slot released immediately.
                print(
                    f"  ⏰ {sig_id} timed out (8h) — "
                    f"marking INVALIDATED (was: entry_hit={entry_hit})"
                )
                signal.update({
                    "status":       "INVALIDATED",
                    "result":       "TIMEOUT",
                    "closed_at":    int(time.time() * 1000),
                    "closed_price": signal.get("current_price", 0),
                    "pnl_usdt":     0.0,
                    "pnl_pct":      0.0,
                })
                _save_closed_signal(signal)
                self.state["signals"] = [
                    s for s in self.state["signals"] if s["id"] != sig_id
                ]
                self.state["active_signal_count"] = self._active_count()
                self._emit("signal_invalidated", {
                    "id":        sig_id,
                    "symbol":    signal.get("symbol"),
                    "price":     signal.get("current_price"),
                    "timestamp": int(time.time() * 1000),
                    "reason":    "timeout_8h",
                })
                price_feed.unwatch(symbol)

    def _find_signal(self, sig_id: str) -> Optional[Dict]:
        for s in self.state["signals"]:
            if s["id"] == sig_id:
                return s
        return None

    # ------------------------------------------------------------------
    # State / Stats
    # ------------------------------------------------------------------
    def get_state(self) -> dict:
        wins    = self.state["win_count"]
        losses  = self.state["loss_count"]
        closed  = wins + losses
        winrate = round(wins / closed * 100, 2) if closed > 0 else 0.0
        active  = self._active_count()
        return {
            **self.state,
            "winrate":             winrate,
            "active_signal_count": active,
            "max_active_signals":  MAX_ACTIVE_SIGNALS,
            "balance":             virtual_exchange.balance,
        }

    def reset_stats(self):
        self.state.update({
            "signals":             [],
            "trade_count":         0,
            "win_count":           0,
            "loss_count":          0,
            "no_trade_count":      0,
            "total_pnl_pct":       0.0,
            "total_pnl_usdt":      0.0,
            "last_signal":         None,
            "last_error":          None,
            "symbols_scanned":     0,
            "active_signal_count": 0,
        })
        self._pass_scanned = set()
        virtual_exchange.reset()
        try:
            SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SIGNALS_FILE.write_text(json.dumps([], indent=2))
            print(f"🗑️  Signals file cleared: {SIGNALS_FILE.absolute()}")
        except Exception as e:
            logger.warning(f"Could not clear signals file: {e}")


bot_engine = BotEngine()
