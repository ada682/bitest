"""
Indicator calculations for scalping bot.
"""
from typing import List, Optional


def compute_ema(closes: List[float], period: int) -> List[float]:
    ema = []
    k = 2 / (period + 1)
    for i, c in enumerate(closes):
        if i == 0:
            ema.append(c)
        else:
            ema.append(c * k + ema[-1] * (1 - k))
    return ema


def compute_rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    if len(closes) <= period:
        return [None] * len(closes)

    rsi = [None] * period
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in diffs]
    losses = [max(-d, 0) for d in diffs]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(closes)):
        if avg_loss == 0:
            rsi.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - 100 / (1 + rs))
        if i < len(closes) - 1:
            idx = i  # diffs[i] corresponds to closes[i+1]-closes[i]
            g = gains[idx]
            l = losses[idx]
            avg_gain = (avg_gain * (period - 1) + g) / period
            avg_loss = (avg_loss * (period - 1) + l) / period

    return rsi


def compute_parabolic_sar(highs: List[float], lows: List[float],
                           af_start=0.02, af_step=0.02, af_max=0.2) -> List[Optional[float]]:
    if len(highs) < 2:
        return [None] * len(highs)

    sar = [None] * len(highs)
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


def compute_all(candles: list) -> dict:
    """
    Compute all indicators from candle data.
    candles: [[timestamp, open, high, low, close, volume], ...]
    """
    opens = [float(c[1]) for c in candles]
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]

    ema9 = compute_ema(closes, 9)
    ema21 = compute_ema(closes, 21)
    rsi = compute_rsi(closes, 14)
    psar = compute_parabolic_sar(highs, lows)

    trend = "BULLISH" if ema9[-1] > ema21[-1] else "BEARISH"

    return {
        "ema9": ema9,
        "ema21": ema21,
        "rsi": rsi,
        "psar": psar,
        "ema9_last": round(ema9[-1], 4),
        "ema21_last": round(ema21[-1], 4),
        "rsi_last": round(rsi[-1], 2) if rsi[-1] is not None else None,
        "psar_last": round(psar[-1], 4) if psar[-1] is not None else None,
        "current_price": closes[-1],
        "trend": trend,
    }


def format_ohlcv_text(candles: list, limit: int = 50) -> str:
    """Format OHLCV data as readable text for AI prompt."""
    recent = candles[-limit:]
    lines = ["timestamp, open, high, low, close, volume"]
    for c in recent:
        lines.append(f"{c[0]}, {c[1]}, {c[2]}, {c[3]}, {c[4]}, {c[5]}")
    return "\n".join(lines)


def calculate_position_size(balance: float, leverage: float, price: float,
                              mode: str = "ALL_IN", manual_margin: float = None,
                              volume_place: int = 3,
                              safety_factor: float = 0.95) -> str:
    """
    Calculate order size.
    mode: ALL_IN or MANUAL
    safety_factor: fraction of balance to use (default 0.95 = 95%) to reserve
                   room for fees and avoid 'exceeds balance' errors.
    For MANUAL mode, if manual_margin > available balance it is capped at
    balance * safety_factor so the order never exceeds what the account holds.
    """
    if mode == "MANUAL" and manual_margin is not None:
        # Cap manual margin so it never exceeds available balance
        max_margin = balance * safety_factor
        margin = min(float(manual_margin), max_margin)
    else:
        # ALL_IN: use most of the balance but keep a fee buffer
        margin = balance * safety_factor

    notional = margin * leverage
    size = notional / price
    return str(round(size, volume_place))
