import hmac
import hashlib
import base64
import time
import json
import httpx
import os
from typing import Optional

BITGET_BASE_URL = "https://api.bitget.com"

class BitgetClient:
    def __init__(self):
        self.api_key = os.getenv("BITGET_API_KEY", "")
        self.secret_key = os.getenv("BITGET_SECRET_KEY", "")
        self.passphrase = os.getenv("BITGET_PASSPHRASE", "")
        self.client = httpx.AsyncClient(base_url=BITGET_BASE_URL, timeout=30)

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        message = timestamp + method.upper() + path + body
        mac = hmac.new(self.secret_key.encode(), message.encode(), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _headers(self, method: str, path: str, body: str = "") -> dict:
        ts = str(int(time.time() * 1000))
        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": self._sign(ts, method, path, body),
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }

    async def get(self, path: str, params: dict = None) -> dict:
        query = ""
        if params:
            query = "?" + "&".join(f"{k}={v}" for k, v in params.items())
        headers = self._headers("GET", path + query)
        resp = await self.client.get(path + query, headers=headers)
        return resp.json()

    async def post(self, path: str, body: dict) -> dict:
        body_str = json.dumps(body)
        headers = self._headers("POST", path, body_str)
        resp = await self.client.post(path, headers=headers, content=body_str)
        return resp.json()

    # --- Market ---

    async def get_contracts(self, product_type: str = "umcbl") -> list:
        data = await self.get("/api/mix/v1/market/contracts", {"productType": product_type})
        return data.get("data", [])

    async def get_ticker(self, symbol: str) -> dict:
        data = await self.get("/api/mix/v1/market/ticker", {"symbol": symbol})
        return data.get("data", {})

    async def get_candles(self, symbol: str, granularity: str, limit: int = 100) -> list:
        data = await self.get("/api/mix/v1/market/candles", {
            "symbol": symbol,
            "granularity": granularity,
            "limit": str(limit),
        })
        return data.get("data", [])

    async def get_symbol_leverage(self, symbol: str) -> dict:
        data = await self.get("/api/mix/v1/market/symbol-leverage", {"symbol": symbol})
        return data.get("data", {})

    # --- Account ---

    async def get_account(self, symbol: str, margin_coin: str = "USDT") -> dict:
        data = await self.get("/api/mix/v1/account/account", {"symbol": symbol, "marginCoin": margin_coin})
        return data.get("data", {})

    async def set_leverage(self, symbol: str, leverage: str, margin_coin: str = "USDT", hold_side: str = "long") -> dict:
        return await self.post("/api/mix/v1/account/setLeverage", {
            "symbol": symbol,
            "marginCoin": margin_coin,
            "leverage": leverage,
            "holdSide": hold_side,
        })

    async def set_position_mode(self, symbol: str, margin_coin: str = "USDT") -> dict:
        return await self.post("/api/mix/v1/account/setPositionMode", {
            "symbol": symbol,
            "marginCoin": margin_coin,
            "holdMode": "single_hold",
        })

    async def get_positions(self, product_type: str = "umcbl") -> list:
        data = await self.get("/api/mix/v1/position/allPosition", {"productType": product_type})
        return data.get("data", [])

    async def get_account_bill(self, symbol: str, margin_coin: str = "USDT", start_time: str = None, end_time: str = None, page_size: int = 100) -> list:
        params = {"symbol": symbol, "marginCoin": margin_coin, "pageSize": str(page_size)}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        data = await self.get("/api/mix/v1/account/accountBill", params)
        return data.get("data", {}).get("result", [])

    async def get_history_positions(self, symbol: str, margin_coin: str = "USDT", page_size: int = 50) -> list:
        data = await self.get("/api/mix/v1/position/history-position", {
            "symbol": symbol,
            "marginCoin": margin_coin,
            "pageSize": str(page_size),
        })
        return data.get("data", {}).get("list", [])

    # --- Orders ---

    async def place_order(self, symbol: str, margin_coin: str, size: str, side: str, order_type: str = "market") -> dict:
        return await self.post("/api/mix/v1/order/placeOrder", {
            "symbol": symbol,
            "marginCoin": margin_coin,
            "size": size,
            "side": side,
            "orderType": order_type,
            "timeInForceValue": "normal",
        })

    async def place_plan(self, symbol: str, margin_coin: str, size: str, side: str,
                          trigger_price: str, plan_type: str) -> dict:
        return await self.post("/api/mix/v1/plan/placePlan", {
            "symbol": symbol,
            "marginCoin": margin_coin,
            "size": size,
            "side": side,
            "triggerPrice": trigger_price,
            "triggerType": "fill_price",
            "executePrice": "0",
            "planType": plan_type,
            "orderType": "market",
        })

    async def close(self):
        await self.client.aclose()

bitget = BitgetClient()