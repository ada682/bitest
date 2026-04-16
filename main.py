import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from routes import trading, bot, market, history
from services.bot_engine import bot_engine as _engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.bot_engine = _engine
    yield
    await _engine.shutdown()


app = FastAPI(
    title="CryptoSignals API — MEXC Scanner + Virtual Trading",
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
    from services.virtual_exchange import virtual_exchange
    return {
        "status":   "ok",
        "data":     "MEXC (klines + contracts)",
        "balance":  virtual_exchange.balance,
        "leverage": virtual_exchange.leverage,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
