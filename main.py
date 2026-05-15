import yfinance as yf
import pandas as pd
import pandas_ta as ta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

# ---------------------------
# GOOGLE SHEETS CONNECTION
# ---------------------------

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

sheet = client.open("AI_Trading_System")

portfolio_ws = sheet.worksheet("Portfolio")

# ---------------------------
# STOCK LIST
# ---------------------------

stocks = [
    "BDL.NS",
    "BEL.NS",
    "TCS.NS",
    "INFY.NS",
    "RELIANCE.NS",
    "HAL.NS"
]

results = []

# ---------------------------
# ANALYSIS LOOP
# ---------------------------

for ticker in stocks:

    try:

        df = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            progress=False
        )

        if df.empty:
            continue

        close = df['Close']

        # Indicators
        df['EMA20'] = ta.ema(close, length=20)
        df['EMA50'] = ta.ema(close, length=50)
        df['RSI'] = ta.rsi(close, length=14)

        latest = df.iloc[-1]

        cmp = round(latest['Close'], 2)
        rsi = round(latest['RSI'], 2)

        ema20 = latest['EMA20']
        ema50 = latest['EMA50']

        # SIGNAL LOGIC
        score = 0

        if ema20 > ema50:
            score += 40

        if rsi > 60:
            score += 30

        if cmp > ema20:
            score += 30

        # Final Signal
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
            trend,
            score,
            signal
        ])

    except Exception as e:
        print(e)

# ---------------------------
# UPDATE GOOGLE SHEET
# ---------------------------

scanner_ws = sheet.worksheet("Scanner")

scanner_ws.clear()

headers = [
    "Ticker",
    "CMP",
    "RSI",
    "Trend",
    "Score",
    "Signal"
]

scanner_ws.append_row(headers)

for row in results:
    scanner_ws.append_row(row)

print("Sheet Updated Successfully")
