"""
MEXC Futures Client (replaces Bitget)
Public market data endpoints — no auth required for klines/tickers/contracts.
"""

import time
import httpx
import os
import hmac
import hashlib
import json
import logging  # ← FIX: was missing, caused NameError in get_ticker()

logger = logging.getLogger(__name__)  # ← FIX: was missing

MEXC_BASE_URL = "https://api.mexc.com"

# ---------------------------------------------------------------------------
# Non-crypto asset blacklist
# ---------------------------------------------------------------------------
# MEXC Futures menyertakan US stock futures & commodity futures yang memakai
# format simbol yang sama dengan crypto (e.g. NVDA_USDT, TSLA_USDT).
# Bot ini hanya untuk crypto — semua aset di bawah akan di-skip.
#
# Pengecualian: XAU (Gold perpetual) tetap diizinkan karena berkorelasi
# kuat dengan crypto dan sering dipakai sebagai hedge reference.
#
# Sumber: https://www.mexc.com/futures/stock-futures
# ---------------------------------------------------------------------------

# US Stock futures (tokenized equities)
_STOCK_BASE_COINS: set[str] = {
    # Tech & Growth
    "NVDA", "AAPL", "AMZN", "GOOGL", "META", "MSFT", "AMD", "ADBE", "NFLX",
    # EV / Consumer
    "TSLA", "MCD",
    # Finance / Crypto-native stocks
    "COIN", "HOOD", "CRCL",
    # Defense / Other equities
    "PLTR", "DFDV",
    # ETFs
    "QQQ", "SPY", "SPXS", "SQQQ", "TQQQ",
    # Strategy/Leveraged equity products
    "MSTR",
}

# Commodity futures (non-crypto, non-XAU)
_COMMODITY_BASE_COINS: set[str] = {
    # Crude oil
    "OIL", "WTI", "BRENT", "CRUDE",
    # Silver / other metals (XAU is intentionally excluded from this set)
    "XAG", "SILVER",
    # Misc commodities
    "GAS", "NGAS",
}

# Combined blacklist — O(1) lookup
_BLACKLISTED_BASE_COINS: set[str] = _STOCK_BASE_COINS | _COMMODITY_BASE_COINS


def _is_non_crypto(base_coin: str) -> bool:
    """Return True if baseCoin is a non-crypto asset that should be skipped."""
    bc = (base_coin or "").upper()
    # Exact match against blacklist
    if bc in _BLACKLISTED_BASE_COINS:
        return True
    # Catch any future MEXC additions that end with 'STOCK' (e.g. NVDASTOCK)
    if bc.endswith("STOCK"):
        return True
    return False

# Map bot timeframes → MEXC interval strings
INTERVAL_MAP = {
    "1m":  "Min1",
    "3m":  "Min5",   # MEXC has no Min3; use Min5
    "5m":  "Min5",
    "15m": "Min15",
    "30m": "Min30",
    "1h":  "Min60",
    "2h":  "Hour4",  # MEXC has no Hour2; use Hour4
    "4h":  "Hour4",
}

# Seconds per MEXC interval (for calculating start time)
INTERVAL_SECONDS = {
    "Min1":  60,
    "Min5":  300,
    "Min15": 900,
    "Min30": 1800,
    "Min60": 3600,
    "Hour4": 14400,
    "Hour8": 28800,
    "Day1":  86400,
}


