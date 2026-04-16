"""
Bot engine — daily 20-signal scanner.

Changes vs original:
  • Symbol pool → fetched from Bitget USDT-FUTURES (previously MEXC)
  • Candles       → still MEXC (better free kline data)
  • On actionable signal → places real limit order on Bitget Demo account
    with preset TP/SL
  • _monitor_signal → kept as lightweight fallback, but primary tracking is
    via Bitget private WebSocket (bitget_ws.py)
  • handle_bitget_position_update() → called by WS to close signals
    based on real Bitget position data
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

from services.mexc_client   import mexc_client
from services.bitget_client import bitget_client, mexc_to_bitget, bitget_to_mexc
from services.deepseek_ai   import deepseek_ai
from utils.indicators       import format_ohlcv_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIMEFRAMES   = ["5m", "15m", "30m", "1h", "4h"]
CANDLE_LIMIT = 150

SIGNALS_FILE = Path(os.getenv("SIGNALS_FILE", "signals.json"))
MAX_SIGNALS  = 500

MAX_DAILY_SIGNALS  = int(os.getenv("MAX_DAILY_SYMBOLS", "20"))
REQUIRED_SYMBOLS   = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]   # MEXC format internally

INTER_SYMBOL_DELAY = float(os.getenv("INTER_SYMBOL_DELAY", "2.0"))
DAILY_STATE_FILE   = Path(os.getenv("DAILY_STATE_FILE", "daily_state.json"))

# Bitget order settings (configurable via env)
BITGET_LEVERAGE    = int(os.getenv("BITGET_LEVERAGE", "10"))
BITGET_MARGIN_MODE = os.getenv("BITGET_MARGIN_MODE", "isolated")
# Position size: USDT margin per trade (0 = skip auto-order)
BITGET_MARGIN_USDT = float(os.getenv("BITGET_MARGIN_USDT", "10"))


# ---------------------------------------------------------------------------
# Helpers (unchanged from original)
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
    now      = datetime.now()
    midnight = datetime(now.year, now.month, now.day) + timedelta(days=1)
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
            "signals":            [],
            "trade_count":        0,
            "win_count":          0,
            "loss_count":         0,
            "no_trade_count":     0,
            "total_pnl_pct":      0.0,
            "current_symbol":     None,
            "symbols_scanned":    0,
            "scan_date":          "",
            "daily_signal_count": 0,
            "daily_scanned":      [],
        }
        self._rebuild_counters()
        self._restore_daily_state()

        self._task:           Optional[asyncio.Task] = None
        self._listeners:      List[Callable]         = []
        self._active_signal                          = None

        # Map bitget_order_id → signal_id for WS-driven close
        self._order_to_signal: Dict[str, str] = {}

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
                self.state["total_pnl_pct"] = round(
                    self.state["total_pnl_pct"] + (s.get("pnl_pct") or 0), 4)
            elif result == "SL":
                self.state["trade_count"] += 1
                self.state["loss_count"]  += 1
                self.state["total_pnl_pct"] = round(
                    self.state["total_pnl_pct"] + (s.get("pnl_pct") or 0), 4)
            elif status == "OPEN":
                self.state["signals"].append(s)
        self.state["signals"] = self.state["signals"][:MAX_SIGNALS]

    def _restore_daily_state(self):
        ds    = _load_daily_state()
        today = date.today().isoformat()
        if ds.get("date") == today:
            self.state["scan_date"]          = today
            self.state["daily_signal_count"] = ds.get("daily_signal_count", 0)
            self.state["daily_scanned"]      = ds.get("scanned_symbols", [])
            self.state["symbols_scanned"]    = len(self.state["daily_scanned"])

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
        await bitget_client.close()
        await deepseek_ai.close()

    # ------------------------------------------------------------------
    # Bitget WebSocket callback — called by bitget_ws.py
    # Updates open signals when Bitget reports a position was closed
    # ------------------------------------------------------------------
    def handle_bitget_order_update(self, event: str, data: dict):
        """
        Called by bitget_ws when an order status changes.
        Looks for filled/closed orders that match open signals and
        marks them TP or SL accordingly.
        """
        orders = data.get("orders", [])
        for o in orders:
            order_id = o.get("orderId")
            pnl      = o.get("pnl")
            status   = o.get("status", "")

            if status not in ("filled", "full_fill"):
                continue

            sig_id = self._order_to_signal.get(order_id)
            if not sig_id:
                continue

            signal = self._find_signal(sig_id)
            if not signal:
                continue

            # Determine TP or SL from PnL
            try:
                pnl_val = float(pnl or 0)
            except (ValueError, TypeError):
                pnl_val = 0.0

            result    = "TP" if pnl_val >= 0 else "SL"
            pnl_pct   = round(pnl_val / max(float(signal.get("entry") or 1), 1) * 100, 4)

            signal["status"]       = "CLOSED"
            signal["result"]       = result
            signal["pnl_pct"]      = pnl_pct
            signal["closed_at"]    = int(time.time() * 1000)
            signal["closed_price"] = float(o.get("fillPrice") or 0)

            self.state["trade_count"] += 1
            if result == "TP":
                self.state["win_count"] += 1
            else:
                self.state["loss_count"] += 1
            self.state["total_pnl_pct"] = round(
                self.state["total_pnl_pct"] + pnl_pct, 4)

            _save_closed_signal(signal)
            self.state["signals"] = [
                s for s in self.state["signals"] if s["id"] != sig_id
            ]

            self._emit("signal_closed", signal)
            print(f"  [Bitget WS] Signal {sig_id} closed via order: "
                  f"{result} | PnL: {pnl_pct}%")

    # ------------------------------------------------------------------
    # Main loop  —  daily rhythm (unchanged from original)
    # ------------------------------------------------------------------
    async def _loop(self):
        logger.info("Bot scanner loop started")
        print("Bot scanner loop started")

        n_workers = max(len(deepseek_ai.clients), 1)
        print(f"[BotEngine] Parallel workers: {n_workers}")

        await asyncio.sleep(2)

        while self.running:
            try:
                today = date.today().isoformat()

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

                if self.state["daily_signal_count"] >= MAX_DAILY_SIGNALS:
                    secs = _seconds_until_midnight()
                    hh   = int(secs // 3600)
                    mm   = int((secs % 3600) // 60)
                    msg  = (f"Daily quota reached "
                            f"({self.state['daily_signal_count']}/{MAX_DAILY_SIGNALS}). "
                            f"Next run in {hh}h {mm}m.")
                    print(msg)
                    self._emit("status", msg)
                    self.state["status"] = "WAITING_NEXT_DAY"
                    await asyncio.sleep(secs)
                    self.state["status"] = "RUNNING"
                    continue

                pool = await self._build_pool(exclude=set(self.state["daily_scanned"]))
                if not pool:
                    secs = _seconds_until_midnight()
                    print(f"Pool exhausted. Waiting {int(secs)}s.")
                    self._emit("status", "All symbols scanned — waiting next day.")
                    self.state["status"] = "WAITING_NEXT_DAY"
                    await asyncio.sleep(secs)
                    self.state["status"] = "RUNNING"
                    continue

                i = 0
                while i < len(pool):
                    if not self.running:
                        break
                    if self.state["daily_signal_count"] >= MAX_DAILY_SIGNALS:
                        break

                    batch = pool[i:i + n_workers]
                    i    += n_workers

                    print(f"\n[Batch] {', '.join(batch)}")
                    self._emit("status", f"Batch: {', '.join(batch)}")

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
                        self._mark_scanned(sym, today)

                    if not ai_items:
                        await asyncio.sleep(INTER_SYMBOL_DELAY)
                        continue

                    ai_items = ai_items[:n_workers]
                    print(f"  Sending {len(ai_items)} AI requests in parallel…")
                    ai_batch = [(sym, tfs, price) for sym, tfs, price in ai_items]
                    signals  = await deepseek_ai.analyze_batch(ai_batch)

                    for (sym, candles_by_tf, current_price), signal in zip(ai_items, signals):
                        found = self._process_signal(sym, current_price, signal, today)
                        self._mark_scanned(sym, today)

                        if found:
                            self._emit("progress", {
                                "daily_signal_count": self.state["daily_signal_count"],
                                "max_daily_signals":  MAX_DAILY_SIGNALS,
                                "symbols_scanned":    self.state["symbols_scanned"],
                            })
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
    # Fetch candles + ticker (MEXC) — unchanged
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
    # Build symbol pool  — NOW from Bitget (converted to MEXC format)
    # ------------------------------------------------------------------
    async def _build_pool(self, exclude: set = None) -> List[str]:
        exclude = exclude or set()
        self._emit("status", "Fetching contract list from Bitget…")
        try:
            contracts = await bitget_client.get_contracts()
        except Exception as e:
            logger.error(f"Failed to fetch Bitget contracts: {e}")
            self._emit("error", f"Contract fetch error: {e}")
            # Fallback to required symbols
            return [s for s in REQUIRED_SYMBOLS if s not in exclude]

        # contracts return "symbol" in Bitget format (BTCUSDT);
        # "mexcSymbol" is pre-computed in bitget_client (BTC_USDT)
        all_symbols = [c["mexcSymbol"] for c in contracts if c.get("mexcSymbol")]

        mandatory = [s for s in REQUIRED_SYMBOLS
                     if s in all_symbols and s not in exclude]
        pool      = [s for s in all_symbols
                     if s not in REQUIRED_SYMBOLS and s not in exclude]
        random.shuffle(pool)

        return mandatory + pool

    # ------------------------------------------------------------------
    # Mark scanned
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
    # Process one AI signal  — places real Bitget order if actionable
    # ------------------------------------------------------------------
    def _process_signal(self, symbol: str, current_price: float,
                        signal: dict, today: str) -> bool:
        """symbol is MEXC format (BTC_USDT) throughout the engine."""
        self.state["current_symbol"] = symbol
        decision = signal.get("decision", "NO TRADE")

        if decision == "NO TRADE":
            self.state["no_trade_count"] += 1
            print(f"  {symbol} → NO TRADE")
            return False

        sig_id = str(uuid.uuid4())[:8]
        signal_record = {
            "id":             sig_id,
            "symbol":         symbol,            # MEXC format stored
            "bitgetSymbol":   mexc_to_bitget(symbol),  # e.g. BTCUSDT
            "timestamp":      int(time.time() * 1000),
            "current_price":  current_price,
            "trend":          signal.get("trend"),
            "pattern":        signal.get("pattern"),
            "decision":       decision,
            "entry":          signal.get("entry"),
            "tp":             signal.get("tp"),
            "sl":             signal.get("sl"),
            "invalidation":   signal.get("invalidation"),
            "reason":         signal.get("reason"),
            "confidence":     signal.get("confidence"),
            "status":         "OPEN",
            "result":         None,
            "pnl_pct":        None,
            "closed_at":      None,
            "closed_price":   None,
            "entry_hit":      False,
            "bitget_order_id": None,
        }

        self.state["signals"].insert(0, signal_record)
        self.state["signals"] = self.state["signals"][:MAX_SIGNALS]
        _save_signals(self.state["signals"])

        # Validate TP/SL direction
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
                    self.state["signals"] = [
                        x for x in self.state["signals"] if x["id"] != sig_id
                    ]
                    _save_signals(self.state["signals"])
                    return False
            except (TypeError, ValueError):
                pass

        self.state["last_signal"]        = signal_record
        self.state["daily_signal_count"] += 1
        self._emit("signal", signal_record)

        print(f"  ✅ {symbol} {decision} @ {current_price} | "
              f"TP={signal.get('tp')} SL={signal.get('sl')} | "
              f"conf={signal.get('confidence')}% "
              f"[{self.state['daily_signal_count']}/{MAX_DAILY_SIGNALS} today]")

        # ── Place real Bitget Demo order ─────────────────────────────
        # Fire-and-forget so it doesn't block the scanner loop
        asyncio.create_task(
            self._place_bitget_order(sig_id, signal_record)
        )

        # Fallback monitor (will stop early if WS closes signal first)
        asyncio.create_task(self._monitor_signal(sig_id))

        return True

    # ------------------------------------------------------------------
    # Place limit order on Bitget Demo
    # ------------------------------------------------------------------
    async def _place_bitget_order(self, sig_id: str, signal: dict):
        """Place a limit order with preset TP/SL on Bitget demo account."""
        if not bitget_client.api_key:
            print(f"  [Bitget] No API key — skipping order for {sig_id}")
            return

        if BITGET_MARGIN_USDT <= 0:
            print(f"  [Bitget] BITGET_MARGIN_USDT=0 — order placement disabled")
            return

        decision   = signal["decision"]
        entry      = signal.get("entry")
        tp         = signal.get("tp")
        sl         = signal.get("sl")
        bitget_sym = signal["bitgetSymbol"]

        if not entry or not tp or not sl:
            print(f"  [Bitget] Missing entry/tp/sl for {sig_id} — skip order")
            return

        try:
            entry_f = float(entry)
            # Calculate size: margin * leverage / entry price
            # Get live balance to be safe
            balance_data = await bitget_client.get_account_balance()
            available    = balance_data.get("available", BITGET_MARGIN_USDT)
            margin       = min(BITGET_MARGIN_USDT, available * 0.95)
            size         = round(margin * BITGET_LEVERAGE / entry_f, 4)

            # Set leverage first
            hold_side = "long" if decision == "LONG" else "short"
            await bitget_client.set_leverage(bitget_sym, BITGET_LEVERAGE, hold_side)

            side = "buy" if decision == "LONG" else "sell"

            result = await bitget_client.place_order(
                symbol      = bitget_sym,
                side        = side,
                trade_side  = "open",
                size        = str(size),
                price       = str(entry_f),
                tp_price    = str(float(tp)),
                sl_price    = str(float(sl)),
                margin_mode = BITGET_MARGIN_MODE,
                leverage    = BITGET_LEVERAGE,
            )

            if result["ok"]:
                order_id = result.get("orderId")
                signal["bitget_order_id"] = order_id
                if order_id:
                    self._order_to_signal[order_id] = sig_id
                _save_signals(self.state["signals"])
                print(f"  ✅ [Bitget] Order placed for {sig_id} "
                      f"({bitget_sym} {side}) | orderId={order_id}")
                self._emit("order_placed", {
                    "sig_id":   sig_id,
                    "symbol":   bitget_sym,
                    "side":     side,
                    "size":     size,
                    "price":    entry_f,
                    "tp":       tp,
                    "sl":       sl,
                    "orderId":  order_id,
                })
            else:
                print(f"  ❌ [Bitget] Order failed for {sig_id}: {result.get('msg')}")
                self._emit("order_error", {
                    "sig_id": sig_id,
                    "symbol": bitget_sym,
                    "msg":    result.get("msg"),
                })

        except Exception as e:
            print(f"  ❌ [Bitget] Exception placing order for {sig_id}: {e}")
            import traceback; traceback.print_exc()

    # ------------------------------------------------------------------
    # Fallback monitor (MEXC price check) — same as original
    # Primary close tracking is via Bitget WS; this is a safety net.
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
        entry_hit    = False

        while time.time() - start < max_duration:
            await asyncio.sleep(10)
            if not self.running:
                break

            signal = self._find_signal(sig_id)
            if not signal:
                break  # Already closed by WS

            if signal.get("status") == "CLOSED":
                break  # WS already handled it

            try:
                ticker = await mexc_client.get_ticker(symbol)
                price  = float(ticker.get("lastPr", ticker.get("last", 0)) or 0)
            except Exception:
                continue

            if price <= 0:
                continue

            # Invalidation check
            if inv_price and inv_price > 0:
                inv_hit = (
                    (direction == "LONG"  and price <= inv_price) or
                    (direction == "SHORT" and price >= inv_price)
                )
                if inv_hit:
                    signal["status"]       = "INVALIDATED"
                    signal["result"]       = "INVALIDATED"
                    signal["closed_at"]    = int(time.time() * 1000)
                    signal["closed_price"] = price
                    _save_closed_signal(signal)
                    self.state["signals"] = [
                        s for s in self.state["signals"] if s["id"] != sig_id
                    ]
                    self.state["daily_signal_count"] = max(
                        0, self.state["daily_signal_count"] - 1)
                    self._emit("signal_invalidated", {
                        "id": sig_id, "symbol": symbol, "price": price,
                        "timestamp": int(time.time() * 1000),
                    })
                    print(f"  ❌ Signal {sig_id} INVALIDATED @ {price}")
                    break

            # Entry gate
            if not entry_hit:
                if entry <= 0:
                    entry_hit = True
                elif direction == "LONG"  and price >= entry:
                    entry_hit = True
                    signal["entry_hit"] = True
                elif direction == "SHORT" and price <= entry:
                    entry_hit = True
                    signal["entry_hit"] = True
                else:
                    continue
                continue

            # TP/SL check
            hit = None
            if direction == "LONG":
                if price >= float(tp):   hit = "TP"
                elif price <= float(sl): hit = "SL"
            elif direction == "SHORT":
                if price <= float(tp):   hit = "TP"
                elif price >= float(sl): hit = "SL"

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

                self.state["trade_count"] += 1
                if hit == "TP":
                    self.state["win_count"] += 1
                else:
                    self.state["loss_count"] += 1
                self.state["total_pnl_pct"] = round(
                    self.state["total_pnl_pct"] + pnl_pct, 4)

                _save_closed_signal(signal)
                self.state["signals"] = [
                    s for s in self.state["signals"] if s["id"] != sig_id
                ]
                self._emit("signal_closed", signal)
                print(f"  Signal {sig_id} closed (fallback monitor): "
                      f"{hit} @ {price} | PnL: {pnl_pct}%")
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
        wins    = self.state["win_count"]
        losses  = self.state["loss_count"]
        closed  = wins + losses
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
        self._order_to_signal.clear()
        _save_signals([])
        _save_daily_state({"date": "", "daily_signal_count": 0, "scanned_symbols": []})


bot_engine = BotEngine()
