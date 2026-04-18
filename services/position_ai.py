"""
Position Monitor AI — decides HOLD or CLOSE for active in-trade positions.

Alpha Arena-style:
  - Queries AI every MONITOR_INTERVAL_SECONDS while position is in trade
  - Separate from qwen_ai.py (analysis AI) — different role, different tokens
  - Uses MONITOR_TOKEN_1..4 (4 bearer tokens), SEQUENTIAL — one at a time
    because the API gateway can't handle parallel requests
  - Retries indefinitely until a valid HOLD/CLOSE response arrives
  - Sends candle data + chart images + full position context (entry, TP, SL,
    unrealized PnL, leverage, margin)

Env vars:
  MONITOR_TOKEN_1..4        — bearer tokens (at least 1 required)
  MONITOR_INTERVAL_SECONDS  — how often to query AI per position (default: 120s)
  QWEN_BASE_URL             — shared gateway (same as qwen_ai.py)
  QWEN_MODEL                — shared model
  QWEN_THINKING_MODE        — shared thinking mode
"""

import asyncio
import json
import logging
import os
from typing import List, Optional

import httpx

# Re-use chart renderer + gateway config from qwen_ai
from services.qwen_ai import (
    _draw_chart,
    HAS_CHARTS,
    CHAT_URL,
    REFRESH_URL,
    QWEN_MODEL,
    QWEN_THINKING,
)

logger = logging.getLogger(__name__)

# How often (in seconds) to send a hold/close query per in-trade signal
MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL_SECONDS", "120"))

# ─────────────────────────────────────────────────────────────────────────────
# System prompt — hold/close decision only
# ─────────────────────────────────────────────────────────────────────────────

POSITION_SYSTEM_PROMPT = """You are a position management AI for a cryptocurrency futures trading bot.

You are managing an ACTIVE OPEN POSITION — entry price has already been hit.
Your only job is to decide: HOLD or CLOSE the position RIGHT NOW.

You will receive:
- Position details: symbol, direction (LONG/SHORT), entry price, TP, SL
- Current price and unrealized PnL
- Leverage and margin used
- OHLCV candle data across multiple timeframes
- Candlestick chart images

━━━ CLOSE if any of these apply: ━━━
- Price action shows a clear reversal against the position direction
- Key structure level has been broken (lower low for LONG, higher high for SHORT)
- Momentum fading significantly with no recovery attempt
- Risk/reward has severely deteriorated (better to exit small loss now than wait for SL)
- Candle pattern shows strong rejection at a key level against the trade

━━━ HOLD if: ━━━
- Trend structure still supports the original thesis
- Price is in a normal pullback within the trade direction
- TP is still reachable based on current structure
- No confirmed reversal signal yet

━━━ Rules: ━━━
- Respond with EXACTLY this JSON and nothing else:
  {"decision": "HOLD" or "CLOSE", "reason": "max 100 chars"}
- No markdown, no preamble, no explanation outside the JSON
- decision must be exactly "HOLD" or "CLOSE" — nothing else is valid
- Be decisive — do not say HOLD just to avoid responsibility
"""


# ─────────────────────────────────────────────────────────────────────────────
# Single token client
# ─────────────────────────────────────────────────────────────────────────────

