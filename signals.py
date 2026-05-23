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
# INSTITUTIONAL SCORE ENGINE
# -------------------------
def calculate_institutional_score(cmp, rsi, ema20, ema50):

    score = 0

    # Trend strength
    if ema20 > ema50:
        score += 25

    # Momentum zone
    if 55 < rsi < 75:
        score += 20
    elif rsi >= 75:
        score += 10

    # Price structure
    if cmp > ema20:
        score += 15
    if cmp > ema50:
        score += 10

    # Stability zone
    if 40 < rsi < 70:
        score += 10

    # Weak structure penalty
    if ema20 < ema50:
        score -= 15

    return max(0, min(100, score))


# -------------------------
# SIGNAL CLASSIFIER
# -------------------------
def classify_signal(score, regime):

    if regime == "BEAR":
        if score >= 85:
            return "TACTICAL BUY (BEAR MARKET)"
        elif score >= 60:
            return "AVOID / SHORT WATCH"
        else:
            return "NO TRADE"

    if regime == "SIDEWAYS":
        if score >= 85:
            return "SWING BUY ONLY"
        else:
            return "NO TRADE"

    # BULL MARKET
    if score >= 85:
        return "INSTITUTIONAL STRONG BUY"
    elif score >= 70:
        return "BUY"
    elif score >= 55:
        return "ACCUMULATE"
    else:
        return "NO TRADE"


# -------------------------
# MAIN GENERATOR
# -------------------------
def generate_signal(df, regime="BULL"):

    close = df["Close"]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = pd.Series(close).dropna()

    # Indicators
    ema20 = close.ewm(span=20).mean()
    ema50 = close.ewm(span=50).mean()
    rsi = calculate_rsi(close)

    # Latest values
    cmp = float(close.iloc[-1])
    ema20_val = float(ema20.iloc[-1])
    ema50_val = float(ema50.iloc[-1])
    rsi_val = float(rsi.iloc[-1])

    # NaN safety
    if pd.isna(rsi_val):
        rsi_val = 0
    if pd.isna(ema20_val):
        ema20_val = 0
    if pd.isna(ema50_val):
        ema50_val = 0

    # Score + Signal
    score = calculate_institutional_score(cmp, rsi_val, ema20_val, ema50_val)
    signal = classify_signal(score, regime)

    trend = "Bullish" if ema20_val > ema50_val else "Bearish"

    return [
        round(cmp, 2),
        round(rsi_val, 2),
        round(ema20_val, 2),
        round(ema50_val, 2),
        trend,
        score,
        signal
    ]
