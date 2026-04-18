"use client";
import { useRef, useEffect, useState, useCallback } from "react";
import type { Signal } from "@/lib/types";
import QRCode from "qrcode";

// ─── THEMES ──────────────────────────────────────────────────────────────────
const T_VIOLET = {
  a1: "#c4b5fd", a2: "#7c3aed", a3: "#4c1d95",
  glow: "#6d28d9", bg1: "#08050f", bg2: "#0d0819",
  stripe: "#0e0920", card: "#ffffff07",
  orb: "#7c3aed",
};
const T_ROSE = {
  a1: "#fda4af", a2: "#f43f5e", a3: "#881337",
  glow: "#e11d48", bg1: "#0f0008", bg2: "#1a0010",
  stripe: "#200012", card: "#ffffff06",
  orb: "#e11d48",
};

type Mode = "roe" | "pnl" | "both";

// ─── HELPERS ─────────────────────────────────────────────────────────────────
function h2r(h: string, a = 1) {
  const r = parseInt(h.slice(1, 3), 16);
  const g = parseInt(h.slice(3, 5), 16);
  const b = parseInt(h.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

function rr(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  r: number | { tl: number; tr: number; bl: number; br: number },
) {
  const rad = typeof r === "number"
    ? { tl: r, tr: r, bl: r, br: r }
    : r;
  ctx.beginPath();
  ctx.moveTo(x + rad.tl, y);
  ctx.lineTo(x + w - rad.tr, y);
  ctx.arcTo(x + w, y, x + w, y + rad.tr, rad.tr);
  ctx.lineTo(x + w, y + h - rad.br);
  ctx.arcTo(x + w, y + h, x + w - rad.br, y + h, rad.br);
  ctx.lineTo(x + rad.bl, y + h);
  ctx.arcTo(x, y + h, x, y + h - rad.bl, rad.bl);
  ctx.lineTo(x, y + rad.tl);
  ctx.arcTo(x, y, x + rad.tl, y, rad.tl);
  ctx.closePath();
}

function drawQR(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, size: number, color: string,
) {
  const cell = size / 8;
  const pat = [
    [1,1,1,1,0,1,1,1],[1,0,0,1,0,1,0,1],[1,0,1,1,1,0,0,1],[1,1,1,1,0,1,1,0],
    [0,1,0,0,1,0,1,1],[1,0,1,0,0,1,0,1],[1,1,1,1,0,0,1,0],[1,0,1,1,1,0,1,1],
  ];
  ctx.fillStyle = h2r(color, 0.45);
  pat.forEach((row, ri) =>
    row.forEach((c, ci) => {
      if (c) ctx.fillRect(x + ci * cell + 0.5, y + ri * cell + 0.5, cell - 1, cell - 1);
    }),
  );
  ctx.strokeStyle = h2r(color, 0.6);
  ctx.lineWidth = 1;
  [[0,0],[5,0],[0,5]].forEach(([cx, cy]) => {
    ctx.strokeRect(x + cx * cell, y + cy * cell, cell * 3, cell * 3);
  });
}

function makeNoise(W: number, H: number): HTMLCanvasElement {
  const off = document.createElement("canvas");
  off.width = W; off.height = H;
  const ox = off.getContext("2d")!;
  const id = ox.createImageData(W, H);
  for (let i = 0; i < id.data.length; i += 4) {
    const v = (Math.random() * 255) | 0;
    id.data[i] = id.data[i+1] = id.data[i+2] = v;
    id.data[i+3] = 10;
  }
  ox.putImageData(id, 0, 0);
  return off;
}

// ─── SMART PRICE FORMATTER ───────────────────────────────────────────────────
function smartFmt(n: number | null | undefined, withDollar = false): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  let str: string;
  if (abs === 0)         str = "0";
  else if (abs >= 10000) str = n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  else if (abs >= 1)     str = n.toFixed(4);
  else if (abs >= 0.01)  str = n.toFixed(6);
  else if (abs >= 0.0001) str = n.toFixed(8);
  else                   str = n.toPrecision(4);
  return withDollar ? `$${str}` : str;
}

// ─── COIN ICON ───────────────────────────────────────────────────────────────
function drawCoinIcon(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  ticker: string,
  T: typeof T_VIOLET,
  isLong: boolean,
) {
  const R = 44;
  ctx.save();

  ctx.save();
  ctx.strokeStyle = h2r(T.a1, 0.18);
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 5]);
  ctx.beginPath();
  ctx.arc(cx, cy, R + 14, 0, Math.PI * 2);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();

  ctx.save();
  ctx.strokeStyle = h2r(T.a1, 0.35);
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(cx, cy, R + 6, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();

  [0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2].forEach((angle, i) => {
    const dotR = R + 6;
    const dx = cx + dotR * Math.cos(angle);
    const dy = cy + dotR * Math.sin(angle);
    ctx.beginPath();
    ctx.arc(dx, dy, i % 2 === 0 ? 3 : 2, 0, Math.PI * 2);
    ctx.fillStyle = i % 2 === 0 ? T.a1 : h2r(T.a1, 0.5);
    ctx.fill();
  });

  const grad = ctx.createRadialGradient(cx - 12, cy - 14, 6, cx, cy, R);
  grad.addColorStop(0, T.a1);
  grad.addColorStop(0.5, T.a2);
  grad.addColorStop(1, T.a3);
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.fillStyle = grad;
  ctx.fill();

  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.clip();
  ctx.strokeStyle = h2r("#ffffff", 0.05);
  ctx.lineWidth = 1;
  for (let ix = cx - R; ix <= cx + R; ix += 12) {
    ctx.beginPath(); ctx.moveTo(ix, cy - R); ctx.lineTo(ix, cy + R); ctx.stroke();
  }
  for (let iy = cy - R; iy <= cy + R; iy += 12) {
    ctx.beginPath(); ctx.moveTo(cx - R, iy); ctx.lineTo(cx + R, iy); ctx.stroke();
  }
  ctx.fillStyle = "rgba(255,255,255,0.13)";
  ctx.beginPath();
  ctx.arc(cx - 14, cy - 16, 20, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  ctx.strokeStyle = h2r("#ffffff", 0.25);
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, R * 0.6, 0, Math.PI * 2);
  ctx.stroke();

  const label = ticker.slice(0, 4).toUpperCase();
  const fs = label.length <= 3 ? 20 : 16;
  ctx.fillStyle = "#ffffff";
  ctx.font = `700 ${fs}px "Bebas Neue",sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, cx, cy + 2);

  const badgeY = cy + R - 8;
  const sc = isLong ? "#4ade80" : "#f87171";
  ctx.beginPath();
  ctx.arc(cx, badgeY, 10, 0, Math.PI * 2);
  ctx.fillStyle = "#050505";
  ctx.fill();
  ctx.strokeStyle = h2r(sc, 0.6);
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.fillStyle = sc;
  ctx.font = "bold 12px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(isLong ? "↗" : "↘", cx, badgeY);

  ctx.restore();
}

// ─── MAIN POSTER DRAW ────────────────────────────────────────────────────────
function drawPoster(
  canvas: HTMLCanvasElement,
  signal: Signal,
  mode: Mode,
  roeVal: number,
  pnlVal: number,
  leverage: number,
  currentPrice: number,
  platform = "SonneTrade",
  website = "sonnetrades.vercel.app",
  dpr = 1,
  candles: number[][] = [],
  qrImg: HTMLImageElement | null = null,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const W = 540, H = 800;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  ctx.scale(dpr, dpr);

  const isPos = mode === "pnl" ? pnlVal >= 0 : roeVal >= 0;
  const T = isPos ? T_VIOLET : T_ROSE;
  const isLong = signal.decision === "LONG";
  const sc = isLong ? "#4ade80" : "#f87171";

  const pair  = signal.symbol.replace("_USDT", "");
  const quote = "USDT";

  const websiteDisplay = "http://" + website.replace(/^https?:\/\//, "");

  // ── Background ────────────────────────────────────────────────────────────
  rr(ctx, 0, 0, W, H, 20);
  const bgG = ctx.createLinearGradient(0, 0, 0, H);
  bgG.addColorStop(0, T.bg1); bgG.addColorStop(1, T.bg2);
  ctx.fillStyle = bgG; ctx.fill();

  const noise = makeNoise(W, H);
  ctx.save(); rr(ctx, 0, 0, W, H, 20); ctx.clip();
  ctx.drawImage(noise, 0, 0); ctx.restore();

  ctx.save(); rr(ctx, 0, 0, W, H, 20); ctx.clip();
  ctx.strokeStyle = T.stripe; ctx.lineWidth = 1;
  for (let i = -H; i < W + H; i += 32) {
    ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + H, H); ctx.stroke();
  }
  ctx.restore();

  [[W * 0.85, H * 0.15, 340, 0.22], [W * 0.1, H * 0.9, 220, 0.15], [-20, H * 0.45, 180, 0.1]].forEach(([ox, oy, or_, oa]) => {
    const g = ctx.createRadialGradient(ox, oy, 0, ox, oy, or_);
    g.addColorStop(0, h2r(T.glow, oa)); g.addColorStop(1, "transparent");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  });

  ctx.save(); rr(ctx, 0, 0, W, H, 20); ctx.clip();
  ctx.save();
  ctx.translate(W - 30, 50); ctx.rotate(Math.PI / 8);
  ctx.strokeStyle = h2r(T.a1, 0.06); ctx.lineWidth = 1.5;
  for (let r2 = 40; r2 <= 140; r2 += 28) {
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = i * Math.PI / 3;
      i === 0 ? ctx.moveTo(r2 * Math.cos(a), r2 * Math.sin(a))
              : ctx.lineTo(r2 * Math.cos(a), r2 * Math.sin(a));
    }
    ctx.closePath(); ctx.stroke();
  }
  ctx.restore();
  ctx.strokeStyle = h2r(T.a1, 0.06); ctx.lineWidth = 1;
  for (let xi = 20; xi < 120; xi += 14) {
    for (let yi = H - 130; yi < H - 10; yi += 14) {
      ctx.beginPath(); ctx.moveTo(xi - 3, yi); ctx.lineTo(xi + 3, yi); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(xi, yi - 3); ctx.lineTo(xi, yi + 3); ctx.stroke();
    }
  }
  ctx.strokeStyle = h2r(T.a1, 0.16); ctx.lineWidth = 1; ctx.setLineDash([4, 8]);
  ctx.beginPath(); ctx.moveTo(-10, 90); ctx.lineTo(110, -10); ctx.stroke();
  ctx.setLineDash([]); ctx.restore();

  // ── Header ───────────────────────────────────────────────────────────────
  ctx.save();
  rr(ctx, 0, 0, W, 88, { tl: 20, tr: 20, bl: 0, br: 0 });
  const hG = ctx.createLinearGradient(0, 0, 0, 88);
  hG.addColorStop(0, h2r(T.a1, 0.1)); hG.addColorStop(1, "transparent");
  ctx.fillStyle = hG; ctx.fill(); ctx.restore();

  const hbG = ctx.createLinearGradient(0, 0, W, 0);
  hbG.addColorStop(0, "transparent"); hbG.addColorStop(0.2, h2r(T.a1, 0.35));
  hbG.addColorStop(0.8, h2r(T.a1, 0.35)); hbG.addColorStop(1, "transparent");
  ctx.strokeStyle = hbG; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, 88); ctx.lineTo(W, 88); ctx.stroke();

  ctx.save(); ctx.translate(32, 44);
  const hexG = ctx.createLinearGradient(-14, -14, 14, 14);
  hexG.addColorStop(0, T.a1); hexG.addColorStop(1, T.a2);
  ctx.fillStyle = hexG;
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = i * Math.PI / 3 - Math.PI / 6;
    ctx.lineTo(16 * Math.cos(a), 16 * Math.sin(a));
  }
  ctx.closePath(); ctx.fill();
  ctx.strokeStyle = h2r("#ffffff", 0.3); ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = i * Math.PI / 3 - Math.PI / 6;
    ctx.lineTo(9 * Math.cos(a), 9 * Math.sin(a));
  }
  ctx.closePath(); ctx.stroke(); ctx.restore();

  ctx.fillStyle = "#ffffff";
  ctx.font = "700 22px Outfit,sans-serif";
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText(platform.toUpperCase(), 56, 38);
  const pW = ctx.measureText(platform.toUpperCase()).width;
  ctx.fillStyle = T.a1;
  ctx.beginPath(); ctx.arc(60 + pW, 33, 4, 0, Math.PI * 2); ctx.fill();

  const ds = new Date(signal.timestamp).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  ctx.fillStyle = "#555555";
  ctx.font = "400 10px \"JetBrains Mono\",monospace";
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText(ds, 57, 60);

  const sBg = isLong ? h2r("#4ade80", 0.12) : h2r("#f87171", 0.12);
  const sBd = isLong ? h2r("#4ade80", 0.45) : h2r("#f87171", 0.45);
  const pillW = 96, pillH = 30;
  rr(ctx, W - 28 - pillW, 28, pillW, pillH, 8);
  ctx.fillStyle = sBg; ctx.fill();
  ctx.strokeStyle = sBd; ctx.lineWidth = 1; ctx.stroke();
  ctx.fillStyle = sc;
  ctx.font = "700 12px Outfit,sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText((isLong ? "▲ " : "▼ ") + signal.decision, W - 28 - pillW / 2, 43);

  // ── Coin section ─────────────────────────────────────────────────────────
  const coinY = 110;
  const iCx = 60, iCy = coinY + 56;
  drawCoinIcon(ctx, iCx, iCy, pair, T, isLong);

  const pairX = 122;
  ctx.fillStyle = "#ffffff";
  ctx.font = "900 58px \"Bebas Neue\",sans-serif";
  ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
  ctx.fillText(pair, pairX, coinY + 62);
  const bw = ctx.measureText(pair).width;
  ctx.fillStyle = "#3d3d3d";
  ctx.font = "300 26px \"JetBrains Mono\",monospace";
  ctx.fillText("/" + quote, pairX + bw + 4, coinY + 56);

  const tagY = coinY + 74;
  const tags = [
    { label: `${leverage}× LEVERAGE`, c: T.a1, bc: T.a2 },
    { label: isLong ? "LONG" : "SHORT", c: sc, bc: sc },
    { label: "FUTURES PERP", c: "#555", bc: "#333" },
  ];
  tags.forEach((tag, i) => {
    const tw = 86, tx = pairX + i * (tw + 7);
    rr(ctx, tx, tagY, tw, 22, 6);
    ctx.fillStyle = h2r(tag.bc, 0.14); ctx.fill();
    ctx.strokeStyle = h2r(tag.bc, 0.4); ctx.lineWidth = 0.75; ctx.stroke();
    ctx.fillStyle = tag.c;
    ctx.font = "500 9.5px \"JetBrains Mono\",monospace";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(tag.label, tx + tw / 2, tagY + 11);
  });
  ctx.textBaseline = "alphabetic";

  // ── Divider 1 ────────────────────────────────────────────────────────────
  const divY = 240;
  const dg = ctx.createLinearGradient(0, 0, W, 0);
  dg.addColorStop(0, "transparent"); dg.addColorStop(0.12, h2r(T.a1, 0.7));
  dg.addColorStop(0.5, T.a1); dg.addColorStop(0.88, h2r(T.a1, 0.7));
  dg.addColorStop(1, "transparent");
  ctx.strokeStyle = dg; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(28, divY); ctx.lineTo(W - 28, divY); ctx.stroke();

  // ── ROE / PnL display ────────────────────────────────────────────────────
  const roeStr = (roeVal >= 0 ? "+" : "") + roeVal.toLocaleString() + "%";
  const pnlStr = (pnlVal >= 0 ? "+" : "") + pnlVal.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " USDT";

  let statsYBase = 370;

  if (mode === "both") {
    let fs = 80;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    while (ctx.measureText(roeStr).width > W - 44 && fs > 40) {
      fs -= 4; ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    }
    const roeY = 260 + fs;

    ctx.save();
    ctx.shadowColor = T.glow; ctx.shadowBlur = 50;
    ctx.fillStyle = T.a1; ctx.textAlign = "center";
    ctx.fillText(roeStr, W / 2, roeY);
    ctx.restore();

    const rg = ctx.createLinearGradient(0, roeY - fs, 0, roeY + 8);
    rg.addColorStop(0, "#ffffff"); rg.addColorStop(0.5, T.a1); rg.addColorStop(1, T.a2);
    ctx.fillStyle = rg;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    ctx.textAlign = "center"; ctx.fillText(roeStr, W / 2, roeY);

    ctx.fillStyle = "#888888";
    ctx.font = "500 10px \"JetBrains Mono\",monospace";
    ctx.textAlign = "center";
    ctx.fillText("R · E · T · U · R · N   O N   E · Q · U · I · T · Y", W / 2, roeY + 20);

    const pnlBY = roeY + 44;
    const pnlFmt = pnlStr;
    ctx.font = "700 28px \"Bebas Neue\",sans-serif";
    const pnlBW = ctx.measureText(pnlFmt).width + 48;
    rr(ctx, (W - pnlBW) / 2, pnlBY, pnlBW, 38, 10);
    ctx.fillStyle = h2r(isPos ? T_VIOLET.a2 : T_ROSE.a2, 0.15); ctx.fill();
    ctx.strokeStyle = h2r(T.a1, 0.35); ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = isPos ? "#4ade80" : "#f87171";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(pnlFmt, W / 2, pnlBY + 19);
    ctx.textBaseline = "alphabetic";

    statsYBase = pnlBY + 60;
  } else if (mode === "roe") {
    let fs = 108;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    while (ctx.measureText(roeStr).width > W - 44 && fs > 48) {
      fs -= 4; ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    }
    const roeY = 258 + fs;

    ctx.save();
    ctx.shadowColor = T.glow; ctx.shadowBlur = 60;
    ctx.fillStyle = T.a1; ctx.textAlign = "center";
    ctx.fillText(roeStr, W / 2, roeY); ctx.restore();

    const rg = ctx.createLinearGradient(0, roeY - fs, 0, roeY + 8);
    rg.addColorStop(0, "#ffffff"); rg.addColorStop(0.5, T.a1); rg.addColorStop(1, T.a2);
    ctx.fillStyle = rg;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    ctx.textAlign = "center"; ctx.fillText(roeStr, W / 2, roeY);

    ctx.fillStyle = "#888888";
    ctx.font = "500 10px \"JetBrains Mono\",monospace";
    ctx.textAlign = "center";
    ctx.fillText("R · E · T · U · R · N   O N   E · Q · U · I · T · Y", W / 2, roeY + 22);

    statsYBase = roeY + 48;
  } else {
    let fs = 86;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    while (ctx.measureText(pnlStr).width > W - 44 && fs > 40) {
      fs -= 4; ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    }
    const pnlY = 258 + fs;

    ctx.save();
    ctx.shadowColor = isPos ? "#4ade80" : "#f87171"; ctx.shadowBlur = 55;
    ctx.fillStyle = isPos ? "#4ade80" : "#f87171"; ctx.textAlign = "center";
    ctx.fillText(pnlStr, W / 2, pnlY); ctx.restore();

    const pg = ctx.createLinearGradient(0, pnlY - fs, 0, pnlY + 8);
    pg.addColorStop(0, "#ffffff");
    pg.addColorStop(0.5, isPos ? "#4ade80" : "#f87171");
    pg.addColorStop(1, isPos ? "#16a34a" : "#b91c1c");
    ctx.fillStyle = pg;
    ctx.font = `900 ${fs}px "Bebas Neue",sans-serif`;
    ctx.textAlign = "center"; ctx.fillText(pnlStr, W / 2, pnlY);

    ctx.fillStyle = "#888888";
    ctx.font = "500 10px \"JetBrains Mono\",monospace";
    ctx.textAlign = "center";
    ctx.fillText("R · E · A · L · I · Z · E · D   P · R · O · F · I · T", W / 2, pnlY + 22);

    statsYBase = pnlY + 48;
  }

  // ── Stat cards ────────────────────────────────────────────────────────────
  const _cur   = currentPrice > 0 ? currentPrice : (signal.current_price ?? null);
  const _entry = signal.entry != null ? Number(signal.entry) : null;
  const _tp    = signal.tp    != null ? Number(signal.tp)    : null;
  const _sl    = signal.sl    != null ? Number(signal.sl)    : null;

  const statDefs = [
    { label: "CURRENT",     val: (_cur != null && _cur > 0) ? `$${smartFmt(_cur)}` : "—", c: "#93c5fd" },
    { label: "ENTRY",       val: (_entry != null && _entry > 0) ? `$${smartFmt(_entry)}` : "—", c: "#e2e8f0" },
    { label: "TAKE PROFIT", val: (_tp != null && _tp > 0) ? `$${smartFmt(_tp)}` : "—", c: "#86efac" },
    { label: "STOP LOSS",   val: (_sl != null && _sl > 0) ? `$${smartFmt(_sl)}` : "—", c: "#fca5a5" },
  ];

  const gap2 = 7;
  const cW = (W - 56 - gap2 * (statDefs.length - 1)) / statDefs.length;

  statDefs.forEach((s, i) => {
    const sx = 28 + i * (cW + gap2), sy = statsYBase, sh = 68;
    rr(ctx, sx, sy, cW, sh, 12);
    ctx.fillStyle = "rgba(255,255,255,0.04)"; ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.09)"; ctx.lineWidth = 1; ctx.stroke();
    rr(ctx, sx, sy, cW, 3, { tl: 12, tr: 12, bl: 0, br: 0 });
    ctx.fillStyle = h2r(T.a1, 0.6); ctx.fill();

    ctx.fillStyle = "#909090";
    ctx.font = "400 9px \"JetBrains Mono\",monospace";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(s.label, sx + cW / 2, sy + 22);

    let vfs = 14;
    ctx.font = `700 ${vfs}px "Bebas Neue",sans-serif`;
    while (ctx.measureText(s.val).width > cW - 8 && vfs > 9) {
      vfs -= 1; ctx.font = `700 ${vfs}px "Bebas Neue",sans-serif`;
    }
    ctx.fillStyle = s.c;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(s.val, sx + cW / 2, sy + 50);
  });
  ctx.textBaseline = "alphabetic";

  // ── Price Chart (elegant smooth curve + synced live price) ──────────────
  const arcY = statsYBase + 84;
  const chX = 28, chW = W - 56, chH = 130;

  const _entry2 = signal.entry != null ? Number(signal.entry) : null;
  const _tp2    = signal.tp    != null ? Number(signal.tp)    : null;
  const _sl2    = signal.sl    != null ? Number(signal.sl)    : null;
  const _cur2   = currentPrice > 0 ? currentPrice : (signal.current_price ?? null);

  // ── Price series from real candles (close) or synthetic fallback ──────────
  let prices: number[] = [];
  let candleTimes: number[] = [];
  if (candles && candles.length > 2) {
    prices      = candles.map(c => parseFloat(String(c[4])));
    candleTimes = candles.map(c => Number(c[0]));
  } else {
    const base = _entry2 ?? (_cur2 ?? 100);
    const offs = [0,-0.3,0.2,-0.5,0.4,0.1,-0.2,0.6,0.3,0.7,
                  0.2,0.5,0.3,0.8,0.4,0.9,0.6,1.1,0.8,1.3,
                  1.0,1.5,1.2,1.8,1.4,2.0,1.6,2.2,1.9,2.5];
    prices = offs.map(d => base * (1 + d * 0.001));
  }
  const n = prices.length;

  // ── Y-range: fit closes + all key price levels ────────────────────────────
  const allPr: number[] = [...prices];
  if (_entry2 && _entry2 > 0) allPr.push(_entry2);
  if (_cur2   && _cur2   > 0) allPr.push(_cur2);
  if (_tp2    && _tp2    > 0) allPr.push(_tp2);
  if (_sl2    && _sl2    > 0) allPr.push(_sl2);
  const rawMin = Math.min(...allPr), rawMax = Math.max(...allPr);
  const rawRng = rawMax - rawMin || rawMax * 0.02 || 1;
  const pad2   = rawRng * 0.15;
  const yMin2  = rawMin - pad2, yMax2 = rawMax + pad2, yRng2 = yMax2 - yMin2;

  // ── Coordinate helpers ────────────────────────────────────────────────────
  // Historical closes fill 85% of chart width; right 15% is "live" extension
  const histW = chW - 52;
  const nowX  = chX + chW - 16;

  const toXC = (i: number) => chX + 12 + (i / Math.max(n - 1, 1)) * histW;
  const toY2 = (v: number) =>
    arcY + chH - 10 - ((v - yMin2) / yRng2) * (chH - 20);

  // ── Build smooth bezier path through close prices ─────────────────────────
  // Uses cardinal spline control points for organic, non-jagged curves.
  const pts = prices.map((v, i) => ({ x: toXC(i), y: toY2(v) }));
  const liveY = _cur2 && _cur2 > 0 ? toY2(_cur2) : pts[pts.length - 1].y;

  function smoothPath(c: CanvasRenderingContext2D, points: {x:number;y:number}[], tension = 0.35) {
    // Draw a smooth cubic bezier through all points using cardinal spline
    c.moveTo(points[0].x, points[0].y);
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[Math.max(i - 1, 0)];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[Math.min(i + 2, points.length - 1)];
      const cp1x = p1.x + (p2.x - p0.x) * tension;
      const cp1y = p1.y + (p2.y - p0.y) * tension;
      const cp2x = p2.x - (p3.x - p1.x) * tension;
      const cp2y = p2.y - (p3.y - p1.y) * tension;
      c.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
    }
  }

  // ── Chart background ──────────────────────────────────────────────────────
  rr(ctx, chX, arcY, chW, chH, 14);
  ctx.fillStyle = "rgba(255,255,255,0.016)"; ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.055)"; ctx.lineWidth = 1; ctx.stroke();

  // Clip everything from here
  ctx.save();
  rr(ctx, chX, arcY, chW, chH, 14); ctx.clip();

  // Subtle horizontal grid lines
  ctx.strokeStyle = "rgba(255,255,255,0.025)"; ctx.lineWidth = 1;
  [0.25, 0.5, 0.75].forEach(p => {
    const ly = arcY + chH * p;
    ctx.beginPath(); ctx.moveTo(chX + 10, ly); ctx.lineTo(chX + chW - 10, ly); ctx.stroke();
  });

  // ── TP / SL zone fills (subtle color bands) ───────────────────────────────
  if (_tp2 && _tp2 > 0 && _entry2 && _entry2 > 0) {
    const y1 = Math.min(toY2(_tp2), toY2(_entry2));
    const y2 = Math.max(toY2(_tp2), toY2(_entry2));
    const zg = ctx.createLinearGradient(0, y1, 0, y2);
    zg.addColorStop(0, "rgba(74,222,128,0.07)"); zg.addColorStop(1, "rgba(74,222,128,0.02)");
    ctx.fillStyle = zg;
    ctx.fillRect(chX + 10, Math.max(y1, arcY + 4), chW - 20,
      Math.min(y2, arcY + chH - 4) - Math.max(y1, arcY + 4));
  }
  if (_sl2 && _sl2 > 0 && _entry2 && _entry2 > 0) {
    const y1 = Math.min(toY2(_sl2), toY2(_entry2));
    const y2 = Math.max(toY2(_sl2), toY2(_entry2));
    const zg = ctx.createLinearGradient(0, y1, 0, y2);
    zg.addColorStop(0, "rgba(248,113,113,0.02)"); zg.addColorStop(1, "rgba(248,113,113,0.07)");
    ctx.fillStyle = zg;
    ctx.fillRect(chX + 10, Math.max(y1, arcY + 4), chW - 20,
      Math.min(y2, arcY + chH - 4) - Math.max(y1, arcY + 4));
  }

  // ── TP / SL / Entry horizontal lines ─────────────────────────────────────
  const hlines = [
    { price: _tp2,    color: "rgba(74,222,128,0.4)",   label: "TP", dash: [4,5] as number[] },
    { price: _sl2,    color: "rgba(248,113,113,0.4)",  label: "SL", dash: [4,5] as number[] },
    { price: _entry2, color: "rgba(255,255,255,0.18)", label: "",   dash: [2,7] as number[] },
  ];
  hlines.forEach(({ price, color, label, dash }) => {
    if (!price || price <= 0) return;
    const ly = toY2(price);
    if (ly <= arcY + 5 || ly >= arcY + chH - 5) return;
    ctx.strokeStyle = color; ctx.lineWidth = 0.75;
    ctx.setLineDash(dash);
    ctx.beginPath(); ctx.moveTo(chX + 10, ly); ctx.lineTo(chX + chW - 10, ly); ctx.stroke();
    ctx.setLineDash([]);
    if (label) {
      ctx.fillStyle = color.replace(/[\d.]+\)$/, "0.85)");
      ctx.font = "500 6.5px \"JetBrains Mono\",monospace";
      ctx.textAlign = "left"; ctx.textBaseline = "middle";
      ctx.fillText(label, chX + 14, ly - 5);
      ctx.textBaseline = "alphabetic";
    }
  });

  // ── Area fill under the smooth curve ─────────────────────────────────────
  // Gradient from theme color → transparent, includes the live extension
  const areaGrad = ctx.createLinearGradient(0, arcY, 0, arcY + chH);
  areaGrad.addColorStop(0, h2r(T.a2, 0.28));
  areaGrad.addColorStop(0.6, h2r(T.a2, 0.08));
  areaGrad.addColorStop(1, "transparent");

  ctx.beginPath();
  smoothPath(ctx, pts);
  // Extend to live price, then close path along bottom
  ctx.lineTo(nowX, liveY);
  ctx.lineTo(nowX, arcY + chH - 4);
  ctx.lineTo(pts[0].x, arcY + chH - 4);
  ctx.closePath();
  ctx.fillStyle = areaGrad; ctx.fill();

  // ── Smooth price line (glowing stroke) ────────────────────────────────────
  // Draw the glow pass first (wider, blurred), then the crisp line on top
  ctx.save();
  ctx.shadowColor = T.a1; ctx.shadowBlur = 8;
  ctx.beginPath(); smoothPath(ctx, pts);
  ctx.strokeStyle = h2r(T.a1, 0.35); ctx.lineWidth = 4;
  ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.stroke();
  ctx.restore();

  ctx.beginPath(); smoothPath(ctx, pts);
  ctx.strokeStyle = T.a1; ctx.lineWidth = 1.8;
  ctx.lineJoin = "round"; ctx.lineCap = "round"; ctx.stroke();

  // ── Live extension: dotted bridge from last historical close → now ────────
  // This is THE fix: the dot is always the endpoint of a connected segment,
  // never floating. Dotted style signals "price still moving".
  const lastPt = pts[pts.length - 1];
  ctx.setLineDash([2, 4]);
  ctx.strokeStyle = h2r(T.a1, 0.4); ctx.lineWidth = 1.2;
  ctx.beginPath(); ctx.moveTo(lastPt.x, lastPt.y); ctx.lineTo(nowX, liveY);
  ctx.stroke(); ctx.setLineDash([]);

  // ── Entry crosshair + dot ─────────────────────────────────────────────────
  if (_entry2 && _entry2 > 0 && n > 2) {
    let entXIdx = Math.floor(n * 0.35);
    if (candleTimes.length > 0 && signal.timestamp) {
      let minDiff = Infinity;
      candleTimes.forEach((t, idx) => {
        const diff = Math.abs(t - signal.timestamp);
        if (diff < minDiff) { minDiff = diff; entXIdx = idx; }
      });
    }
    const entMX = toXC(entXIdx);
    const entMY = toY2(_entry2);

    // Vertical tick
    ctx.strokeStyle = "rgba(255,255,255,0.12)"; ctx.lineWidth = 1;
    ctx.setLineDash([2, 5]);
    ctx.beginPath(); ctx.moveTo(entMX, arcY + 5); ctx.lineTo(entMX, arcY + chH - 5); ctx.stroke();
    ctx.setLineDash([]);

    // Dot at entry price level (not at close price)
    ctx.beginPath(); ctx.arc(entMX, entMY, 4.5, 0, Math.PI * 2);
    ctx.fillStyle = T.bg1; ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.8)"; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.beginPath(); ctx.arc(entMX, entMY, 2, 0, Math.PI * 2);
    ctx.fillStyle = T.a1; ctx.fill();

    // Label
    ctx.fillStyle = "rgba(255,255,255,0.3)";
    ctx.font = "400 6px \"JetBrains Mono\",monospace";
    ctx.textAlign = "center"; ctx.textBaseline = "bottom";
    ctx.fillText("ENTRY", entMX, arcY + chH - 2);
    ctx.textBaseline = "alphabetic";
  }

  // ── Live price dot — always at the end of the line ───────────────────────
  if (_cur2 && _cur2 > 0) {
    // Soft pulse ring
    ctx.save();
    ctx.shadowColor = T.a1; ctx.shadowBlur = 16;
    ctx.beginPath(); ctx.arc(nowX, liveY, 6, 0, Math.PI * 2);
    ctx.fillStyle = h2r(T.a1, 0.25); ctx.fill();
    ctx.restore();
    // Solid glow dot
    ctx.beginPath(); ctx.arc(nowX, liveY, 4.5, 0, Math.PI * 2);
    ctx.fillStyle = T.a1; ctx.fill();
    // White core
    ctx.beginPath(); ctx.arc(nowX, liveY, 2, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff"; ctx.fill();

    // Price pill to the left of the dot
    const prLabel = `$${smartFmt(_cur2)}`;
    ctx.font = "600 7.5px \"JetBrains Mono\",monospace";
    const lblW = ctx.measureText(prLabel).width;
    let pillX = nowX - lblW - 16;
    if (pillX < chX + 14) pillX = nowX + 10;
    const pillY = liveY - 6.5;
    rr(ctx, pillX - 5, pillY - 1, lblW + 10, 14, 3);
    ctx.fillStyle = h2r(T.a3, 0.85); ctx.fill();
    ctx.strokeStyle = h2r(T.a1, 0.4); ctx.lineWidth = 0.5; ctx.stroke();
    ctx.fillStyle = T.a1;
    ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.fillText(prLabel, pillX, pillY + 6);
    ctx.textBaseline = "alphabetic";
  }

  ctx.restore(); // end chart clip

  // ── Bottom bar ────────────────────────────────────────────────────────────
  const botBarH = 80;
  const botY = arcY + chH + 24;
  rr(ctx, 28, botY, W - 56, botBarH, 14);
  ctx.fillStyle = h2r(T.a1, 0.05); ctx.fill();
  ctx.strokeStyle = h2r(T.a1, 0.12); ctx.lineWidth = 1; ctx.stroke();

  // Pattern behind bottom bar
  ctx.save(); rr(ctx, 28, botY, W - 56, botBarH, 14); ctx.clip();
  ctx.strokeStyle = h2r(T.a1, 0.04); ctx.lineWidth = 1;
  for (let ix2 = 28; ix2 < W - 28; ix2 += 18) {
    ctx.beginPath(); ctx.moveTo(ix2, botY); ctx.lineTo(ix2, botY + botBarH); ctx.stroke();
  }
  ctx.restore();

  // Subtitle (moved up, no verified / confidence labels)
  ctx.fillStyle = "#5a5a5a";
  ctx.font = "400 9px \"JetBrains Mono\",monospace";
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText("Auto-generated via AI analysis", 44, botY + 20);

  // URL chip — measure AFTER setting font so width is accurate
  const chipPad = 12, chipH = 28;
  const chipX = 30, chipY = botY + 38;
  const urlText = "http://" + website.replace(/^https?:\/\//, "");
  ctx.font = "500 11px \"JetBrains Mono\",monospace";
  const urlTextW = ctx.measureText(urlText).width;
  const globeIconW = 16; // globe icon width + gap
  const chipW = chipPad * 2 + globeIconW + urlTextW + 4;
  rr(ctx, chipX, chipY, chipW, chipH, 7);
  ctx.fillStyle = h2r(T.a1, 0.1); ctx.fill();
  ctx.strokeStyle = h2r(T.a1, 0.4); ctx.lineWidth = 1; ctx.stroke();
  const globeX = chipX + chipPad + 4, globeY2 = chipY + chipH / 2;
  ctx.strokeStyle = T.a1; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(globeX, globeY2, 6, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.ellipse(globeX, globeY2, 3.5, 6, 0, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(globeX - 6.5, globeY2); ctx.lineTo(globeX + 6.5, globeY2); ctx.stroke();
  ctx.fillStyle = T.a1;
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText(urlText, chipX + chipPad + globeIconW + 4, chipY + chipH / 2);

  // ── QR Code (real, scannable → website URL) ──────────────────────────────
  const qrX = W - 74, qrY = botY + 12, qrSize = 56;
  if (qrImg) {
    // Real QR: draw with slight opacity tint matching theme
    ctx.save();
    ctx.globalAlpha = 0.75;
    ctx.drawImage(qrImg, qrX, qrY, qrSize, qrSize);
    ctx.globalAlpha = 1;
    ctx.restore();
  } else {
    // Fallback: decorative placeholder while QR loads
    drawQR(ctx, qrX, qrY, qrSize, T.a1);
  }

  const botStrip = ctx.createLinearGradient(0, 0, W, 0);
  botStrip.addColorStop(0, "transparent"); botStrip.addColorStop(0.2, T.a1);
  botStrip.addColorStop(0.8, T.a1); botStrip.addColorStop(1, "transparent");
  ctx.fillStyle = botStrip; ctx.fillRect(0, H - 4, W, 4);

  const vig = ctx.createRadialGradient(W/2, H/2, H*0.3, W/2, H/2, H*0.75);
  vig.addColorStop(0, "transparent"); vig.addColorStop(1, "rgba(0,0,0,0.35)");
  ctx.save(); rr(ctx, 0, 0, W, H, 20); ctx.clip();
  ctx.fillStyle = vig; ctx.fillRect(0, 0, W, H);
  ctx.restore();
}

// ─── ROE / PnL calculators ───────────────────────────────────────────────────
function calcAutoROE(signal: Signal, leverage: number, livePrice?: number): number {
  if (signal.pnl_pct != null) {
    return parseFloat((Number(signal.pnl_pct) * leverage).toFixed(2));
  }
  const entry = Number(signal.entry ?? signal.current_price);
  const cur   = livePrice ?? Number(signal.current_price);
  if (!entry || !cur) return 0;
  const movePct = signal.decision === "LONG"
    ? ((cur - entry) / entry) * 100
    : ((entry - cur) / entry) * 100;
  return parseFloat((movePct * leverage).toFixed(2));
}

function calcAutoPnL(signal: Signal, leverage: number, entryUsdt = 100, livePrice?: number): number {
  if (signal.pnl_usdt != null) return Number(signal.pnl_usdt);
  const entry = Number(signal.entry ?? signal.current_price);
  const cur   = livePrice ?? Number(signal.current_price);
  if (!entry || !cur) return 0;
  const movePct = signal.decision === "LONG"
    ? (cur - entry) / entry
    : (entry - cur) / entry;
  return parseFloat((entryUsdt * leverage * movePct).toFixed(2));
}

// ─── RESOLVE WS URL ──────────────────────────────────────────────────────────
function getBotWsUrl(): string {
  if (typeof window === "undefined") return "";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host  = window.location.host;
  return `${proto}//${host}/api/bot/ws`;
}

