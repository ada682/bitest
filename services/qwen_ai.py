"""
Qwen AI Client — drop-in replacement for deepseek_ai.py

Features:
  • Up to 5 bearer tokens (QWEN_TOKEN_1 .. QWEN_TOKEN_5) — round-robin + failover
  • Thinking mode ("Thinking") — deep step-by-step reasoning
  • Vision — sends candlestick chart PNG per timeframe alongside OHLCV text
  • Charts generated server-side with matplotlib (non-interactive Agg backend)
  • Auto token refresh via GET /v1/refresh on 401

Railway env vars:
  QWEN_TOKEN_1 .. QWEN_TOKEN_5  ← bearer tokens from chat.qwen.ai (at least 1)
  QWEN_BASE_URL                 ← default: https://qwen-web-gateway.onrender.com
  QWEN_MODEL                    ← default: qwen3.6-plus
  QWEN_THINKING_MODE            ← default: Thinking  (Auto | Thinking | Fast)

Token expiry & refresh:
  Tokens are web-session cookies, NOT credit-based quotas — they don't "run out"
  on a schedule.  They expire when the browser session expires (~24-48h idle).
  This client calls GET /v1/refresh automatically on every 401, so short-lived
  expiries are handled without manual intervention.  For long-term reliability,
  keep 5 fresh tokens and rotate via QWEN_TOKEN_1..5.
"""

import asyncio
import base64
import io
import json
import logging
import os
from typing import Dict, List, Optional

import httpx

from services.ai_lock import ai_lock   # ← FIX: was missing, caused NameError on ai_lock()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (Railway env vars)
# ---------------------------------------------------------------------------
_GATEWAY      = os.getenv("QWEN_BASE_URL", "https://qwen-web-gateway.onrender.com")
QWEN_MODEL    = os.getenv("QWEN_MODEL",    "qwen3.6-plus")
QWEN_THINKING = os.getenv("QWEN_THINKING_MODE", "Thinking")   # Auto | Thinking | Fast

CHAT_URL    = f"{_GATEWAY}/v1/openai/chat/completions"
REFRESH_URL = f"{_GATEWAY}/v1/refresh"

# ---------------------------------------------------------------------------
# Chart generation  (matplotlib — non-interactive Agg backend)
# ---------------------------------------------------------------------------
try:
    import matplotlib
    matplotlib.use("Agg")           # must be set BEFORE importing pyplot
    import matplotlib.pyplot as plt
    HAS_CHARTS = True
    logger.info("matplotlib loaded — candlestick charts enabled")
    print("📊 qwen_ai: matplotlib OK — charts will be sent with each analysis")
except ImportError:
    HAS_CHARTS = False
    logger.warning("matplotlib not installed — falling back to text-only mode")
    print("⚠️  qwen_ai: matplotlib not found — text-only mode (pip install matplotlib)")


