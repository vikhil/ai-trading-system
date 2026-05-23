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

    # SAFE SCALAR EXTRACTION (ONLY ONCE)
    cmp = float(close.iloc[-1])

    ema20 = latest["EMA20"]
    ema50 = latest["EMA50"]
    rsi = latest["RSI"]

    # Convert safely to float
    ema20 = float(ema20) if pd.notna(ema20) else 0.0
    ema50 = float(ema50) if pd.notna(ema50) else 0.0
    rsi = float(rsi) if pd.notna(rsi) else 0.0

    # SCORE
    score = 0

    if ema20 > ema50:
        score += 30
        
    if rsi > 60:
        score += 25
    
    if cmp > ema20:
        score += 20
    
    if rsi > 70:
        score += 15
    
    if cmp > ema50:
        score += 10

    # SIGNAL
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
