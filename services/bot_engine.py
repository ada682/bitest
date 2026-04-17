"""
Bot engine — daily signal scanner.

Data sources:
  • Symbol pool  →  MEXC USDT-FUTURES (get_contracts)
  • Candles      →  MEXC (best free kline data)
  • AI analysis  →  DeepSeek
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
from services.deepseek_ai      import deepseek_ai
from services.mexc_price_feed  import price_feed        # ← WS price feed
from utils.indicators          import format_ohlcv_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIMEFRAMES   = ["5m", "15m", "30m", "1h", "4h"]
CANDLE_LIMIT = 150

SIGNALS_FILE = Path(os.getenv("SIGNALS_FILE", "signals.json"))
MAX_SIGNALS  = 500

MAX_DAILY_SIGNALS = int(os.getenv("MAX_DAILY_SYMBOLS", "20"))
REQUIRED_SYMBOLS  = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]   # MEXC format

INTER_SYMBOL_DELAY = float(os.getenv("INTER_SYMBOL_DELAY", "2.0"))
DAILY_STATE_FILE   = Path(os.getenv("DAILY_STATE_FILE", "daily_state.json"))


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
            "total_pnl_usdt":     0.0,
            "current_symbol":     None,
            "symbols_scanned":    0,
            "scan_date":          "",
            "daily_signal_count": 0,
            "daily_scanned":      [],
        }
        self._rebuild_counters()
        self._restore_daily_state()

        self._task:      Optional[asyncio.Task] = None
        self._listeners: List[Callable]         = []

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
                self.state["total_pnl_pct"]  = round(
                    self.state["total_pnl_pct"] + (s.get("pnl_pct") or 0), 4)
                self.state["total_pnl_usdt"] = round(
                    self.state["total_pnl_usdt"] + (s.get("pnl_usdt") or 0), 4)
            elif result == "SL":
                self.state["trade_count"] += 1
                self.state["loss_count"]  += 1
                self.state["total_pnl_pct"]  = round(
                    self.state["total_pnl_pct"] + (s.get("pnl_pct") or 0), 4)
                self.state["total_pnl_usdt"] = round(
                    self.state["total_pnl_usdt"] + (s.get("pnl_usdt") or 0), 4)
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
        # Pastikan WS price feed aktif sebelum loop dimulai
        await price_feed.start()
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
        await price_feed.stop()
        await mexc_client.close()
        await deepseek_ai.close()

    # ------------------------------------------------------------------
    # Main loop — daily rhythm
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
                    msg  = (
                        f"Daily quota reached "
                        f"({self.state['daily_signal_count']}/{MAX_DAILY_SIGNALS}). "
                        f"Next run in {hh}h {mm}m."
                    )
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
                    signals  = await deepseek_ai.analyze_batch(ai_items)

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

        # contracts return "symbol" in MEXC format (BTC_USDT)
        all_symbols = [c["symbol"] for c in contracts if c.get("symbol")]

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
    # Process one AI signal
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

        self.state["last_signal"]        = signal_record
        self.state["daily_signal_count"] += 1
        self._emit("signal", signal_record)

        print(
            f"  ✅ {symbol} {decision} @ {current_price} | "
            f"TP={signal.get('tp')} SL={signal.get('sl')} | "
            f"conf={signal.get('confidence')}% "
            f"[{self.state['daily_signal_count']}/{MAX_DAILY_SIGNALS} today]"
        )

        # Spawn price monitor (tracks entry / TP / SL / invalidation)
        # Subscribe per-ticker WS untuk resolusi 1s pada simbol ini
        price_feed.watch(symbol)
        asyncio.create_task(self._monitor_signal(sig_id))

        return True

    # ------------------------------------------------------------------
    # Price monitor — pakai WS price feed, tanpa REST polling
    # ------------------------------------------------------------------
    async def _monitor_signal(self, sig_id: str):
        signal = self._find_signal(sig_id)
        if not signal:
            return

        symbol    = signal["symbol"]
        direction = signal["decision"]          # "LONG" | "SHORT"
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

        max_duration = 60 * 60 * 8   # 8 hours
        start        = time.time()
        entry_hit    = (entry <= 0)  # treat "no entry level" as already filled
    
        # ── Throttle constants for price_tick broadcasts ──────────────
        PRICE_TICK_INTERVAL = 3   # seconds between price_tick WS broadcasts
        _last_tick_emit: float = start  # initialize with start time

        # ── Deteksi arah pendekatan entry ──────────────────────────────
        _start_price = float(signal.get("current_price") or entry)

        if entry > 0:
            if direction == "LONG":
                _pullback_entry = _start_price > entry
            else:  # SHORT
                _pullback_entry = _start_price < entry
        else:
            _pullback_entry = False

        print(
            f"  🔍 {sig_id} monitor start (WS) | direction={direction} "
            f"entry={entry} start_price={_start_price} "
            f"pullback_mode={_pullback_entry}"
        )

        while time.time() - start < max_duration:
            if not self.running:
                break

        signal = self._find_signal(sig_id)
        if not signal or signal.get("status") == "CLOSED":
            break

            # ── Ambil harga dari WS price cache (non-blocking) ────────
            # Tunggu update berikutnya — max 5s sebelum re-check state
            price = await price_feed.wait_for_price(symbol, timeout=5.0)

            if not price or price <= 0:
                # Fallback ke REST kalau WS belum punya harga simbol ini
                try:
                    ticker = await mexc_client.get_ticker(symbol)
                    price  = float(ticker.get("lastPr", ticker.get("last", 0)) or 0)
                except Exception:
                    continue
                if price <= 0:
                    continue

        # ── Live current_price update (so frontend sees fresh price) ──
            signal["current_price"] = price

        # ── Throttled price_tick broadcast to frontend ─────────────────
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

        # ── Invalidation check (sebelum entry) ────────────────────
            if inv_f and not entry_hit:
                inv_hit = (
                    (direction == "LONG"  and price <= inv_f) or
                    (direction == "SHORT" and price >= inv_f)
                )
                if inv_hit:
                    signal["status"]       = "INVALIDATED"
                    signal["result"]       = "INVALIDATED"
                    signal["closed_at"]    = int(time.time() * 1000)
                    signal["closed_price"] = price
                    signal["pnl_usdt"]     = 0.0
                    signal["pnl_pct"]      = 0.0

                    _save_closed_signal(signal)
                    self.state["signals"] = [
                        s for s in self.state["signals"] if s["id"] != sig_id
                    ]
                    self.state["daily_signal_count"] = max(
                        0, self.state["daily_signal_count"] - 1)
                    self._emit("signal_invalidated", {
                        "id":        sig_id,
                        "symbol":    symbol,
                        "price":     price,
                        "timestamp": int(time.time() * 1000),
                    })
                    self._emit("balance_update", virtual_exchange.get_info())
                    print(f"  ❌ Signal {sig_id} INVALIDATED @ {price}")
                    price_feed.unwatch(symbol)
                    break

        # ── Entry gate ────────────────────────────────────────────
            if not entry_hit:
                if direction == "LONG":
                    if _pullback_entry:
                        touched = price <= entry
                    else:
                        touched = price >= entry
                else:  # SHORT
                    if _pullback_entry:
                        touched = price >= entry
                    else:
                        touched = price <= entry

                if touched:
                    entry_hit = True
                    signal["entry_hit"] = True
                    mode_label = "pullback" if _pullback_entry else "breakout"
                    print(f"  📍 {sig_id} entry HIT ({direction} {mode_label}) @ {price}")
                else:
                    continue   # belum menyentuh entry, tunggu
                continue       # re-check on next tick

        # ── TP / SL check (setelah entry) ─────────────────────────
            hit = None
            if direction == "LONG":
                if price >= tp_f:   hit = "TP"
                elif price <= sl_f: hit = "SL"
            elif direction == "SHORT":
                if price <= tp_f:   hit = "TP"
                elif price >= sl_f: hit = "SL"

            if hit:
                if entry > 0:
                    pnl_pct = round(
                        (price - entry) / entry * 100 if direction == "LONG"
                        else (entry - price) / entry * 100, 4
                    )
                else:
                    pnl_pct = 0.0

                close_p  = tp_f if hit == "TP" else sl_f
                pnl_usdt = virtual_exchange.apply_result(hit, direction, entry, close_p)

                signal["status"]       = "CLOSED"
                signal["result"]       = hit
                signal["pnl_pct"]      = pnl_pct
                signal["pnl_usdt"]     = pnl_usdt
                signal["closed_at"]    = int(time.time() * 1000)
                signal["closed_price"] = close_p

                self.state["trade_count"] += 1
                if hit == "TP":
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

                self._emit("signal_closed", {**signal, "balance": virtual_exchange.balance})
                self._emit("balance_update", virtual_exchange.get_info())
                print(
                    f"  Signal {sig_id} {hit} @ {close_p} | "
                    f"pnl={pnl_pct}% / {pnl_usdt:+.4f} USDT | "
                    f"balance={virtual_exchange.balance} USDT"
                )
                price_feed.unwatch(symbol)
                break

        # Timed out — leave signal open, akan persist on restart
        if self.running:
            signal = self._find_signal(sig_id)
            if signal and signal.get("status") == "OPEN":
                print(f"  ⏰ Signal {sig_id} timed out (8h) — staying OPEN")
                    # Jangan unwatch — signal masih OPEN, feed tetap jaga harga

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
            "balance":            virtual_exchange.balance,
        }

    def reset_stats(self):
        self.state.update({
            "signals":            [],
            "trade_count":        0,
            "win_count":          0,
            "loss_count":         0,
            "no_trade_count":     0,
            "total_pnl_pct":      0.0,
            "total_pnl_usdt":     0.0,
            "last_signal":        None,
            "last_error":         None,
            "symbols_scanned":    0,
            "daily_signal_count": 0,
            "scan_date":          "",
            "daily_scanned":      [],
        })
        virtual_exchange.reset()
        # ── Langsung tulis file kosong, JANGAN pakai _save_signals([])
        # karena _save_signals() akan merge dengan existing data → file tidak terhapus
        try:
            SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SIGNALS_FILE.write_text(json.dumps([], indent=2))
            print(f"🗑️  Signals file cleared: {SIGNALS_FILE.absolute()}")
        except Exception as e:
            logger.warning(f"Could not clear signals file: {e}")
        _save_daily_state({"date": "", "daily_signal_count": 0, "scanned_symbols": []})


bot_engine = BotEngine()
