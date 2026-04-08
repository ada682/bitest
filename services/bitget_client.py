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

    # --- Market (V2) ---

    async def get_contracts(self, product_type: str = "USDT-FUTURES") -> list:
        """V2: productType uses 'USDT-FUTURES' instead of 'umcbl'"""
        resp = await self.get("/api/v2/mix/market/tickers", {"productType": product_type})
        return resp.get("data") or []

    async def get_ticker(self, symbol: str) -> dict:
        """V2 ticker. Returns single dict."""
        resp = await self.get("/api/v2/mix/market/ticker", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
        })
        data = resp.get("data")
        if isinstance(data, list) and data:
            return data[0]
        return data or {}

    async def get_candles(self, symbol: str, granularity: str, limit: int = 100) -> list:
        resp = await self.get("/api/v2/mix/market/candles", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "granularity": granularity,
            "limit": str(limit),
        })
        return resp.get("data") or []

    async def get_symbol_leverage(self, symbol: str) -> dict:
        resp = await self.get("/api/v2/mix/market/symbol-leverage", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
        })
        return resp.get("data") or {}

    # --- Account (V2) ---

    async def get_account(self, symbol: str, margin_coin: str = "USDT") -> dict:
        resp = await self.get("/api/v2/mix/account/account", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "marginCoin": margin_coin,
        })
        return resp.get("data") or {}

    async def set_leverage(self, symbol: str, leverage: str, margin_coin: str = "USDT", hold_side: str = "long") -> dict:
        return await self.post("/api/v2/mix/account/set-leverage", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "marginCoin": margin_coin,
            "leverage": leverage,
            "holdSide": hold_side,
        })

    async def set_position_mode(self, symbol: str, margin_coin: str = "USDT") -> dict:
        return await self.post("/api/v2/mix/account/set-position-mode", {
            "productType": "USDT-FUTURES",
            "posMode": "one_way_mode",
        })

    async def get_positions(self, product_type: str = "USDT-FUTURES") -> list:
        resp = await self.get("/api/v2/mix/position/all-position", {
            "productType": product_type,
            "marginCoin": "USDT",
        })
        return resp.get("data") or []

    async def get_account_bill(self, symbol: str, margin_coin: str = "USDT",
                               start_time: str = None, end_time: str = None,
                               page_size: int = 100) -> list:
        params = {
            "productType": "USDT-FUTURES",
            "pageSize": str(page_size),
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        resp = await self.get("/api/v2/mix/account/bill", params)
        data = resp.get("data")
        if isinstance(data, dict):
            return data.get("resultList") or data.get("result") or []
        return data or []

    async def get_history_positions(self, symbol: str, margin_coin: str = "USDT",
                                    page_size: int = 50) -> list:
        """V2: data is { list: [...], endId: '...' }"""
        params = {
            "productType": "USDT-FUTURES",
            "limit": str(page_size),
        }
        if symbol:
            params["symbol"] = symbol
        resp = await self.get("/api/v2/mix/position/history-position", params)
        data = resp.get("data")
        if isinstance(data, dict):
            return data.get("list") or []
        return data or []

    # --- Orders (V2) ---

    async def place_order(self, symbol: str, margin_coin: str, size: str,
                          side: str, order_type: str = "market") -> dict:
        """
        Translates V1 side strings to V2 side + tradeSide:
          open_long  -> buy  / open
          open_short -> sell / open
          close_long -> sell / close
          close_short-> buy  / close
        """
        v1_to_v2 = {
            "open_long":   ("buy",  "open"),
            "open_short":  ("sell", "open"),
            "close_long":  ("sell", "close"),
            "close_short": ("buy",  "close"),
        }
        v2_side, trade_side = v1_to_v2.get(side, (side, "open"))
        return await self.post("/api/v2/mix/order/place-order", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "marginMode": "isolated",
            "marginCoin": margin_coin,
            "size": size,
            "side": v2_side,
            "tradeSide": trade_side,
            "orderType": order_type,
            "force": "gtc",
        })

    async def place_plan(self, symbol: str, margin_coin: str, size: str, side: str,
                         trigger_price: str, plan_type: str) -> dict:
        """V2 TP/SL order via place-tpsl-order."""
        v1_to_v2 = {
            "open_long":   ("buy",  "open"),
            "open_short":  ("sell", "open"),
            "close_long":  ("sell", "close"),
            "close_short": ("buy",  "close"),
        }
        v2_side, trade_side = v1_to_v2.get(side, (side, "close"))
        pt = "profit" if plan_type == "profit_plan" else "loss"
        return await self.post("/api/v2/mix/order/place-tpsl-order", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "marginCoin": margin_coin,
            "planType": pt,
            "triggerPrice": trigger_price,
            "triggerType": "fill_price",
            "executePrice": "0",
            "size": size,
            "side": v2_side,
            "tradeSide": trade_side,
            "orderType": "market",
        })

    async def close(self):
        await self.client.aclose()


bitget = BitgetClient()
