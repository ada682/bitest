"""
DeepSeek AI integration using Web API with image support.
Flow: Upload chart image -> poll until SUCCESS -> send with OHLCV data.
"""

import asyncio
import base64
import json
import os
import time
import struct
import ctypes
import httpx
import wasmtime
from threading import Lock
from typing import Optional


DEEPSEEK_BASE = "https://chat.deepseek.com"


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
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "authorization": f"Bearer {self.token}",
            "x-client-platform": "web",
            "x-client-locale": "en_US",
            "x-client-version": "1.8.0",
            "x-app-version": "20241129.1",
            "referer": "https://chat.deepseek.com/",
            "origin": "https://chat.deepseek.com",
        }
        self.client = httpx.AsyncClient(base_url=DEEPSEEK_BASE, timeout=60)
        self._chat_session_id: Optional[str] = None
        self._parent_message_id: Optional[int] = None

    def _init_solver(self):
        if os.path.exists(self.wasm_path):
            self.solver = DeepSeekHashV1Solver(self.wasm_path)

    async def _do_pow(self, target_path: str) -> str:
        resp = await self.client.post(
            "/api/v0/chat/create_pow_challenge",
            headers={**self.headers, "Content-Type": "application/json"},
            json={"target_path": target_path},
        )
        data = resp.json()
        challenge = data.get("data", {}).get("biz_data", {}).get("challenge")
        if not challenge or not self.solver:
            return ""

        answer = self.solver.solve(challenge)
        pow_dict = {
            "algorithm": "DeepSeekHashV1",
            "challenge": challenge["challenge"],
            "salt": challenge["salt"],
            "answer": answer,
            "signature": challenge["signature"],
            "target_path": target_path,
        }
        return base64.b64encode(json.dumps(pow_dict, separators=(",", ":")).encode()).decode()

    async def _ensure_session(self):
        if not self._chat_session_id:
            resp = await self.client.post(
                "/api/v0/chat_session/create",
                headers={**self.headers, "Content-Type": "application/json"},
                json={},
            )
            data = resp.json()
            self._chat_session_id = data.get("data", {}).get("biz_data", {}).get("id")
            self._parent_message_id = None

    async def upload_image(self, image_base64: str, filename: str = "chart.png") -> Optional[str]:
        """Upload base64 image to DeepSeek, return file_id."""
        image_bytes = base64.b64decode(image_base64)

        # Get POW for upload
        pow_token = await self._do_pow("/api/v0/file/upload_file")

        upload_headers = {k: v for k, v in self.headers.items() if k != "Content-Type"}
        upload_headers["x-ds-pow-response"] = pow_token
        upload_headers["x-file-size"] = str(len(image_bytes))

        files = {"file": (filename, image_bytes, "image/png")}
        resp = await self.client.post(
            "/api/v0/file/upload_file",
            headers=upload_headers,
            files=files,
        )
        data = resp.json()
        file_id = data.get("data", {}).get("biz_data", {}).get("id")
        if not file_id:
            return None

        # Poll until SUCCESS
        for _ in range(30):
            await asyncio.sleep(1)
            poll_resp = await self.client.get(
                f"/api/v0/file/fetch_files",
                params={"file_ids": file_id},
                headers=self.headers,
            )
            poll_data = poll_resp.json()
            files_status = poll_data.get("data", {}).get("biz_data", {}).get("files", [])
            if files_status and files_status[0].get("status") == "SUCCESS":
                return file_id
            elif files_status and files_status[0].get("status") not in ("PENDING", "PARSING"):
                return None

        return None

    async def analyze(self, ohlcv_text: str, indicators: dict, chart_image_b64: str) -> dict:
        """
        Send chart image + OHLCV data to DeepSeek for trading decision.
        Returns parsed JSON decision.
        """
        await self._ensure_session()

        # Upload chart image
        file_id = await self.upload_image(chart_image_b64)
        ref_file_ids = [file_id] if file_id else []

        # Build prompt
        prompt = f"""You are a professional crypto scalping trader AI. Analyze the provided chart image AND OHLCV data below to make a trading decision.

OHLCV Data (last candles, newest last):
{ohlcv_text}

Pre-calculated Indicators:
- EMA9 (last): {indicators.get('ema9_last', 'N/A')}
- EMA21 (last): {indicators.get('ema21_last', 'N/A')}
- RSI (last): {indicators.get('rsi_last', 'N/A')}
- Parabolic SAR (last): {indicators.get('psar_last', 'N/A')}
- Current price: {indicators.get('current_price', 'N/A')}
- Trend (EMA crossover): {indicators.get('trend', 'N/A')}

Instructions:
1. Analyze the chart image for visual patterns, market structure, support/resistance
2. Validate with the OHLCV numbers above
3. Combine both signals to make your decision

IMPORTANT: Respond ONLY with a valid JSON object, no markdown, no explanation outside JSON:
{{
  "decision": "BUY" or "SELL" or "NO TRADE",
  "entry": <current price as number>,
  "tp": <take profit price as number>,
  "sl": <stop loss price as number>,
  "confidence": <0-100 as number>,
  "reason": "<brief explanation under 100 chars>"
}}

Rules:
- Only BUY or SELL if confidence > 75
- Target profit: 0.2% to 0.5%
- Stop loss: 0.15% to 0.3%
- NO TRADE if market is sideways or unclear"""

        # Get POW
        pow_token = await self._do_pow("/api/v0/chat/completion")

        comp_headers = {
            **self.headers,
            "Content-Type": "application/json",
            "x-ds-pow-response": pow_token,
        }

        payload = {
            "chat_session_id": self._chat_session_id,
            "parent_message_id": self._parent_message_id,
            "prompt": prompt,
            "ref_file_ids": ref_file_ids,
            "thinking_enabled": False,
            "search_enabled": False,
            "preempt": False,
            "model_type": "default",
        }

        full_text = ""
        response_message_id = None

        async with self.client.stream(
            "POST",
            "/api/v0/chat/completion",
            headers=comp_headers,
            json=payload,
        ) as resp:
            last_event = ""
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if line.startswith("event: "):
                    last_event = line[7:]
                    continue
                if not line.startswith("data: "):
                    continue
                content = line[6:]
                try:
                    jdata = json.loads(content)
                except Exception:
                    continue

                if last_event == "ready":
                    response_message_id = jdata.get("response_message_id")
                elif "p" in jdata and jdata["p"] == "response/fragments/-1/content":
                    full_text += jdata.get("v", "")
                elif "v" in jdata:
                    v = jdata["v"]
                    if isinstance(v, str):
                        full_text += v

        self._parent_message_id = response_message_id

        # Parse JSON from response
        try:
            # Find JSON block
            start = full_text.find("{")
            end = full_text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(full_text[start:end])
                return result
        except Exception:
            pass

        return {"decision": "NO TRADE", "entry": 0, "tp": 0, "sl": 0, "confidence": 0, "reason": "Parse error"}

    async def close(self):
        await self.client.aclose()

deepseek_ai = DeepSeekAI()