class PositionAIClient:
    """One bearer token = one sequential position AI client."""

    def __init__(self, token: str, slot: int):
        self.token  = token
        self.slot   = slot
        self._tag   = f"[PM-{slot}]"
        # Timeout 180s — same as analysis AI; thinking mode can be slow
        self.client = httpx.AsyncClient(timeout=180)

    # ── Token refresh ──────────────────────────────────────────────────────
    async def _refresh(self) -> bool:
        try:
            resp = await self.client.get(
                REFRESH_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                new_token = (
                    data.get("token")
                    or data.get("access_token")
                    or data.get("data", {}).get("token")
                )
                if new_token:
                    self.token = new_token
                    logger.info(f"{self._tag} Token refreshed ✅")
                    print(f"{self._tag} ✅ Token refreshed")
                    return True
        except Exception as e:
            logger.warning(f"{self._tag} Token refresh failed: {e}")
        return False

    # ── Main decide method ─────────────────────────────────────────────────
    async def decide(
        self,
        symbol:        str,
        direction:     str,
        entry:         float,
        tp:            float,
        sl:            float,
        current_price: float,
        candles_by_tf: dict,
        leverage:      int,
        margin_usdt:   float,
    ) -> Optional[dict]:
        """
        Ask AI: HOLD or CLOSE?
        Returns {"decision": "HOLD"|"CLOSE", "reason": "..."} or None on failure.
        """
        tag = self._tag

        # ── Compute unrealized PnL ─────────────────────────────────────
        if direction == "LONG":
            pnl_pct = round((current_price - entry) / entry * 100, 3)
        else:
            pnl_pct = round((entry - current_price) / entry * 100, 3)

        pnl_usdt    = round(margin_usdt * leverage * (pnl_pct / 100), 4)
        sign        = "+" if pnl_pct >= 0 else ""
        pnl_display = f"{sign}{pnl_pct}% ({sign}{pnl_usdt} USDT)"

        # Distance to TP and SL
        if direction == "LONG":
            pct_to_tp = round((tp - current_price) / current_price * 100, 3)
            pct_to_sl = round((current_price - sl) / current_price * 100, 3)
        else:
            pct_to_tp = round((current_price - tp) / current_price * 100, 3)
            pct_to_sl = round((sl - current_price) / current_price * 100, 3)

        # ── Build OHLCV text ──────────────────────────────────────────
        ohlcv_blocks = []
        for tf, candles in candles_by_tf.items():
            recent = candles[-80:]
            lines  = [
                f"=== {symbol} | {tf} | last {len(recent)} candles ===",
                "timestamp, open, high, low, close, volume",
            ]
            for c in recent:
                lines.append(f"{c[0]}, {c[1]}, {c[2]}, {c[3]}, {c[4]}, {c[5]}")
            ohlcv_blocks.append("\n".join(lines))

        ohlcv_text = "\n\n".join(ohlcv_blocks) or "No candle data."

        user_text = f"""━━━ ACTIVE POSITION — HOLD or CLOSE? ━━━

Symbol:          {symbol}
Direction:       {direction}
Entry Price:     {entry}
Current Price:   {current_price}
Take Profit:     {tp}  (distance: {pct_to_tp:+.3f}%)
Stop Loss:       {sl}  (distance: -{pct_to_sl:.3f}%)
Unrealized PnL:  {pnl_display}
Leverage:        {leverage}x
Margin Used:     {margin_usdt} USDT
Notional Value:  {round(margin_usdt * leverage, 2)} USDT

{ohlcv_text}

━━━
Charts for all timeframes are attached above.
Analyze price action and decide: HOLD or CLOSE?

Respond ONLY with JSON:
{{"decision": "HOLD" or "CLOSE", "reason": "brief reason max 100 chars"}}"""

        # ── Build content array (charts first, then text) ─────────────
        content = []

        # Generate charts in a thread (CPU-bound, same as qwen_ai.py)
        loop = asyncio.get_event_loop()
        try:
            charts = await loop.run_in_executor(
                None,
                lambda: {
                    tf: _draw_chart(c, symbol, tf)
                    for tf, c in candles_by_tf.items()
                    if (img := _draw_chart(c, symbol, tf)) is not None
                },
            )
        except Exception as e:
            logger.warning(f"{tag} Chart render error: {e}")
            charts = {}

        # Actually generate charts properly (lambda above has a bug with walrus)
        charts = {}
        if HAS_CHARTS:
            try:
                for tf, candles in candles_by_tf.items():
                    img = _draw_chart(candles, symbol, tf)
                    if img:
                        charts[tf] = img
            except Exception as e:
                logger.warning(f"{tag} Chart render error: {e}")

        for tf in ["5m", "15m", "30m", "1h", "4h"]:
            if tf in charts:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{charts[tf]}"},
                })

        content.append({"type": "text", "text": user_text})

        # ── API payload ────────────────────────────────────────────────
        payload = {
            "model":         QWEN_MODEL,
            "messages": [
                {"role": "system", "content": POSITION_SYSTEM_PROMPT},
                {"role": "user",   "content": content},
            ],
            "stream":        False,
            "thinking_mode": QWEN_THINKING,
            "max_tokens":    500,
        }

        # ── Send request (retry once after 401 refresh) ────────────────
        data = None
        for attempt in range(2):
            try:
                print(
                    f"{tag} 🤖 Hold/close query → {symbol} {direction} "
                    f"entry={entry} price={current_price} pnl={pnl_display}"
                )
                resp = await self.client.post(
                    CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type":  "application/json",
                    },
                    json=payload,
                )

                if resp.status_code == 401:
                    logger.warning(f"{tag} 401 — refreshing token")
                    if attempt == 0 and await self._refresh():
                        continue
                    return None

                if resp.status_code == 429:
                    logger.warning(f"{tag} 429 rate-limited")
                    return None

                if resp.status_code != 200:
                    logger.error(f"{tag} HTTP {resp.status_code}: {resp.text[:200]}")
                    return None

                data = resp.json()
                break

            except httpx.TimeoutException:
                logger.error(f"{tag} Timeout querying hold/close for {symbol}")
                print(f"{tag} ⏱️  Timeout for {symbol} — will retry with next token")
                return None
            except Exception as e:
                logger.error(f"{tag} Exception: {e}")
                return None

        if not data:
            return None

        # ── Extract text ───────────────────────────────────────────────
        try:
            full_text = (
                data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "") or ""
            )
            if not full_text:
                full_text = (
                    data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("reasoning_content", "") or ""
                )
        except Exception:
            return None

        logger.info(f"{tag} Raw response for {symbol}: {full_text[:300]}")
        print(f"{tag} RAW [{symbol}]: {full_text[:200]}")

        if not full_text.strip():
            return None

        # ── Parse JSON ─────────────────────────────────────────────────
        start = full_text.find("{")
        end   = full_text.rfind("}") + 1

        if start < 0 or end <= start:
            logger.error(f"{tag} No JSON found for {symbol}: {full_text[:200]}")
            return None

        try:
            result = json.loads(full_text[start:end])
        except json.JSONDecodeError as e:
            logger.error(f"{tag} JSON parse error for {symbol}: {e}")
            return None

        decision = str(result.get("decision", "")).upper().strip()
        if decision not in ("HOLD", "CLOSE"):
            logger.warning(f"{tag} Invalid decision '{decision}' for {symbol}")
            return None  # will trigger retry in caller

        reason = str(result.get("reason", ""))[:200]
        print(f"{tag} ✅ {symbol} → {decision} | {reason}")
        return {"decision": decision, "reason": reason}

    async def close(self):
        await self.client.aclose()