def _draw_chart(candles: list, symbol: str, tf: str) -> Optional[str]:
    """
    Render a dark-theme OHLCV candlestick + volume chart.
    Returns base64-encoded PNG string, or None on any error.
    """
    if not HAS_CHARTS or not candles:
        return None

    data = candles[-150:]   # matches CANDLE_LIMIT
    n    = len(data)

    try:
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(13, 7),
            gridspec_kw={"height_ratios": [3, 1]},
            facecolor="#0d1117",
        )
        ax1.set_facecolor("#0d1117")
        ax2.set_facecolor("#0d1117")

        for i, c in enumerate(data):
            try:
                o, h, l, close = float(c[1]), float(c[2]), float(c[3]), float(c[4])
                vol = float(c[5]) if len(c) > 5 else 0.0
            except (IndexError, ValueError, TypeError):
                continue

            bull  = close >= o
            color = "#26a69a" if bull else "#ef5350"

            # wick
            ax1.plot([i, i], [l, h], color=color, linewidth=0.6, zorder=1)

            # body — guarantee a minimum visible height
            body_y = min(o, close)
            body_h = max(abs(close - o), (h - l) * 0.004)
            ax1.add_patch(
                plt.Rectangle(
                    (i - 0.38, body_y), 0.76, body_h,
                    color=color, linewidth=0, zorder=2,
                )
            )

            # volume
            ax2.bar(i, vol, color=color, alpha=0.72, width=0.8)

        # ── styling ──────────────────────────────────────────────────
        ax1.set_title(
            f"{symbol}  ·  {tf}  ·  {n} candles",
            color="#e0e0e0", fontsize=10, pad=6,
        )
        ax1.set_xlim(-1, n)
        ax2.set_xlim(-1, n)
        ax1.set_xticks([])
        ax2.set_xlabel("candle index", color="#444", fontsize=7)

        for ax in (ax1, ax2):
            ax.tick_params(colors="#666", labelsize=6.5)
            for spine in ax.spines.values():
                spine.set_edgecolor("#2a2a2a")
            ax.yaxis.set_tick_params(labelcolor="#aaa")

        plt.tight_layout(pad=0.4)

        buf = io.BytesIO()
        plt.savefig(
            buf, format="png", dpi=75,
            bbox_inches="tight", facecolor="#0d1117",
        )
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode()
        plt.close(fig)
        return img_b64

    except Exception as e:
        logger.warning(f"Chart render failed {symbol}/{tf}: {e}")
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def _generate_all_charts(candles_by_tf: dict, symbol: str) -> Dict[str, str]:
    """Render charts for every timeframe available. Returns {tf: base64_png}."""
    result = {}
    for tf, candles in candles_by_tf.items():
        img = _draw_chart(candles, symbol, tf)
        if img:
            result[tf] = img
    return result


# ---------------------------------------------------------------------------
# System prompt  (identical strategy rules as the original DeepSeek version)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an AI trained to mimic a specific trading strategy based on example data.

Your job:
- Learn from the examples
- Apply the SAME behavior to new data

Focus on:
- Trend structure (market direction)
- Wick behavior (rejection / inefficiency)
- Void 
- Candle relationships
- Multi-timeframe context (HTF vs LTF)

----------------------------------------
STRICT TREND RULE:
- UP → ONLY LONG (Higher Low → Higher High)
- DOWN → ONLY SHORT (Lower High → Lower Low)
- Do NOT counter-trade by default

----------------------------------------
WICK + VOID DIRECTION RULE (CRITICAL):

- UP trend:
  → use UPPER WICK voids (see some candle before)
  → ignore lower wick voids

- DOWN trend:
  → use lower WICK voids (see some candle before)
  → ignore upper wick voids

IMPORTANT:
- The void must be in the direction of a RETRACEMENT, not continuation

Logic:
- LONG = buy lower → void must be BELOW current price
- SHORT = sell higher → void must be ABOVE current price

- NEVER choose a void that would require chasing price

----------------------------------------
ENTRY DISTANCE RULE:
- Entry MUST be placed at a clear void
- Entry must NOT be near current price without structure
- If price is already near the level → NO TRADE
- Entry should feel like a LIMIT order (far from price), not a market entry

----------------------------------------
NO TRADE RULE:
- No clear void → NO TRADE
- Bad structure → NO TRADE
- Entry too close to price → NO TRADE
- If very low volume → NO TRADE

----------------------------------------
REVERSAL RULE (ADVANCED):
Reversal trades are allowed ONLY if ALL conditions are met:

1. There is a clear void (4H / 2H — if found on a higher timeframe, check further back
   on a lower timeframe; if a pattern similar to the training data exists, verify the
   previous high/low from the higher timeframe)
2. The level comes from past price action (look-back structure)
3. The level has NOT been revisited

If ALL valid → Counter-trend entry is allowed
If NOT       → Stay with trend or NO TRADE

----------------------------------------
PRIORITY RULE:
1. Primary → Trend-following setups
2. Secondary → Reversal (ONLY with strong HTF confirmation)

