import json
import os
import pandas as pd
import gspread
import yfinance as yf

from oauth2client.service_account import ServiceAccountCredentials

from data_loader import load_universe
from signals import generate_signal, calculate_atr, apply_risk_engine, add_volume_and_breakout
from sheets_writer import safe_update

import time

def safe_download(ticker, period="6mo", interval="1d", retries=2):

    for attempt in range(retries + 1):
        try:
            df = yf.download(
                ticker,
                period=period,
                interval=interval,
                auto_adjust=True,
                progress=False,
                threads=False
            )

            if df is not None and not df.empty:
                return df, None

        except Exception as e:
            time.sleep(1.5 * (attempt + 1))

            if attempt == retries:
                return None, str(e)

    return None, "Unknown failure"
    
print("Script Started")

def get_market_regime():

    nifty = yf.download(
        "^NSEI",
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False
    )
    
    if nifty.empty:
        return "SIDEWAYS"

    close = nifty["Close"]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = pd.Series(close).dropna()

    ema50 = close.ewm(span=50).mean()
    ema200 = close.ewm(span=200).mean()

    last_close = float(close.iloc[-1])
    last_ema50 = float(ema50.iloc[-1])
    last_ema200 = float(ema200.iloc[-1])

    if last_close > last_ema50 and last_ema50 > last_ema200:
        return "BULL"

    elif last_close < last_ema50 and last_ema50 < last_ema200:
        return "BEAR"

    else:
        return "SIDEWAYS"
        

# ----------------------------
# GOOGLE SHEETS AUTH
# ----------------------------
creds_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open_by_key("1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI")

scanner_ws = sheet.worksheet("Scanner")

try:
    failed_ws = sheet.worksheet("FailedLogs")
except:
    failed_ws = sheet.add_worksheet(title="FailedLogs", rows="1000", cols="10")
    
watchlist_ws = sheet.worksheet("Watchlist")

failed_logs = []

print("Connected")

# ----------------------------
# LOAD STOCKS
# ----------------------------
stocks = load_universe()

stocks = sorted(list(set(stocks)))

print("Stocks:", len(stocks))

# ----------------------------
# UPDATE WATCHLIST (1 CALL ONLY)
# ----------------------------

watchlist_data = [["Ticker", "CMP", "RSI", "EMA20", "EMA50", "Trend", "Score", "Edge Rating"]]

# ----------------------------
# MARKET REGIME
# ----------------------------

regime = get_market_regime()

# ----------------------------
# NIFTY DATA FOR RELATIVE STRENGTH
# ----------------------------

nifty_df = yf.download("^NSEI", period="6mo", interval="1d", auto_adjust=True, progress=False)

nifty_close = nifty_df["Close"]

if isinstance(nifty_close, pd.DataFrame):
    nifty_close = nifty_close.iloc[:, 0]

nifty_close = pd.Series(nifty_close).dropna()

nifty_return = float((nifty_close.iloc[-1] / nifty_close.iloc[0]) - 1)

print("Market Regime:", regime)

# ----------------------------
# ANALYSIS
# ----------------------------
results = []

def calculate_edge_score(score, risk_reward, rs_score, volume_spike, breakout, regime):

    if pd.isna(score) or score < 60:
        return 0

    edge = 0
    
    score = float(score)
    risk_reward = float(risk_reward) if pd.notna(risk_reward) else 0
    rs_score = float(rs_score) if pd.notna(rs_score) else 0
    volume_spike = float(volume_spike) if pd.notna(volume_spike) else 0
    
    # 1. Signal strength
    if score >= 80:
        edge += 5
    elif score >= 75:
        edge += 4
    elif score >= 70:
        edge += 3
    elif score >= 65:
        edge += 2
    elif score >= 60:
        edge += 1

    # 2. Risk-reward quality
    if risk_reward >= 3:
        edge += 2
    elif risk_reward >= 2:
        edge += 1

    # 3. Relative strength
    if rs_score >= 50:
        edge += 2
    elif rs_score >= 25:
        edge += 1

    # 4. Volume + breakout
    if volume_spike >= 1.5 and str(breakout).upper() == "YES":
        edge += 2
    elif volume_spike >= 1.2:
        edge += 1

    base_score = edge * 10

    # regime adjustment (IMPORTANT — keep this)
    if regime == "BEAR":
        base_score *= 0.85
    elif regime == "SIDEWAYS":
        base_score *= 0.92

    return min(base_score, 100)

