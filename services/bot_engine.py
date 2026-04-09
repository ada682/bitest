"""
Main bot engine - manages the scalping trading loop.
"""

import asyncio
import json
import time
import logging
from typing import Optional, Callable, Dict, Any

from services.bitget_client import bitget
from services.deepseek_ai import deepseek_ai
from services.chart_generator import generate_chart_image
from utils.indicators import compute_all, format_ohlcv_text, calculate_position_size

logger = logging.getLogger(__name__)


class BotEngine:
    def __init__(self):
        self.running = False
        self.config: Dict[str, Any] = {}
        self.state = {
            "status": "IDLE",
            "open_position": None,
            "last_signal": None,
            "last_error": None,
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "total_pnl": 0.0,
        }
        self._task: Optional[asyncio.Task] = None
        self._listeners: list[Callable] = []

    def add_listener(self, fn: Callable):
        self._listeners.append(fn)

    def _emit(self, event: str, data: Any):
        for fn in self._listeners:
            try:
                fn(event, data)
            except Exception:
                pass

    async def start(self, config: dict):
        print("🔥 BOT START called")
        if self.running:
            return {"ok": False, "reason": "Bot already running"}
    
        self.config = config
        self.running = True
        self.state["status"] = "RUNNING"
    
        print(f"✅ Bot set to RUNNING, creating task...")
        self._task = asyncio.create_task(self._loop())
        print(f"✅ Task created: {self._task}")
    
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

    async def _loop(self):
        print("🚀 BOT LOOP STARTED - this should appear in logs!")
        logger.info("Bot loop started")
    
        await asyncio.sleep(2)
    
        while self.running:
            try:
                print("🔄 Bot cycle beginning...")
                await self._cycle()
                print("⏸ Cycle finished, waiting 5 seconds...")
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                print("❌ Bot loop cancelled")
                break
            except Exception as e:
                print(f"💥 Bot loop error: {e}")
                import traceback
                traceback.print_exc()
                self.state["last_error"] = str(e)
                self._emit("error", str(e))
                await asyncio.sleep(5)
    
        print("🛑 Bot loop ended")
        self.state["status"] = "IDLE"

    async def _cycle(self):
        try:
            print("=== CYCLE START ===")
            cfg = self.config
            raw_symbol = cfg.get("symbol", "BTCUSDT")
            symbol = raw_symbol.replace('_UMCBL', '')
        
            print(f"🎯 Symbol: {symbol}")
        
            margin_coin = "USDT"
            leverage = str(cfg.get("leverage", "10"))
            mode = cfg.get("mode", "MANUAL")
            manual_margin = cfg.get("manual_margin", None)
            tp_pct = cfg.get("tp_pct", 0.004)
            sl_pct = cfg.get("sl_pct", 0.002)

            # 1. Fetch candle data
            print(f"📊 Fetching candles for {symbol}...")
            candles_1m = await bitget.get_candles(symbol, "1m", 100)
            print(f"✅ Received {len(candles_1m)} candles for 1m")
        
            candles_3m = await bitget.get_candles(symbol, "3m", 100)
            print(f"✅ Received {len(candles_3m)} candles for 3m")

            if not candles_1m or len(candles_1m) < 30:
                print(f"❌ Insufficient candle data: {len(candles_1m)} candles (need 30)")
                self._emit("status", f"Insufficient candle data: {len(candles_1m)}/30")
                await asyncio.sleep(10)
                return

            # 2. Generate chart image
            print("📈 Generating chart image...")
            chart_b64 = generate_chart_image(candles_1m, symbol.replace("USDT", "/USDT"), "1m")
            print(f"✅ Chart generated: {chart_b64 is not None} (length: {len(chart_b64) if chart_b64 else 0})")

            # 3. Compute indicators
            print("📐 Computing indicators...")
            indicators_1m = compute_all(candles_1m)
            ohlcv_text = f"=== 1m Candles ===\n{format_ohlcv_text(candles_1m, 50)}\n\n=== 3m Candles ===\n{format_ohlcv_text(candles_3m, 30)}"
            print(f"✅ Indicators computed. Current price: {indicators_1m.get('current_price')}")

            # 4. AI analysis
            print("🤖 Sending to AI for analysis...")
            self._emit("status", "Analyzing with DeepSeek AI...")
        
            decision = await deepseek_ai.analyze(ohlcv_text, indicators_1m, chart_b64)
        
            print(f"✅ AI Response: decision={decision.get('decision')}, confidence={decision.get('confidence')}")

            self.state["last_signal"] = {
                "symbol": symbol,
                "decision": decision.get("decision"),
                "entry": decision.get("entry"),
                "tp": decision.get("tp"),
                "sl": decision.get("sl"),
                "confidence": decision.get("confidence"),
                "reason": decision.get("reason"),
                "timestamp": int(time.time() * 1000),
            }
            self._emit("signal", self.state["last_signal"])

            # 5. Execute trade if signal is strong
            trade_decision = decision.get("decision")
            confidence = decision.get("confidence", 0)

            print(f"📊 Checking trade conditions: decision={trade_decision}, confidence={confidence} (need >= 60)")

            # Check if there's already an open position
            if self.state["open_position"] is not None:
                print(f"⚠️ Already have open position, skipping new trade")
                self._emit("status", f"Already have open position, waiting...")
                await asyncio.sleep(5)
                return

            # Execute trade for LONG/SHORT with confidence >= 60
            if trade_decision in ("LONG", "SHORT") and confidence >= 60:
                print(f"🎯 Executing {trade_decision} trade with {confidence}% confidence")
                await self._execute_trade(
                    symbol, margin_coin, leverage, mode, manual_margin,
                    trade_decision, decision, tp_pct, sl_pct
                )
                await self._monitor_position(symbol)
                await asyncio.sleep(3)
            else:
                print(f"⏸ No trade. Decision: {trade_decision}, Confidence: {confidence}% (need >=60)")
                self._emit("status", f"No trade. Decision: {trade_decision}, Confidence: {confidence}%")
                await asyncio.sleep(15)
            
        except Exception as e:
            print(f"💥 CYCLE ERROR: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def _execute_trade(self, symbol, margin_coin, leverage, mode, manual_margin,
                              direction, decision, tp_pct, sl_pct):
        try:
            print(f"🔧 EXECUTING TRADE: {direction} on {symbol}")
            
            # Set position mode
            await bitget.set_position_mode(symbol, margin_coin)

            # Set leverage for both sides
            await bitget.set_leverage(symbol, leverage, margin_coin, "long")
            await bitget.set_leverage(symbol, leverage, margin_coin, "short")

            # Get account balance
            account = await bitget.get_futures_account(symbol, margin_coin)
            print(f"💰 Account response: {account}")
            
            # Try different possible field names for available balance
            balance = 0
            if "available" in account:
                balance = float(account.get("available", 0))
            elif "availableMargin" in account:
                balance = float(account.get("availableMargin", 0))
            elif "equity" in account:
                balance = float(account.get("equity", 0)) * 0.9  # Use 90% of equity
            
            lev = float(leverage)
            
            # Get current price if not in decision
            price = float(decision.get("entry", 0))
            if price == 0:
                ticker = await bitget.get_ticker(symbol)
                price = float(ticker.get("lastPr", ticker.get("last", 0)))
                print(f"💰 Using live price: {price}")

            print(f"💰 Balance: {balance}, Leverage: {lev}, Price: {price}")

            if balance <= 0 or price <= 0:
                self._emit("error", f"Cannot execute: balance={balance}, price={price}")
                print(f"❌ Invalid balance or price: balance={balance}, price={price}")
                return

            # Determine size
            volume_place = int(self.config.get("volume_place", 3))
            size = calculate_position_size(balance, lev, price, mode, manual_margin, volume_place)
            print(f"📊 Position size: {size}")

            # Map direction to order sides
            if direction == "LONG":
                side_open = "open_long"
                side_close = "close_long"
                tp_price = str(round(price * (1 + tp_pct), 6))
                sl_price = str(round(price * (1 - sl_pct), 6))
            elif direction == "SHORT":
                side_open = "open_short"
                side_close = "close_short"
                tp_price = str(round(price * (1 - tp_pct), 6))
                sl_price = str(round(price * (1 + sl_pct), 6))
            else:
                print(f"❌ Unknown direction: {direction}")
                return

            print(f"📈 TP: {tp_price}, SL: {sl_price}")

            # Place main order
            self._emit("status", f"Placing {direction} order, size={size}...")
            print(f"🚀 Placing order: {side_open}, size={size}")
            
            order_resp = await bitget.place_order(symbol, margin_coin, size, side_open)
            print(f"📦 Order response: {order_resp}")
            
            logger.info(f"Order response: {order_resp}")

            # Check if order was successful
            if order_resp.get("code") != "00000":
                print(f"❌ Order failed: {order_resp.get('msg')}")
                self._emit("error", f"Order failed: {order_resp.get('msg')}")
                return

            await asyncio.sleep(1)

            # Set TP
            print(f"🎯 Setting TP: {tp_price}")
            tp_resp = await bitget.place_plan(symbol, margin_coin, size, side_close, tp_price, "profit_plan")
            print(f"📦 TP response: {tp_resp}")
            
            # Set SL
            print(f"🛑 Setting SL: {sl_price}")
            sl_resp = await bitget.place_plan(symbol, margin_coin, size, side_close, sl_price, "loss_plan")
            print(f"📦 SL response: {sl_resp}")

            self.state["open_position"] = {
                "symbol": symbol,
                "direction": direction,
                "entry": price,
                "tp": float(tp_price),
                "sl": float(sl_price),
                "size": size,
                "timestamp": int(time.time() * 1000),
            }
            self.state["trade_count"] += 1
            self._emit("position_open", self.state["open_position"])
            print(f"✅ Position opened successfully!")

        except Exception as e:
            logger.error(f"Trade execution error: {e}")
            print(f"❌ Trade execution error: {e}")
            import traceback
            traceback.print_exc()
            self._emit("error", f"Trade error: {str(e)}")

    async def _monitor_position(self, symbol: str):
        """Poll position until closed."""
        self._emit("status", "Monitoring open position...")
        max_wait = 300  # 5 min max
        start = time.time()

        while time.time() - start < max_wait and self.state["open_position"] is not None:
            await asyncio.sleep(3)
            try:
                positions = await bitget.get_positions()
                open_pos = [p for p in positions if p.get("symbol") == symbol and float(p.get("total", 0)) > 0]

                if not open_pos:
                    # Position closed
                    pos_data = self.state.get("open_position", {})
                    # Calculate PnL from closed position if available
                    pnl = 0.0
                    # Try to get actual PnL from position history
                    for pos in positions:
                        if pos.get("symbol") == symbol and float(pos.get("total", 0)) == 0:
                            pnl = float(pos.get("unrealizedPL", 0))
                            break
                    
                    self.state["total_pnl"] += pnl
                    if pnl > 0:
                        self.state["win_count"] += 1
                    elif pnl < 0:
                        self.state["loss_count"] += 1
                    
                    self.state["open_position"] = None
                    self._emit("position_close", {"symbol": symbol, "pnl": pnl})
                    print(f"✅ Position closed! PnL: {pnl}")
                    return
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                print(f"⚠️ Monitor error: {e}")

        # Force check after timeout
        if self.state["open_position"] is not None:
            print(f"⚠️ Position monitor timeout, forcing close check")
            self.state["open_position"] = None

    def get_state(self) -> dict:
        return {**self.state}
