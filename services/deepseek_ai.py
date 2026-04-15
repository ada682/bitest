"""
DeepSeek AI integration - Void/Wick pattern strategy signal generator.
Signal only (no auto-trade). Uses OHLCV text only, no chart images.
"""

import json
import os
import re
import base64
import struct
import ctypes
import httpx
import wasmtime
from threading import Lock
from typing import Optional

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

Below is OHLCV data that represents VALID trading setups based on a custom strategy.

Your job:
1. Study the patterns in the data
2. Identify what makes these setups valid
3. Apply the SAME logic to new data

Focus on:
- Price structure (trend)
- Wick behavior (rejection / inefficiency)
- Areas where price leaves imbalance (void)
- Relationship between candles

Then analyze the NEW data using the SAME behavior.

Output:
- Trend
- Key pattern detected
- Entry (LONG / SHORT / NO TRADE)
- Entry price
- Short reasoning

IMPORTANT:
Do NOT use generic indicators.
ONLY mimic the pattern from the training examples.

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


class DeepSeekAI:
    def __init__(self):
        self.token = os.getenv("DEEPSEEK_TOKEN", "")
        self.wasm_path = os.getenv("DEEPSEEK_WASM_PATH", "sha3.wasm")
        self.solver = None
        self._init_solver()

        self.headers = WORKING_HEADERS.copy()
        self.headers["authorization"] = f"Bearer {self.token}"

        self.client = httpx.AsyncClient(base_url=DEEPSEEK_BASE, timeout=120)
        self._chat_session_id: Optional[str] = None
        self._parent_message_id: Optional[int] = None

    def _init_solver(self):
        if os.path.exists(self.wasm_path):
            print(f"✅ Loading WASM: {self.wasm_path}")
            self.solver = DeepSeekHashV1Solver(self.wasm_path)
        else:
            print(f"⚠️ WASM not found: {self.wasm_path}")

    async def _do_pow(self, target_path: str) -> str:
        try:
            resp = await self.client.post(
                "/api/v0/chat/create_pow_challenge",
                headers=self.headers,
                json={"target_path": target_path},
            )
            data = resp.json()
            if data.get("code") != 0:
                return ""
            challenge = data.get("data", {}).get("biz_data", {}).get("challenge")
            if not challenge or not self.solver:
                return ""
            answer = self.solver.solve(challenge)
            if answer is None:
                return ""
            pow_dict = {
                "algorithm": "DeepSeekHashV1",
                "challenge": challenge["challenge"],
                "salt": challenge["salt"],
                "answer": answer,
                "signature": challenge["signature"],
                "target_path": target_path,
            }
            return base64.b64encode(json.dumps(pow_dict, separators=(",", ":")).encode()).decode()
        except Exception:
            return ""

    async def _ensure_session(self):
        if not self._chat_session_id:
            resp = await self.client.post(
                "/api/v0/chat_session/create",
                headers=self.headers,
                json={},
            )
            data = resp.json()
            if data.get("code") != 0:
                raise Exception(f"Session error: {data.get('msg')}")
            biz_data = data.get("data", {}).get("biz_data", {})
            chat_session = biz_data.get("chat_session", {})
            self._chat_session_id = chat_session.get("id")

    async def analyze(self, symbol: str, candles_by_tf: dict) -> dict:
        """
        Analyze OHLCV data across multiple timeframes using void/wick strategy.

        candles_by_tf: {
            "3m":  [[ts, o, h, l, c, v], ...],
            "5m":  [...],
            "15m": [...],
            "30m": [...],
            "1h":  [...],
            "2h":  [...],
            "4h":  [...],
        }

        Returns:
        {
            "trend": str,
            "pattern": str,
            "decision": "LONG" | "SHORT" | "NO TRADE",
            "entry": float | None,
            "reason": str,
            "confidence": int,
        }
        """
        await self._ensure_session()

        # Build OHLCV text block for each timeframe
        tf_blocks = []
        last_price = None
        for tf in ["3m", "5m", "15m", "30m", "1h", "2h", "4h"]:
            candles = candles_by_tf.get(tf, [])
            if not candles:
                continue
            lines = [f"=== {symbol} | {tf} (last {min(len(candles), 50)} candles) ==="]
            lines.append("timestamp, open, high, low, close, volume")
            for c in candles[-50:]:
                lines.append(f"{c[0]}, {c[1]}, {c[2]}, {c[3]}, {c[4]}, {c[5]}")
            tf_blocks.append("\n".join(lines))
            if candles:
                last_price = float(candles[-1][4])

        ohlcv_section = "\n\n".join(tf_blocks) if tf_blocks else "No candle data available."

        prompt = f"""{SYSTEM_PROMPT}

---

analyst {symbol}

{ohlcv_section}

---

Now analyze the data above using the SAME void/wick imbalance pattern from the training examples.
Current live price (latest close): {last_price}

You MUST respond in this EXACT JSON format ONLY — no extra text:
{{
  "trend": "UP" or "DOWN" or "SIDEWAYS",
  "pattern": "brief description of what pattern you detected",
  "decision": "LONG" or "SHORT" or "NO TRADE",
  "entry": <entry price as float, or null if NO TRADE>,
  "tp": <take profit price as float, or null if NO TRADE>,
  "sl": <stop loss price as float, or null if NO TRADE>,
  "reason": "short explanation referencing the void/wick imbalance",
  "confidence": <integer 0-100>
}}

If there is NO clear void/imbalance setup, return "NO TRADE" — do NOT force a trade."""

        pow_token = await self._do_pow("/api/v0/chat/completion")
        comp_headers = {**self.headers, "x-ds-pow-response": pow_token}

        payload = {
            "chat_session_id": self._chat_session_id,
            "parent_message_id": self._parent_message_id,
            "prompt": prompt,
            "ref_file_ids": [],
            "thinking_enabled": True,
            "search_enabled": False,
            "preempt": False,
        }

        full_text = ""
        in_thinking = False

        try:
            async with self.client.stream(
                "POST",
                "/api/v0/chat/completion",
                headers=comp_headers,
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    return self._no_trade_response("API error")

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    content_chunk = line[6:]
                    if not content_chunk or content_chunk == "{}":
                        continue
                    try:
                        jdata = json.loads(content_chunk)
                        chunk = jdata.get("v", "")
                        if not isinstance(chunk, str):
                            continue
                        if "<think>" in chunk:
                            in_thinking = True
                            before, _, rest = chunk.partition("<think>")
                            if before:
                                full_text += before
                        elif "</think>" in chunk:
                            in_thinking = False
                            _, _, after = chunk.partition("</think>")
                            if after:
                                full_text += after
                        elif not in_thinking:
                            full_text += chunk
                    except Exception:
                        pass

            # Parse JSON response
            start = full_text.find("{")
            end = full_text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(full_text[start:end])
                decision = result.get("decision", "NO TRADE").upper()
                if decision not in ("LONG", "SHORT", "NO TRADE"):
                    decision = "NO TRADE"
                return {
                    "trend": result.get("trend", "SIDEWAYS"),
                    "pattern": result.get("pattern", ""),
                    "decision": decision,
                    "entry": result.get("entry"),
                    "tp": result.get("tp"),
                    "sl": result.get("sl"),
                    "reason": result.get("reason", ""),
                    "confidence": int(result.get("confidence", 0)),
                }
            else:
                return self._no_trade_response("Failed to parse AI response")

        except Exception as e:
            return self._no_trade_response(f"Exception: {str(e)}")

    def _no_trade_response(self, reason: str) -> dict:
        return {
            "trend": "SIDEWAYS",
            "pattern": "none",
            "decision": "NO TRADE",
            "entry": None,
            "tp": None,
            "sl": None,
            "reason": reason,
            "confidence": 0,
        }

    async def close(self):
        await self.client.aclose()


deepseek_ai = DeepSeekAI()