def calculate_edge_rating(edge_score):
    edge_score = float(edge_score) if pd.notna(edge_score) else 0

    if edge_score >= 90:
        return 9
    elif edge_score >= 80:
        return 8
    elif edge_score >= 70:
        return 7
    elif edge_score >= 60:
        return 6
    elif edge_score >= 50:
        return 5
    elif edge_score >= 40:
        return 4
    elif edge_score >= 30:
        return 3
    elif edge_score >= 20:
        return 2
    elif edge_score >= 10:
        return 1
    else:
        return 0

def get_trade_action(edge_rating):
    if edge_rating >= 8:
        return "STRONG_BUY"
    elif edge_rating >= 7:
        return "BUY"
    elif edge_rating >= 6:
        return "WATCH"
    elif edge_rating >= 4:
        return "IGNORE_WATCH"
    else:
        return "IGNORE"

for ticker in stocks:
    error_reason = None
    
    try:

        df, error = safe_download(ticker)

        # =========================
        # HARD DATAFRAME NORMALIZATION FIX
        # =========================
        
        if error:
            failed_logs.append([ticker, "DOWNLOAD_FAILED", str(error)])
            continue
        
        if df is None:
            failed_logs.append([ticker, "EMPTY_DATA", "No data returned"])
            continue
        
        # 1. Flatten MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 2. Remove duplicate columns
        df = df.loc[:, ~df.columns.duplicated()]
        
        # 3. Keep only OHLCV columns
        required_cols = ["Open", "High", "Low", "Close", "Volume"]
        
        df = df[[col for col in required_cols if col in df.columns]]
        
        # 4. Convert all columns to numeric
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # 5. Drop bad rows
        df = df.dropna()

        if len(df) < 60:
            failed_logs.append([ticker, "INSUFFICIENT_DATA", len(df)])
            continue
        
        # 6. Final safety check
        if df.empty:
            failed_logs.append([
                ticker,
                "EMPTY_AFTER_NORMALIZATION",
                "DataFrame empty after cleanup"
            ])
            continue
        
        # ----------------------------
        # ATR CALCULATION AND VOLUME/BREAKOUT
        # ----------------------------
        
        df = calculate_atr(df)
        df = add_volume_and_breakout(df)

        avg_volume = df["Avg Volume"].iloc[-1]
        current_volume = df["Volume"].iloc[-1]
        volume_spike = df["Volume Spike"].iloc[-1]
        breakout = df["Breakout"].iloc[-1]

        # ---------------------------
        # FILTERS (EARLY EXIT CONDITIONS)
        # ---------------------------
        
        current_volume = df["Volume"].iloc[-1] if "Volume" in df.columns else 0
        atr_indicator = df["ATR"].iloc[-1] if "ATR" in df.columns else 0
        
        # B) Liquidity filter
        if current_volume < 100000:
            continue
        
        # C) ATR filter
        if atr_indicator <= 0 or pd.isna(atr_indicator):
            continue
        
        # =========================
        # FINAL DATA NORMALIZATION FIX
        # =========================
        
        for col in ["Open", "High", "Low", "Close", "Volume"]:
        
            if col in df.columns:
        
                if isinstance(df[col], pd.DataFrame):
                    df[col] = df[col].iloc[:, 0]
        
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        if df.empty:
            continue
        
        stock_close = df["Close"]

        if isinstance(stock_close, pd.DataFrame):
            stock_close = stock_close.iloc[:, 0]

        stock_close = pd.Series(stock_close).dropna()

        if len(stock_close) < 2:
            continue
    
        # ----------------------------
        # BASIC RETURNS (RS LOGIC)
        # ----------------------------
        
        stock_return = float((stock_close.iloc[-1] / stock_close.iloc[0]) - 1)

        rs_score = (stock_return - nifty_return) * 100
        rs_score = round(max(min(rs_score, 100), -100), 2)
            
        if rs_score > 1.5:
            rs_rank = "ELITE"
            
        elif rs_score > 1.0:
            rs_rank = "STRONG"
            
        elif rs_score > 0.8:
            rs_rank = "AVERAGE"
            
        else:
            rs_rank = "WEAK"
    
        # ----------------------------
        # SIGNAL ENGINE
        # ----------------------------
        
        try:
            signal_data = generate_signal(df, regime)
        
            if signal_data is None:
                failed_logs.append([ticker, "SIGNAL_FAILED", "generate_signal returned None"])
                continue
        
        except Exception as e:
            failed_logs.append([ticker, "SIGNAL_EXCEPTION", str(e)])
            continue

        if signal_data is None:
            continue

        (
            cmp,
            rsi,
            ema20,
            ema50,
            trend,
            score,
            signal,
            avg_volume,
            current_volume,
            volume_spike,
            breakout
        ) = signal_data

        rsi = float(rsi) if pd.notna(rsi) else 0
        ema20 = float(ema20) if pd.notna(ema20) else 0
        ema50 = float(ema50) if pd.notna(ema50) else 0
        
        # ----------------------------
        # ATR RISK ENGINE
        # ----------------------------

        last_row = df.iloc[-1]

        risk_values = apply_risk_engine(last_row, df=df)
        
        #risk_values = apply_risk_engine(last_row)
        
        #atr_indicator = df["ATR"].iloc[-1] if "ATR" in df.columns else 0
        atr_risk = round(float(risk_values.iloc[0]), 2)
        stop_loss = round(float(risk_values.iloc[1]), 2)
        target = round(float(risk_values.iloc[2]), 2)
        risk_reward = round(float(risk_values.iloc[3]), 2)
        
        if risk_reward < 1.5:
            continue
            
        # ----------------------------
        # DEBUG LOGGING
        # ----------------------------
        
        #print(
        #    ticker,
        #    "Score:", score,
        #    "RR:", risk_reward,
        #    "Signal:", signal
        #)
        
        # Temporary fallback fixes
        if pd.isna(risk_reward):
            risk_reward = 0

        # ----------------------------
        # FINAL ROW
        # ----------------------------
    
        edge_score = calculate_edge_score(
            score,
            risk_reward,
            rs_score,
            #volume_spike,
            #breakout,
            df["Volume Spike"].iloc[-1],
            df["Breakout"].iloc[-1],
            regime
        )

        edge_rating = int(calculate_edge_rating(edge_score))
        trade_action = get_trade_action(edge_rating)

        # Regime filter override
        if regime == "BEAR":
            if trade_action == "STRONG_BUY":
                trade_action = "BUY"
            elif trade_action == "BUY":
                trade_action = "WATCH"
        
        # ----------------------------
        # STREAM ROUTING
        # ----------------------------
        
        if trade_action == "WATCH":
            print("👀 WATCH:", ticker, "Edge:", edge_rating)
            watchlist_data.append([ticker, cmp, rsi, ema20, ema50, trend, score, edge_rating])
            
        elif trade_action in ["STRONG_BUY", "BUY"]:
            print("🔥 TRADE ALERT:", ticker, trade_action, "Edge:", edge_rating)
            # later we can send to Telegram / WhatsApp / email
        else:
            pass
    
        print(
            ticker,
            "Score:", score,
            "Edge:", edge_score,
            "RR:", risk_reward,
            "Signal:", signal
        )
        
        results.append([
            ticker,
            cmp,
            rsi,
            ema20,
            ema50,
            trend,
            score,
            edge_score,   # NEW FIELD (Edge Score replaces Signal-only ranking logic)
            edge_rating,
            trade_action,
            signal,
            atr_risk,
            stop_loss,
            target,
            risk_reward,
            rs_score,
            rs_rank,
            avg_volume,
            current_volume,
            volume_spike,
            breakout
        ])

    except Exception as e:
        error_reason = str(e)
        print(f"Error Processing {ticker}: {e}")
        failed_logs.append([ticker, "PIPELINE_ERROR", error_reason])
        continue
        
