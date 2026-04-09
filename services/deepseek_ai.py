"""
DeepSeek AI integration using Web API with image support.
Using Android headers (proven working) with full debugging.
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

# DeepSeek Base URL
DEEPSEEK_BASE = "https://chat.deepseek.com"

# HEADERS ANDROID (dari repository yang terbukti berhasil)
ANDROID_HEADERS = {
    "Host": "chat.deepseek.com",
    "User-Agent": "DeepSeek/1.0.13 Android/35",
    "Accept": "application/json",
    "Accept-Encoding": "identity",
    "Content-Type": "application/json",
    "x-client-platform": "android",
    "x-client-version": "1.3.0-auto-resume",
    "x-client-locale": "zh_CN",
    "accept-charset": "UTF-8",
    "referer": "https://chat.deepseek.com/",
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
        
        # Initialize headers dengan ANDROID version
        self.headers = ANDROID_HEADERS.copy()
        if self.token:
            self.headers["authorization"] = f"Bearer {self.token}"
        
        # Create client
        self.client = httpx.AsyncClient(base_url=DEEPSEEK_BASE, timeout=120.0)
        
        self._chat_session_id: Optional[str] = None
        self._parent_message_id: Optional[int] = None

    def _init_solver(self):
        """Initialize WebAssembly solver for PoW"""
        if os.path.exists(self.wasm_path):
            print(f"✅ Loading WASM from: {self.wasm_path}")
            self.solver = DeepSeekHashV1Solver(self.wasm_path)
        else:
            print(f"⚠️ WASM file not found at: {self.wasm_path}")

    async def _do_pow(self, target_path: str) -> str:
        """Get PoW token for DeepSeek API."""
        try:
            resp = await self.client.post(
                "/api/v0/chat/create_pow_challenge",
                headers=self.headers,
                json={"target_path": target_path},
            )
            data = resp.json()
            
            if data.get("code") != 0:
                print(f"⚠️ PoW challenge error: {data.get('msg')}")
                return ""
            
            challenge = data.get("data", {}).get("biz_data", {}).get("challenge")
            if not challenge or not self.solver:
                print("⚠️ No challenge or solver available")
                return ""

            print(f"🔐 Solving PoW for {target_path}...")
            answer = self.solver.solve(challenge)
            if answer is None:
                print("❌ Failed to solve PoW")
                return ""
            
            pow_dict = {
                "algorithm": "DeepSeekHashV1",
                "challenge": challenge["challenge"],
                "salt": challenge["salt"],
                "answer": answer,
                "signature": challenge["signature"],
                "target_path": target_path,
            }
            pow_token = base64.b64encode(json.dumps(pow_dict, separators=(",", ":")).encode()).decode()
            print(f"✅ PoW solved: {answer}")
            return pow_token
        except Exception as e:
            print(f"❌ PoW error: {e}")
            return ""

    async def _ensure_session(self):
        """Create or ensure chat session exists."""
        if not self._chat_session_id:
            print(f"🔐 Creating DeepSeek session...")
        
            resp = await self.client.post(
                "/api/v0/chat_session/create",
                headers=self.headers,
                json={},
            )
        
            print(f"📦 Session create response status: {resp.status_code}")
        
            try:
                data = resp.json()
                print(f"📄 Response: code={data.get('code')}")
            except Exception as e:
                print(f"❌ Failed to parse response: {e}")
                raise
        
            if data.get("code") != 0:
                error_msg = data.get("msg", "Unknown error")
                print(f"❌ DeepSeek API error: {error_msg}")
                raise Exception(f"DeepSeek API error: {error_msg}")
        
            biz_data = data.get("data", {}).get("biz_data", {})
            chat_session = biz_data.get("chat_session", {})
            self._chat_session_id = chat_session.get("id")
            self._parent_message_id = None
        
            if self._chat_session_id:
                print(f"✅ Created DeepSeek session: {self._chat_session_id}")
            else:
                raise Exception("No session ID returned from DeepSeek")

    async def upload_image(self, image_base64: str, filename: str = "image.png") -> Optional[str]:
        """Upload base64 image to DeepSeek, return file_id."""
        if not image_base64:
            return None
        
        try:
            image_bytes = base64.b64decode(image_base64)
            print(f"📸 Image size: {len(image_bytes)} bytes")
        except Exception as e:
            print(f"❌ Failed to decode base64 image: {e}")
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
                print(f"❌ Upload failed: {data.get('msg')}")
                return None
                
            file_id = data.get("data", {}).get("biz_data", {}).get("id")
            if not file_id:
                return None
                
            print(f"📤 File uploaded: {file_id}")
            
            # Poll until SUCCESS
            for attempt in range(30):
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
                    print(f"  Poll {attempt+1}: {status}")
                    
                    if status == "SUCCESS":
                        print(f"✅ File ready!")
                        return file_id
                    elif status in ("FAILED", "ERROR"):
                        return None
            
            return None
            
        except Exception as e:
            print(f"❌ Upload error: {e}")
            return None

    async def analyze(self, ohlcv_text: str, indicators: dict, chart_image_b64: str = None) -> dict:
        """
        Send chart image + OHLCV data to DeepSeek for trading decision.
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

        # Simple prompt for testing
        current_price = indicators.get('current_price', 0)
        
        prompt = f"""Current price: {current_price}
EMA9: {indicators.get('ema9_last', 'N/A')}
EMA21: {indicators.get('ema21_last', 'N/A')}
RSI: {indicators.get('rsi_last', 'N/A')}

Respond with JSON: {{"decision": "BUY" or "SELL" or "NO TRADE", "confidence": 0-100}}"""

        # Get POW for chat completion
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

        print(f"🤖 Sending request to DeepSeek...")
        print(f"   Session: {self._chat_session_id}")
        
        full_text = ""
        response_message_id = None

        try:
            async with self.client.stream(
                "POST",
                "/api/v0/chat/completion",
                headers=comp_headers,
                json=payload,
            ) as resp:
                print(f"📡 Response status: {resp.status_code}")
                print(f"📡 Response headers: {dict(resp.headers)}")
                
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    print(f"❌ Error response: {error_text.decode()[:500]}")
                    return {"decision": "NO TRADE", "reason": f"HTTP {resp.status_code}"}
                
                async for line in resp.aiter_lines():
                    if line:
                        print(f"📨 LINE: {line[:200]}")  # DEBUG: print every line
                        
                    if not line:
                        continue
                    
                    if line.startswith("event: "):
                        event_type = line[7:]
                        print(f"   Event: {event_type}")
                        continue
                        
                    if not line.startswith("data: "):
                        continue
                        
                    content = line[6:]
                    if not content or content == "{}":
                        continue
                        
                    try:
                        jdata = json.loads(content)
                        
                        # Extract text from response
                        if "v" in jdata and isinstance(jdata["v"], str):
                            full_text += jdata["v"]
                            print(f"   + Text chunk: {jdata['v'][:50]}")
                            
                        elif "choices" in jdata:
                            # OpenAI format
                            delta = jdata["choices"][0].get("delta", {})
                            if "content" in delta:
                                full_text += delta["content"]
                                
                    except json.JSONDecodeError:
                        pass

            print(f"\n📝 Full response ({len(full_text)} chars):")
            print(full_text[:500])
            
            self._parent_message_id = response_message_id

            # Parse JSON
            try:
                start = full_text.find("{")
                end = full_text.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(full_text[start:end])
                    print(f"✅ Parsed: {result}")
                    return result
            except Exception as e:
                print(f"❌ Parse error: {e}")

            return {"decision": "NO TRADE", "confidence": 0, "reason": "No valid JSON"}
            
        except Exception as e:
            print(f"❌ Chat completion error: {e}")
            import traceback
            traceback.print_exc()
            return {"decision": "NO TRADE", "reason": str(e)}

    async def close(self):
        await self.client.aclose()


deepseek_ai = DeepSeekAI()
