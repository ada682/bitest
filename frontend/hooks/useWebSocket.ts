"use client";
import { useEffect, useRef, useCallback } from "react";
import type { WsEvent } from "@/lib/types";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

type Handler = (event: WsEvent) => void;

export function useWebSocket(onMessage: Handler) {
  const ws      = useRef<WebSocket | null>(null);
  const retries = useRef(0);
  const handler = useRef(onMessage);
  handler.current = onMessage;

  const connect = useCallback(() => {
    try {
      const socket = new WebSocket(`${WS_BASE}/api/bot/ws`);
      ws.current = socket;

      socket.onopen = () => {
        retries.current = 0;
      };

      socket.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data) as WsEvent;
          handler.current(msg);
        } catch {}
      };

      socket.onclose = () => {
        // Exponential back-off: 2s, 4s, 8s … max 30s
        const delay = Math.min(2 ** retries.current * 1000, 30_000);
        retries.current += 1;
        setTimeout(connect, delay);
      };

      socket.onerror = () => socket.close();
    } catch {}
  }, []);

  useEffect(() => {
    connect();
    return () => ws.current?.close();
  }, [connect]);
}