----------------------------------------
ANTI-FAKE RULE:
- Do NOT assume reversal randomly
- Do NOT force trades
- If unsure → NO TRADE

----------------------------------------
TRAINING DATA:

[
  {
    "input": "the trend is going down; found this on the 4h timeframe: o:0.003942 h:0.003979 l:0.003791 c:0.003843 v:246.84M; +1 o:0.003844 h:0.003887 l:0.003831 c:0.003835 v:103.39M; -1 o:0.003858 h:0.003942 l:0.003845 c:0.003941 v:98.58M — enter at the last wick body candle from that void",
    "output": "limit short at 0.003942 (trend down, level not yet touched)"
  },
  {
    "input": "trend is up; looking for short entry; -1 o:0.0004684 h:0.0004692 l:0.0004635 c:0.0004637; main o:0.0004636 h:0.0004646 l:0.0004539 c:0.0004582; +1 o:0.0004581 h:0.0004585 l:0.0004556 c:0.0004570; +2 o:0.0004570 h:0.0004570 l:0.0004526 c:0.0004541 — main candle long wick, next candle does not close it → void",
    "output": "entry short at 0.0004582 (body close of last wick candle)"
  },
  {
    "input": "trend up; looking for long; o:13.33160 h:13.73500 l:13.10230 c:13.21796; +1 o:13.21795 h:13.26964 l:13.04792 c:13.22730; +2 o:13.22775 h:13.87839 l:13.20719 c:13.81678; -1 o:13.23907 h:13.33333 l:13.06984 c:13.33331; -2 o:13.04731 h:13.24540 l:12.98318 c:13.23923 — wick then gap then close: void in the middle",
    "output": "entry long at 13.33160 (candle body open)"
  },
  {
    "input": "trend up; 3m; o:2.42663 h:2.97600 l:2.35226 c:2.48033; +1 o:2.48030 h:2.52137 l:2.25767 c:2.40491; +2 o:2.40507 h:2.49556 l:2.33333 c:2.43605; -1 o:2.05480 h:2.56645 l:2.05450 c:2.42613; -2 o:2.01596 h:2.05789 l:2.01000 c:2.05443",
    "output": "entry long at 2.42613 (void confirmed)"
  },
  {
    "input": "same void on 15m: o:2.01596 h:2.97600 l:2.01000 c:2.48033; +1 o:2.48030 h:2.52137 l:2.25767 c:2.45024; +2 o:2.45016 h:3.17200 l:2.44670 c:2.77272; -1 o:1.97052 h:2.03159 l:1.95600 c:2.01583",
    "output": "entry long at 2.48033 (queue on 15m timeframe)"
  },
  {
    "input": "trend down on 15m; o:16.69993 h:16.91653 l:13.86700 c:15.71328; -3 empty -4 wick -5 last wick; -5 o:17.52713 h:17.63100 l:16.64201 c:17.21921",
    "output": "entry short at 17.21921 (body close of last wick, void behind)"
  }
]"""


# ---------------------------------------------------------------------------
# Single-token Qwen client
# ---------------------------------------------------------------------------

class QwenAIClient:
    """One bearer token = one independent Qwen API client."""

    def __init__(self, token: str, slot: int):
        self.token  = token
        self.slot   = slot
        self._tag   = f"[QW-{slot}]"
        self.client = httpx.AsyncClient(timeout=240)

    # ------------------------------------------------------------------
    # Token refresh (called automatically on 401)
    # ------------------------------------------------------------------
    async def _refresh(self) -> bool:
        """Ask the gateway to silently renew the session token."""
        try:
            resp = await self.client.get(
                REFRESH_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                new_token = data.get("token") or data.get("access_token") or data.get("data", {}).get("token")
                if new_token:
                    self.token = new_token
                    logger.info(f"{self._tag} Token refreshed ✅")
                    print(f"{self._tag} ✅ Token refreshed successfully")
                    return True
        except Exception as e:
            logger.warning(f"{self._tag} Token refresh failed: {e}")
        return False

    # ------------------------------------------------------------------
    # Main analysis method
    # ------------------------------------------------------------------
    async def analyze(
        self,
        symbol: str,
        candles_by_tf: dict,
        current_price: float = None,
    ) -> dict:
        tag = self._tag
        logger.info(f"{tag} Starting analysis for {symbol}")

        # ── 1. Generate candlestick charts (CPU → thread pool) ────────
        loop   = asyncio.get_event_loop()
        charts: Dict[str, str] = {}
        try:
            charts = await loop.run_in_executor(
                None, _generate_all_charts, candles_by_tf, symbol
            )
            if charts:
                print(f"{tag} 📊 {symbol} charts ready: {list(charts.keys())}")
            else:
                print(f"{tag} ⚠️  {symbol} charts skipped (matplotlib missing or no candles)")
        except Exception as e:
            logger.warning(f"{tag} Chart generation error for {symbol}: {e}")

        # ── 2. Build OHLCV text blocks ────────────────────────────────
        tf_blocks = []
        last_candle_price = None

        for tf in ["5m", "15m", "30m", "1h", "4h"]:
            candles = candles_by_tf.get(tf, [])
            if not candles:
                continue
            lines = [
                f"=== {symbol} | {tf} | last {min(len(candles), 150)} candles ===",
                "timestamp, open, high, low, close, volume",
            ]
            for c in candles[-150:]:
                lines.append(f"{c[0]}, {c[1]}, {c[2]}, {c[3]}, {c[4]}, {c[5]}")
            tf_blocks.append("\n".join(lines))
            last_candle_price = float(candles[-1][4])

        live_price   = current_price if (current_price and current_price > 0) else last_candle_price
        ohlcv_text   = "\n\n".join(tf_blocks) if tf_blocks else "No candle data available."

        prompt_text = f"""Analyze {symbol}

