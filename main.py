import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from routes import trading, bot, market, history
from services.bot_engine import bot_engine as _engine
from services.bitget_ws  import bitget_ws   as _bws


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.bot_engine = _engine

    # Wire Bitget WS order updates → bot_engine signal tracker
    _bws.add_callback(_engine.handle_bitget_order_update)

    # Start Bitget private WS only if API key is configured
    if os.getenv("BITGET_API_KEY"):
        _bws.start()
    else:
        print("⚠️  BITGET_API_KEY not set — private WebSocket not started. "
              "Set BITGET_API_KEY, BITGET_SECRET_KEY, BITGET_PASSPHRASE in .env")

    yield

    await _bws.stop()
    await _engine.shutdown()


app = FastAPI(
    title="CryptoSignals API — Bitget Demo + MEXC Futures Scanner",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trading.router, prefix="/api/trading", tags=["trading"])
app.include_router(bot.router,     prefix="/api/bot",     tags=["bot"])
app.include_router(market.router,  prefix="/api/market",  tags=["market"])
app.include_router(history.router, prefix="/api/history", tags=["history"])


@app.get("/api/health")
async def health():
    return {
        "status":        "ok",
        "exchange_data": "MEXC (klines) + Bitget (coins / trading)",
        "bitget_ws":     "connected" if _bws._ws else "disconnected",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
