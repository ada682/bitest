"""
MEXC Futures WebSocket Price Feed
===================================
Centralized real-time price feed menggunakan MEXC Futures WS.
- 1 koneksi WS untuk semua simbol (sub.tickers → push tiap ~2s)
- Dynamic subscribe/unsubscribe per-symbol kalau butuh resolusi lebih tinggi
- Auto-reconnect dengan exponential backoff
- Asyncio Event per-symbol → monitor signal bisa await tanpa polling

Endpoint: wss://contract.mexc.com/edge

Usage:
    from services.mexc_price_feed import price_feed

    # Start feed (biasanya dipanggil saat bot start)
    await price_feed.start()

    # Ambil harga terakhir (non-blocking)
    price = price_feed.get_price("BTC_USDT")   # None kalau belum ada

    # Tunggu update harga berikutnya (blocking, cocok untuk monitor loop)
    price = await price_feed.wait_for_price("BTC_USDT", timeout=30)

    # Stop feed
    await price_feed.stop()
"""

import asyncio
import json
import logging
import time
from typing import Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

WS_URL       = "wss://contract.mexc.com/edge"
PING_INTERVAL = 15   # detik — MEXC tutup koneksi jika > 60s tanpa ping
RECONNECT_BASE = 2   # detik, backoff awal
RECONNECT_MAX  = 60  # detik, backoff maksimum


