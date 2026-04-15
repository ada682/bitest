import type { BotState, Signal } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { next: { revalidate: 0 } });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export async function fetchBotState(): Promise<BotState> {
  const data = await get<BotState>("/api/bot/state");
  return data;
}

export async function fetchStats() {
  const r = await get<{ data: ReturnType<typeof Object> }>("/api/bot/stats");
  return (r as any).data;
}

export async function fetchSignals(limit = 100): Promise<Signal[]> {
  const r = await get<{ data: Signal[] }>(`/api/bot/signals?limit=${limit}`);
  return r.data ?? [];
}

export async function startBot(payload: {
  symbol?: string;
  interval?: number;
}) {
  const r = await fetch(`${BASE}/api/bot/start`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ symbol: "ALL", interval: 300, ...payload }),
  });
  return r.json();
}

export async function stopBot() {
  const r = await fetch(`${BASE}/api/bot/stop`, { method: "POST" });
  return r.json();
}

export async function resetStats() {
  const r = await fetch(`${BASE}/api/bot/reset`, { method: "POST" });
  return r.json();
}

export async function verifyPin(pin: string): Promise<boolean> {
  const r = await fetch(`${BASE}/api/bot/verify-pin`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ pin }),
  });
  const d = await r.json();
  return d.ok === true;
}
