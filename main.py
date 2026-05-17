import yfinance as yf
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

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
# STOCK LIST
# -----------------------------------

stocks = [
    "BEL.NS",
    "GRAPHITE.NS",
    "TATACONSUM.NS"
]

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

        if ema20 > ema50:
            score += 40

        if rsi > 60:
            score += 30

        if cmp > ema20:
            score += 30

        # -----------------------------
        # SIGNAL
        # -----------------------------

        if score >= 80:
            signal = "STRONG BUY"

        elif score >= 60:
            signal = "BUY"

        elif score >= 40:
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