class MexcPriceFeed:
    """
    Singleton WebSocket price feed untuk MEXC Futures.

    Arsitektur:
      - 1 background task (_run_loop) menjaga koneksi WS tetap hidup.
      - Saat terima push.tickers  → update semua harga sekaligus.
      - Saat terima push.ticker   → update harga 1 simbol (resolusi 1s).
      - Setiap update harga → set asyncio.Event(symbol) agar
        wait_for_price() bisa wake-up tanpa sleep.
    """

    def __init__(self):
        self._prices: Dict[str, float]         = {}   # symbol → last price
        self._events: Dict[str, asyncio.Event] = {}   # symbol → Event
        self._watched: Set[str]                = set()# simbol yang di-subscribe per-ticker
        self._task:    Optional[asyncio.Task]  = None
        self._running: bool                    = False
        self._ws                               = None  # websockets connection

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self):
        """Start background WS loop (idempotent)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="mexc_price_feed")
        logger.info("MexcPriceFeed started")
        print("📡 MexcPriceFeed: starting WebSocket price feed …")

    async def stop(self):
        """Stop background WS loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
        logger.info("MexcPriceFeed stopped")
        print("📡 MexcPriceFeed: stopped")

    def get_price(self, symbol: str) -> Optional[float]:
        """Return harga terakhir yang diketahui, atau None."""
        return self._prices.get(symbol)

    async def wait_for_price(self, symbol: str, timeout: float = 30.0) -> Optional[float]:
        """
        Tunggu hingga ada update harga untuk symbol ini.
        Return harga terbaru, atau None jika timeout.
        """
        event = self._get_event(symbol)
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._prices.get(symbol)
        except asyncio.TimeoutError:
            return self._prices.get(symbol)   # kembalikan harga lama kalau ada

    def watch(self, symbol: str):
        """
        Subscribe per-ticker (resolusi 1s) untuk simbol ini.
        Dipanggil saat signal baru muncul.
        """
        if symbol not in self._watched:
            self._watched.add(symbol)
            self._get_event(symbol)          # pastikan event ada
            asyncio.create_task(self._subscribe_ticker(symbol))

    def unwatch(self, symbol: str):
        """Unsubscribe per-ticker untuk simbol ini."""
        if symbol in self._watched:
            self._watched.discard(symbol)
            asyncio.create_task(self._unsubscribe_ticker(symbol))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_event(self, symbol: str) -> asyncio.Event:
        if symbol not in self._events:
            self._events[symbol] = asyncio.Event()
        return self._events[symbol]

    def _update_price(self, symbol: str, price: float):
        """Simpan harga dan wake-up semua waiter."""
        if price > 0:
            self._prices[symbol] = price
            if symbol in self._events:
                self._events[symbol].set()

    # ------------------------------------------------------------------
    # WS background loop
    # ------------------------------------------------------------------

    async def _run_loop(self):
        """Maintain WS connection dengan auto-reconnect."""
        backoff = RECONNECT_BASE
        while self._running:
            try:
                async with websockets.connect(
                    WS_URL,
                    ping_interval=None,   # kita kirim ping manual
                    ping_timeout=None,
                    close_timeout=5,
                    max_size=10 * 1024 * 1024,
                ) as ws:
                    self._ws = ws
                    backoff  = RECONNECT_BASE   # reset backoff saat sukses connect
                    print(f"📡 MexcPriceFeed: connected → {WS_URL}")
                    logger.info("MexcPriceFeed: WS connected")

                    # Subscribe push.tickers (semua simbol, tiap ~2s)
                    await ws.send(json.dumps({
                        "method": "sub.tickers",
                        "param":  {},
                        "gzip":   False,
                    }))

                    # Re-subscribe per-ticker yang masih ditonton
                    for sym in list(self._watched):
                        await ws.send(json.dumps({
                            "method": "sub.ticker",
                            "param":  {"symbol": sym},
                            "gzip":   False,
                        }))

                    # Start ping task
                    ping_task = asyncio.create_task(self._ping_loop(ws))

                    try:
                        async for raw in ws:
                            if not self._running:
                                break
                            await self._handle_message(raw)
                    finally:
                        ping_task.cancel()

            except asyncio.CancelledError:
                break
            except (ConnectionClosed, OSError, Exception) as e:
                if not self._running:
                    break
                logger.warning(f"MexcPriceFeed WS error: {e} — reconnecting in {backoff}s")
                print(f"📡 MexcPriceFeed: disconnected ({e}) — retry in {backoff}s")
                self._ws = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, RECONNECT_MAX)

        self._ws = None
        print("📡 MexcPriceFeed: loop ended")

    async def _ping_loop(self, ws):
        """Kirim ping setiap PING_INTERVAL detik agar koneksi tetap hidup."""
        while True:
            try:
                await asyncio.sleep(PING_INTERVAL)
                await ws.send(json.dumps({"method": "ping"}))
            except asyncio.CancelledError:
                break
            except Exception:
                break

    async def _handle_message(self, raw: str):
        """Parse pesan WS dan update price cache."""
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return

        channel = msg.get("channel", "")

        # ----------------------------------------------------------
        # push.tickers → array semua kontrak, tiap ~2s
        # ----------------------------------------------------------
        if channel == "push.tickers":
            data = msg.get("data", [])
            for item in data:
                sym   = item.get("symbol")
                price = item.get("lastPrice")
                if sym and price is not None:
                    self._update_price(sym, float(price))

        # ----------------------------------------------------------
        # push.ticker → 1 kontrak, tiap ~1s (subscribe per-ticker)
        # ----------------------------------------------------------
        elif channel == "push.ticker":
            sym   = msg.get("symbol") or msg.get("data", {}).get("symbol")
            price = (msg.get("data") or {}).get("lastPrice")
            if sym and price is not None:
                self._update_price(sym, float(price))

        # ----------------------------------------------------------
        # pong — log only
        # ----------------------------------------------------------
        elif channel == "pong":
            pass  # keepalive OK

        # ----------------------------------------------------------
        # Lain-lain
        # ----------------------------------------------------------
        else:
            logger.debug(f"MexcPriceFeed unhandled channel: {channel}")

    async def _subscribe_ticker(self, symbol: str):
        """Kirim subscribe per-ticker ke WS yang sedang aktif."""
        if self._ws:
            try:
                await self._ws.send(json.dumps({
                    "method": "sub.ticker",
                    "param":  {"symbol": symbol},
                    "gzip":   False,
                }))
                logger.debug(f"MexcPriceFeed: subscribed ticker {symbol}")
            except Exception as e:
                logger.warning(f"MexcPriceFeed: failed to subscribe {symbol}: {e}")

    async def _unsubscribe_ticker(self, symbol: str):
        """Kirim unsubscribe per-ticker."""
        if self._ws:
            try:
                await self._ws.send(json.dumps({
                    "method": "unsub.ticker",
                    "param":  {"symbol": symbol},
                    "gzip":   False,
                }))
                logger.debug(f"MexcPriceFeed: unsubscribed ticker {symbol}")
            except Exception as e:
                logger.warning(f"MexcPriceFeed: failed to unsubscribe {symbol}: {e}")


# Singleton
price_feed = MexcPriceFeed()
