"""
WsPriceFeed — Real-time price feed via MEXC Futures WebSocket.

Single persistent WS connection to wss://contract.mexc.com/edge
Subscribes/unsubscribes per symbol on demand.
All open signal monitors share ONE connection → zero REST polling.

Usage:
    from services.ws_price_feed import ws_price_feed

    # Start feed (call once at app startup)
    await ws_price_feed.start()

    # Subscribe to a symbol and wait for price updates
    await ws_price_feed.subscribe("BTC_USDT")
    price = await ws_price_feed.wait_price("BTC_USDT", timeout=30)

    # Get latest cached price instantly (non-blocking)
    price = ws_price_feed.get_price("BTC_USDT")   # None if not yet received

    # Unsubscribe when no longer needed
    ws_price_feed.unsubscribe("BTC_USDT")

MEXC Futures WS docs:
  Endpoint : wss://contract.mexc.com/edge
  Sub      : {"method": "sub.ticker",   "param": {"symbol": "BTC_USDT"}}
  Unsub    : {"method": "unsub.ticker", "param": {"symbol": "BTC_USDT"}}
  Ping     : {"method": "ping"}
  Ticker push:
    {"channel": "push.ticker", "symbol": "BTC_USDT",
     "data": {"lastPrice": 67000.0, "bid1": ..., "ask1": ..., ...}}
"""

import asyncio
import json
import logging
import time
from typing import Dict, Optional, Set

import websockets

logger = logging.getLogger(__name__)

MEXC_WS_URL   = "wss://contract.mexc.com/edge"
PING_INTERVAL = 20          # seconds between keep-alive pings
RECONNECT_WAIT = 5          # seconds before reconnect after disconnect
MAX_RECONNECT_WAIT = 60     # cap on backoff


class WsPriceFeed:
    """
    Manages a single persistent WebSocket connection to MEXC Futures.
    Provides real-time prices to all signal monitors without REST polling.
    """

    def __init__(self):
        # Latest price cache: symbol → float
        self._prices: Dict[str, float] = {}

        # asyncio.Event per symbol: set whenever a new price arrives
        self._events: Dict[str, asyncio.Event] = {}

        # Symbols currently subscribed
        self._subscribed: Set[str] = set()

        # Ref count — how many monitors are watching each symbol
        self._ref_count: Dict[str, int] = {}

        self._ws = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._send_queue: asyncio.Queue = asyncio.Queue()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self):
        """Start the WS feed loop (call once at app startup)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("WsPriceFeed started")

    async def stop(self):
        """Stop the feed loop."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("WsPriceFeed stopped")

    async def subscribe(self, symbol: str):
        """
        Subscribe to ticker for `symbol`.
        Safe to call multiple times — ref-counted.
        """
        self._ref_count[symbol] = self._ref_count.get(symbol, 0) + 1
        if symbol not in self._events:
            self._events[symbol] = asyncio.Event()

        if symbol not in self._subscribed:
            self._subscribed.add(symbol)
            await self._enqueue({"method": "sub.ticker", "param": {"symbol": symbol}})
            logger.debug(f"WsFeed: subscribed {symbol}")

    def unsubscribe(self, symbol: str):
        """
        Decrement ref count. Unsubscribes from WS when count reaches 0.
        """
        count = self._ref_count.get(symbol, 0)
        if count <= 1:
            self._ref_count.pop(symbol, None)
            if symbol in self._subscribed:
                self._subscribed.discard(symbol)
                asyncio.create_task(
                    self._enqueue({"method": "unsub.ticker", "param": {"symbol": symbol}})
                )
                logger.debug(f"WsFeed: unsubscribed {symbol}")
        else:
            self._ref_count[symbol] = count - 1

    def get_price(self, symbol: str) -> Optional[float]:
        """Return latest cached price, or None if not yet received."""
        return self._prices.get(symbol)

    async def wait_price(self, symbol: str, timeout: float = 30.0) -> Optional[float]:
        """
        Wait until a fresh price arrives for `symbol` (or timeout).
        Returns the price, or None on timeout.
        """
        event = self._events.get(symbol)
        if event is None:
            return None
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._prices.get(symbol)
        except asyncio.TimeoutError:
            return self._prices.get(symbol)   # return last known price if any

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _enqueue(self, msg: dict):
        """Queue a message to be sent over the WS."""
        await self._send_queue.put(json.dumps(msg))

    async def _resubscribe_all(self):
        """Re-subscribe to all symbols after reconnect."""
        for symbol in list(self._subscribed):
            await self._enqueue({"method": "sub.ticker", "param": {"symbol": symbol}})

    def _handle_message(self, raw: str):
        """Parse incoming WS message and update price cache."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        channel = msg.get("channel", "")
        if channel != "push.ticker":
            return

        symbol = msg.get("symbol", "")
        data   = msg.get("data") or {}

        # MEXC uses "lastPrice" in futures ticker push
        raw_price = data.get("lastPrice") or data.get("last") or data.get("close")
        if raw_price is None:
            return

        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            return

        if price <= 0:
            return

        self._prices[symbol] = price

        # Wake up any coroutine waiting on this symbol
        event = self._events.get(symbol)
        if event:
            event.set()

    # ------------------------------------------------------------------
    # Main connection loop (reconnects automatically)
    # ------------------------------------------------------------------

    async def _run(self):
        backoff = RECONNECT_WAIT
        while self._running:
            try:
                logger.info(f"WsPriceFeed: connecting to {MEXC_WS_URL}")
                async with websockets.connect(
                    MEXC_WS_URL,
                    ping_interval=None,   # we handle ping ourselves
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    backoff  = RECONNECT_WAIT    # reset on successful connect
                    logger.info("WsPriceFeed: connected")

                    # Re-subscribe to all symbols
                    await self._resubscribe_all()

                    # Concurrently: receive messages + drain send queue + ping
                    await asyncio.gather(
                        self._recv_loop(ws),
                        self._send_loop(ws),
                        self._ping_loop(ws),
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"WsPriceFeed disconnected: {e}. Reconnecting in {backoff}s…")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_RECONNECT_WAIT)

        self._ws = None

    async def _recv_loop(self, ws):
        async for raw in ws:
            self._handle_message(raw)

    async def _send_loop(self, ws):
        while True:
            msg = await self._send_queue.get()
            try:
                await ws.send(msg)
            except Exception as e:
                logger.warning(f"WsFeed send error: {e}")
                # Re-queue the message so it's sent after reconnect
                await self._send_queue.put(msg)
                raise   # kill this loop → triggers reconnect

    async def _ping_loop(self, ws):
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                await ws.send(json.dumps({"method": "ping"}))
            except Exception as e:
                logger.warning(f"WsFeed ping error: {e}")
                raise


# Singleton
ws_price_feed = WsPriceFeed()