{ohlcv_text}

---

Candlestick charts for all timeframes are attached as images above this text.
Use BOTH the chart images AND the OHLCV text to identify void.
Cross-reference: what you see visually in the charts should match the OHLCV numbers.

⚠️ CURRENT REALTIME PRICE: {live_price}
(This is the live ticker price — use it as the reference for entry placement)

----------------------------------------
VOID POSITION RULE (CRITICAL):
- LONG  → void MUST be BELOW current price ({live_price})
- SHORT → void MUST be ABOVE current price ({live_price})
- If void is on the wrong side → IGNORE IT
- If no valid void on correct side → NO TRADE

ENTRY DIRECTION RULE (CRITICAL — violations cause instant loss):
- LONG  → entry MUST be BELOW {live_price}
- SHORT → entry MUST be ABOVE {live_price}
- NEVER: ❌ LONG above price  |  ❌ SHORT below price

----------------------------------------
Respond in this EXACT JSON format ONLY — no preamble, no markdown:

{{
  "trend":        "UP" or "DOWN" or "SIDEWAYS",
  "pattern":      "brief description of void/wick pattern detected",
  "decision":     "LONG" or "SHORT" or "NO TRADE",
  "entry":        <float entry price, or null if NO TRADE>,
  "tp":           <float take-profit price, or null if NO TRADE>,
  "sl":           <float stop-loss price, or null if NO TRADE>,
  "invalidation": <float price that completely invalidates the setup>,
  "reason":       "short explanation referencing the void/wick imbalance",
  "confidence":   <integer 0-100>
}}

