import numpy as np
import pandas as pd

def calculate_rsi(data, period=14):
    
    delta = data.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    
    rsi = 100 - (100 / (1 + rs))

    return rsi


def generate_signal(df):
    
    # FORCE CLEAN CLOSE SERIES
     close = df["Close"]

    # HANDLE DATAFRAME CASE
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = pd.Series(close).dropna()

    # EMA
    ema20_series = close.ewm(span=20).mean()
    ema50_series = close.ewm(span=50).mean()

    # RSI
    rsi_series = calculate_rsi(close)

    # SAFE LATEST VALUES
    cmp = float(close.iloc[-1])

    # SAFE SCALAR EXTRACTION (ONLY ONCE)
    cmp = float(close.iloc[-1])

    ema20 = float(ema20_series.iloc[-1])
    ema50 = float(ema50_series.iloc[-1])
    rsi = float(rsi_series.iloc[-1])

    # HANDLE NaN
    if pd.isna(rsi):
        rsi = 0

    if pd.isna(ema20):
        ema20 = 0

    if pd.isna(ema50):
        ema50 = 0

    # -----------------------------
    # SCORE
    # -----------------------------
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

    # -----------------------------
    # SIGNAL
    # -----------------------------
    if score >= 75:
        signal = "STRONG BUY"
    elif score >= 55:
        signal = "BUY"
    elif score >= 35:
        signal = "HOLD"
    else:
        signal = "SELL"

    trend = "Bullish" if ema20 > ema50 else "Bearish"

    return [
        round(cmp, 2),
        round(rsi, 2),
        round(ema20, 2),
        round(ema50, 2),
        trend,
        score,
        signal
    ]
