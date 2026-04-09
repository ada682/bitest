import hmac
import hashlib
import base64
import time
import json
import httpx
import os

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
        """V2 tickers endpoint — returns all symbols with price info."""
        resp = await self.get("/api/v2/mix/market/tickers", {"productType": product_type})
        raw = resp.get("data") or []
        # Normalize to match what frontend expects
        result = []
        for c in raw:
            sym = c.get("symbol", "")
            result.append({
                "symbol": sym,
                "baseCoin": sym.replace("USDT", ""),
                "quoteCoin": "USDT",
                "lastPrice": c.get("lastPr", "0"),
                "volume24h": c.get("usdtVolume", "0"),
                "minTradeNum": c.get("minTradeNum", "1"),
                "volumePlace": c.get("volumePlace", "3"),
                "pricePlace": c.get("pricePlace", "2"),
                "maxLeverage": c.get("maxLeverage", "125"),
            })
        return result

    async def get_ticker(self, symbol: str) -> dict:
        """V2 ticker. V2 uses 'lastPr' — we add 'last' alias for compat."""
        resp = await self.get("/api/v2/mix/market/ticker", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
        })
        data = resp.get("data")
        if isinstance(data, list) and data:
            t = data[0]
        elif isinstance(data, dict):
            t = data
        else:
            return {}
        # Add V1-compatible aliases so frontend doesn't break
        t["last"] = t.get("lastPr", "0")
        t["bestAsk"] = t.get("askPr", "0")
        t["bestBid"] = t.get("bidPr", "0")
        t["priceChangePercent"] = t.get("change24h", "0")
        return t

    async def get_candles(self, symbol: str, granularity: str, limit: int = 100) -> list:
        """V2 candles. Format: [ts, open, high, low, close, baseVol, quoteVol]"""
        symbol = self._clean_symbol(symbol)
    
        print(f"🔍 Fetching candles for {symbol} with granularity {granularity}")
    
        resp = await self.get("/api/v2/mix/market/candles", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "granularity": granularity,
            "limit": str(limit),
        })
    
        print(f"📦 Response code: {resp.get('code')}")
    
        data = resp.get("data")
        if data and isinstance(data, list):
            print(f"✅ Raw data length: {len(data)}")
            if len(data) > 0:
                print(f"📊 Sample candle: {data[0]}")
        
            cleaned_data = []
            for candle in data:
                if isinstance(candle, list) and len(candle) >= 7:
                    cleaned_candle = [
                        int(candle[0]),      # timestamp
                        float(candle[1]),    # open
                        float(candle[2]),    # high
                        float(candle[3]),    # low
                        float(candle[4]),    # close
                        float(candle[5]),    # base volume
                        float(candle[6]),    # quote volume
                    ]
                    cleaned_data.append(cleaned_candle)
            print(f"✅ Cleaned data length: {len(cleaned_data)}")
            return cleaned_data
    
        print(f"❌ No data or invalid format: {type(data)}")
        return data or []

    async def get_symbol_leverage(self, symbol: str) -> dict:
        resp = await self.get("/api/v2/mix/market/symbol-leverage", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
        })
        return resp.get("data") or {}

    # --- Account (V2) ---

    async def get_futures_account(self, symbol: str = "BTCUSDT", margin_coin: str = "USDT") -> dict:
        """Get futures account balance for a specific symbol."""
        resp = await self.get("/api/v2/mix/account/account", {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "marginCoin": margin_coin,
        })
        return resp.get("data") or {}

    async def get_all_futures_accounts(self) -> list:
        """Get all futures account balances across all margin coins."""
        resp = await self.get("/api/v2/mix/account/accounts", {
            "productType": "USDT-FUTURES",
        })
        return resp.get("data") or []

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
        params = {"productType": "USDT-FUTURES", "pageSize": str(page_size)}
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
        """V2: data = { list: [...], endId: '...' }"""
        params = {"productType": "USDT-FUTURES", "limit": str(page_size)}
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
