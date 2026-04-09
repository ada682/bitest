"""
DeepSeek AI integration using Web API with image support.
Updated with Android headers, Chinese locale, and thinking_enabled.
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

# Konfigurasi seperti deepseek_wrapper.py yang lancar
DEEPSEEK_BASE = "https://chat.deepseek.com"

# Headers ala Android + Chinese locale (mirip wrapper yang lancar)
BASE_HEADERS = {
    "Host": "chat.deepseek.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "x-client-platform": "web",  # Ganti dari android ke web
    "x-client-version": "1.8.0",  # Versi terbaru
    "x-app-version": "20241129.1",
    "x-client-locale": "en_US",  # Ganti dari zh_CN
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
        # Gunakan headers ala Android
        self.headers = BASE_HEADERS.copy()
        self.headers["authorization"] = f"Bearer {self.token}"
        self.client = httpx.AsyncClient(base_url=DEEPSEEK_BASE, timeout=60)
        self._chat_session_id: Optional[str] = None
        self._parent_message_id: Optional[int] = None

    def _init_solver(self):
        if os.path.exists(self.wasm_path):
            self.solver = DeepSeekHashV1Solver(self.wasm_path)

    async def _do_pow(self, target_path: str) -> str:
        """Get PoW token for DeepSeek API."""
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

    async def _get_cookies(self):
        """Get initial cookies from DeepSeek homepage"""
        resp = await self.client.get("https://chat.deepseek.com/")
        cookies = resp.cookies
        ds_session_id = cookies.get("ds_session_id")
        if ds_session_id:
            self.headers["cookie"] = f"ds_session_id={ds_session_id}"
        return ds_session_id

    async def _ensure_session(self):
        """Create or ensure chat session exists."""
        if not self._chat_session_id:
            print(f"🔐 Creating DeepSeek session with token: {self.token[:20]}...")
    
            resp = await self.client.post(
                "/api/v0/chat_session/create",
                headers=self.headers,
                json={},
            )
    
            print(f"📦 Session create response status: {resp.status_code}")
    
            try:
                data = resp.json()
                print(f"📄 Response body: {json.dumps(data, indent=2)[:500]}")
            except Exception as e:
                print(f"❌ Failed to parse response: {e}")
                print(f"Raw response: {resp.text[:500]}")
                raise
    
        # Cek apakah ada error
            if data.get("code") != 0:
                error_msg = data.get("msg", "Unknown error")
                print(f"❌ DeepSeek API error: {error_msg}")
                raise Exception(f"DeepSeek API error: {error_msg}")
    
        # FIX: Extract session ID from correct path
            biz_data = data.get("data", {}).get("biz_data", {})
            if biz_data is None:
                print(f"❌ biz_data is None. Full response: {data}")
                raise Exception("Failed to create session: biz_data is None")
        
        # Get chat_session object
            chat_session = biz_data.get("chat_session", {})
            if not chat_session:
                print(f"❌ No chat_session in biz_data: {biz_data}")
                raise Exception("No chat_session in response")
        
            self._chat_session_id = chat_session.get("id")
            self._parent_message_id = None
    
            if self._chat_session_id:
                print(f"✅ Created DeepSeek session: {self._chat_session_id}")
            else:
                print(f"❌ No session ID in response: {biz_data}")
                raise Exception("No session ID returned from DeepSeek")

    async def upload_image(self, image_base64: str, filename: str = "chart.png") -> Optional[str]:
        """Upload base64 image to DeepSeek, return file_id."""
        if not image_base64:
            print("❌ No image data provided")
            return None
        
        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception as e:
            print(f"❌ Failed to decode base64 image: {e}")
            return None

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

    async def analyze(self, ohlcv_text: str, indicators: dict, chart_image_b64: str = None) -> dict:
        """
        Send chart image + OHLCV data to DeepSeek for trading decision.
        Returns parsed JSON decision.
        """
        await self._ensure_session()

        # Upload chart image (optional)
        ref_file_ids = []
        if chart_image_b64:
            print("📤 Uploading chart image...")
            file_id = await self.upload_image(chart_image_b64)
            if file_id:
                ref_file_ids = [file_id]
                print(f"✅ Chart uploaded: {file_id}")
            else:
                print("⚠️ Chart upload failed, continuing without image")

        # Build prompt - lebih sederhana seperti wrapper yang lancar
        prompt = f"""You are a professional crypto scalping trader AI. Analyze the data below to make a trading decision.

Current Price: {indicators.get('current_price', 'N/A')}
EMA9: {indicators.get('ema9_last', 'N/A')}
EMA21: {indicators.get('ema21_last', 'N/A')}
RSI: {indicators.get('rsi_last', 'N/A')}
Trend: {indicators.get('trend', 'N/A')}

OHLCV Data (last candles, newest last):
{ohlcv_text}

IMPORTANT: Respond ONLY with a valid JSON object, no markdown, no explanation outside JSON:
{{"decision": "BUY" or "SELL" or "NO TRADE", "entry": {indicators.get('current_price', 0)}, "tp": {indicators.get('current_price', 0) * 1.004}, "sl": {indicators.get('current_price', 0) * 0.996}, "confidence": 0-100, "reason": "brief explanation"}}

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
            "thinking_enabled": True,  # <-- AKTIF!
            "search_enabled": False,
            "preempt": False,
            "model_type": "default",
        }

        print(f"🤖 Sending request to DeepSeek with thinking_enabled=True...")
        
        full_text = ""
        thinking_text = ""
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
                elif "p" in jdata:
                    p = jdata["p"]
                    v = str(jdata.get("v", ""))
                    if p == "response/content":
                        full_text += v
                    elif p == "thinking/content":
                        thinking_text += v
                    elif p == "response/start":
                        pass
                    elif p == "response/end":
                        pass
                    elif p == "thinking/start":
                        pass
                    elif p == "thinking/end":
                        pass
                elif "v" in jdata:
                    v = jdata["v"]
                    if isinstance(v, str):
                        full_text += v

        self._parent_message_id = response_message_id

        if thinking_text:
            print(f"🧠 Thinking ({len(thinking_text)} chars): {thinking_text[:200]}...")

        print(f"📝 Response ({len(full_text)} chars): {full_text[:300]}...")

        # Parse JSON dari response
        try:
            # Cari JSON object
            start = full_text.find("{")
            end = full_text.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = full_text[start:end]
                result = json.loads(json_str)
                print(f"✅ Parsed result: {result}")
                return result
        except Exception as e:
            print(f"❌ JSON Parse error: {e}")
            print(f"Raw response: {full_text[:500]}")

        # Fallback: coba cari dengan regex
        import re
        json_pattern = r'\{[^{}]*"decision"[^{}]*\}'
        matches = re.findall(json_pattern, full_text)
        if matches:
            try:
                result = json.loads(matches[0])
                print(f"✅ Regex parsed: {result}")
                return result
            except:
                pass

        return {"decision": "NO TRADE", "entry": 0, "tp": 0, "sl": 0, "confidence": 0, "reason": "Parse error"}

    async def close(self):
        await self.client.aclose()


deepseek_ai = DeepSeekAI()
