"""
Position Monitor AI — HOLD or CLOSE untuk posisi yang sudah entry.

Perbedaan dari versi sebelumnya:
  - Hanya 1 token (MONITOR_TOKEN_1, atau fallback ke QWEN_TOKEN_1)
  - Pakai ai_lock() agar tidak bentrok dengan analysis AI
  - Retry terus sampai dapat HOLD/CLOSE yang valid

Env vars:
  MONITOR_TOKEN_1           — bearer token khusus monitor
                              (kalau tidak diset, fallback ke QWEN_TOKEN_1)
  MONITOR_INTERVAL_SECONDS  — seberapa sering query per posisi (default: 120s)
  QWEN_BASE_URL / QWEN_MODEL / QWEN_THINKING_MODE — shared dengan qwen_ai.py
"""

import asyncio
import json
import logging
import os
from typing import Optional

import httpx

from services.qwen_ai import (
    _draw_chart,
    HAS_CHARTS,
    CHAT_URL,
    REFRESH_URL,
    QWEN_MODEL,
    QWEN_THINKING,
)
from services.ai_lock import ai_lock

logger = logging.getLogger(__name__)

MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL_SECONDS", "120"))

_token = (
    os.getenv("MONITOR_TOKEN_1", "").strip()
    or os.getenv("QWEN_TOKEN_1", "").strip()
)

if _token:
    print(f"[PositionAI] token loaded | interval={MONITOR_INTERVAL}s")
else:
    print("[PositionAI] no token — set MONITOR_TOKEN_1 or QWEN_TOKEN_1")

POSITION_SYSTEM_PROMPT = """You are a position management AI for a crypto futures trading bot.

An ACTIVE OPEN POSITION is running — entry price has already been hit.
Your only job: decide HOLD or CLOSE right now.

CLOSE if:
- Clear reversal against the position direction
- Key structure broken (lower low for LONG / higher high for SHORT)
- Momentum fading with no recovery
- Better to take small loss now than wait for full SL

HOLD if:
- Trend still supports original thesis
- Normal pullback within trade direction
- TP still reachable from current structure

Rules:
- Respond with EXACTLY this JSON and nothing else:
  {"decision": "HOLD" or "CLOSE", "reason": "max 100 chars"}
- No markdown, no preamble, no extra text outside the JSON
- decision must be exactly "HOLD" or "CLOSE"
"""


