"""
DeepSeek AI integration - No bias, pure technical analysis
"""

import asyncio
import base64
import json
import os
import struct
import ctypes
import httpx
import wasmtime
from threading import Lock
from typing import Optional

DEEPSEEK_BASE = "https://chat.deepseek.com"

# Headers from working inspect element
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
                raise Exception(f"DeepSeek API error: {data.get('msg')}")
        
            biz_data = data.get("data", {}).get("biz_data", {})
            chat_session = biz_data.get("chat_session", {})
            self._chat_session_id = chat_session.get("id")

    async def upload_image(self, image_base64: str, filename: str = "image.png") -> Optional[str]:
        if not image_base64:
            return None
        
        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception:
            return None

        pow_token = await self._do_pow("/api/v0/file/upload_file")

        upload_headers = {k: v for k, v in self.headers.items() if k != "Content-Type"}
        upload_headers["x-ds-pow-response"] = pow_token
        upload_headers["x-file-size"] = str(len(image_bytes))

        files = {"file": (filename, image_bytes, "image/png")}
        
        try:
            resp = await self.client.post(
                "/api/v0/file/upload_file",
                headers=upload_headers,
                files=files,
            )
            data = resp.json()
            
            if data.get("code") != 0:
                return None
                
            file_id = data.get("data", {}).get("biz_data", {}).get("id")
            if not file_id:
                return None
            
            # Poll until SUCCESS
            for _ in range(30):
                await asyncio.sleep(1)
                poll_resp = await self.client.get(
                    "/api/v0/file/fetch_files",
                    params={"file_ids": file_id},
                    headers=self.headers,
                )
                poll_data = poll_resp.json()
                files_data = poll_data.get("data", {}).get("biz_data", {}).get("files", [])
                
                if files_data:
                    status = files_data[0].get("status")
                    if status == "SUCCESS":
                        return file_id
                    elif status in ("FAILED", "ERROR"):
                        return None
            
            return None
            
        except Exception:
            return None

    async def analyze(self, ohlcv_text: str, indicators: dict, chart_image_b64: str = None) -> dict:
        """
        Analyze market data and return trading decision.
        No bias - pure technical analysis based on indicators.
        """
        await self._ensure_session()

        # Upload chart image (optional)
        ref_file_ids = []
        if chart_image_b64:
            file_id = await self.upload_image(chart_image_b64)
            if file_id:
                ref_file_ids = [file_id]

        # Extract indicators with defaults
        current_price = indicators.get('current_price', 0)
        ema9 = indicators.get('ema9_last', current_price)
        ema21 = indicators.get('ema21_last', current_price)
        rsi = indicators.get('rsi_last', 50)
        trend = indicators.get('trend', 'NEUTRAL')
        
        # Calculate dynamic TP/SL based on ATR or fixed percentages
        tp_long = round(current_price * 1.004, 8)
        sl_long = round(current_price * 0.996, 8)
        tp_short = round(current_price * 0.996, 8)
        sl_short = round(current_price * 1.004, 8)

        # Neutral prompt - let AI decide based on data only
        prompt = f"""Analyze this crypto market data objectively. No bias.

=== DATA ===
Price: {current_price}
EMA9: {ema9}
EMA21: {ema21}
RSI: {rsi}
Trend: {trend}

=== OHLCV ===
{ohlcv_text}

=== RULES ===
- LONG 
- SHORT 
- SCALP TRADE OR DIE
- Minimum confidence: 65

=== OUTPUT ===
Respond ONLY with JSON. No markdown, no explanation:

{{"decision": "LONG" or "SHORT", "entry": {current_price}, "tp_long": {tp_long}, "sl_long": {sl_long}, "tp_short": {tp_short}, "sl_short": {sl_short}, "confidence": 0-100, "reason": "one sentence"}}"""

        pow_token = await self._do_pow("/api/v0/chat/completion")

        comp_headers = {
            **self.headers,
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
        }

        full_text = ""

        try:
            async with self.client.stream(
                "POST",
                "/api/v0/chat/completion",
                headers=comp_headers,
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    return self._default_response(current_price, "HTTP error")
                
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    
                    content = line[6:]
                    if not content or content == "{}":
                        continue
                        
                    try:
                        jdata = json.loads(content)
                        if "v" in jdata and isinstance(jdata["v"], str):
                            full_text += jdata["v"]
                    except:
                        pass

            # Parse JSON response
            try:
                start = full_text.find("{")
                end = full_text.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(full_text[start:end])
                    
                    # Ensure required fields exist
                    if "decision" not in result:
                        result["decision"] = "NO TRADE"
                    if "confidence" not in result:
                        result["confidence"] = 0
                    if "entry" not in result or result["entry"] == 0:
                        result["entry"] = current_price
                    
                    # Add TP/SL based on decision
                    if result["decision"] == "LONG":
                        result["tp"] = result.get("tp_long", tp_long)
                        result["sl"] = result.get("sl_long", sl_long)
                    elif result["decision"] == "SHORT":
                        result["tp"] = result.get("tp_short", tp_short)
                        result["sl"] = result.get("sl_short", sl_short)
                    else:
                        result["tp"] = 0
                        result["sl"] = 0
                    
                    return result
                    
            except json.JSONDecodeError:
                pass
            
            return self._default_response(current_price, "Parse error")
            
        except Exception:
            return self._default_response(current_price, "API error")

    def _default_response(self, current_price: float, reason: str) -> dict:
        """Return safe default response"""
        return {
            "decision": "NO TRADE",
            "entry": current_price,
            "tp": 0,
            "sl": 0,
            "confidence": 0,
            "reason": reason
        }

    async def close(self):
        await self.client.aclose()


deepseek_ai = DeepSeekAI()
