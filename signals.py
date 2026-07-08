import pandas as pd
import numpy as np
from engine.trend_persistence import calculate_trend_persistence

# =========================================================
# UTILITIES (GLOBAL SAFE HELPERS)
# =========================================================

def safe_last_value(data, default=0.0):
    try:
        if isinstance(data, pd.DataFrame):
            data = data.iloc[:, 0]

        if isinstance(data, pd.Series):
            return float(data.dropna().iloc[-1])

        return float(data)

    except:
        return default


def safe_string_last(data, default="NO"):
    try:
        if isinstance(data, pd.DataFrame):
            data = data.iloc[:, 0]

        if isinstance(data, pd.Series):
            return str(data.dropna().iloc[-1])

        return str(data)

    except:
        return default


# =========================================================
# RSI
# =========================================================

def calculate_rsi(close, period=14):
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


# =========================================================
# SCORE ENGINE
# =========================================================

def calculate_institutional_score(cmp, rsi, ema20, ema50, ema200, volume_spike, breakout, rs_score):

    score = 0

    # -------------------
    # TREND QUALITY (40)
    # -------------------

    if ema20 > ema50:
        score += 15

    if ema50 > ema200:
        score += 15

    if cmp > ema20:
        score += 10

    # -------------------
    # MOMENTUM (20)
    # -------------------

    if 55 <= rsi <= 70:
        score += 20

    elif 50 <= rsi < 55:
        score += 10

    elif rsi > 70:
        score += 5

    # -------------------
    # VOLUME (20)
    # -------------------

    if volume_spike >= 2:
        score += 20

    elif volume_spike >= 1.5:
        score += 15

    elif volume_spike >= 1.2:
        score += 10

    # -------------------
    # RELATIVE STRENGTH
    # -------------------
    
    if rs_score >= 50:
        score += 20
    
    elif rs_score >= 25:
        score += 15
    
    elif rs_score >= 10:
        score += 10
    
    # -------------------
    # BREAKOUT (20)
    # -------------------

    if str(breakout).upper() == "YES":
        score += 20

    return min(score, 100)

# =========================================================
# SIGNAL CLASSIFIER
# =========================================================

def classify_signal(score, regime):

    if regime == "BEAR":
        return (
            "TACTICAL BUY" if score >= 85 else
            "WATCHLIST" if score >= 70 else
            "NO TRADE"
        )

    if regime == "SIDEWAYS":
        return (
            "SWING BUY" if score >= 82 else
            "WATCHLIST" if score >= 65 else
            "NO TRADE"
        )

    return (
        "INSTITUTIONAL BUY" if score >= 90 else
        "BUY" if score >= 78 else
        "ACCUMULATE" if score >= 60 else
        "WATCHLIST" if score >= 50 else
        "NO TRADE"
    )

# =========================================================
# SIGNAL ENGINE (MAIN OUTPUT)
# =========================================================

def generate_signal(df, regime="BULL", rs_score=0):

    try:
        # -------------------------
        # SAFE CLOSE SERIES
        # -------------------------
        
        df = df.copy()

        if "Close" not in df.columns:
            return None
    
        close = df["Close"]

        # Handle multi-column DataFrame (yfinance edge case)
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

        close = pd.Series(close).dropna()

        # HARD SAFETY CHECKS (IMPORTANT)
        if close.empty or len(close) < 50:
            return None

        close = pd.to_numeric(close, errors="coerce").dropna()

        if close.empty:
            return None
        
        # -------------------------
        # INDICATORS
        # -------------------------
        ema20 = close.ewm(span=20).mean()
        ema50 = close.ewm(span=50).mean()
        ema200 = close.ewm(span=200).mean()
        rsi = calculate_rsi(close)

        # ---------------------------------
        # Trend Persistence
        # ---------------------------------
        
        df["EMA20"] = ema20
        df["EMA50"] = ema50
        
        trend_persistence = calculate_trend_persistence(df)
        #trend_persistence = 50
        
        cmp = float(close.iloc[-1])
        ema20_v = float(ema20.iloc[-1])
        ema50_v = float(ema50.iloc[-1])
        ema200_v = float(ema200.iloc[-1])
        rsi_v = float(rsi.iloc[-1])
        
        trend = "Bullish" if ema20_v > ema50_v else "Bearish"

        # VOLUME / BREAKOUT FIRST
        avg_volume = safe_last_value(df["Avg Volume"]) if "Avg Volume" in df.columns else 0
        current_volume = safe_last_value(df["Volume"]) if "Volume" in df.columns else 0
        volume_spike = safe_last_value(df["Volume Spike"]) if "Volume Spike" in df.columns else 0
        breakout = safe_string_last(df["Breakout"]) if "Breakout" in df.columns else "NO"

        # NOW SAFE SCORE
        score = calculate_institutional_score(cmp, rsi_v, ema20_v, ema50_v, ema200_v, volume_spike, breakout, rs_score)
        
        signal = classify_signal(score, regime)

        return [
            round(cmp, 2),
            round(rsi_v, 2),
            round(ema20_v, 2),
            round(ema50_v, 2),
            trend,
            int(score),
            signal,
            round(avg_volume, 0),
            round(current_volume, 0),
            round(volume_spike, 2),
            breakout,
            trend_persistence
        ]

    except Exception as e:
        print(f"Signal Engine Error: {e}")
        return None


