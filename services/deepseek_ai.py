"""
DeepSeek AI integration - Forced LONG/SHORT for scalping (NO NO TRADE)
Keep original TP/SL calculation
"""

import asyncio
import base64
import json
import os
import re
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
                raise Exception(f"Session error: {data.get('msg')}")
        
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
        Analyze market data - FORCED to return LONG or SHORT only.
        NO TRADE is not allowed for scalping.
        Uses original TP/SL calculation (0.4% tp, 0.4% sl)
        """
        await self._ensure_session()

        # Upload chart image (optional)
        ref_file_ids = []
        if chart_image_b64:
            file_id = await self.upload_image(chart_image_b64)
            if file_id:
                ref_file_ids = [file_id]

        # Extract indicators
        current_price = indicators.get('current_price', 0)
        ema9 = indicators.get('ema9_last', current_price)
        ema21 = indicators.get('ema21_last', current_price)
        rsi = indicators.get('rsi_last', 50)
        trend = indicators.get('trend', 'NEUTRAL')
        
        # Original TP/SL calculation (0.4% for both)
        tp_long = round(current_price * 1.004, 8)
        sl_long = round(current_price * 0.996, 8)
        tp_short = round(current_price * 0.996, 8)
        sl_short = round(current_price * 1.004, 8)

        # PROMPT: Force LONG or SHORT, no NO TRADE allowed
        prompt = f"""You are a scalping trading AI. You MUST choose LONG or SHORT. NO TRADE is NOT allowed.

Current Price: {current_price}
EMA9: {ema9}
EMA21: {ema21}
RSI: {rsi}
Trend: {trend}

Recent candles (oldest to newest):
{ohlcv_text}

RULES for scalping:
- LONG if: price is above EMA21 OR RSI > 55 OR uptrend OR recent candles show higher lows
- SHORT if: price is below EMA21 OR RSI < 45 OR downtrend OR recent candles show lower highs
- If both signals are weak, choose based on recent price action

You MUST respond with ONLY this JSON format. NO other text:
{{"decision": "LONG", "confidence": 85, "reason": "price above EMA21 with bullish momentum"}}

OR

{{"decision": "SHORT", "confidence": 80, "reason": "RSI below 45 with bearish candles"}}

CONFIDENCE must be between 60-100 (60=weak signal, 100=very strong)
decision MUST be either "LONG" or "SHORT" - never "NO TRADE""""

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
                    return self._forced_response(current_price, tp_long, sl_long, tp_short, sl_short, 
                                                "LONG" if current_price >= ema21 else "SHORT", 
                                                "API error, defaulting based on EMA")
                
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

            # Parse response
            try:
                # Fix missing braces
                if full_text and not full_text.startswith('{'):
                    if full_text.startswith('"decision"') or full_text.startswith('decision'):
                        full_text = '{' + full_text
                if full_text and not full_text.endswith('}'):
                    full_text = full_text + '}'
                
                start = full_text.find("{")
                end = full_text.rfind("}") + 1
                
                if start >= 0 and end > start:
                    result = json.loads(full_text[start:end])
                    decision = result.get("decision", "LONG").upper()
                    confidence = result.get("confidence", 70)
                    reason = result.get("reason", "AI analysis")
                else:
                    # Regex fallback
                    decision_match = re.search(r'"decision"?:\s*"(LONG|SHORT)"', full_text, re.IGNORECASE)
                    decision = decision_match.group(1).upper() if decision_match else ("LONG" if current_price >= ema21 else "SHORT")
                    
                    conf_match = re.search(r'"confidence"?:\s*(\d+)', full_text)
                    confidence = int(conf_match.group(1)) if conf_match else 70
                    
                    reason_match = re.search(r'"reason"?:\s*"([^"]+)"', full_text)
                    reason = reason_match.group(1) if reason_match else "Technical analysis"
                
                # Force decision to be LONG or SHORT
                if decision not in ["LONG", "SHORT"]:
                    decision = "LONG" if current_price >= ema21 else "SHORT"
                    confidence = 65
                    reason = f"Default: price {'above' if decision == 'LONG' else 'below'} EMA21"
                
                # Build response with original TP/SL
                if decision == "LONG":
                    return {
                        "decision": "LONG",
                        "entry": current_price,
                        "tp": tp_long,
                        "sl": sl_long,
                        "confidence": min(100, max(60, confidence)),
                        "reason": reason
                    }
                else:
                    return {
                        "decision": "SHORT",
                        "entry": current_price,
                        "tp": tp_short,
                        "sl": sl_short,
                        "confidence": min(100, max(60, confidence)),
                        "reason": reason
                    }
                    
            except Exception:
                # Default fallback - always return LONG or SHORT
                return self._forced_response(current_price, tp_long, sl_long, tp_short, sl_short, 
                                            "LONG" if current_price >= ema21 else "SHORT", 
                                            "Fallback based on EMA position")
            
        except Exception:
            return self._forced_response(current_price, tp_long, sl_long, tp_short, sl_short,
                                        "LONG" if current_price >= ema21 else "SHORT",
                                        "Emergency fallback")

    def _forced_response(self, price: float, tp_long: float, sl_long: float, 
                         tp_short: float, sl_short: float, decision: str, reason: str) -> dict:
        """Return forced response when AI fails - never NO TRADE"""
        if decision == "LONG":
            return {
                "decision": "LONG",
                "entry": price,
                "tp": tp_long,
                "sl": sl_long,
                "confidence": 65,
                "reason": reason
            }
        else:
            return {
                "decision": "SHORT",
                "entry": price,
                "tp": tp_short,
                "sl": sl_short,
                "confidence": 65,
                "reason": reason
            }

    async def close(self):
        await self.client.aclose()


deepseek_ai = DeepSeekAI()
