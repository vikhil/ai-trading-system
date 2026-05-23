import yfinance as yf
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import requests
from io import StringIO
import time
from gspread.exceptions import APIError

print("Script Started")

# -----------------------------------
# GOOGLE SHEETS AUTH
# -----------------------------------
try:
    creds_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    print("Google Auth Successful")

except Exception as e:
    print("Google Auth Error:", e)
    raise

# -----------------------------------
# OPEN SHEET
# -----------------------------------
spreadsheet_id = "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"
sheet = client.open_by_key(spreadsheet_id)
scanner_ws = sheet.worksheet("Scanner")
watchlist_ws = sheet.worksheet("Watchlist")

print("Spreadsheet Connected")

# -----------------------------------
# RSI FUNCTION
# -----------------------------------

def calculate_rsi(data, period=14):

    delta = data.diff()

    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    gain = pd.Series(gain).rolling(period).mean()
    loss = pd.Series(loss).rolling(period).mean()

    rs = gain / loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


# -----------------------------------
# NSE STOCK FETCHER
# -----------------------------------

def fetch_nse_index_stocks(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch NSE data: {response.status_code}")

    df = pd.read_csv(StringIO(response.text))
    return [s + ".NS" for s in df["Symbol"].tolist()]
    
    #stocks = df['Symbol'].tolist()
    #stocks = [stock + ".NS" for stock in stocks]
    #return stocks


# -----------------------------------
# LOAD STOCKS (ONLY ONCE)
# -----------------------------------
try:
    nifty50_url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    niftynext50_url = "https://archives.nseindia.com/content/indices/ind_niftynext50list.csv"

    stocks = list(set(
        fetch_nse_index_stocks(nifty50_url) +
        fetch_nse_index_stocks(niftynext50_url)
    ))

    print(f"{len(stocks)} NSE Stocks Loaded")

except Exception as e:
    print("Stock loading failed:", e)
    stocks = []

# -----------------------------------
# WATCHLIST UPDATE (FIXED - SINGLE BULK CALL)
# -----------------------------------
try:    
    watchlist_data = [["Ticker"]] + [[s] for s in stocks]

    watchlist_ws.clear()
    watchlist_ws.update("A1", watchlist_data)

    print("Watchlist Updated Successfully")
    
except Exception as e:
    print("Watchlist Update Error:", e)
    raise   
    
# -----------------------------------
# MAIN ANALYSIS
# -----------------------------------
results = []

for ticker in stocks:
    print(f"Processing {ticker}")

    try:
        df = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False
        )
        if df is None or df.empty:
            continue

        close = df['Close'].squeeze()
        
        # EMA
        df['EMA20'] = close.ewm(span=20).mean()
        df['EMA50'] = close.ewm(span=50).mean()

        # RSI
        df['RSI'] = calculate_rsi(close)

        latest = df.iloc[-1]
        
        cmp = float(close.iloc[-1])

        ema20 = float(latest['EMA20']) if pd.notna(latest['EMA20']) else 0
        ema50 = float(latest['EMA50']) if pd.notna(latest['EMA50']) else 0
        rsi = float(latest['RSI']) if pd.notna(latest['RSI']) else 0
        
        # -----------------------------
        # SCORING
        # -----------------------------

        score = 0

        # EMA Trend
        if ema20 > ema50: score += 30
        
        # RSI Strength
        if rsi > 60: score += 25
        
        # Price Above EMA
        if cmp > ema20: score += 20
        
        # Strong Momentum
        if rsi > 70: score += 15
        
        # Bullish Structure
        if cmp > ema50: score += 10
            
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

        results.append([
            ticker, cmp, rsi, ema20, ema50, trend, score, signal
        ])

    except Exception as e:
        print(f"Error Processing {ticker}: {e}")
        continue
        
# -----------------------------------
# SORT RESULTS BY SCORE
# -----------------------------------

results = sorted(results, key=lambda x: x[6], reverse=True)

# -----------------------------------
# UPDATE SCANNER SHEET (BULK SAFE)
# -----------------------------------
try:
    scanner_ws.clear()

    headers = ["Ticker", "CMP", "RSI", "EMA20", "EMA50", "Trend", "Score", "Signal"]

    # PREPARE SCANNER DATA

    scanner_data = [headers] + results

    # BULK UPDATE

    scanner_ws.update("A1", scanner_data)

    print("Scanner Sheet Updated Successfully")
    
except APIError as e:
    print("Google Sheets API Error:", e)
    time.sleep(5)
    raise
    
except Exception as e:
    print("Scanner Update Error:", e)
    raise

print("Script Completed Successfully")
