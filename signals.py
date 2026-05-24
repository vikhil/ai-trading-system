import pandas as pd
import numpy as np


# -----------------------------------
# RSI CALCULATION
# -----------------------------------

def calculate_rsi(data, period=14):

    delta = data.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


# -----------------------------------
# INSTITUTIONAL SCORE ENGINE
# -----------------------------------

def calculate_institutional_score(cmp, rsi, ema20, ema50):

    score = 0

    # Trend
    if ema20 > ema50:
        score += 25

    # Momentum
    if 55 < rsi < 75:
        score += 20
    elif rsi >= 75:
        score += 10

    # Price structure
    if cmp > ema20:
        score += 15

    if cmp > ema50:
        score += 10

    # Stability
    if 40 < rsi < 70:
        score += 10

    # Weak structure penalty
    if ema20 < ema50:
        score -= 15

    return max(0, min(100, score))


# -----------------------------------
# SIGNAL CLASSIFIER
# -----------------------------------

def classify_signal(score, regime):

    if regime == "BEAR":

        if score >= 85:
            return "TACTICAL BUY"

        elif score >= 60:
            return "WATCHLIST"

        else:
            return "NO TRADE"

    elif regime == "SIDEWAYS":

        if score >= 85:
            return "SWING BUY"

        else:
            return "NO TRADE"

    else:

        if score >= 85:
            return "INSTITUTIONAL BUY"

        elif score >= 70:
            return "BUY"

        elif score >= 55:
            return "ACCUMULATE"

        else:
            return "NO TRADE"


# -----------------------------------
# MAIN SIGNAL ENGINE
# -----------------------------------

def generate_signal(df, regime="BULL"):

    try:

        # -------------------------
        # CLOSE SERIES SAFETY
        # -------------------------

        close = df["Close"]

        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

        close = pd.Series(close).dropna()

        if len(close) < 50:
            return None

        # -------------------------
        # INDICATORS
        # -------------------------

        ema20_series = close.ewm(span=20).mean()
        ema50_series = close.ewm(span=50).mean()

        rsi_series = calculate_rsi(close)

        # -------------------------
        # SAFE FLOAT VALUES
        # -------------------------

        cmp = float(close.iloc[-1])

        ema20 = float(ema20_series.iloc[-1])
        ema50 = float(ema50_series.iloc[-1])

        rsi = float(rsi_series.iloc[-1])

        # -------------------------
        # NaN SAFETY
        # -------------------------

        if np.isnan(rsi):
            rsi = 0

        if np.isnan(ema20):
            ema20 = 0

        if np.isnan(ema50):
            ema50 = 0

        # -------------------------
        # TREND
        # -------------------------

        trend = "Bullish" if ema20 > ema50 else "Bearish"

        # -------------------------
        # SCORE
        # -------------------------

        score = calculate_institutional_score(
            cmp,
            rsi,
            ema20,
            ema50
        )

        # -------------------------
        # SIGNAL
        # -------------------------

        signal = classify_signal(score, regime)

        return [
            round(cmp, 2),
            round(rsi, 2),
            round(ema20, 2),
            round(ema50, 2),
            trend,
            score,
            signal
        ]

    except Exception as e:

        print(f"Signal Engine Error: {e}")

        return None
