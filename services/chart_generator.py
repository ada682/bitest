"""
Chart image generator using matplotlib.
Generates candlestick chart with EMA9, EMA21, Parabolic SAR, and RSI panel.
"""

import io
import base64
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec


def compute_ema(closes: list, period: int) -> list:
    ema = []
    k = 2 / (period + 1)
    for i, c in enumerate(closes):
        if i == 0:
            ema.append(c)
        else:
            ema.append(c * k + ema[-1] * (1 - k))
    return ema


def compute_rsi(closes: list, period: int = 14) -> list:
    rsi = [None] * period
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(closes)):
        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - 100 / (1 + rs))
        if i < len(closes) - 1:
            g = gains[i]
            l = losses[i]
            avg_gain = (avg_gain * (period - 1) + g) / period
            avg_loss = (avg_loss * (period - 1) + l) / period

    return rsi


def compute_parabolic_sar(highs: list, lows: list, af_start=0.02, af_step=0.02, af_max=0.2) -> list:
    sar = [None] * len(highs)
    if len(highs) < 2:
        return sar

    bull = True
    ep = highs[0]
    af = af_start
    sar[0] = lows[0]

    for i in range(1, len(highs)):
        prev_sar = sar[i - 1]
        new_sar = prev_sar + af * (ep - prev_sar)

        if bull:
            new_sar = min(new_sar, lows[i - 1], lows[i - 2] if i > 1 else lows[i - 1])
            if lows[i] < new_sar:
                bull = False
                new_sar = ep
                ep = lows[i]
                af = af_start
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_step, af_max)
        else:
            new_sar = max(new_sar, highs[i - 1], highs[i - 2] if i > 1 else highs[i - 1])
            if highs[i] > new_sar:
                bull = True
                new_sar = ep
                ep = highs[i]
                af = af_start
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_step, af_max)

        sar[i] = new_sar

    return sar


def generate_chart_image(candles: list, symbol: str = "BTC/USDT", timeframe: str = "1m") -> str:
    """
    Generate a candlestick chart with indicators.
    
    Args:
        candles: List of [timestamp, open, high, low, close, volume]
        symbol: Trading pair symbol
        timeframe: Timeframe label
        
    Returns:
        Base64 encoded PNG image string
    """
    if not candles or len(candles) < 20:
        return None

    # Parse candles
    opens = [float(c[1]) for c in candles]
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]

    n = len(candles)
    x = np.arange(n)

    # Compute indicators
    ema9 = compute_ema(closes, 9)
    ema21 = compute_ema(closes, 21)
    rsi = compute_rsi(closes, 14)
    psar = compute_parabolic_sar(highs, lows)

    # Plot setup
    fig = plt.figure(figsize=(14, 9), facecolor="#0d1117")
    gs = GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.05, figure=fig)

    ax1 = fig.add_subplot(gs[0])  # Candlestick
    ax2 = fig.add_subplot(gs[1], sharex=ax1)  # RSI
    ax3 = fig.add_subplot(gs[2], sharex=ax1)  # Volume

    for ax in [ax1, ax2, ax3]:
        ax.set_facecolor("#0d1117")
        ax.tick_params(colors="#8b949e", labelsize=7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("#21262d")
        ax.spines["left"].set_color("#21262d")
        ax.yaxis.set_label_position("right")
        ax.yaxis.tick_right()

    # Draw candles
    for i in x:
        color = "#26a641" if closes[i] >= opens[i] else "#f85149"
        body_bottom = min(opens[i], closes[i])
        body_height = abs(closes[i] - opens[i])
        ax1.bar(i, body_height, bottom=body_bottom, color=color, width=0.7, linewidth=0)
        ax1.plot([i, i], [lows[i], highs[i]], color=color, linewidth=0.8)

    # EMA lines
    ax1.plot(x, ema9, color="#58a6ff", linewidth=1.2, label="EMA 9")
    ax1.plot(x, ema21, color="#f78166", linewidth=1.2, label="EMA 21")

    # Parabolic SAR
    for i in x:
        if psar[i] is not None:
            dot_color = "#26a641" if psar[i] < closes[i] else "#f85149"
            ax1.scatter(i, psar[i], color=dot_color, s=8, zorder=5)

    # Legend
    ax1.legend(loc="upper left", fontsize=7, facecolor="#161b22", labelcolor="#c9d1d9", edgecolor="#30363d")
    ax1.set_title(f"{symbol} | {timeframe}", color="#c9d1d9", fontsize=9, pad=4)
    ax1.tick_params(labelbottom=False)

    # RSI
    rsi_vals = [r if r is not None else np.nan for r in rsi]
    ax2.plot(x, rsi_vals, color="#bc8cff", linewidth=1.0)
    ax2.axhline(70, color="#f85149", linewidth=0.5, linestyle="--")
    ax2.axhline(30, color="#26a641", linewidth=0.5, linestyle="--")
    ax2.fill_between(x, rsi_vals, 70, where=[r >= 70 if r else False for r in rsi_vals], alpha=0.15, color="#f85149")
    ax2.fill_between(x, rsi_vals, 30, where=[r <= 30 if r else False for r in rsi_vals], alpha=0.15, color="#26a641")
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("RSI", color="#8b949e", fontsize=7, rotation=0, labelpad=25)
    ax2.tick_params(labelbottom=False)

    # Volume
    vol = [float(c[5]) for c in candles]
    vol_colors = ["#26a641" if closes[i] >= opens[i] else "#f85149" for i in range(n)]
    ax3.bar(x, vol, color=vol_colors, width=0.7, alpha=0.7, linewidth=0)
    ax3.set_ylabel("Vol", color="#8b949e", fontsize=7, rotation=0, labelpad=25)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    buf.seek(0)

    return base64.b64encode(buf.read()).decode("utf-8")
