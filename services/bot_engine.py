"""
Bot engine — multi-symbol scanner (no auto-trade).

Fetches OHLCV from MEXC futures for EVERY active USDT contract,
runs AI analysis one-by-one, emits signals and monitors price for TP/SL.

Signals are persisted to signals.json so they survive restarts and are
visible to ALL users as soon as they open the frontend (global signals).
"""

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from services.mexc_client import mexc_client
from services.deepseek_ai import deepseek_ai
from utils.indicators import format_ohlcv_text

logger = logging.getLogger(__name__)

# Timeframes to request per symbol (mapped to MEXC intervals inside mexc_client)
TIMEFRAMES    = ["5m", "15m", "30m", "1h", "4h"]
CANDLE_LIMIT  = 60   # candles per timeframe

# Where signals are persisted on disk
SIGNALS_FILE  = Path(os.getenv("SIGNALS_FILE", "signals.json"))
MAX_SIGNALS   = 500  # keep last N signals in memory / on disk

# Delay between analysing consecutive symbols (seconds) — respect MEXC rate limits
INTER_SYMBOL_DELAY = float(os.getenv("INTER_SYMBOL_DELAY", "2.0"))


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


class BotEngine:
    def __init__(self):
        self.running  = False
        self.config: Dict[str, Any] = {}
        self.state = {
            "status":         "IDLE",
            "last_signal":    None,
            "last_error":     None,
            "signals":        _load_signals(),   # ← loaded from disk on boot
            "trade_count":    0,
            "win_count":      0,
            "loss_count":     0,
            "no_trade_count": 0,
            "total_pnl_pct":  0.0,
            "current_symbol": None,
            "symbols_scanned": 0,
            "symbols_total":  0,
        }
        # Re-populate counters from persisted signals
        self._rebuild_counters()

        self._task: Optional[asyncio.Task]  = None
        self._listeners: List[Callable]     = []
        self._active_signal: Optional[Dict] = None

    # ------------------------------------------------------------------
    # Rebuild win/loss counters from persisted signals on startup
    # ------------------------------------------------------------------
    def _rebuild_counters(self):
        for s in self.state["signals"]:
            if s.get("status") == "NO TRADE":
                self.state["no_trade_count"] += 1
            elif s.get("decision") in ("LONG", "SHORT"):
                self.state["trade_count"] += 1
                result = s.get("result")
                if result == "TP":
                    self.state["win_count"]  += 1
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
        self._task   = asyncio.create_task(self._loop())
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
    # Main loop
    # ------------------------------------------------------------------
    async def _loop(self):
        logger.info("Bot scanner loop started")
        print("Bot scanner loop started")
        await asyncio.sleep(2)

        while self.running:
            try:
                await self._scan_all_symbols()
                interval = int(self.config.get("interval", 300))
                print(f"Full scan done. Next scan in {interval}s")
                self._emit("status", f"Scan complete. Next in {interval}s")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                print("Scanner loop cancelled")
                break
            except Exception as e:
                print(f"Loop error: {e}")
                import traceback; traceback.print_exc()
                self.state["last_error"] = str(e)
                self._emit("error", str(e))
                await asyncio.sleep(15)

        self.state["status"] = "IDLE"
        print("Scanner loop ended")

    # ------------------------------------------------------------------
    # Scan ALL MEXC USDT futures symbols
    # ------------------------------------------------------------------
    async def _scan_all_symbols(self):
        self._emit("status", "Fetching contract list from MEXC…")
        try:
            contracts = await mexc_client.get_contracts()
        except Exception as e:
            logger.error(f"Failed to fetch contracts: {e}")
            self._emit("error", f"Contract fetch error: {e}")
            return

        if not contracts:
            self._emit("status", "No contracts returned from MEXC")
            return

        # Filter: only active USDT-settled (state==0 already done in client)
        symbols = [c["symbol"] for c in contracts]
        # Optionally honour a whitelist/blacklist from config
        whitelist = self.config.get("symbols")  # None = all
        if whitelist:
            symbols = [s for s in symbols if s in whitelist]

        self.state["symbols_total"]   = len(symbols)
        self.state["symbols_scanned"] = 0
        print(f"Scanning {len(symbols)} MEXC USDT-perp symbols…")

        for symbol in symbols:
            if not self.running:
                break
            await self._cycle(symbol)
            self.state["symbols_scanned"] += 1
            await asyncio.sleep(INTER_SYMBOL_DELAY)

    # ------------------------------------------------------------------
    # One analysis cycle for a single symbol
    # ------------------------------------------------------------------
    async def _cycle(self, symbol: str):
        self.state["current_symbol"] = symbol
        self._emit("status", f"Analysing {symbol}…")
        print(f"--- {symbol} ---")

        # 1. Fetch candles for all timeframes
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

        # 4. Build signal record
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
            "status":        "OPEN" if decision in ("LONG", "SHORT") else "NO TRADE",
            "result":        None,
            "pnl_pct":       None,
            "closed_at":     None,
            "closed_price":  None,
        }

        # Prepend (newest first) and persist
        self.state["signals"].insert(0, signal_record)
        self.state["signals"] = self.state["signals"][:MAX_SIGNALS]
        _save_signals(self.state["signals"])   # global persistence

        self.state["last_signal"] = signal_record

        if decision == "NO TRADE":
            self.state["no_trade_count"] += 1
            self._emit("signal", signal_record)
            return

        self.state["trade_count"] += 1
        self._emit("signal", signal_record)
        print(f"  Signal: {decision} @ {current_price} | TP={signal.get('tp')} SL={signal.get('sl')} | {signal.get('confidence')}%")

        # 5. Launch monitor task (max one monitor per signal)
        asyncio.create_task(self._monitor_signal(sig_id))

    # ------------------------------------------------------------------
    # Monitor a signal until TP / SL is hit (or timeout)
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
                if entry and entry > 0:
                    pnl_pct = round(
                        (price - entry) / entry * 100 if direction == "LONG"
                        else (entry - price) / entry * 100, 4
                    )
                else:
                    pnl_pct = 0.0

                signal["status"]       = "CLOSED"
                signal["result"]       = hit
                signal["pnl_pct"]      = pnl_pct
                signal["closed_at"]    = int(time.time() * 1000)
                signal["closed_price"] = price

                if hit == "TP":
                    self.state["win_count"]  += 1
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
        return {**self.state, "winrate": winrate}

    def reset_stats(self):
        self.state.update({
            "signals":         [],
            "trade_count":     0,
            "win_count":       0,
            "loss_count":      0,
            "no_trade_count":  0,
            "total_pnl_pct":   0.0,
            "last_signal":     None,
            "last_error":      None,
            "symbols_scanned": 0,
        })
        _save_signals([])


bot_engine = BotEngine()
