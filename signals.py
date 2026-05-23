import numpy as np
import pandas as pd

def calculate_rsi(data, period=14):
    delta = data.diff()

    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    gain = pd.Series(gain).rolling(period).mean()
    loss = pd.Series(loss).rolling(period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def generate_signal(df):
    close = df["Close"].squeeze()

    df["EMA20"] = close.ewm(span=20).mean()
    df["EMA50"] = close.ewm(span=50).mean()
    df["RSI"] = calculate_rsi(close)

    latest = df.iloc[-1]

    cmp = float(close.iloc[-1])

    ema20 = latest["EMA20"]
    ema50 = latest["EMA50"]
    rsi = latest["RSI"]

    # FORCE SCALAR SAFETY
    ema20 = float(ema20.iloc[-1]) if hasattr(ema20, "iloc") else float(ema20)
    ema50 = float(ema50.iloc[-1]) if hasattr(ema50, "iloc") else float(ema50)
    rsi = float(rsi.iloc[-1]) if hasattr(rsi, "iloc") else float(rsi)

    ema20 = float(latest["EMA20"]) if pd.notna(latest["EMA20"]) else 0
    ema50 = float(latest["EMA50"]) if pd.notna(latest["EMA50"]) else 0
    rsi = float(latest["RSI"]) if pd.notna(latest["RSI"]) else 0

    score = 0

    if pd.notna(ema20) and pd.notna(ema50) and ema20 > ema50:
        score += 30
    if rsi > 60:
        score += 25
    if cmp > ema20:
        score += 20
    if rsi > 70:
        score += 15
    if cmp > ema50:
        score += 10

    if score >= 75:
        signal = "STRONG BUY"
    elif score >= 55:
        signal = "BUY"
    elif score >= 35:
        signal = "HOLD"
    else:
        signal = "SELL"

    trend = "Bullish" if ema20 > ema50 else "Bearish"

    return [cmp, rsi, ema20, ema50, trend, score, signal]