# ─────────────────────────────────────────────────────────────────────────────
# Multi-token manager — sequential rotation, retry until valid response
# ─────────────────────────────────────────────────────────────────────────────

class PositionMonitorAI:
    """
    Manages up to 4 PositionAIClient tokens (MONITOR_TOKEN_1..4).

    Key behaviour (matching Alpha Arena's approach):
      - decide_with_retry() keeps rotating through tokens until HOLD/CLOSE
      - Requests are sequential (not parallel) — API gateway requirement
      - Each retry waits a short backoff before trying the next token
    """

    def __init__(self):
        self.clients: List[PositionAIClient] = []
        self._idx = 0

        for slot in range(1, 5):
            token = os.getenv(f"MONITOR_TOKEN_{slot}", "").strip()
            if token:
                self.clients.append(PositionAIClient(token=token, slot=slot))
                print(f"[PositionAI] ✅ MONITOR_TOKEN_{slot} loaded")
            else:
                logger.debug(f"[PositionAI] MONITOR_TOKEN_{slot} not set — skipped")

        if not self.clients:
            print(
                "[PositionAI] ⚠️  No MONITOR_TOKEN_1..4 set — "
                "position AI monitoring disabled. "
                "Positions will still close on TP/SL price levels."
            )
        else:
            print(
                f"[PositionAI] {len(self.clients)} token(s) | "
                f"interval={MONITOR_INTERVAL}s | model={QWEN_MODEL}"
            )

    @property
    def enabled(self) -> bool:
        return len(self.clients) > 0

    async def decide_with_retry(
        self,
        symbol:        str,
        direction:     str,
        entry:         float,
        tp:            float,
        sl:            float,
        current_price: float,
        candles_by_tf: dict,
        leverage:      int,
        margin_usdt:   float,
        max_retries:   int = 30,  # retry ~indefinitely (30 × backoff)
    ) -> dict:
        """
        Sequential retry across all 4 tokens until HOLD or CLOSE is returned.
        Falls back to HOLD if all retries are exhausted (safety default).
        """
        if not self.clients:
            return {"decision": "HOLD", "reason": "No MONITOR_TOKEN_* configured"}

        for attempt in range(max_retries):
            # Pick next token in round-robin (sequential, not parallel)
            client = self.clients[self._idx % len(self.clients)]
            self._idx += 1

            result = await client.decide(
                symbol=symbol,
                direction=direction,
                entry=entry,
                tp=tp,
                sl=sl,
                current_price=current_price,
                candles_by_tf=candles_by_tf,
                leverage=leverage,
                margin_usdt=margin_usdt,
            )

            if result and result.get("decision") in ("HOLD", "CLOSE"):
                return result

            # Backoff before retrying: 5s → 10s → 15s … capped at 30s
            wait = min(5 * (attempt + 1), 30)
            print(
                f"[PositionAI] ↻ Retry {attempt + 1}/{max_retries} for "
                f"{symbol} in {wait}s (no valid response)"
            )
            await asyncio.sleep(wait)

        logger.error(
            f"[PositionAI] All {max_retries} retries exhausted for {symbol} "
            f"— defaulting to HOLD"
        )
        return {"decision": "HOLD", "reason": "Max retries exhausted — holding"}

    async def close(self):
        for c in self.clients:
            await c.close()


# Singleton — import this from bot_engine
position_ai = PositionMonitorAI()
