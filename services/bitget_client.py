"""
Bitget Demo Futures Client (V2 API)
====================================
- Uses X-SIMULATED-TRADING: 1 header → semua request ke demo/paper account
- Semua signed request pakai HMAC-SHA256
- Env vars: BITGET_API_KEY, BITGET_SECRET_KEY, BITGET_PASSPHRASE
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

import httpx

BITGET_BASE_URL   = "https://api.bitget.com"
PRODUCT_TYPE      = "USDT-FUTURES"
MARGIN_COIN       = "USDT"


# ---------------------------------------------------------------------------
# Symbol helpers
# ---------------------------------------------------------------------------

def bitget_to_mexc(symbol: str) -> str:
    """BTCUSDT  →  BTC_USDT  (for MEXC kline lookup)"""
    if symbol.endswith("USDT"):
        return symbol[:-4] + "_USDT"
    return symbol


def mexc_to_bitget(symbol: str) -> str:
    """BTC_USDT  →  BTCUSDT"""
    return symbol.replace("_", "")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class BitgetClient:
    def __init__(self):
        self.api_key    = os.getenv("BITGET_API_KEY",    "")
        self.secret_key = os.getenv("BITGET_SECRET_KEY", "")
        self.passphrase = os.getenv("BITGET_PASSPHRASE", "")

        self.client = httpx.AsyncClient(
            base_url=BITGET_BASE_URL,
            timeout=30,
            headers={
                "Content-Type":        "application/json",
                "locale":              "en-US",
                # ← demo / simulated trading flag
                "X-SIMULATED-TRADING": "1",
            },
        )

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        msg = timestamp + method.upper() + path + (body or "")
        mac = hmac.new(
            self.secret_key.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode()

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict:
        ts = str(int(time.time() * 1000))
        return {
            "ACCESS-KEY":       self.api_key,
            "ACCESS-SIGN":      self._sign(ts, method, path, body),
            "ACCESS-TIMESTAMP": ts,
            "ACCESS-PASSPHRASE": self.passphrase,
        }

    # ------------------------------------------------------------------
    # Generic request helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict = None, signed: bool = False) -> dict:
        try:
            qs = ""
            if params:
                qs = "?" + "&".join(f"{k}={v}" for k, v in params.items())
            full_path = path + qs
            headers   = self._auth_headers("GET", full_path) if signed else {}
            resp      = await self.client.get(path, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"code": "-1", "msg": str(e)}

    async def _post(self, path: str, body: dict, signed: bool = True) -> dict:
        try:
            body_str = json.dumps(body)
            headers  = self._auth_headers("POST", path, body_str) if signed else {}
            resp     = await self.client.post(path, content=body_str, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"code": "-1", "msg": str(e)}

    # ------------------------------------------------------------------
    # Public market data
    # ------------------------------------------------------------------

    async def get_contracts(self) -> list:
        """
        Return all active USDT-FUTURES contracts from Bitget.
        Symbol format returned: 'BTCUSDT'
        """
        resp = await self._get(
            "/api/v2/mix/market/tickers",
            {"productType": PRODUCT_TYPE},
        )
        raw = resp.get("data") or []
        result = []
        for c in raw:
            sym = c.get("symbol", "")
            if not sym:
                continue
            result.append({
                "symbol":        sym,                            # BTCUSDT
                "mexcSymbol":    bitget_to_mexc(sym),           # BTC_USDT
                "lastPrice":     c.get("lastPr",   "0"),
                "markPrice":     c.get("markPrice","0"),
                "indexPrice":    c.get("indexPrice","0"),
                "openInterest":  c.get("holdingAmount","0"),
                "fundingRate":   c.get("fundingRate","0"),
                "volume24h":     c.get("baseVolume","0"),
                "change24h":     c.get("change24h", "0"),
            })
        return result

    # ------------------------------------------------------------------
    # Account (signed — demo)
    # ------------------------------------------------------------------

    async def get_account_balance(self) -> dict:
        """Get USDT balance of demo futures account."""
        resp = await self._get(
            "/api/v2/mix/account/account",
            {"productType": PRODUCT_TYPE, "marginCoin": MARGIN_COIN},
            signed=True,
        )
        data = resp.get("data") or {}
        return {
            "available":    float(data.get("available",    0)),
            "equity":       float(data.get("accountEquity",0)),
            "unrealizedPnl":float(data.get("unrealizedPL", 0)),
            "usedMargin":   float(data.get("isolatedMargin",0)),
            "raw":          data,
        }

    # ------------------------------------------------------------------
    # Open positions (signed — demo)
    # ------------------------------------------------------------------

    async def get_open_positions(self, symbol: str = None) -> list:
        """
        Get all open positions on the demo account.
        Optional: filter by symbol (Bitget format, e.g. 'BTCUSDT')
        """
        params = {"productType": PRODUCT_TYPE, "marginCoin": MARGIN_COIN}
        if symbol:
            params["symbol"] = symbol

        resp = await self._get(
            "/api/v2/mix/position/all-position",
            params,
            signed=True,
        )
        raw = resp.get("data") or []
        positions = []
        for p in raw:
            total = float(p.get("total", 0))
            if total <= 0:
                continue  # skip empty
            positions.append({
                "symbol":        p.get("symbol"),
                "mexcSymbol":    bitget_to_mexc(p.get("symbol", "")),
                "side":          p.get("holdSide"),          # long / short
                "size":          total,
                "avgEntryPrice": float(p.get("openPriceAvg", 0)),
                "markPrice":     float(p.get("markPrice",    0)),
                "leverage":      float(p.get("leverage",     1)),
                "unrealizedPnl": float(p.get("unrealizedPL", 0)),
                "marginMode":    p.get("marginMode"),
                "orderId":       p.get("positionId"),
                "raw":           p,
            })
        return positions

    # ------------------------------------------------------------------
    # Place limit order with preset TP / SL (signed — demo)
    # ------------------------------------------------------------------

    async def place_order(
        self,
        symbol:     str,           # Bitget format  e.g. 'BTCUSDT'
        side:       str,           # 'buy' | 'sell'
        trade_side: str,           # 'open' | 'close'
        size:       str,           # contract qty as string
        price:      str,           # limit price as string
        tp_price:   Optional[str] = None,
        sl_price:   Optional[str] = None,
        margin_mode: str = "isolated",
        leverage:   int  = 10,
    ) -> dict:
        """
        Place a limit order on demo futures.
        Returns the raw Bitget response.
        """
        body: dict = {
            "symbol":      symbol,
            "productType": PRODUCT_TYPE,
            "marginMode":  margin_mode,
            "marginCoin":  MARGIN_COIN,
            "size":        str(size),
            "price":       str(price),
            "side":        side,        # 'buy' or 'sell'
            "tradeSide":   trade_side,  # 'open' or 'close'
            "orderType":   "limit",
            "leverage":    str(leverage),
        }
        if tp_price:
            body["presetStopSurplusPrice"] = str(tp_price)
        if sl_price:
            body["presetStopLossPrice"] = str(sl_price)

        resp = await self._post("/api/v2/mix/order/place-order", body)
        ok   = resp.get("code") == "00000"
        return {
            "ok":      ok,
            "orderId": (resp.get("data") or {}).get("orderId"),
            "msg":     resp.get("msg"),
            "raw":     resp,
        }

    # ------------------------------------------------------------------
    # Set TP/SL on an existing position (signed — demo)
    # ------------------------------------------------------------------

    async def place_tpsl(
        self,
        symbol:    str,
        plan_type: str,   # 'profit_loss' | 'pos_profit' | 'pos_loss'
        trigger_price: str,
        hold_side: str,   # 'long' | 'short'
        size:      str = "0",  # 0 = entire position
    ) -> dict:
        body = {
            "symbol":       symbol,
            "productType":  PRODUCT_TYPE,
            "marginCoin":   MARGIN_COIN,
            "planType":     plan_type,
            "triggerPrice": str(trigger_price),
            "holdSide":     hold_side,
            "size":         str(size),
        }
        resp = await self._post("/api/v2/mix/order/place-tpsl-order", body)
        ok   = resp.get("code") == "00000"
        return {"ok": ok, "msg": resp.get("msg"), "raw": resp}

    # ------------------------------------------------------------------
    # Close a position (market order — signed — demo)
    # ------------------------------------------------------------------

    async def close_position(
        self,
        symbol:    str,   # Bitget format
        hold_side: str,   # 'long' | 'short'
        size:      str = "0",   # 0 = full position
    ) -> dict:
        body = {
            "symbol":      symbol,
            "productType": PRODUCT_TYPE,
            "marginCoin":  MARGIN_COIN,
            "holdSide":    hold_side,
        }
        resp = await self._post("/api/v2/mix/position/close-position", body)
        ok   = resp.get("code") == "00000"
        return {"ok": ok, "msg": resp.get("msg"), "raw": resp}

    # ------------------------------------------------------------------
    # Order history (closed / filled) — signed — demo
    # ------------------------------------------------------------------

    async def get_order_history(
        self,
        symbol:    str = None,
        limit:     int = 50,
        start_time: str = None,
        end_time:   str = None,
    ) -> list:
        params = {
            "productType": PRODUCT_TYPE,
            "pageSize":    str(min(limit, 100)),
        }
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        resp = await self._get(
            "/api/v2/mix/order/history-orders",
            params,
            signed=True,
        )
        raw = (resp.get("data") or {})
        orders = raw.get("orderList") or raw if isinstance(raw, list) else []
        result = []
        for o in orders:
            result.append({
                "orderId":      o.get("orderId"),
                "symbol":       o.get("symbol"),
                "mexcSymbol":   bitget_to_mexc(o.get("symbol", "")),
                "side":         o.get("side"),
                "tradeSide":    o.get("tradeSide"),
                "orderType":    o.get("orderType"),
                "size":         o.get("size"),
                "price":        o.get("price"),
                "fillPrice":    o.get("priceAvg"),
                "fillSize":     o.get("filledQty"),
                "pnl":          o.get("pnl"),
                "status":       o.get("status"),
                "createdTime":  o.get("cTime"),
                "updatedTime":  o.get("uTime"),
                "raw":          o,
            })
        return result

    # ------------------------------------------------------------------
    # Set leverage (signed — demo)
    # ------------------------------------------------------------------

    async def set_leverage(
        self,
        symbol:    str,
        leverage:  int,
        hold_side: str = "long",  # 'long' | 'short'
    ) -> dict:
        body = {
            "symbol":      symbol,
            "productType": PRODUCT_TYPE,
            "marginCoin":  MARGIN_COIN,
            "leverage":    str(leverage),
            "holdSide":    hold_side,
        }
        resp = await self._post("/api/v2/mix/account/set-leverage", body)
        return {"ok": resp.get("code") == "00000", "msg": resp.get("msg")}

    # ------------------------------------------------------------------
    # Cancel order (signed — demo)
    # ------------------------------------------------------------------

    async def cancel_order(self, symbol: str, order_id: str) -> dict:
        body = {
            "symbol":      symbol,
            "productType": PRODUCT_TYPE,
            "orderId":     order_id,
        }
        resp = await self._post("/api/v2/mix/order/cancel-order", body)
        return {"ok": resp.get("code") == "00000", "msg": resp.get("msg")}

    async def close(self):
        await self.client.aclose()


# Singleton
bitget_client = BitgetClient()