# ----------------------------
# SORT RESULTS
# ----------------------------

results = sorted(results, key=lambda x: x[7] if x[7] is not None else 0, reverse=True)

print("Final Results Count:", len(results))

# ----------------------------
# UPDATE SCANNER
# ----------------------------

headers = [
    "Ticker",
    "CMP",
    "RSI",
    "EMA20",
    "EMA50",
    "Trend",
    "Score",
    "Edge Score",
    "Edge Rating",
    "Trade Action",
    "Signal",
    "ATR",
    "Stop Loss",
    "Target",
    "Risk Reward",
    "RS Score",
    "Relative Rank",
    "Avg Volume",
    "Current Volume",
    "Volume Spike",
    "Breakout"
]

scanner_data = [headers] + results

try:
    safe_update(scanner_ws, scanner_data)
    print("Scanner Updated")
except Exception as e:
    print("Scanner Update Failed:", e)

print("Scanner Rows:", len(scanner_data))

if len(watchlist_data) > 1:
    print("Watchlist Rows:", len(watchlist_data))
    safe_update(watchlist_ws, watchlist_data)

if failed_logs:
    failed_headers = [["Ticker", "Error Type", "Reason"]]
    print("Failed Rows:", len(failed_logs))
    safe_update(failed_ws, failed_headers + failed_logs)

print("Completed Successfully")