class PositionAIClient:
    def __init__(self, token: str):
        self.token  = token
        self.client = httpx.AsyncClient(timeout=180)

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
                    print("[PositionAI] token refreshed")
                    return True
        except Exception as e:
            logger.warning(f"[PositionAI] Token refresh failed: {e}")
        return False

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
        if direction == "LONG":
            pnl_pct  = round((current_price - entry) / entry * 100, 3)
            pct_to_tp = round((tp - current_price) / current_price * 100, 3)
            pct_to_sl = round((current_price - sl) / current_price * 100, 3)
        else:
            pnl_pct  = round((entry - current_price) / entry * 100, 3)
            pct_to_tp = round((current_price - tp) / current_price * 100, 3)
            pct_to_sl = round((sl - current_price) / current_price * 100, 3)

        pnl_usdt = round(margin_usdt * leverage * pnl_pct / 100, 4)
        sign     = "+" if pnl_pct >= 0 else ""

        ohlcv_blocks = []
        for tf, candles in candles_by_tf.items():
            recent = candles[-80:]
            lines  = [f"=== {symbol} | {tf} | {len(recent)} candles ===",
                      "timestamp, open, high, low, close, volume"]
            for c in recent:
                lines.append(f"{c[0]}, {c[1]}, {c[2]}, {c[3]}, {c[4]}, {c[5]}")
            ohlcv_blocks.append("\n".join(lines))

        user_text = (
            f"ACTIVE POSITION — HOLD or CLOSE?\n\n"
            f"Symbol:         {symbol}\n"
            f"Direction:      {direction}\n"
            f"Entry:          {entry}\n"
            f"Current Price:  {current_price}\n"
            f"Take Profit:    {tp}  ({pct_to_tp:+.3f}% away)\n"
            f"Stop Loss:      {sl}  (-{pct_to_sl:.3f}% away)\n"
            f"Unrealized PnL: {sign}{pnl_pct}% ({sign}{pnl_usdt} USDT)\n"
            f"Leverage:       {leverage}x\n"
            f"Margin Used:    {margin_usdt} USDT\n\n"
            f"{chr(10).join(ohlcv_blocks)}\n\n"
            f'Charts attached above. Respond ONLY with JSON:\n'
            f'{{"decision": "HOLD" or "CLOSE", "reason": "brief reason"}}'
        )

        content = []
        if HAS_CHARTS:
            for tf, candles in candles_by_tf.items():
                img = _draw_chart(candles, symbol, tf)
                if img:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img}"},
                    })
        content.append({"type": "text", "text": user_text})

        payload = {
            "model":         QWEN_MODEL,
            "messages": [
                {"role": "system", "content": POSITION_SYSTEM_PROMPT},
                {"role": "user",   "content": content},
            ],
            "stream":        False,
            "thinking_mode": QWEN_THINKING,
            "max_tokens":    300,
        }

        lock = ai_lock()
        print(f"[PositionAI] waiting for lock ({symbol} {direction} pnl={sign}{pnl_pct}%)")
        async with lock:
            print(f"[PositionAI] lock acquired → hold/close query for {symbol}")
            data = None
            for attempt in range(2):
                try:
                    resp = await self.client.post(
                        CHAT_URL,
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Content-Type":  "application/json",
                        },
                        json=payload,
                    )
                    if resp.status_code == 401:
                        if attempt == 0 and await self._refresh():
                            continue
                        return None
                    if resp.status_code == 429:
                        logger.warning("[PositionAI] 429 rate-limited")
                        return None
                    if resp.status_code != 200:
                        logger.error(f"[PositionAI] HTTP {resp.status_code}: {resp.text[:200]}")
                        return None
                    data = resp.json()
                    break
                except httpx.TimeoutException:
                    print(f"[PositionAI] timeout for {symbol} — will retry")
                    return None
                except Exception as e:
                    logger.error(f"[PositionAI] {e}")
                    return None

        if not data:
            return None

        try:
            full_text = (
                data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "") or ""
            )
        except Exception:
            return None

        print(f"[PositionAI] raw [{symbol}]: {full_text[:200]}")
        if not full_text.strip():
            return None

        start = full_text.find("{")
        end   = full_text.rfind("}") + 1
        if start < 0 or end <= start:
            return None

        try:
            result = json.loads(full_text[start:end])
        except json.JSONDecodeError:
            return None

        decision = str(result.get("decision", "")).upper().strip()
        if decision not in ("HOLD", "CLOSE"):
            logger.warning(f"[PositionAI] invalid decision '{decision}' for {symbol}")
            return None

        reason = str(result.get("reason", ""))[:200]
        print(f"[PositionAI] {symbol} → {decision} | {reason}")
        return {"decision": decision, "reason": reason}

    async def close(self):
        await self.client.aclose()


class PositionMonitorAI:
    def __init__(self):
        self._client: Optional[PositionAIClient] = None
        if _token:
            self._client = PositionAIClient(token=_token)

    @property
    def enabled(self) -> bool:
        return self._client is not None

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
        max_retries:   int = 999,
    ) -> dict:
        """Retry sampai dapat HOLD/CLOSE. Backoff 10s → 30s."""
        if not self._client:
            return {"decision": "HOLD", "reason": "No token configured"}

        for attempt in range(max_retries):
            result = await self._client.decide(
                symbol=symbol, direction=direction, entry=entry,
                tp=tp, sl=sl, current_price=current_price,
                candles_by_tf=candles_by_tf,
                leverage=leverage, margin_usdt=margin_usdt,
            )
            if result and result.get("decision") in ("HOLD", "CLOSE"):
                return result

            wait = min(10 * (attempt + 1), 30)
            print(f"[PositionAI] no valid response for {symbol} — retry {attempt+1} in {wait}s")
            await asyncio.sleep(wait)

        return {"decision": "HOLD", "reason": "Retries exhausted"}

    async def close(self):
        if self._client:
            await self._client.close()


position_ai = PositionMonitorAI()
