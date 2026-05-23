import yfinance as yf
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os
import requests
from io import StringIO

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

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict,
        scope
    )

    client = gspread.authorize(creds)

    print("Google Auth Successful")

except Exception as e:

    print("Google Auth Error:", e)
    raise

# -----------------------------------
# OPEN SHEET
# -----------------------------------

try:

    spreadsheet_id = "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"

    sheet = client.open_by_key(spreadsheet_id)

    print("Spreadsheet Connected")

except Exception as e:

    print("Spreadsheet Connection Error:", e)
    raise

# -----------------------------------
# OPEN WORKSHEET
# -----------------------------------

try:

    scanner_ws = sheet.worksheet("Scanner")

    print("Scanner Worksheet Found")

except Exception as e:

    print("Worksheet Error:", e)
    raise

# -----------------------------------
# AUTO LOAD STOCKS
# -----------------------------------

try:

    nifty50 = pd.read_csv("data/nifty50.csv")

    niftynext50 = pd.read_csv("data/niftynext50.csv")

    # COMBINE STOCKS

    combined_stocks = pd.concat([
        nifty50,
        niftynext50
    ])

    # REMOVE DUPLICATES

    combined_stocks.drop_duplicates(inplace=True)

    # CONVERT TO LIST

    stocks = combined_stocks['Ticker'].tolist()

    print(f"{len(stocks)} Stocks Loaded")

    # -----------------------------------
    # UPDATE WATCHLIST SHEET
    # -----------------------------------
    
    watchlist_ws = sheet.worksheet("Watchlist")
    
    watchlist_ws.clear()
    
    watchlist_ws.append_row(["Ticker"])
    
    for stock in stocks:
    
        watchlist_ws.append_row([stock])
    
    print("Watchlist Updated Successfully")

except Exception as e:

    print("Stock Loading Error:", e)

    raise

results = []

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

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch NSE data: {response.status_code}")

    df = pd.read_csv(StringIO(response.text))

    stocks = df['Symbol'].tolist()

    stocks = [stock + ".NS" for stock in stocks]

    return stocks

# -----------------------------------
# AUTO FETCH NSE STOCKS
# -----------------------------------

try:

    nifty50_url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"

    niftynext50_url = "https://archives.nseindia.com/content/indices/ind_niftynext50list.csv"

    nifty50_stocks = fetch_nse_index_stocks(nifty50_url)

    niftynext50_stocks = fetch_nse_index_stocks(niftynext50_url)

    # COMBINE

    stocks = list(set(
        nifty50_stocks +
        niftynext50_stocks
    ))

    print(f"{len(stocks)} NSE Stocks Loaded")

    # UPDATE WATCHLIST SHEET
    
    watchlist_ws = sheet.worksheet("Watchlist")
    
    watchlist_ws.clear()
    
    watchlist_ws.append_row(["Ticker"])
    
    for stock in stocks:
    
        watchlist_ws.append_row([stock])
    
    print("Watchlist Updated Successfully")

except Exception as e:

    print("NSE Fetch Error:", e)

    raise
# -----------------------------------
# MAIN ANALYSIS
# -----------------------------------

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

        if df.empty:

            print(f"No Data Found: {ticker}")
            continue

        close = df['Close'].squeeze()
        
        # EMA
        df['EMA20'] = close.ewm(span=20).mean()
        df['EMA50'] = close.ewm(span=50).mean()

        # RSI
        df['RSI'] = calculate_rsi(close)

        latest = df.tail(1)

        cmp = round(float(close.iloc[-1]), 2)

        ema20 = round(float(latest['EMA20'].iloc[0]) if pd.notna(latest['EMA20'].iloc[0]) else 0, 2)
        ema50 = round(float(latest['EMA50'].iloc[0]) if pd.notna(latest['EMA50'].iloc[0]) else 0, 2)

        rsi = round(float(latest['RSI'].iloc[0]) if pd.notna(latest['RSI'].iloc[0]) else 0, 2)

        # CLEAN INVALID VALUES

        if np.isnan(rsi):
            rsi = 0
        
        if np.isnan(ema20):
            ema20 = 0
        
        if np.isnan(ema50):
            ema50 = 0
        
        # -----------------------------
        # SCORING
        # -----------------------------

        score = 0

        # EMA Trend
        if ema20 > ema50:
            score += 30
        
        # RSI Strength
        if rsi > 60:
            score += 25
        
        # Price Above EMA
        if cmp > ema20:
            score += 20
        
        # Strong Momentum
        if rsi > 70:
            score += 15
        
        # Bullish Structure
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

        results.append([
            ticker,
            cmp,
            rsi,
            ema20,
            ema50,
            trend,
            score,
            signal
        ])

        print(f"{ticker} Processed Successfully")

    except Exception as e:

        print(f"Error Processing {ticker}: {e}")

# -----------------------------------
# SORT RESULTS BY SCORE
# -----------------------------------

results = sorted(results, key=lambda x: x[6], reverse=True)

# -----------------------------------
# UPDATE GOOGLE SHEET
# -----------------------------------

try:

    scanner_ws.clear()

    headers = [
        "Ticker",
        "CMP",
        "RSI",
        "EMA20",
        "EMA50",
        "Trend",
        "Score",
        "Signal"
    ]

    scanner_ws.append_row(headers)

    for row in results:
        scanner_ws.append_row(row)

    print("Google Sheet Updated Successfully")

except Exception as e:

    print("Google Sheet Update Error:", e)
    raise

print("Script Completed")
