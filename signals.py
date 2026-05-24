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

        rsi = 0 if np.isnan(rsi) else rsi
        ema20 = 0 if np.isnan(ema20) else ema20
        ema50 = 0 if np.isnan(ema50) else ema50

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

# -----------------------------------
# ATR RISK ENGINE (FIXED + PRODUCTION READY)
# -----------------------------------

def calculate_atr(df, period=14):

    df = df.copy()

    if len(df) < period + 1:
        df["ATR"] = np.nan
        return df

    df["prev_close"] = df["Close"].shift(1)

    df["tr1"] = df["High"] - df["Low"]
    df["tr2"] = abs(df["High"] - df["prev_close"])
    df["tr3"] = abs(df["Low"] - df["prev_close"])

    df["TR"] = df[["tr1", "tr2", "tr3"]].max(axis=1)

    df["ATR"] = df["TR"].rolling(window=period).mean()

    return df


# -----------------------------------
# RISK ENGINE (LONG ONLY - aligned with your system)
# -----------------------------------

def apply_risk_engine(row, atr_multiplier=1.5, rr_multiple=2.0):

    entry = row["Close"]
    atr = row["ATR"]

    if pd.isna(atr):
        return pd.Series([np.nan, np.nan, np.nan, np.nan])

    stop_loss = entry - (atr * atr_multiplier)
    risk = entry - stop_loss
    target = entry + (risk * rr_multiple)

    rr = (target - entry) / (entry - stop_loss)

    return pd.Series([
        round(atr, 2),
        round(stop_loss, 2),
        round(target, 2),
        round(rr, 2)
    ])
