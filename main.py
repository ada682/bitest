import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from routes import bot, market
from services.bot_engine import BotEngine

bot_engine = BotEngine()

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.bot_engine = bot_engine
    yield
    await bot_engine.shutdown()

app = FastAPI(title="Crypto Signal Bot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(bot.router, prefix="/api/bot", tags=["bot"])
app.include_router(market.router, prefix="/api/market", tags=["market"])

@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
