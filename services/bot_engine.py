"""
Bot engine - signal generator only (no auto-trade).
Fetches OHLCV from multiple timeframes, runs AI analysis,
emits signals and monitors price to detect TP/SL hit.
"""

import asyncio
import time
import logging
import uuid
from typing import Optional, Callable, Dict, Any, List

from services.bitget_client import bitget
from services.deepseek_ai import deepseek_ai
from utils.indicators import format_ohlcv_text

logger = logging.getLogger(__name__)

TIMEFRAMES = ["3m", "5m", "15m", "30m", "1h", "2h", "4h"]
CANDLE_LIMIT = 60  # candles per TF


class BotEngine:
    def __init__(self):
        self.running = False
        self.config: Dict[str, Any] = {}
        self.state = {
            "status": "IDLE",
            "last_signal": None,
            "last_error": None,
            # Signal history & stats
            "signals": [],       # list of all signals with status
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "no_trade_count": 0,
            "total_pnl_pct": 0.0,
        }
        self._task: Optional[asyncio.Task] = None
        self._listeners: List[Callable] = []
        # Active signal being monitored {id, symbol, direction, entry, tp, sl}
        self._active_signal: Optional[Dict] = None

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
        self.config = config
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
        await bitget.close()
        await deepseek_ai.close()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _loop(self):
        logger.info("Bot signal loop started")
        print("🚀 Signal loop started")

        await asyncio.sleep(2)

        while self.running:
            try:
                await self._cycle()
                interval = int(self.config.get("interval", 60))
                print(f"⏸ Cycle done. Next scan in {interval}s…")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                print("❌ Signal loop cancelled")
                break
            except Exception as e:
                print(f"💥 Loop error: {e}")
                import traceback; traceback.print_exc()
                self.state["last_error"] = str(e)
                self._emit("error", str(e))
                await asyncio.sleep(10)

        self.state["status"] = "IDLE"
        print("🛑 Signal loop ended")

    # ------------------------------------------------------------------
    # One analysis cycle
    # ------------------------------------------------------------------

    async def _cycle(self):
        cfg = self.config
        raw_symbol = cfg.get("symbol", "BTCUSDT")
        symbol = raw_symbol.replace("_UMCBL", "")

        print(f"=== CYCLE: {symbol} ===")
        self._emit("status", f"Fetching data for {symbol}…")

        # 1. Fetch candles for all timeframes
        candles_by_tf: Dict[str, list] = {}
        for tf in TIMEFRAMES:
            try:
                candles = await bitget.get_candles(symbol, tf, CANDLE_LIMIT)
                if candles and len(candles) >= 5:
                    candles_by_tf[tf] = candles
                    print(f"  ✅ {tf}: {len(candles)} candles")
                else:
                    print(f"  ⚠️ {tf}: insufficient ({len(candles) if candles else 0})")
            except Exception as e:
                print(f"  ❌ {tf} fetch error: {e}")

        if not candles_by_tf:
            self._emit("status", "No candle data available")
            return

        # 2. Get current price
        try:
            ticker = await bitget.get_ticker(symbol)
            current_price = float(ticker.get("lastPr", ticker.get("last", 0)))
        except Exception:
            # Fallback: last close from any available TF
            tf_any = next(iter(candles_by_tf.values()))
            current_price = float(tf_any[-1][4])

        print(f"  💰 Current price: {current_price}")

        # 3. AI analysis
        self._emit("status", "Analyzing with AI (void/wick pattern)…")
        try:
            signal = await deepseek_ai.analyze(symbol, candles_by_tf)
        except Exception as e:
            logger.error(f"AI analyze error: {e}")
            self._emit("error", f"AI error: {e}")
            return

        decision = signal.get("decision", "NO TRADE")
        print(f"  🤖 AI decision: {decision} | confidence: {signal.get('confidence')}%")

        # 4. Build signal record
        sig_id = str(uuid.uuid4())[:8]
        signal_record = {
            "id": sig_id,
            "symbol": symbol,
            "timestamp": int(time.time() * 1000),
            "current_price": current_price,
            "trend": signal.get("trend"),
            "pattern": signal.get("pattern"),
            "decision": decision,
            "entry": signal.get("entry"),
            "tp": signal.get("tp"),
            "sl": signal.get("sl"),
            "reason": signal.get("reason"),
            "confidence": signal.get("confidence"),
            "status": "OPEN" if decision in ("LONG", "SHORT") else "NO TRADE",
            "result": None,      # "TP" | "SL" | None
            "pnl_pct": None,
            "closed_at": None,
            "closed_price": None,
        }

        # Prepend (newest first)
        self.state["signals"].insert(0, signal_record)
        # Keep last 200 signals
        self.state["signals"] = self.state["signals"][:200]

        self.state["last_signal"] = signal_record

        if decision == "NO TRADE":
            self.state["no_trade_count"] += 1
            self._emit("signal", signal_record)
            return

        self.state["trade_count"] += 1
        self._emit("signal", signal_record)

        # 5. Monitor this signal for TP/SL
        if self._active_signal is None:
            self._active_signal = signal_record
            asyncio.create_task(self._monitor_signal(sig_id))

    # ------------------------------------------------------------------
    # Signal monitor (polls price until TP or SL hit)
    # ------------------------------------------------------------------

    async def _monitor_signal(self, sig_id: str):
        """Poll live price and mark signal TP or SL when hit."""
        signal = self._find_signal(sig_id)
        if not signal:
            return

        symbol = signal["symbol"]
        direction = signal["decision"]
        entry = signal.get("entry") or signal.get("current_price")
        tp = signal.get("tp")
        sl = signal.get("sl")

        if not tp or not sl:
            self._active_signal = None
            return

        print(f"👀 Monitoring signal {sig_id}: {direction} @ {entry} | TP={tp} SL={sl}")
        self._emit("status", f"Monitoring signal {sig_id}…")

        max_duration = 60 * 60 * 8  # 8 hours max
        start = time.time()

        while time.time() - start < max_duration:
            await asyncio.sleep(5)
            if not self.running:
                break

            try:
                ticker = await bitget.get_ticker(symbol)
                price = float(ticker.get("lastPr", ticker.get("last", 0)))
            except Exception:
                continue

            hit = None
            if direction == "LONG":
                if price >= tp:
                    hit = "TP"
                elif price <= sl:
                    hit = "SL"
            elif direction == "SHORT":
                if price <= tp:
                    hit = "TP"
                elif price >= sl:
                    hit = "SL"

            if hit:
                # Calculate pnl %
                if entry and entry > 0:
                    if direction == "LONG":
                        pnl_pct = round((price - entry) / entry * 100, 4)
                    else:
                        pnl_pct = round((entry - price) / entry * 100, 4)
                else:
                    pnl_pct = 0.0

                # Update signal record
                signal["status"] = "CLOSED"
                signal["result"] = hit
                signal["pnl_pct"] = pnl_pct
                signal["closed_at"] = int(time.time() * 1000)
                signal["closed_price"] = price

                # Update stats
                if hit == "TP":
                    self.state["win_count"] += 1
                else:
                    self.state["loss_count"] += 1
                self.state["total_pnl_pct"] = round(
                    self.state["total_pnl_pct"] + pnl_pct, 4
                )

                print(f"  {'✅' if hit == 'TP' else '❌'} Signal {sig_id} closed: {hit} @ {price} | PnL: {pnl_pct}%")
                self._emit("signal_closed", signal)
                break

        self._active_signal = None

    def _find_signal(self, sig_id: str) -> Optional[Dict]:
        for s in self.state["signals"]:
            if s["id"] == sig_id:
                return s
        return None

    # ------------------------------------------------------------------
    # State / Stats
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        trades = self.state["trade_count"]
        wins = self.state["win_count"]
        losses = self.state["loss_count"]
        winrate = round(wins / trades * 100, 2) if trades > 0 else 0.0
        return {
            **self.state,
            "winrate": winrate,
        }

    def reset_stats(self):
        self.state["signals"] = []
        self.state["trade_count"] = 0
        self.state["win_count"] = 0
        self.state["loss_count"] = 0
        self.state["no_trade_count"] = 0
        self.state["total_pnl_pct"] = 0.0
        self.state["last_signal"] = None
        self.state["last_error"] = None


bot_engine = BotEngine()
