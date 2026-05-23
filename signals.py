import numpy as np
import pandas as pd

# -------------------------
# RSI CALCULATION
# -------------------------

def calculate_rsi(data, period=14):

    delta = data.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


# -------------------------
# MAIN GENERATOR
# -------------------------

def generate_signal(df, regime="BULL"):

    close = df["Close"]

    # HANDLE MULTI-COLUMN CASE
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    # CLEAN SERIES
    close = pd.Series(close).dropna()

    # -------------------------
    # INDICATORS
    # -------------------------

    ema20_series = close.ewm(span=20).mean()
    ema50_series = close.ewm(span=50).mean()

    rsi_series = calculate_rsi(close)

    # -------------------------
    # SAFE SCALAR VALUES
    # -------------------------

    cmp = float(close.iloc[-1])

    ema20_val = float(ema20_series.iloc[-1])
    ema50_val = float(ema50_series.iloc[-1])

    rsi_val = float(rsi_series.iloc[-1])

    # -------------------------
    # NaN SAFETY
    # -------------------------

    if pd.isna(rsi_val):
        rsi_val = 0

    if pd.isna(ema20_val):
        ema20_val = 0

    if pd.isna(ema50_val):
        ema50_val = 0

    # -------------------------
    # INSTITUTIONAL SCORE
    # -------------------------

    score = 0

    # Trend Structure
    if ema20_val > ema50_val:
        score += 25
    else:
        score -= 15

    # Momentum
    if 55 < rsi_val < 75:
        score += 20

    elif rsi_val >= 75:
        score += 10

    # Price Structure
    if cmp > ema20_val:
        score += 15

    if cmp > ema50_val:
        score += 10

    # Stability Zone
    if 40 < rsi_val < 70:
        score += 10

    # Clamp score
    score = max(0, min(100, score))

    # -------------------------
    # SIGNAL CLASSIFICATION
    # -------------------------

    if regime == "BEAR":

        if score >= 85:
            signal = "TACTICAL BUY"

        elif score >= 60:
            signal = "WATCHLIST"

        else:
            signal = "NO TRADE"

    elif regime == "SIDEWAYS":

        if score >= 85:
            signal = "SWING BUY"

        else:
            signal = "NO TRADE"

    else:

        if score >= 85:
            signal = "INSTITUTIONAL STRONG BUY"

        elif score >= 70:
            signal = "BUY"

        elif score >= 55:
            signal = "ACCUMULATE"

        else:
            signal = "NO TRADE"

    # -------------------------
    # TREND
    # -------------------------

    trend = "Bullish" if ema20_val > ema50_val else "Bearish"

    # -------------------------
    # RETURN
    # -------------------------

    return [
        round(cmp, 2),
        round(rsi_val, 2),
        round(ema20_val, 2),
        round(ema50_val, 2),
        trend,
        score,
        signal
    ]