If there is NO clear void/imbalance setup → return "NO TRADE". Do NOT force a trade."""

        # ── 3. Compose message with images first, then text ───────────
        content = []

        # Chart images (one per timeframe — in order 5m → 4h)
        for tf in ["5m", "15m", "30m", "1h", "4h"]:
            if tf in charts:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{charts[tf]}"},
                })

        # OHLCV text + instructions
        content.append({"type": "text", "text": prompt_text})

        # ── 4. Call Qwen API (retry once after token refresh) ─────────
        payload = {
            "model":         QWEN_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": content},
            ],
            "stream":        False,
            "thinking_mode": QWEN_THINKING,
            "max_tokens":    2000,
        }

        data = None
        lock = ai_lock()
        async with lock:
            for attempt in range(2):
                try:
                    print(f"{tag} 🔄 Qwen request [{QWEN_MODEL}] for {symbol} (attempt {attempt + 1})")
                    resp = await self.client.post(
                        CHAT_URL,
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Content-Type":  "application/json",
                        },
                        json=payload,
                        timeout=180,
                    )

                    if resp.status_code == 401:
                        logger.warning(f"{tag} 401 Unauthorized for {symbol} — trying token refresh")
                        print(f"{tag} 🔑 Token expired — refreshing...")
                        if attempt == 0 and await self._refresh():
                            # update header and retry
                            continue
                        return self._no_trade("Auth failed (401) even after refresh")

                    if resp.status_code == 429:
                        logger.warning(f"{tag} 429 Rate-limited for {symbol}")
                        return self._no_trade("Rate limited (429) — try again later")

                    if resp.status_code != 200:
                        logger.error(f"{tag} HTTP {resp.status_code} for {symbol}: {resp.text[:400]}")
                        return self._no_trade(f"HTTP {resp.status_code}")

                    data = resp.json()
                    break   # ← success, exit retry loop

                except httpx.TimeoutException:
                    logger.error(f"{tag} Timeout for {symbol}")
                    return self._no_trade("Request timeout (180s)")
                except Exception as e:
                    logger.error(f"{tag} Request exception for {symbol}: {e}", exc_info=True)
                    return self._no_trade(f"Request error: {e}")

            if data is None:
                return self._no_trade("No response after retries")

        # ── 5. Extract response text ──────────────────────────────────
            try:
                full_text = (
                    data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    or ""
                )
            # Some implementations put thinking in a separate field
                if not full_text:
                    full_text = (
                        data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("reasoning_content", "")
                        or ""
                    )
            except Exception:
                return self._no_trade("Failed to extract response content")

            logger.info(f"{tag} Raw response for {symbol} ({len(full_text)} chars):\n{full_text[:600]}")
            print(f"{tag} RAW [{symbol}]: {full_text[:400]}")

            if not full_text.strip():
                return self._no_trade("Empty AI response")

        # ── 6. Parse JSON from response ───────────────────────────────
            start = full_text.find("{")
            end   = full_text.rfind("}") + 1

            if start < 0 or end <= start:
                logger.error(f"{tag} No JSON found for {symbol}. Response: {full_text[:500]}")
                return self._no_trade("No JSON in AI response")

            json_str = full_text[start:end]
            try:
                result = json.loads(json_str)
            except json.JSONDecodeError as je:
                logger.error(f"{tag} JSON decode error for {symbol}: {je}")
                return self._no_trade(f"JSON parse error: {je}")

            decision = result.get("decision", "NO TRADE").upper().strip()
            if decision not in ("LONG", "SHORT", "NO TRADE"):
                logger.warning(f"{tag} Unexpected decision '{decision}' for {symbol} — forcing NO TRADE")
                decision = "NO TRADE"

            parsed = {
                "trend":        result.get("trend", "SIDEWAYS"),
                "pattern":      result.get("pattern", ""),
                "decision":     decision,
                "entry":        result.get("entry"),
                "tp":           result.get("tp"),
                "sl":           result.get("sl"),
                "invalidation": result.get("invalidation"),
                "reason":       result.get("reason", ""),
                "confidence":   int(result.get("confidence", 0)),
            }

            print(
                f"{tag} ✅ {symbol} → {decision} "
                f"entry={parsed['entry']} conf={parsed['confidence']}%"
            )
            logger.info(
                f"{tag} Signal parsed for {symbol}: "
                f"decision={decision} entry={parsed['entry']} confidence={parsed['confidence']}"
            )
            return parsed

        # ------------------------------------------------------------------

    def _no_trade(self, reason: str) -> dict:
        logger.warning(f"{self._tag} NO TRADE — {reason}")
        return {
            "trend":        "SIDEWAYS",
            "pattern":      "none",
            "decision":     "NO TRADE",
            "entry":        None,
            "tp":           None,
            "sl":           None,
            "invalidation": None,
            "reason":       reason,
            "confidence":   0,
        }

    async def close(self):
        await self.client.aclose()


# ---------------------------------------------------------------------------
# Parallel wrapper — manages up to 5 tokens
# ---------------------------------------------------------------------------

class ParallelQwenAI:
    """
    Manages up to 5 QwenAIClient instances.

    analyze_batch(items):
        Each item gets its own client (modulo assignment → round-robin).
        All items run concurrently — same parallel behaviour as the old
        ParallelDeepSeekAI.analyze_batch().

    analyze(symbol, candles_by_tf):
        Legacy single-symbol call; uses the next client in round-robin order.
    """

    def __init__(self):
        self.clients: List[QwenAIClient] = []
        self._rr_idx = 0   # round-robin counter

        for slot in range(1, 6):
            token = os.getenv(f"QWEN_TOKEN_{slot}", "").strip()
            if token:
                self.clients.append(QwenAIClient(token=token, slot=slot))
                logger.info(f"[ParallelQwen] Token slot {slot} registered")
                print(f"[ParallelQwen] ✅ Token {slot} loaded")
            else:
                logger.debug(f"[ParallelQwen] QWEN_TOKEN_{slot} not set — skipped")

        if not self.clients:
            logger.error("[ParallelQwen] No tokens configured! Set QWEN_TOKEN_1 at minimum.")
            print("[ParallelQwen] ❌ No Qwen tokens found in environment!")
        else:
            print(
                f"[ParallelQwen] {len(self.clients)} token(s) | "
                f"model={QWEN_MODEL} | thinking={QWEN_THINKING} | "
                f"charts={'ON' if HAS_CHARTS else 'OFF (install matplotlib)'}"
            )

    # ------------------------------------------------------------------
    # Batch — parallel, order-preserving
    # ------------------------------------------------------------------
    async def analyze_batch(self, items: list) -> list:
        """
        Analyze a list of symbols concurrently.

        items : list of (symbol, candles_by_tf) or
                         (symbol, candles_by_tf, current_price)
        Returns results in the SAME ORDER as input items.
        """
        if not self.clients:
            return [self._no_trade("No tokens configured")] * len(items)

        tasks = []
        for i, item in enumerate(items):
            sym    = item[0]
            tfs    = item[1]
            price  = item[2] if len(item) > 2 else None
            client = self.clients[i % len(self.clients)]   # round-robin
            tasks.append(asyncio.create_task(client.analyze(sym, tfs, price)))

        # asyncio.gather preserves order
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [
            r if isinstance(r, dict) else self._no_trade(f"Task exception: {r}")
            for r in results
        ]

    # ------------------------------------------------------------------
    # Single (legacy / backward compat)
    # ------------------------------------------------------------------
    async def analyze(
        self,
        symbol: str,
        candles_by_tf: dict,
        current_price: float = None,
    ) -> dict:
        if not self.clients:
            return self._no_trade("No tokens configured")
        client = self.clients[self._rr_idx % len(self.clients)]
        self._rr_idx += 1
        return await client.analyze(symbol, candles_by_tf, current_price)

    # ------------------------------------------------------------------

    def _no_trade(self, reason: str) -> dict:
        return {
            "trend":        "SIDEWAYS",
            "pattern":      "none",
            "decision":     "NO TRADE",
            "entry":        None,
            "tp":           None,
            "sl":           None,
            "invalidation": None,
            "reason":       reason,
            "confidence":   0,
        }

    async def close(self):
        for client in self.clients:
            await client.close()


# ---------------------------------------------------------------------------
# Singleton — drop-in replacement for:   from services.deepseek_ai import deepseek_ai
# ---------------------------------------------------------------------------
qwen_ai = ParallelQwenAI()
