"""
Bitget Private WebSocket — Real-time position & order updates (demo account).
=============================================================================
- Connect ke wss://ws.bitget.com/v2/ws/private
- Login otomatis dengan HMAC sign
- Subscribe: positions + orders channel
- Broadcast ke frontend via ws_manager
- Auto-reconnect jika putus
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from services.ws_manager import ws_manager

logger = logging.getLogger(__name__)

BITGET_WS_PRIVATE = "wss://ws.bitget.com/v2/ws/private"
PRODUCT_TYPE      = "USDT-FUTURES"


class BitgetPrivateWS:
    """
    Maintain a single persistent WebSocket to Bitget private channel.
    Receives position & order snapshots and broadcasts them to the
    frontend WebSocket clients via ws_manager.
    """

    def __init__(self):
        self.api_key    = os.getenv("BITGET_API_KEY",    "")
        self.secret_key = os.getenv("BITGET_SECRET_KEY", "")
        self.passphrase = os.getenv("BITGET_PASSPHRASE", "")

        self._ws:        Optional[websockets.WebSocketClientProtocol] = None
        self._task:      Optional[asyncio.Task] = None
        self._running    = False
        self._callbacks: list[Callable] = []

        # Latest snapshot caches
        self.positions: list = []
        self.orders:    list = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start the background WebSocket loop."""
        if self._running:
            return
        self._running = True
        self._task    = asyncio.create_task(self._loop())
        logger.info("BitgetPrivateWS: started")

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._task:
            self._task.cancel()
        logger.info("BitgetPrivateWS: stopped")

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def add_callback(self, fn: Callable):
        """Register a callback(event: str, data: dict) for position/order updates."""
        if fn not in self._callbacks:
            self._callbacks.append(fn)

    def _emit(self, event: str, data):
        asyncio.create_task(ws_manager.broadcast(event, data))
        for fn in self._callbacks:
            try:
                fn(event, data)
            except Exception as e:
                logger.warning(f"BitgetPrivateWS callback error: {e}")

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _login_sign(self, timestamp: str) -> str:
        """Sign = base64(HMAC-SHA256(ts + 'GET' + '/user/verify'))"""
        msg = timestamp + "GET" + "/user/verify"
        mac = hmac.new(
            self.secret_key.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode()

    def _login_msg(self) -> str:
        ts  = str(int(time.time()))
        sig = self._login_sign(ts)
        return json.dumps({
            "op": "login",
            "args": [{
                "apiKey":     self.api_key,
                "passphrase": self.passphrase,
                "timestamp":  ts,
                "sign":       sig,
            }],
        })

    def _subscribe_msg(self) -> str:
        return json.dumps({
            "op": "subscribe",
            "args": [
                {
                    "instType": PRODUCT_TYPE,
                    "channel":  "positions",
                    "instId":   "default",
                },
                {
                    "instType": PRODUCT_TYPE,
                    "channel":  "orders",
                    "instId":   "default",
                },
            ],
        })

    # ------------------------------------------------------------------
    # Main loop with auto-reconnect
    # ------------------------------------------------------------------

    async def _loop(self):
        retry_delay = 5
        while self._running:
            try:
                logger.info("BitgetPrivateWS: connecting…")
                async with websockets.connect(
                    BITGET_WS_PRIVATE,
                    ping_interval=20,
                    ping_timeout=30,
                    close_timeout=5,
                ) as ws:
                    self._ws  = ws
                    retry_delay = 5  # reset on success

                    # Step 1: Login
                    await ws.send(self._login_msg())
                    login_resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                    if login_resp.get("event") != "login":
                        logger.error(f"BitgetPrivateWS login failed: {login_resp}")
                        continue
                    logger.info("BitgetPrivateWS: logged in")

                    # Step 2: Subscribe
                    await ws.send(self._subscribe_msg())
                    logger.info("BitgetPrivateWS: subscribed to positions + orders")

                    # Step 3: Listen
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            await self._handle(msg)
                        except Exception as e:
                            logger.warning(f"BitgetPrivateWS parse error: {e}")

            except asyncio.CancelledError:
                break
            except (ConnectionClosed, OSError) as e:
                logger.warning(f"BitgetPrivateWS disconnected: {e}. Retry in {retry_delay}s")
            except Exception as e:
                logger.error(f"BitgetPrivateWS error: {e}")

            if self._running:
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

        self._ws = None
        logger.info("BitgetPrivateWS loop ended")

    # ------------------------------------------------------------------
    # Message handler
    # ------------------------------------------------------------------

    async def _handle(self, msg: dict):
        event   = msg.get("event")
        action  = msg.get("action")
        arg     = msg.get("arg", {})
        channel = arg.get("channel")
        data    = msg.get("data", [])

        # Ping/pong keepalive
        if msg.get("op") == "pong" or event == "pong":
            return

        # Subscription ack
        if event == "subscribe":
            logger.info(f"BitgetPrivateWS subscribed: {arg}")
            return

        if event == "error":
            logger.error(f"BitgetPrivateWS server error: {msg}")
            self._emit("ws_error", msg)
            return

        if not channel or not data:
            return

        # ── Positions update ─────────────────────────────────────────
        if channel == "positions":
            positions = []
            for p in data:
                total = float(p.get("total", 0))
                positions.append({
                    "symbol":        p.get("instId",      p.get("symbol", "")),
                    "side":          p.get("holdSide",    p.get("posSide", "")),
                    "size":          total,
                    "available":     float(p.get("available",    0)),
                    "avgEntryPrice": float(p.get("openPriceAvg", 0)),
                    "markPrice":     float(p.get("markPrice",    0)),
                    "leverage":      float(p.get("leverage",     1)),
                    "unrealizedPnl": float(p.get("unrealizedPL", 0)),
                    "marginMode":    p.get("marginMode"),
                    "positionId":    p.get("positionId"),
                    "timestamp":     int(time.time() * 1000),
                })
            # Filter empties (snapshot may include closed positions with total=0)
            open_pos = [p for p in positions if p["size"] > 0]
            self.positions = open_pos

            self._emit("positions_update", {
                "action":    action,   # "snapshot" | "update"
                "positions": open_pos,
                "timestamp": int(time.time() * 1000),
            })
            logger.debug(f"BitgetPrivateWS positions update: {len(open_pos)} open")

        # ── Orders update ─────────────────────────────────────────────
        elif channel == "orders":
            orders = []
            for o in data:
                orders.append({
                    "orderId":      o.get("ordId"),
                    "symbol":       o.get("instId", o.get("symbol", "")),
                    "side":         o.get("side"),
                    "tradeSide":    o.get("tradeSide"),
                    "orderType":    o.get("ordType"),
                    "size":         o.get("sz"),
                    "price":        o.get("px"),
                    "fillPrice":    o.get("avgPx"),
                    "fillSize":     o.get("fillSz"),
                    "pnl":          o.get("pnl"),
                    "status":       o.get("state"),
                    "tpPrice":      o.get("slOrdPx"),   # may vary by version
                    "slPrice":      o.get("tpOrdPx"),
                    "createdTime":  o.get("cTime"),
                    "updatedTime":  o.get("uTime"),
                    "timestamp":    int(time.time() * 1000),
                })
            self.orders = orders
            self._emit("orders_update", {
                "action": action,
                "orders": orders,
                "timestamp": int(time.time() * 1000),
            })


# Singleton — import and call .start() inside lifespan
bitget_ws = BitgetPrivateWS()