// ─── POSTER MODAL ────────────────────────────────────────────────────────────
function PosterModal({
  signal, leverage, entryUsdt = 20, onClose,
}: {
  signal: Signal;
  leverage: number;
  entryUsdt?: number;
  onClose: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [mode, setMode]     = useState<Mode>("roe");
  const [sharing, setSharing] = useState(false);

  const isClosed = signal.status === "CLOSED" || signal.status === "INVALIDATED";
  const sym      = signal.symbol; // e.g. "BTC_USDT"

  // ── QR Code: generate real scannable QR from website URL ─────────────────
  const [qrImg, setQrImg] = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    const url = "https://sonnetrades.vercel.app";
    QRCode.toDataURL(url, {
      width: 112,       // 2× render size for HD sharpness
      margin: 1,
      color: {
        dark:  "#ffffff",   // white modules — tinted to theme via globalAlpha in drawPoster
        light: "#00000000", // transparent background so poster bg shows through
      },
    }).then((dataUrl) => {
      const img = new window.Image();
      img.onload = () => setQrImg(img);
      img.src = dataUrl;
    }).catch(() => { /* silently fall back to decorative QR */ });
  }, []);

  // ── Candle data for price chart ───────────────────────────────────────────
  const [candles, setCandles] = useState<number[][]>([]);

  useEffect(() => {
    const fetchCandles = async () => {
      try {
        const res  = await fetch(`/api/market/candles/${sym}?granularity=5m&limit=60`);
        const json = await res.json();
        const data = json.data ?? [];
        if (Array.isArray(data) && data.length > 2) {
          setCandles(data);
        }
      } catch { /* silently ignore */ }
    };
    fetchCandles();
    // Refresh candles every 30s to keep chart relatively fresh
    const t = setInterval(fetchCandles, 30_000);
    return () => clearInterval(t);
  }, [sym]);

  // ── Live price state ─────────────────────────────────────────────────────
  const [livePrice, setLivePrice] = useState<number>(
    Number(signal.current_price) || 0,
  );
  // Track source for debug label in UI
  const [priceSource, setPriceSource] = useState<"ws" | "rest" | "initial">("initial");

  // ── FIX: Primary — WebSocket price_tick listener ─────────────────────────
  //
  //  bot_engine emits `price_tick` events every ~2s for every monitored
  //  signal. We tap into the same /api/bot/ws stream so the poster gets
  //  the SAME real-time price the bot uses — zero extra REST overhead.
  //
  //  Flow: WS message → parse JSON → if event=price_tick & symbol matches
  //        → setLivePrice(price)  → canvas redraws automatically.
  useEffect(() => {
    if (isClosed) return;

    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let alive = true;

    const connect = () => {
      if (!alive) return;
      const url = getBotWsUrl();
      if (!url) return;

      ws = new WebSocket(url);

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data as string);
          // price_tick: { id, symbol, price, entry_hit, timestamp }
          if (msg.event === "price_tick" && msg.data?.symbol === sym) {
            const p = Number(msg.data.price);
            if (p > 0) {
              setLivePrice(p);
              setPriceSource("ws");
            }
          }
          // signal_closed / signal_invalidated also carry price
          if (
            (msg.event === "signal_closed" || msg.event === "signal_invalidated") &&
            msg.data?.symbol === sym
          ) {
            const p = Number(msg.data.price ?? msg.data.closed_price);
            if (p > 0) setLivePrice(p);
          }
        } catch { /* ignore malformed frames */ }
      };

      ws.onerror = () => { /* suppress console noise */ };

      ws.onclose = () => {
        // Auto-reconnect with 3s delay (handles page tab re-focus, etc.)
        if (alive) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      };
    };

    connect();

    return () => {
      alive = false;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [sym, isClosed]);

  // ── Fallback — REST poll every 3s ────────────────────────────────────────
  //
  //  Always-on safety net that runs regardless of WS state.
  //  Backend /api/market/ticker hits the WS price cache (≤2s old), so this
  //  is effectively real-time with zero extra MEXC API cost.
  //
  //  We always apply the REST price — WS will still "win" in practice because
  //  price_tick fires every 3s and sets priceSource="ws" immediately.
  //  If WS dies (ws_manager crash, network drop), REST keeps the price live.
  useEffect(() => {
    if (isClosed) return;

    const fetchPrice = async () => {
      try {
        const res  = await fetch(`/api/market/ticker/${sym}`);
        const json = await res.json();
        const d    = json.data ?? {};
        const p    = parseFloat(d.lastPr ?? d.last ?? d.lastPrice ?? "0");
        if (p > 0) {
          // Always update — REST hits the backend WS cache so it's real-time.
          // Only downgrade source label to "rest" if WS hasn't connected yet.
          setLivePrice(p);
          setPriceSource(src => src === "ws" ? "ws" : "rest");
        }
      } catch { /* silently ignore */ }
    };

    fetchPrice();                                  // immediate seed on open
    const timer = setInterval(fetchPrice, 3000);   // 3s continuous safety-net
    return () => clearInterval(timer);
  }, [sym, isClosed]);

  // ── Derived values ───────────────────────────────────────────────────────
  const roeVal = calcAutoROE(signal, leverage, livePrice > 0 ? livePrice : undefined);
  const pnlVal = calcAutoPnL(signal, leverage, entryUsdt, livePrice > 0 ? livePrice : undefined);

  // ── Canvas redraw whenever any input changes ──────────────────────────────
  useEffect(() => {
    if (!canvasRef.current) return;
    drawPoster(canvasRef.current, signal, mode, roeVal, pnlVal, leverage, livePrice, undefined, undefined, 1, candles, qrImg);
  }, [signal, mode, roeVal, pnlVal, leverage, livePrice, candles, qrImg]);

  // ── HD export blob ────────────────────────────────────────────────────────
  const getHDBlob = useCallback((): Promise<Blob> => {
    return new Promise((resolve, reject) => {
      const hd = document.createElement("canvas");
      drawPoster(hd, signal, mode, roeVal, pnlVal, leverage, livePrice, undefined, undefined, 2, candles, qrImg);
      hd.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error("Canvas to Blob failed"));
      }, "image/png");
    });
  }, [signal, mode, roeVal, pnlVal, leverage, livePrice, candles, qrImg]);

  const handleSave = useCallback(async () => {
    const blob = await getHDBlob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `sonnetrade-${signal.symbol}-poster.png`;
    a.click();
    URL.revokeObjectURL(url);
  }, [getHDBlob, signal.symbol]);

  const handleShare = useCallback(async () => {
    setSharing(true);
    try {
      const blob = await getHDBlob();
      const file = new File([blob], `sonnetrade-${signal.symbol}.png`, { type: "image/png" });
      if (navigator.share && navigator.canShare({ files: [file] })) {
        await navigator.share({
          title: `${signal.symbol} ${signal.decision} Signal — SonneTrade`,
          text:  `Check out this ${signal.decision} signal on ${signal.symbol}!`,
          files: [file],
        });
      } else {
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank");
        setTimeout(() => URL.revokeObjectURL(url), 30_000);
      }
    } catch (e) {
      console.error("Share failed", e);
    } finally {
      setSharing(false);
    }
  }, [getHDBlob, signal.symbol, signal.decision]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/75 backdrop-blur-sm sm:p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-card border border-border sm:rounded-2xl rounded-t-2xl w-full sm:max-w-3xl max-h-[95dvh] sm:max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Modal header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold font-mono text-text">Share Poster</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full border border-border text-muted">
              {signal.symbol.replace("_USDT", "")}/USDT · {signal.decision}
            </span>
          </div>
          <button onClick={onClose} className="text-muted hover:text-text transition-colors text-lg leading-none">✕</button>
        </div>

        <div className="flex flex-col-reverse md:flex-row gap-0">
          {/* Controls */}
          <div className="w-full md:w-60 shrink-0 p-4 sm:p-5 border-t md:border-t-0 md:border-r border-border flex flex-col gap-4">
              <div className="flex flex-col gap-2">
              <span className="text-[10px] font-mono uppercase tracking-widest text-muted">Display Mode</span>
              <div className="flex flex-row md:flex-col gap-1.5">
                {(["roe", "pnl", "both"] as Mode[]).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`flex-1 md:flex-none px-3 py-2 rounded-lg text-xs font-mono text-left transition-all border ${
                      mode === m
                        ? "border-accent/50 bg-accent/10 text-accent"
                        : "border-border text-muted hover:text-text hover:border-border/80"
                    }`}
                  >
                    {m === "roe"  && "📊 ROE only"}
                    {m === "pnl"  && "💰 PnL only"}
                    {m === "both" && "✨ ROE + PnL"}
                  </button>
                ))}
              </div>
            </div>

            {/* Live values display */}
            <div className="flex flex-col gap-2 bg-bg/60 rounded-xl p-3 border border-border/50">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] font-mono uppercase tracking-widest text-muted">Live values</span>
                {!isClosed && (
                  <span className="flex items-center gap-1 text-[9px] font-mono text-accent/70">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                    {/* FIX: show which source is feeding the price */}
                    {priceSource === "ws" ? "ws" : priceSource === "rest" ? "rest" : "…"}
                  </span>
                )}
              </div>

              {/* Current price */}
              <div className="flex justify-between items-center">
                <span className="text-[11px] font-mono text-muted">Price</span>
                <span className="text-xs font-mono font-semibold text-blue-300">
                  ${smartFmt(livePrice > 0 ? livePrice : signal.current_price)}
                </span>
              </div>

              {(mode === "roe" || mode === "both") && (
                <div className="flex justify-between items-center">
                  <span className="text-[11px] font-mono text-muted">ROE</span>
                  <span className={`text-xs font-mono font-semibold ${roeVal >= 0 ? "text-success" : "text-danger"}`}>
                    {roeVal >= 0 ? "+" : ""}{roeVal}%
                  </span>
                </div>
              )}
              {(mode === "pnl" || mode === "both") && (
                <div className="flex justify-between items-center">
                  <span className="text-[11px] font-mono text-muted">PnL</span>
                  <span className={`text-xs font-mono font-semibold ${pnlVal >= 0 ? "text-success" : "text-danger"}`}>
                    {pnlVal >= 0 ? "+" : ""}{pnlVal.toFixed(2)} USDT
                  </span>
                </div>
              )}
              <p className="text-[9px] font-mono text-muted/50 mt-1 leading-relaxed">
                {isClosed
                  ? "From closed trade result"
                  : "Live via WebSocket · REST fallback"}
              </p>
            </div>

            {/* Signal info */}
            <div className="border-t border-border pt-3 flex flex-col gap-1.5 text-[11px] font-mono">
              <div className="flex justify-between text-muted">
                <span>Current</span>
                <span className="text-blue-300">
                  {livePrice > 0 ? `$${smartFmt(livePrice)}` : "—"}
                </span>
              </div>
              <div className="flex justify-between text-muted">
                <span>Entry</span>
                <span className="text-text">
                  {signal.entry != null && Number(signal.entry) > 0
                    ? `$${smartFmt(Number(signal.entry))}`
                    : "—"}
                </span>
              </div>
              <div className="flex justify-between text-muted">
                <span>TP</span>
                <span className="text-success">
                  {signal.tp != null && Number(signal.tp) > 0
                    ? `$${smartFmt(Number(signal.tp))}`
                    : "—"}
                </span>
              </div>
              <div className="flex justify-between text-muted">
                <span>SL</span>
                <span className="text-danger">
                  {signal.sl != null && Number(signal.sl) > 0
                    ? `$${smartFmt(Number(signal.sl))}`
                    : "—"}
                </span>
              </div>
              {signal.pnl_pct != null && (
                <div className="flex justify-between text-muted">
                  <span>Result</span>
                  <span className={signal.pnl_pct >= 0 ? "text-success" : "text-danger"}>
                    {signal.result} · {signal.pnl_pct >= 0 ? "+" : ""}{signal.pnl_pct.toFixed(4)}%
                  </span>
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div className="flex flex-col gap-2 pt-1 border-t border-border">
              <button
                onClick={handleSave}
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-xs font-mono font-semibold bg-accent text-white hover:opacity-90 transition-opacity"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Save HD PNG
              </button>
              <button
                onClick={handleShare}
                disabled={sharing}
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-xs font-mono font-semibold border border-border text-text hover:bg-bg transition-colors disabled:opacity-50"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                </svg>
                {sharing ? "Sharing…" : "Share"}
              </button>
              <p className="text-[9px] text-muted/60 text-center font-mono leading-relaxed">
                Share via WA, Telegram, X, etc.<br />
                via your device's share menu
              </p>
            </div>
          </div>

          {/* Canvas preview */}
          <div className="flex-1 p-3 sm:p-5 flex items-center justify-center bg-[#050508]">
            <canvas
              ref={canvasRef}
              style={{ borderRadius: 14, maxWidth: "100%", boxShadow: "0 20px 60px rgba(0,0,0,0.8)" }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── POSTER BUTTON ────────────────────────────────────────────────────────────
export default function PosterButton({
  signal,
  leverage = 50,
  entryUsdt = 20,
  allowForClosed = false,
}: {
  signal: Signal;
  leverage?: number;
  entryUsdt?: number;
  allowForClosed?: boolean;
}) {
  const [open, setOpen] = useState(false);

  const shouldShow =
    (signal.entry_hit && signal.status === "OPEN") ||
    (allowForClosed && signal.status === "CLOSED" && signal.result != null);

  if (!shouldShow) return null;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="Share trade poster"
        className="
          inline-flex items-center justify-center
          w-7 h-7 rounded-lg shrink-0
          border border-accent/30 bg-accent/5 text-accent
          hover:bg-accent/15 hover:border-accent/60
          transition-all duration-150
        "
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      </button>

      {open && (
        <PosterModal
          signal={signal}
          leverage={leverage}
          entryUsdt={entryUsdt}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
