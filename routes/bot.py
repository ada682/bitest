from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
from services.ws_manager import ws_manager

router = APIRouter()


class BotConfig(BaseModel):
    symbol: str
    leverage: str
    mode: str = "MANUAL"
    manual_margin: Optional[float] = None
    tp_pct: float = 0.004
    sl_pct: float = 0.002
    volume_place: int = 3


@router.post("/start")
async def start_bot(config: BotConfig, request: Request):
    engine = request.app.state.bot_engine

    def listener(event, data):
        asyncio.create_task(ws_manager.broadcast(event, data))

    engine.add_listener(listener)
    result = await engine.start(config.dict())
    return result


@router.post("/stop")
async def stop_bot(request: Request):
    engine = request.app.state.bot_engine
    return await engine.stop()


@router.get("/state")
async def get_state(request: Request):
    engine = request.app.state.bot_engine
    return engine.get_state()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)

@router.get("/status/debug")
async def debug_status(request: Request):
    engine = request.app.state.bot_engine
    return {
        "running": engine.running,
        "task_exists": engine._task is not None,
        "task_done": engine._task.done() if engine._task else None,
        "task_cancelled": engine._task.cancelled() if engine._task else None,
        "state": engine.state,
    }

@router.get("/test-ai-direct")
async def test_ai_direct(request: Request):
    """Test AI langsung tanpa bot loop"""
    from services.bitget_client import bitget
    from services.deepseek_ai import deepseek_ai
    from utils.indicators import compute_all, format_ohlcv_text
    from services.chart_generator import generate_chart_image
    
    symbol = "ENJUSDT"
    
    print(f"🧪 Testing AI for {symbol}")
    
    # Fetch data
    candles = await bitget.get_candles(symbol, "1m", 50)
    if not candles or len(candles) < 30:
        return {"error": f"Not enough candles: {len(candles) if candles else 0}"}
    
    print(f"✅ Got {len(candles)} candles")
    
    # Generate chart image (required by analyze)
    print("📈 Generating chart...")
    chart_b64 = generate_chart_image(candles, symbol.replace("USDT", "/USDT"), "1m")
    
    if not chart_b64:
        return {"error": "Failed to generate chart image"}
    
    print(f"✅ Chart generated, length: {len(chart_b64)}")
    
    # Compute indicators
    print("📐 Computing indicators...")
    indicators = compute_all(candles)
    ohlcv_text = format_ohlcv_text(candles, 30)
    
    print(f"📊 Current price: {indicators.get('current_price')}")
    print(f"📊 RSI: {indicators.get('rsi_last')}")
    print(f"📊 Trend: {indicators.get('trend')}")
    
    # Call AI
    print("🤖 Calling DeepSeek AI...")
    try:
        result = await deepseek_ai.analyze(ohlcv_text, indicators, chart_b64)
        print(f"✅ AI Result: {result}")
    except Exception as e:
        print(f"❌ AI Error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "traceback": traceback.format_exc()}
    
    return {
        "symbol": symbol,
        "current_price": indicators.get('current_price'),
        "indicators": {
            "rsi": indicators.get('rsi_last'),
            "trend": indicators.get('trend'),
            "ema9": indicators.get('ema9_last'),
            "ema21": indicators.get('ema21_last'),
        },
        "ai_result": result,
    }

@router.get("/test-ai-raw")
async def test_ai_raw(request: Request):
    """Test AI dan tampilkan raw response tanpa parsing"""
    from services.bitget_client import bitget
    from services.deepseek_ai import deepseek_ai
    from utils.indicators import compute_all, format_ohlcv_text
    from services.chart_generator import generate_chart_image
    
    symbol = "ENJUSDT"
    
    # Fetch data
    candles = await bitget.get_candles(symbol, "1m", 50)
    if not candles or len(candles) < 30:
        return {"error": f"Not enough candles: {len(candles) if candles else 0}"}
    
    # Generate chart
    chart_b64 = generate_chart_image(candles, symbol.replace("USDT", "/USDT"), "1m")
    
    # Compute indicators
    indicators = compute_all(candles)
    ohlcv_text = format_ohlcv_text(candles, 30)
    
    # Call AI with modified analyze that returns raw text
    # Kita perlu akses raw response langsung
    await deepseek_ai._ensure_session()
    
    # Upload chart
    file_id = await deepseek_ai.upload_image(chart_b64) if chart_b64 else None
    ref_file_ids = [file_id] if file_id else []
    
    # Build prompt
    prompt = f"""You are a crypto trading AI. Analyze this data and respond with ONLY a valid JSON object.

Current Price: {indicators.get('current_price', 'N/A')}
EMA9: {indicators.get('ema9_last', 'N/A')}
EMA21: {indicators.get('ema21_last', 'N/A')}
RSI: {indicators.get('rsi_last', 'N/A')}
Trend: {indicators.get('trend', 'N/A')}

Response format (ONLY JSON, no other text):
{{"decision": "BUY or SELL or NO TRADE", "entry": {indicators.get('current_price', 0)}, "tp": {indicators.get('current_price', 0) * 1.004}, "sl": {indicators.get('current_price', 0) * 0.996}, "confidence": 0-100, "reason": "short reason"}}"""
    
    # Get POW
    pow_token = await deepseek_ai._do_pow("/api/v0/chat/completion")
    
    comp_headers = {
        **deepseek_ai.headers,
        "Content-Type": "application/json",
        "x-ds-pow-response": pow_token,
    }
    
    payload = {
        "chat_session_id": deepseek_ai._chat_session_id,
        "parent_message_id": deepseek_ai._parent_message_id,
        "prompt": prompt,
        "ref_file_ids": ref_file_ids,
        "thinking_enabled": False,
        "search_enabled": False,
        "preempt": False,
        "model_type": "default",
    }
    
    full_text = ""
    response_message_id = None
    
    async with deepseek_ai.client.stream(
        "POST",
        "/api/v0/chat/completion",
        headers=comp_headers,
        json=payload,
    ) as resp:
        last_event = ""
        async for line in resp.aiter_lines():
            if not line:
                continue
            if line.startswith("event: "):
                last_event = line[7:]
                continue
            if not line.startswith("data: "):
                continue
            content = line[6:]
            try:
                jdata = json.loads(content)
            except Exception:
                continue
            
            if last_event == "ready":
                response_message_id = jdata.get("response_message_id")
            elif "p" in jdata and jdata["p"] == "response/fragments/-1/content":
                full_text += jdata.get("v", "")
            elif "v" in jdata:
                v = jdata["v"]
                if isinstance(v, str):
                    full_text += v
    
    return {
        "symbol": symbol,
        "current_price": indicators.get('current_price'),
        "raw_response": full_text,
        "response_length": len(full_text),
    }

import asyncio
