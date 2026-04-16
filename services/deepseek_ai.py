"""
    DEEPSEEK_WASM_PATH (default: sha3.wasm)
"""

import asyncio
import json
import logging
import os
import re
import base64
import struct
import ctypes
import httpx
import wasmtime
from threading import Lock
from typing import Optional, List

logger = logging.getLogger(__name__)

DEEPSEEK_BASE = "https://chat.deepseek.com"

WORKING_HEADERS = {
    "Host": "chat.deepseek.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "x-client-platform": "web",
    "x-client-version": "1.8.0",
    "x-app-version": "20241129.1",
    "x-client-locale": "en_US",
    "x-client-timezone-offset": "25200",
    "origin": "https://chat.deepseek.com",
    "referer": "https://chat.deepseek.com/",
    "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

SYSTEM_PROMPT = """You are an AI trained to mimic a specific trading strategy based on example data.

Your job:
- Learn from the examples
- Apply the SAME behavior to new data

Focus on:
- Trend structure (market direction)
- Wick behavior (rejection / inefficiency)
- Void / imbalance zones
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
  → use LOWER WICK voids (void below price)
  → ignore upper wick voids

- DOWN trend:
  → use UPPER WICK voids (void above price)
  → ignore lower wick voids

IMPORTANT:
- The void must be in the direction of a RETRACEMENT, not continuation

Logic:
- LONG = buy lower → void must be BELOW
- SHORT = sell higher → void must be ABOVE

- NEVER choose a void that would require chasing price

----------------------------------------
ENTRY DISTANCE RULE:
- Entry MUST be placed at a clear void / imbalance
- Entry must NOT be near current price without structure
- If price is already near the level → NO TRADE
- Entry should feel like a LIMIT order (far from price), not a market entry

----------------------------------------
NO TRADE RULE:
- No clear void → NO TRADE
- Bad structure → NO TRADE
- Entry too close to price → NO TRADE

----------------------------------------
REVERSAL RULE (ADVANCED):
Reversal trades are allowed ONLY if ALL conditions are met:

1. There is a clear void (4H / 2H)
2. The level comes from past price action (look-back structure)
3. Strong wick rejection exists at that level
4. The level has NOT been revisited

If ALL valid:
→ Counter-trend entry is allowed

If NOT:
→ Stay with trend or NO TRADE

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
OUTPUT FORMAT (STRICT):

Trend: UP / DOWN
Pattern: <void + wick explanation>
Entry: LONG / SHORT / NO TRADE
Entry Price: <number or NONE>
Reason: <short explanation>

----------------------------------------
IMPORTANT:
- Do NOT use indicators
- Do NOT guess
- ONLY act if pattern matches training data behavior
- Think like a patient trader waiting for price to reach a level
----------------------------------------
TRAINING DATA:

[
  {
    "input": "analyze my trading technique,, so this candle data shows the trend is going down, and I searched across multiple timeframes, and found this on the 4h timeframe open : 0.003942 high : 0.003979 low : 0.003791 close : 0.003843 volume : 246.84 M that becomes the reference, and this is the +1 and -1 candle data +1 o: 0.003844 h: 0.003887 l: 0.003831 c:0.003835 v:103.39 M -1 o:0.003858 h:0.003942 l:0.003845 c:0.003941 v:98.58 M so I enter at the last wick body candle from that void",
    "output": "I place a limit short because the trend is going down and hasn't touched that level yet, I enter at 0.003942"
  },
  {
    "input": "and here is another example,, the trend is going up but hasn't reached this candle yet, so looking for a short entry, I give 2 candles after and before +1,+2 , -1 , -2 o:0.0004636 h:0.0004646 l:0.0004539 c:0.0004582 v:903.25 M +1 o:0.0004581 h:0.0004585 l:0.0004556 c:0.0004570 v:135.02 M +2 o:0.0004570 h:0.0004570 l:0.0004526 c:0.0004541 v:345.41 M -1 o:0.0004684 h:0.0004692 l:0.0004635 c:0.0004637 v:179.48 M -2 o:0.0004686 h:0.0004696 l:0.0004655 c:0.0004686 v:96.42 M it can be seen there is a void, the main candle has a long wick, but the next candle does not close that wick, so it becomes empty, therefore we enter short at the body close of the last wick candle c:0.0004582",
    "output": "entry short at 0.0004582"
  },
  {
    "input": "and here is another example, the trend is going up, and looking for a long entry, o:13.33160 h:13.73500 L:13.10230 c:13.21796 v:485.14 K +1 o:13.21795 h:13.26964 l:13.04792 c:13.22730 v:173.6 K +2 o:13.22775 h:13.87839 l:13.20719 c:13.81678 v:432.79 K -1 o:13.23907 h:13.33333 l:13.06984 c:13.33331 v:241.08 K -2 o:13.04731 h:13.24540 l:12.98318 c:13.23923 v:212.93 K so the long entry is at the candle body open 13.33160 you can see there is a void right? wick - next candle does not close the previous wick - then suddenly it gets closed. there is a void in the middle",
    "output": "entry long at 13.33160"
  },
  {
    "input": "and here is another example, the trend is going up, so looking for either short or long, because here there is a long opportunity with my trading technique, so we look for long first, this is on the 3m timeframe o:2.42663 h:2.97600 l:2.35226 c:2.48033 v:21.85 M +1 o:2.48030 h:2.52137 l:2.25767 c:2.40491 v:9.21 M +2 o:2.40507 h:2.49556 l:2.33333 c:2.43605 v:6.08 M -1 o:2.05480 h:2.56645 l:2.05450 c:2.42613 v:16.07 M -2 o:2.01596 h:2.05789 l:2.01000 c:2.05443 v:2 M you can see the void right??? so the entry is at 2.42613",
    "output": "entry long at 2.42613"
  },
  {
    "input": "but wait, shift to a higher timeframe and it turns out the void is in the same place, this is the 15m timeframe o:2.01596 h:2.97600 l:2.01000 c:2.48033 v:39.92 M +1 o:2.48030 h:2.52137 l:2.25767 c:2.45024 v:18.56 M +2 o:2.45016 h:3.17200 l:2.44670 c:2.77272 v:36.31 M -1 o:1.97052 h:2.03159 l:1.95600 c:2.01583 v:4.44 M -2 o:1.96475 h:1.99999 l:1.94000 c:1.97007 v:3.88 M so we queue a long entry on the 15m timeframe at 2.48033",
    "output": "entry long at 2.48033"
  },
  {
    "input": "and one more example, this trend on the 15m timeframe is going down o:16.69993 h:16.91653 l:13.86700 c:15.71328 v:5.01 M +1 o:15.71528 h:16.04210 l:15.46930 c:15.78945 v:1.84 M +2 o:15.78901 h:15.88442 l:14.66984 c:15.58410 v:2.99 M +3 o:15.58391 h:15.59277 l:15.05886 c:15.38774 v:998.97 K +4 o:15.38710 h:15.79744 l:15.19092 c:15.63269 v:1.13 M +5 o:15.63268 h:15.70441 l:15.42000 c:15.66259 v:995.61 K -1 o:16.40347 h:16.82500 l:16.33000 c:16.70014 v:795.51 K -2 o:17.02174 h:17.04372 l:16.25810 c:16.40675 v:1.47 M -3 o:17.08839 h:17.25695 l:16.90150 c:17.01790 v:1.33 M -4 o:17.21850 h:17.32191 l:16.22917 c:17.08670 v:1.57 M -5 o:17.52713 h:17.63100 l:16.64201 c:17.21921 v:1.75 M because behind it there is still a void, so we use the void behind as reference and the body close of the last wick candle, because -3 is empty -4 wick -5 still the last wick",
    "output": "entry short at 17.21921"
  }
]"""


# ---------------------------------------------------------------------------
# WASM POW Solver (singleton, shared across all client instances)
# ---------------------------------------------------------------------------

class DeepSeekHashV1Solver:
    _instance = None
    _lock = Lock()

    def __new__(cls, wasm_path: str):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls.engine = wasmtime.Engine()
                cls.module = wasmtime.Module.from_file(cls.engine, wasm_path)
                cls.linker = wasmtime.Linker(cls.engine)
        return cls._instance

    def solve(self, challenge: dict) -> Optional[int]:
        challenge_str = challenge["challenge"]
        salt = challenge["salt"]
        difficulty = challenge["difficulty"]
        expire_at = challenge["expire_at"]

        store = wasmtime.Store(self.engine)
        instance = self.linker.instantiate(store, self.module)
        exports = instance.exports(store)
        memory = exports["memory"]
        alloc = exports["__wbindgen_export_0"]
        add_to_stack = exports["__wbindgen_add_to_stack_pointer"]
        wasm_solve = exports["wasm_solve"]

        prefix = f"{salt}_{expire_at}_"

        def write_string(text: str):
            data = text.encode("utf-8")
            ptr = alloc(store, len(data), 1)
            base_addr = ctypes.cast(memory.data_ptr(store), ctypes.c_void_p).value
            ctypes.memmove(base_addr + ptr, data, len(data))
            return ptr, len(data)

        retptr = add_to_stack(store, -16)
        p_ch, l_ch = write_string(challenge_str)
        p_pre, l_pre = write_string(prefix)
        wasm_solve(store, retptr, p_ch, l_ch, p_pre, l_pre, float(difficulty))

        base_addr = ctypes.cast(memory.data_ptr(store), ctypes.c_void_p).value
        status = struct.unpack("<i", ctypes.string_at(base_addr + retptr, 4))[0]
        answer = None
        if status != 0:
            value_bytes = ctypes.string_at(base_addr + retptr + 8, 8)
            answer = int(struct.unpack("<d", value_bytes)[0])

        add_to_stack(store, 16)
        return answer


# ---------------------------------------------------------------------------
# Single DeepSeek client (one token / one session)
# ---------------------------------------------------------------------------

class DeepSeekAI:
    def __init__(self, token: str, wasm_path: str, slot: int = 1):
        """
        Parameters
        ----------
        token     : Bearer token for chat.deepseek.com
        wasm_path : Path to sha3.wasm POW file
        slot      : Human-readable index (1/2/3) used in log messages
        """
        self.token     = token
        self.wasm_path = wasm_path
        self.slot      = slot
        self.solver: Optional[DeepSeekHashV1Solver] = None
        self._init_solver()

        self.headers = WORKING_HEADERS.copy()
        self.headers["authorization"] = f"Bearer {self.token}"

        self.client = httpx.AsyncClient(base_url=DEEPSEEK_BASE, timeout=120)
        self._chat_session_id: Optional[str] = None
        self._parent_message_id: Optional[int] = None

    def _tag(self) -> str:
        """Short prefix for log lines, e.g. [DS-2]"""
        return f"[DS-{self.slot}]"

    def _init_solver(self):
        if os.path.exists(self.wasm_path):
            logger.info(f"{self._tag()} Loading WASM solver: {self.wasm_path}")
            print(f"{self._tag()} ✅ Loading WASM: {self.wasm_path}")
            self.solver = DeepSeekHashV1Solver(self.wasm_path)
        else:
            logger.warning(f"{self._tag()} WASM not found at {self.wasm_path} — POW will be empty")
            print(f"{self._tag()} ⚠️ WASM not found: {self.wasm_path}")

    async def _do_pow(self, target_path: str) -> str:
        try:
            resp = await self.client.post(
                "/api/v0/chat/create_pow_challenge",
                headers=self.headers,
                json={"target_path": target_path},
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.warning(f"{self._tag()} POW challenge failed: {data}")
                return ""
            challenge = data.get("data", {}).get("biz_data", {}).get("challenge")
            if not challenge or not self.solver:
                return ""

            answer = self.solver.solve(challenge)
            if answer is None:
                logger.warning(f"{self._tag()} POW solve returned None")
                return ""

            pow_dict = {
                "algorithm": "DeepSeekHashV1",
                "challenge":  challenge["challenge"],
                "salt":       challenge["salt"],
                "answer":     answer,
                "signature":  challenge["signature"],
                "target_path": target_path,
            }
            return base64.b64encode(json.dumps(pow_dict, separators=(",", ":")).encode()).decode()
        except Exception as e:
            logger.error(f"{self._tag()} POW exception: {e}")
            return ""

    async def _ensure_session(self):
        if not self._chat_session_id:
            logger.info(f"{self._tag()} Creating new chat session")
            resp = await self.client.post(
                "/api/v0/chat_session/create",
                headers=self.headers,
                json={},
            )
            data = resp.json()
            if data.get("code") != 0:
                raise Exception(f"{self._tag()} Session error: {data.get('msg')} | full={data}")
            biz_data    = data.get("data", {}).get("biz_data", {})
            chat_session = biz_data.get("chat_session", {})
            self._chat_session_id = chat_session.get("id")
            logger.info(f"{self._tag()} Session created: {self._chat_session_id}")

    async def analyze(self, symbol: str, candles_by_tf: dict,
                      current_price: float = None) -> dict:
        tag = self._tag()
        logger.info(f"{tag} Starting analysis for {symbol}")

        try:
            await self._ensure_session()
        except Exception as e:
            logger.error(f"{tag} Session setup failed for {symbol}: {e}")
            return self._no_trade_response(f"Session error: {e}")

        # Build OHLCV prompt
        tf_blocks  = []
        last_candle_price = None
        for tf in ["3m", "5m", "15m", "30m", "1h", "2h", "4h"]:
            candles = candles_by_tf.get(tf, [])
            if not candles:
                continue
            lines = [f"=== {symbol} | {tf} (last {min(len(candles), 150)} candles) ==="]
            lines.append("timestamp, open, high, low, close, volume")
            for c in candles[-150:]:
                lines.append(f"{c[0]}, {c[1]}, {c[2]}, {c[3]}, {c[4]}, {c[5]}")
            tf_blocks.append("\n".join(lines))
            if candles:
                last_candle_price = float(candles[-1][4])

        # Prefer realtime ticker price; fall back to last candle close
        live_price = current_price if (current_price and current_price > 0) else last_candle_price

        ohlcv_section = "\n\n".join(tf_blocks) if tf_blocks else "No candle data available."

        prompt = f"""{SYSTEM_PROMPT}

---

analyst {symbol}

{ohlcv_section}

---

Now analyze the data above using the SAME void/wick imbalance pattern from the training examples.

⚠️ CURRENT REALTIME PRICE: {live_price}
(This is the live ticker price fetched RIGHT NOW — use this as the reference for entry placement)

----------------------------------------
VOID POSITION RULE (CRITICAL):

- LONG → ONLY use void BELOW current price
- SHORT → ONLY use void ABOVE current price

- If void is on the wrong side → IGNORE IT
- If no valid void on correct side → NO TRADE

----------------------------------------
ENTRY DIRECTION RULE (CRITICAL — violations will cause instant loss):

- If decision is LONG  → entry MUST be BELOW {live_price}
- If decision is SHORT → entry MUST be ABOVE {live_price}

- NEVER:
  ❌ LONG above price
  ❌ SHORT below price

----------------------------------------
You MUST respond in this EXACT JSON format ONLY — no extra text:

{{
  "trend": "UP" or "DOWN" or "SIDEWAYS",
  "pattern": "brief description of what pattern you detected",
  "decision": "LONG" or "SHORT" or "NO TRADE",
  "entry": <entry price as float, or null if NO TRADE>,
  "tp": <take profit price as float, or null if NO TRADE>,
  "sl": <stop loss price as float, or null if NO TRADE>,
  "invalidation": <price level where the setup is COMPLETELY INVALID>,
  "reason": "short explanation referencing the void/wick imbalance",
  "confidence": <integer 0-100>
}}

If there is NO clear void/imbalance setup, return "NO TRADE" — do NOT force a trade."""

        pow_token   = await self._do_pow("/api/v0/chat/completion")
        comp_headers = {**self.headers, "x-ds-pow-response": pow_token}

        payload = {
            "chat_session_id":    self._chat_session_id,
            "parent_message_id":  self._parent_message_id,
            "prompt":             prompt,
            "ref_file_ids":       [],
            "thinking_enabled":   True,
            "search_enabled":     False,
            "preempt":            False,
        }

        full_text         = ""
        current_frag_type = None   # "THINK" or "RESPONSE"

        try:
            logger.info(f"{tag} Sending request to DeepSeek for {symbol}")
            async with self.client.stream(
                "POST",
                "/api/v0/chat/completion",
                headers=comp_headers,
                json=payload,
            ) as resp:
                logger.info(f"{tag} HTTP {resp.status_code} for {symbol}")
                print(f"{tag} HTTP {resp.status_code} | {symbol}")

                if resp.status_code != 200:
                    body = await resp.aread()
                    logger.error(f"{tag} Non-200 response for {symbol}: {body.decode()[:500]}")
                    return self._no_trade_response(f"HTTP {resp.status_code}")

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if not raw or raw == "{}":
                        continue

                    try:
                        jdata = json.loads(raw)
                    except Exception as parse_err:
                        logger.debug(f"{tag} JSON parse error: {parse_err} | line={line[:100]}")
                        continue

                    p = jdata.get("p", "")
                    o = jdata.get("o", "")
                    v = jdata.get("v")

                    # ── New fragment appended to fragments array ──────────────
                    # e.g. {"p":"response/fragments","o":"APPEND","v":[{"type":"RESPONSE","content":"Hello"}]}
                    # This is the moment the model SWITCHES from THINK → RESPONSE
                    if p == "response/fragments" and o == "APPEND" and isinstance(v, list):
                        for frag in v:
                            if isinstance(frag, dict) and "type" in frag:
                                current_frag_type = frag["type"]
                                logger.debug(f"{tag} Fragment switch → {current_frag_type}")
                                # Capture initial content if any (usually the first word)
                                init_content = frag.get("content", "")
                                if current_frag_type == "RESPONSE" and init_content:
                                    full_text += init_content
                        continue

                    # ── Initial response setup message ────────────────────────
                    # e.g. {"v":{"response":{...,"fragments":[{"type":"THINK","content":"Okay"}]}}}
                    if not p and isinstance(v, dict) and "response" in v:
                        frags = v.get("response", {}).get("fragments", [])
                        if frags:
                            current_frag_type = frags[-1].get("type")
                            logger.debug(f"{tag} Initial fragment type: {current_frag_type}")
                        continue

                    # ── Text token (incremental append to current fragment) ────
                    # e.g. {"v":" word"}  or  {"p":"response/fragments/-1/content","o":"APPEND","v":","}
                    # Only accumulate when we are in the RESPONSE fragment.
                    if isinstance(v, str) and v:
                        if current_frag_type == "RESPONSE":
                            full_text += v
                        # THINK tokens are intentionally discarded

            # ── Log the raw AI response ──────────────────────────────────
            logger.info(f"{tag} Raw RESPONSE text for {symbol} ({len(full_text)} chars):\n{full_text}")
            print(f"{tag} RAW AI RESPONSE [{symbol}]:\n{full_text[:1000]}")

            if not full_text.strip():
                logger.error(f"{tag} Empty response from DeepSeek for {symbol}")
                return self._no_trade_response("Empty AI response")

            # ── Parse JSON ───────────────────────────────────────────────
            start = full_text.find("{")
            end   = full_text.rfind("}") + 1

            if start < 0 or end <= start:
                logger.error(
                    f"{tag} No JSON block found in response for {symbol}. "
                    f"Full text: {full_text[:800]}"
                )
                return self._no_trade_response("No JSON in AI response")

            json_str = full_text[start:end]
            logger.debug(f"{tag} Extracted JSON for {symbol}: {json_str}")

            try:
                result = json.loads(json_str)
            except json.JSONDecodeError as je:
                logger.error(
                    f"{tag} JSON decode error for {symbol}: {je}\n"
                    f"Attempted to parse: {json_str[:500]}"
                )
                return self._no_trade_response(f"JSON parse error: {je}")

            decision = result.get("decision", "NO TRADE").upper().strip()
            if decision not in ("LONG", "SHORT", "NO TRADE"):
                logger.warning(
                    f"{tag} Unexpected decision value '{decision}' for {symbol} — "
                    f"treating as NO TRADE. Full result: {result}"
                )
                decision = "NO TRADE"

            parsed = {
                "trend":        result.get("trend", "SIDEWAYS"),
                "pattern":      result.get("pattern", ""),
                "decision":     decision,
                "entry":        result.get("entry"),
                "tp":           result.get("tp"),
                "sl":           result.get("sl"),
                "invalidation": result.get("invalidation"),   # level hapus signal
                "reason":       result.get("reason", ""),
                "confidence":   int(result.get("confidence", 0)),
            }
            logger.info(
                f"{tag} ✅ Parsed signal for {symbol}: "
                f"decision={parsed['decision']} entry={parsed['entry']} "
                f"confidence={parsed['confidence']}"
            )
            print(
                f"{tag} ✅ {symbol} → {parsed['decision']} "
                f"entry={parsed['entry']} conf={parsed['confidence']}%"
            )
            return parsed

        except Exception as e:
            logger.error(f"{tag} Exception during analyze({symbol}): {e}", exc_info=True)
            return self._no_trade_response(f"Exception: {e}")

    def _no_trade_response(self, reason: str) -> dict:
        logger.warning(f"{self._tag()} NO TRADE — reason: {reason}")
        return {
            "trend":      "SIDEWAYS",
            "pattern":    "none",
            "decision":   "NO TRADE",
            "entry":      None,
            "tp":         None,
            "sl":         None,
            "reason":     reason,
            "confidence": 0,
        }

    async def close(self):
        await self.client.aclose()


# ---------------------------------------------------------------------------
# Parallel wrapper — each token analyzes a DIFFERENT coin simultaneously.
# Used by bot_engine._loop() which calls analyze_batch() with a list of
# (symbol, candles_by_tf) tuples — one per available token.
#
# The old single-symbol analyze() is kept for backward-compat but now just
# calls the first available client (same as before if only 1 token).
# ---------------------------------------------------------------------------

class ParallelDeepSeekAI:
    """
    Manages up to 3 DeepSeekAI clients, each with its own token.

    New behaviour (parallel-coins mode):
        bot_engine calls analyze_batch([(sym1, tf1), (sym2, tf2), ...])
        Each symbol gets its own dedicated client — no racing on the same coin.

    Legacy behaviour (single symbol):
        analyze(symbol, candles_by_tf) still works — uses client[0] only.

    Railway env vars:
        DEEPSEEK_TOKEN_1   ← required
        DEEPSEEK_TOKEN_2   ← optional
        DEEPSEEK_TOKEN_3   ← optional
        DEEPSEEK_WASM_PATH ← default: sha3.wasm
    """

    def __init__(self):
        wasm_path = os.getenv("DEEPSEEK_WASM_PATH", "sha3.wasm")
        raw_tokens = [
            os.getenv("DEEPSEEK_TOKEN_1", ""),
            os.getenv("DEEPSEEK_TOKEN_2", ""),
            os.getenv("DEEPSEEK_TOKEN_3", ""),
        ]

        self.clients: List[DeepSeekAI] = []
        for slot, token in enumerate(raw_tokens, start=1):
            t = token.strip()
            if t:
                self.clients.append(DeepSeekAI(token=t, wasm_path=wasm_path, slot=slot))
                logger.info(f"[ParallelDS] Registered token slot {slot}")
                print(f"[ParallelDS] ✅ Token {slot} loaded")
            else:
                logger.warning(f"[ParallelDS] DEEPSEEK_TOKEN_{slot} not set — slot skipped")
                print(f"[ParallelDS] ⚠️  DEEPSEEK_TOKEN_{slot} is empty — skipped")

        if not self.clients:
            logger.error("[ParallelDS] No tokens configured! Set DEEPSEEK_TOKEN_1 at minimum.")
            print("[ParallelDS] ❌ No DeepSeek tokens found in env!")

    # ------------------------------------------------------------------
    # NEW: analyze multiple coins in parallel, one per client
    # ------------------------------------------------------------------
    async def analyze_batch(self, items: list) -> list:
        """
        Analyze a batch of symbols in parallel — one per available client.

        Parameters
        ----------
        items : list of (symbol: str, candles_by_tf: dict) or
                         (symbol: str, candles_by_tf: dict, current_price: float)
                Length must be <= len(self.clients).

        Returns
        -------
        list of result dicts, same order as input items.
        """
        if not self.clients:
            return [self._no_trade_response("No tokens configured")] * len(items)

        tasks = []
        for i, item in enumerate(items):
            sym   = item[0]
            tfs   = item[1]
            price = item[2] if len(item) > 2 else None
            tasks.append(asyncio.create_task(self.clients[i].analyze(sym, tfs, price)))

        results = []
        for t in asyncio.as_completed(tasks):
            try:
                results.append(await t)
            except Exception as e:
                logger.error(f"[ParallelDS] Batch task exception: {e}")
                results.append(self._no_trade_response(f"Exception: {e}"))

        # Re-order results to match input order (as_completed returns out-of-order)
        ordered = [None] * len(items)
        done_tasks = list(zip(tasks, range(len(items))))
        for task, idx in done_tasks:
            try:
                ordered[idx] = task.result()
            except Exception as e:
                ordered[idx] = self._no_trade_response(f"Exception: {e}")

        return ordered

    # ------------------------------------------------------------------
    # LEGACY: single-symbol analyze (uses first available client)
    # ------------------------------------------------------------------
    async def analyze(self, symbol: str, candles_by_tf: dict) -> dict:
        """
        Legacy single-symbol analyze.
        Uses only client[0] — for backward compatibility.
        """
        if not self.clients:
            return self._no_trade_response("No tokens configured")
        return await self.clients[0].analyze(symbol, candles_by_tf)

    def _no_trade_response(self, reason: str) -> dict:
        return {
            "trend":      "SIDEWAYS",
            "pattern":    "none",
            "decision":   "NO TRADE",
            "entry":      None,
            "tp":         None,
            "sl":         None,
            "reason":     reason,
            "confidence": 0,
        }

    async def close(self):
        for client in self.clients:
            await client.close()


# ---------------------------------------------------------------------------
# Singleton used by the rest of the app (drop-in replacement)
# ---------------------------------------------------------------------------

deepseek_ai = ParallelDeepSeekAI()