class MexcClient:
    def __init__(self):
        self.api_key    = os.getenv("MEXC_API_KEY", "")
        self.secret_key = os.getenv("MEXC_SECRET_KEY", "")
        self.client = httpx.AsyncClient(
            base_url=MEXC_BASE_URL,
            timeout=30,
            headers={"Content-Type": "application/json"},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict = None) -> dict:
        try:
            resp = await self.client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Market endpoints (public — no auth needed)
    # ------------------------------------------------------------------

    async def get_contracts(self) -> list:
        """Return all active USDT-settled perpetual contracts."""
        resp = await self._get("/api/v1/contract/detail")
        raw = resp.get("data") or []
        if isinstance(raw, dict):
            raw = [raw]
        skipped_non_crypto = 0
        result = []
        for c in raw:
            # state 0 = enabled/trading
            if c.get("quoteCoin") == "USDT" and c.get("state") == 0:
                base = c.get("baseCoin", "")
                if _is_non_crypto(base):
                    skipped_non_crypto += 1
                    continue
                result.append({
                    "symbol":       c.get("symbol"),          # e.g. "BTC_USDT"
                    "baseCoin":     c.get("baseCoin"),
                    "quoteCoin":    c.get("quoteCoin"),
                    "maxLeverage":  c.get("maxLeverage"),
                    "priceScale":   c.get("priceScale"),
                    "volScale":     c.get("volScale"),
                    "contractSize": c.get("contractSize"),
                    "minVol":       c.get("minVol", 1),
                    "maxVol":       c.get("maxVol"),
                })
        if skipped_non_crypto:
            logger.info(
                f"get_contracts: skipped {skipped_non_crypto} non-crypto contracts "
                f"(US stocks / commodities). Returning {len(result)} crypto contracts."
            )
            print(
                f"[MexcClient] Skipped {skipped_non_crypto} non-crypto contracts "
                f"(stocks/oil/silver). {len(result)} crypto contracts kept."
            )
        return result

    async def get_ticker(self, symbol: str) -> dict:
        """Get single contract ticker. symbol = 'BTC_USDT'"""
        resp = await self._get("/api/v1/contract/ticker", {"symbol": symbol})
        data = resp.get("data") or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        if not data or data.get("lastPrice") is None:
            logger.warning(f"Ticker not found for {symbol}: {resp}")  # ← now works
            return {"error": "not_found", "last": "0", "lastPr": "0"}
        last = str(data.get("lastPrice", data.get("last", "0")))
        return {
            **data,
            "last": last,
            "lastPr": last,
            "bestAsk": str(data.get("ask1", "0")),
            "bestBid": str(data.get("bid1", "0")),
            "priceChangePercent": str(data.get("riseFallRate", "0")),
            "volume24h": str(data.get("volume24", "0")),
        }

    async def get_all_tickers(self) -> list:
        """Get tickers for all contracts."""
        resp = await self._get("/api/v1/contract/ticker")
        data = resp.get("data") or []
        return data if isinstance(data, list) else []

    async def get_candles(self, symbol: str, granularity: str, limit: int = 100) -> list:
        """
        Fetch OHLCV candles.

        Parameters
        ----------
        symbol      : 'BTC_USDT'  (MEXC underscore format)
        granularity : bot-style tf string, e.g. '5m', '1h', '4h'
        limit       : number of candles to return

        Returns list of [timestamp_ms, open, high, low, close, vol, amount]
        matching the shape that bot_engine / indicators.py already expect.
        """
        interval = INTERVAL_MAP.get(granularity, "Min5")
        secs     = INTERVAL_SECONDS.get(interval, 300)
        end_ts   = int(time.time())
        start_ts = end_ts - secs * (limit + 5)   # slight buffer

        resp = await self._get(
            f"/api/v1/contract/kline/{symbol}",
            {"interval": interval, "start": str(start_ts), "end": str(end_ts)},
        )
        data = resp.get("data") or {}
        if not isinstance(data, dict):
            return []

        times   = data.get("time",   [])
        opens   = data.get("open",   [])
        highs   = data.get("high",   [])
        lows    = data.get("low",    [])
        closes  = data.get("close",  [])
        vols    = data.get("vol",    [])
        amounts = data.get("amount", [])

        candles = []
        for i in range(len(times)):
            try:
                candles.append([
                    int(times[i]) * 1000,           # s → ms
                    float(opens[i]),
                    float(highs[i]),
                    float(lows[i]),
                    float(closes[i]),
                    float(vols[i])    if i < len(vols)    else 0.0,
                    float(amounts[i]) if i < len(amounts) else 0.0,
                ])
            except (IndexError, ValueError, TypeError):
                continue

        # Return most-recent `limit` candles in ascending order
        return candles[-limit:]

    # ------------------------------------------------------------------
    # Account / trading (signed) — kept for completeness
    # ------------------------------------------------------------------

    async def get_positions(self) -> list:
        """Requires API key. Returns open positions."""
        if not self.api_key:
            return []
        ts  = str(int(time.time() * 1000))
        sig = hmac.new(
            self.secret_key.encode(),
            (self.api_key + ts).encode(),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "ApiKey":       self.api_key,
            "Request-Time": ts,
            "Signature":    sig,
        }
        resp = await self.client.get("/api/v1/private/position/open_positions", headers=headers)
        return (resp.json().get("data") or [])

    async def close(self):
        await self.client.aclose()


# Singleton used throughout the app
mexc_client = MexcClient()
