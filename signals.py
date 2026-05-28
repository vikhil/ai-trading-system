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

        df = df.copy()
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

        ema20 = ema20_series.iloc[-1] if len(ema20_series) > 0 else 0
        ema50 = ema50_series.iloc[-1] if len(ema50_series) > 0 else 0
        rsi = rsi_series.iloc[-1] if len(rsi_series) > 0 else 0

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
    
    high = df["High"].squeeze().astype(float)
    low = df["Low"].squeeze().astype(float)
    close = df["Close"].squeeze().astype(float)

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)

    tr = pd.concat([tr1, tr2, tr3], axis=1)
    tr = tr.max(axis=1, skipna=True)

    df["ATR"] = tr.rolling(window=period).mean()
    df["ATR"] = df["ATR"].fillna(0)
    
    return df

# -----------------------------------
# Volume and Breakout
# -----------------------------------

def add_volume_and_breakout(df):
    df = df.copy()

    if "Volume" not in df.columns:
        df["Avg Volume"] = np.nan
        df["Volume Spike"] = np.nan
        df["Breakout"] = "NA"
        return df

    df["Avg Volume"] = df["Volume"].rolling(20).mean()
    df["Volume Spike"] = df["Volume"] / df["Avg Volume"]

    df["20D High"] = df["High"].rolling(20).max()

    df["Breakout"] = np.where(
        df["Close"] > df["20D High"].shift(1),
        "YES",
        "NO"
    )

    return df
    
# -----------------------------------
# RISK ENGINE (LONG ONLY - aligned with your system)
# -----------------------------------

def apply_risk_engine(row, atr_multiplier=1.5, rr_multiple=2.0):

    try:
        entry = float(row["Close"])
        atr = float(row["ATR"])

        if pd.isna(atr) or atr == 0:
            return pd.Series([np.nan, np.nan, np.nan, np.nan])

        stop_loss = entry - (atr * atr_multiplier)
        risk = entry - stop_loss
        target = entry + (risk * rr_multiple)

        rr = (target - entry) / risk if risk != 0 else np.nan

        return pd.Series([
            round(atr, 2),
            round(stop_loss, 2),
            round(target, 2),
            round(rr, 2)
        ])

    except Exception:
        return pd.Series([np.nan, np.nan, np.nan, np.nan])
