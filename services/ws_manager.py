"""
WebSocket manager for broadcasting real-time bot state to frontend.
"""

import asyncio
import json
import logging
from typing import Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, event: str, data):
        message = json.dumps({"event": event, "data": data})
        dead = set()
        # FIX: snapshot the set with list() before iterating.
        # Without this, a concurrent disconnect (self.active.discard) that
        # happens while we await ws.send_text() causes:
        #   RuntimeError: Set changed size during iteration
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        self.active -= dead


ws_manager = ConnectionManager()
