"use client";
import { useRef, useEffect, useState, useCallback } from "react";
import type { Signal } from "@/lib/types";

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
// Handles tiny numbers like 0.000002 by auto-scaling decimal places.
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
// DPR param: pass 2 for HD export, 1 for preview
function drawPoster(
  canvas: HTMLCanvasElement,
  signal: Signal,
  mode: Mode,
  roeVal: number,
  pnlVal: number,
  leverage: number,
  currentPrice: number,       // ← live current price
  platform = "SonneTrade",
  website = "sonnetrades.vercel.app",
  dpr = 1,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  // Logical size
  const W = 540, H = 800;
  // Physical size = logical × dpr (HD when dpr=2)
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  // Scale all draw calls so we still think in 540×800
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
    // PnL only
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

  // ── Stat cards (current price / entry / TP / SL) ──────────────────────────
  // Uses smartFmt so tiny prices like 0.000002 display correctly
  const _cur   = currentPrice > 0 ? currentPrice : (signal.current_price ?? null);
  const _entry = signal.entry != null ? Number(signal.entry) : null;
  const _tp    = signal.tp    != null ? Number(signal.tp)    : null;
  const _sl    = signal.sl    != null ? Number(signal.sl)    : null;

  const statDefs = [
    {
      label: "CURRENT",
      val: (_cur != null && _cur > 0) ? `$${smartFmt(_cur)}` : "—",
      c: "#93c5fd",   // blue
    },
    {
      label: "ENTRY",
      val: (_entry != null && _entry > 0) ? `$${smartFmt(_entry)}` : "—",
      c: "#e2e8f0",
    },
    {
      label: "TAKE PROFIT",
      val: (_tp != null && _tp > 0) ? `$${smartFmt(_tp)}` : "—",
      c: "#86efac",
    },
    {
      label: "STOP LOSS",
      val: (_sl != null && _sl > 0) ? `$${smartFmt(_sl)}` : "—",
      c: "#fca5a5",
    },
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

    // Auto-shrink font for long value strings (e.g. 8-decimal prices)
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

  // ── Sparkline ─────────────────────────────────────────────────────────────
  const arcY = statsYBase + 84;
  const chX = 28, chW = W - 56, chH = 100;
  rr(ctx, chX, arcY, chW, chH, 14);
  ctx.fillStyle = "rgba(255,255,255,0.018)"; ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.05)"; ctx.lineWidth = 1; ctx.stroke();

  ctx.strokeStyle = "rgba(255,255,255,0.035)"; ctx.lineWidth = 1;
  [0.33, 0.66].forEach(p => {
    const ly = arcY + chH * p;
    ctx.beginPath(); ctx.moveTo(chX + 10, ly); ctx.lineTo(chX + chW - 10, ly); ctx.stroke();
  });

  const spark = [12, 18, 15, 22, 19, 28, 24, 20, 30, 26, 34, 31, 40, 36, 44, 41, 50, 47, 55, 52, 60, 58, 68, 64, 72, 70, 80, 76, 85, 82, 90, 88, 96, 100];
  const nPts = spark.length, padX = 14, padY = 12;
  const plotW = chW - padX * 2, plotH = chH - padY * 2;

  ctx.save();
  rr(ctx, chX, arcY, chW, chH, 14); ctx.clip();

  const areaFill = ctx.createLinearGradient(0, arcY, 0, arcY + chH);
  areaFill.addColorStop(0, h2r(T.a1, 0.22)); areaFill.addColorStop(1, "transparent");
  ctx.beginPath();
  spark.forEach((v, i) => {
    const px = chX + padX + (i / (nPts - 1)) * plotW;
    const py = arcY + padY + (1 - v / 100) * plotH;
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  });
  ctx.lineTo(chX + padX + plotW, arcY + chH - padY);
  ctx.lineTo(chX + padX, arcY + chH - padY);
  ctx.closePath();
  ctx.fillStyle = areaFill; ctx.fill();

  ctx.beginPath();
  spark.forEach((v, i) => {
    const px = chX + padX + (i / (nPts - 1)) * plotW;
    const py = arcY + padY + (1 - v / 100) * plotH;
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  });
  ctx.strokeStyle = T.a1; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.stroke();

  const endX = chX + padX + plotW;
  const endY = arcY + padY + (1 - spark[nPts - 1] / 100) * plotH;
  ctx.beginPath(); ctx.arc(endX, endY, 5, 0, Math.PI * 2);
  ctx.fillStyle = T.a1; ctx.fill();
  ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke();
  ctx.restore();

  ctx.fillStyle = h2r("#ffffff", 0.18);
  ctx.font = "400 9px \"JetBrains Mono\",monospace";
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText("PERFORMANCE", chX + 10, arcY + 14);
  ctx.fillStyle = sc;
  ctx.font = "bold 18px sans-serif";
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  ctx.fillText(isLong ? "↗" : "↘", chX + chW - 10, arcY + 16);

  // ── Divider 2 ────────────────────────────────────────────────────────────
  const div2Y = arcY + chH + 28;
  ctx.strokeStyle = dg; ctx.lineWidth = 1; ctx.setLineDash([4, 8]);
  ctx.beginPath(); ctx.moveTo(28, div2Y); ctx.lineTo(W - 28, div2Y); ctx.stroke();
  ctx.setLineDash([]);

  // ── Bottom branding ──────────────────────────────────────────────────────
  const botH = 100, botY = H - botH;
  rr(ctx, 0, botY, W, botH, { tl: 0, tr: 0, bl: 20, br: 20 });
  const botG = ctx.createLinearGradient(0, botY, 0, H);
  botG.addColorStop(0, "transparent"); botG.addColorStop(1, h2r(T.a1, 0.08));
  ctx.fillStyle = botG; ctx.fill();

  ctx.strokeStyle = h2r(T.a1, 0.15); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, botY); ctx.lineTo(W, botY); ctx.stroke();

  ctx.fillStyle = T.a1;
  ctx.font = "700 20px Outfit,sans-serif";
  ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
  ctx.fillText(platform.toUpperCase(), 30, botY + 34);

  ctx.fillStyle = "#323232";
  ctx.font = "400 10px \"JetBrains Mono\",monospace";
  ctx.fillText("Trade smart. Trade fast. Trade with edge.", 30, botY + 54);

  ctx.font = "500 11px \"JetBrains Mono\",monospace";
  const urlW2 = ctx.measureText(websiteDisplay).width;
  const chipPad = 14, chipH = 28, chipW = urlW2 + chipPad * 2 + 20;
  const chipX = 30, chipY = botY + 64;
  rr(ctx, chipX, chipY, chipW, chipH, 7);
  ctx.fillStyle = h2r(T.a1, 0.1); ctx.fill();
  ctx.strokeStyle = h2r(T.a1, 0.4); ctx.lineWidth = 1; ctx.stroke();
  const globeX = chipX + chipPad - 2, globeY = chipY + chipH / 2;
  ctx.strokeStyle = T.a1; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(globeX, globeY, 6, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.ellipse(globeX, globeY, 3.5, 6, 0, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(globeX - 6.5, globeY); ctx.lineTo(globeX + 6.5, globeY); ctx.stroke();
  ctx.fillStyle = T.a1;
  ctx.font = "500 11px \"JetBrains Mono\",monospace";
  ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText(websiteDisplay, chipX + chipPad + 12, chipY + chipH / 2);

  drawQR(ctx, W - 74, botY + 16, 56, T.a1);

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

// ─── AUTO-CALCULATE ROE FROM SIGNAL ──────────────────────────────────────────
// livePrice overrides signal.current_price so poster updates in real-time.
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

// ─── POSTER MODAL ────────────────────────────────────────────────────────────
function PosterModal({
  signal, leverage, entryUsdt = 20, onClose,
}: {
  signal: Signal;
  leverage: number;
  entryUsdt?: number;
  onClose: () => void;
}) {
  const canvasRef   = useRef<HTMLCanvasElement>(null);
  const [mode, setMode] = useState<Mode>("roe");
  const [sharing, setSharing] = useState(false);

  // ── Live price polling ────────────────────────────────────────────────────
  // Polls /api/market/ticker every 2s so ROE/PnL update in real-time
  // while the poster is open. For closed signals we skip polling.
  const [livePrice, setLivePrice] = useState<number>(
    Number(signal.current_price) || 0,
  );

  useEffect(() => {
    // Closed signals already have final pnl — no need to poll
    if (signal.status === "CLOSED" || signal.status === "INVALIDATED") return;

    const sym = signal.symbol; // e.g. "BTC_USDT"

    const fetchPrice = async () => {
      try {
        const res  = await fetch(`/api/market/ticker/${sym}`);
        const json = await res.json();
        const d    = json.data ?? {};
        const p    = parseFloat(d.lastPr ?? d.last ?? d.lastPrice ?? "0");
        if (p > 0) setLivePrice(p);
      } catch {
        // silently ignore — keep last known price
      }
    };

    fetchPrice();                                   // immediate first fetch
    const timer = setInterval(fetchPrice, 2000);    // then every 2s
    return () => clearInterval(timer);
  }, [signal.symbol, signal.status]);

  // Auto-calculated values using live price
  const roeVal = calcAutoROE(signal, leverage, livePrice > 0 ? livePrice : undefined);
  const pnlVal = calcAutoPnL(signal, leverage, entryUsdt, livePrice > 0 ? livePrice : undefined);

  // Draw preview (1× DPR) whenever inputs change
  useEffect(() => {
    if (!canvasRef.current) return;
    drawPoster(canvasRef.current, signal, mode, roeVal, pnlVal, leverage, livePrice, undefined, undefined, 1);
  }, [signal, mode, roeVal, pnlVal, leverage, livePrice]);

  // Returns a HD blob (2× DPR) for saving
  const getHDBlob = useCallback((): Promise<Blob> => {
    return new Promise((resolve, reject) => {
      const hd = document.createElement("canvas");
      drawPoster(hd, signal, mode, roeVal, pnlVal, leverage, livePrice, undefined, undefined, 2);
      hd.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error("Canvas to Blob failed"));
      }, "image/png");
    });
  }, [signal, mode, roeVal, pnlVal, leverage, livePrice]);

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

  const isPos = mode === "pnl" ? pnlVal >= 0 : roeVal >= 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-card border border-border rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto shadow-2xl">
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

        <div className="flex flex-col md:flex-row gap-0">
          {/* Controls */}
          <div className="w-full md:w-60 shrink-0 p-5 border-b md:border-b-0 md:border-r border-border flex flex-col gap-4">
            {/* Mode selector */}
            <div className="flex flex-col gap-2">
              <span className="text-[10px] font-mono uppercase tracking-widest text-muted">Display Mode</span>
              <div className="flex flex-col gap-1.5">
                {(["roe", "pnl", "both"] as Mode[]).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`px-3 py-2 rounded-lg text-xs font-mono text-left transition-all border ${
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

            {/* Live-calculated values display */}
            <div className="flex flex-col gap-2 bg-bg/60 rounded-xl p-3 border border-border/50">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] font-mono uppercase tracking-widest text-muted">Live values</span>
                {signal.status === "OPEN" && (
                  <span className="flex items-center gap-1 text-[9px] font-mono text-accent/70">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                    live
                  </span>
                )}
              </div>

              {/* Current price — always shown */}
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
                {signal.pnl_pct != null
                  ? "From closed trade result"
                  : "Updates every 2s from MEXC"}
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
          <div className="flex-1 p-5 flex items-center justify-center bg-[#050508]">
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
// allowForClosed=true → tampilkan untuk signal yang sudah closed (history page)
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

  // Show for: in-trade (entry hit & OPEN), or explicitly allowed for closed
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
          inline-flex items-center gap-1 px-2 py-1 rounded-lg
          border border-accent/30 bg-accent/5 text-accent
          hover:bg-accent/15 hover:border-accent/60
          text-[10px] font-mono font-medium uppercase tracking-wide
          transition-all duration-150
        "
      >
        <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
        Poster
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