# =========================================================
# ATR CALCULATION
# =========================================================

def calculate_atr(df, period=14):

    df = df.copy()

    if len(df) < period + 1:
        df["ATR"] = np.nan
        return df

    high = df["High"].squeeze().astype(float)
    low = df["Low"].squeeze().astype(float)
    close = df["Close"].squeeze().astype(float)

    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        abs(high - prev_close),
        abs(low - prev_close)
    ], axis=1).max(axis=1)

    df["ATR"] = tr.rolling(period).mean().fillna(0)

    return df


# =========================================================
# VOLUME + BREAKOUT ENGINE
# =========================================================

def add_volume_and_breakout(df):

    df = df.copy()

    # ---------------------------------
    # REQUIRED COLUMNS CHECK
    # ---------------------------------
    required_cols = ["Volume", "Close", "High"]

    for col in required_cols:
        if col not in df.columns:
            df["Avg Volume"] = 0
            df["Volume Spike"] = 0
            df["Breakout"] = "NO"
            return df

    # ---------------------------------
    # FORCE 1D SERIES (CRITICAL FIX)
    # ---------------------------------
    volume = pd.Series(df["Volume"]).squeeze()
    close = pd.Series(df["Close"]).squeeze()
    high = pd.Series(df["High"]).squeeze()

    # ---------------------------------
    # NUMERIC SAFETY
    # ---------------------------------
    volume = pd.to_numeric(volume, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")
    high = pd.to_numeric(high, errors="coerce")

    # ---------------------------------
    # AVERAGE VOLUME
    # ---------------------------------
    avg_volume = volume.rolling(20).mean()

    df["Avg Volume"] = avg_volume

    df["Volume Spike"] = np.where(
        avg_volume != 0,
        volume / avg_volume,
        0
    )

    # ---------------------------------
    # 20 DAY BREAKOUT
    # ---------------------------------
    high_20 = high.rolling(20).max()

    df["Breakout"] = np.where(
        (close > high_20.shift(1)) &
        (df["Volume Spike"] > 1.5),
        "YES",
        "NO"
    )

    # ---------------------------------
    # CLEANUP
    # ---------------------------------
    
    df["Volume Spike"] = pd.to_numeric(df["Volume Spike"], errors="coerce").fillna(0)

    return df

# =========================================================
# RISK ENGINE (FIXED SAFE VERSION)
# =========================================================

def apply_risk_engine(row, df=None, atr_multiplier=1.5):

    try:
        entry = float(row["Close"]) if not hasattr(row["Close"], "iloc") else float(row["Close"].iloc[-1])
        atr = float(row["ATR"]) if not hasattr(row["ATR"], "iloc") else float(row["ATR"].iloc[-1])

        # ---------------------------
        # SAFETY CHECK (IMPORTANT)
        # ---------------------------
        if df is None or len(df) < 20 or "Close" not in df.columns:
            return pd.Series([np.nan, np.nan, np.nan, np.nan])

        if atr == 0 or pd.isna(atr):
            return pd.Series([np.nan, np.nan, np.nan, np.nan])

        # ---------------------------
        # STRUCTURE STOP
        # ---------------------------
        structure_low = df["Close"].rolling(10).min().iloc[-1]

        atr_stop = entry - (atr * atr_multiplier)

        stop_loss = max(atr_stop, structure_low)

        # ---------------------------
        # TARGET
        # ---------------------------
        resistance = df["Close"].rolling(20).max().iloc[-1]
        momentum_extension = entry + (atr * 2.5)

        target = max(resistance, momentum_extension)

        # ---------------------------
        # STOP LOSS SAFETY BUFFER (MUST BE BEFORE RISK)
        # ---------------------------
        min_risk_buffer = entry * 0.003  # 0.3%
        
        if abs(entry - stop_loss) < min_risk_buffer:
            stop_loss = entry - min_risk_buffer if entry > stop_loss else entry + min_risk_buffer

        # ---------------------------
        # RISK & REWARD (NOW CORRECT)
        # ---------------------------

        risk = abs(entry - stop_loss)

        # HARD SAFETY: prevent micro-risk distortion
        min_risk_abs = atr * 0.5   # NEW: volatility-based floor
        
        if risk < min_risk_abs:
            risk = min_risk_abs
            
        reward = abs(target - entry)
        
        # SAFE GUARD (CRITICAL FIX)
        if risk <= 0 or pd.isna(risk) or risk < 1e-6:
            rr = 0
        else:
            rr = reward / risk
        
        # volatility sanity cap (more realistic than flat 10)
        rr = min(rr, 6)
        
        rr = round(rr, 2)

        return pd.Series([
            round(atr, 2),
            round(stop_loss, 2),
            round(target, 2),
            round(rr, 2)
        ])

    except Exception:
        return pd.Series([np.nan, np.nan, np.nan, np.nan])
