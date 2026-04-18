"""
PATCH: bot_engine.py
====================
Apply these 3 changes to your existing bot_engine.py.

────────────────────────────────────────────────────────────────────────────
CHANGE 1 — Add import at the top (after the existing imports block)
────────────────────────────────────────────────────────────────────────────

Find this line (around line 34):
    from services.mexc_price_feed  import price_feed          # ← WS price feed

Add BELOW it:
    from services.position_ai      import position_ai, MONITOR_INTERVAL

Also add this constant below the other constants (around line 53):
    TIMEFRAMES_MONITOR = ["5m", "15m", "1h", "4h"]   # TFs used for hold/close AI

────────────────────────────────────────────────────────────────────────────
CHANGE 2 — Add shutdown() call for position_ai
────────────────────────────────────────────────────────────────────────────

Find this method (around line 220):
    async def shutdown(self):
        await self.stop()
        await price_feed.stop()
        await mexc_client.close()
        await qwen_ai.close()

Replace with:
    async def shutdown(self):
        await self.stop()
        await price_feed.stop()
        await mexc_client.close()
        await qwen_ai.close()
        await position_ai.close()   # ← ADD THIS LINE

────────────────────────────────────────────────────────────────────────────
CHANGE 3 — Replace entire _monitor_signal() method
────────────────────────────────────────────────────────────────────────────

Replace the entire _monitor_signal method (line ~480 to ~667) with:
"""


# ─────────────────────────────────────────────────────────────────────────────
# Paste this as the new _monitor_signal method inside BotEngine class
# ─────────────────────────────────────────────────────────────────────────────

NEW_MONITOR_SIGNAL = '''
    async def _monitor_signal(self, sig_id: str):
        """
        Monitor one open signal until TP / SL / AI_CLOSE / INVALIDATED / timeout.

        Flow after entry hit (Alpha Arena-style):
          Every MONITOR_INTERVAL_SECONDS → fetch fresh candles → ask position_ai
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
                pnl_pct  = round(
                    (price - entry) / entry * 100 if direction == "LONG"
                    else (entry - price) / entry * 100, 4
                ) if entry > 0 else 0.0
                close_p  = tp_f if hit == "TP" else sl_f
                pnl_usdt = virtual_exchange.apply_result(hit, direction, entry, close_p)

                signal.update({
                    "status":       "CLOSED",
                    "result":       hit,
                    "pnl_pct":      pnl_pct,
                    "pnl_usdt":     pnl_usdt,
                    "closed_at":    int(time.time() * 1000),
                    "closed_price": close_p,
                })
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
            # Only runs after entry is hit and position_ai has tokens
            if (
                entry_hit
                and position_ai.enabled
                and (time.time() - _last_ai_check) >= MONITOR_INTERVAL
            ):
                _last_ai_check = time.time()
                print(f"  🤖 {sig_id} AI hold/close check ({symbol} {direction} @ {entry})…")

                try:
                    # Fetch fresh candles for AI decision
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

                    # Ask AI — sequential retry until HOLD/CLOSE
                    ai_result = await position_ai.decide_with_retry(
                        symbol        = symbol,
                        direction     = direction,
                        entry         = entry,
                        tp            = tp_f,
                        sl            = sl_f,
                        current_price = price,
                        candles_by_tf = candles_by_tf,
                        leverage      = virtual_exchange.leverage,
                        margin_usdt   = virtual_exchange.entry_usdt,
                    )

                    # Store last AI decision in signal (visible on frontend)
                    signal["last_ai_decision"] = ai_result.get("decision")
                    signal["last_ai_reason"]   = ai_result.get("reason")
                    signal["last_ai_at"]       = int(time.time() * 1000)

                    self._emit("signal_ai_update", {
                        "id":       sig_id,
                        "symbol":   symbol,
                        "decision": ai_result.get("decision"),
                        "reason":   ai_result.get("reason"),
                        "timestamp": int(time.time() * 1000),
                    })

                    if ai_result.get("decision") == "CLOSE":
                        # AI decided to close — exit at current market price
                        pnl_pct = round(
                            (price - entry) / entry * 100 if direction == "LONG"
                            else (entry - price) / entry * 100, 4
                        ) if entry > 0 else 0.0

                        # Use TP or SL label for virtual_exchange PnL (determines sign)
                        ve_label = "TP" if pnl_pct >= 0 else "SL"
                        pnl_usdt = virtual_exchange.apply_result(
                            ve_label, direction, entry, price
                        )

                        signal.update({
                            "status":        "CLOSED",
                            "result":        "AI_CLOSE",
                            "pnl_pct":       pnl_pct,
                            "pnl_usdt":      pnl_usdt,
                            "closed_at":     int(time.time() * 1000),
                            "closed_price":  price,
                            "close_reason":  ai_result.get("reason", "AI decided to close"),
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

        # ─── Loop ended — either bot stopped, signal closed, or 8h timeout ───
        if self.running:
            signal = self._find_signal(sig_id)
            if signal and signal.get("status") == "OPEN":
                # ──────────────────────────────────────────────────────────
                # FIX: previously "staying OPEN" with NO active monitor task
                # → signal would never close, slot was permanently occupied.
                # Now: move to INVALIDATED with result=TIMEOUT so the slot
                # is released immediately and frontend shows correct state.
                # ──────────────────────────────────────────────────────────
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
'''
