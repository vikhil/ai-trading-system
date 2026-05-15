import yfinance as yf
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

# -----------------------------------
# GOOGLE SHEETS AUTH
# -----------------------------------

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

#sheet = client.open("AI_Trading_System")
sheet = client.open_by_key("1AbCDefGHIJK1234567890")

scanner_ws = sheet.worksheet("Scanner")

# -----------------------------------
# STOCK LIST
# -----------------------------------

stocks = [
    "TCS.NS",
    "INFY.NS",
    "RELIANCE.NS"
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

    try:

        df = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            progress=False
        )

        if df.empty:
            continue

        # CLOSE PRICE
        close = df['Close']

        # EMA
        df['EMA20'] = close.ewm(span=20).mean()
        df['EMA50'] = close.ewm(span=50).mean()

        # RSI
        df['RSI'] = calculate_rsi(close)

        latest = df.iloc[-1]

        cmp = round(float(latest['Close']), 2)

        ema20 = float(latest['EMA20'])
        ema50 = float(latest['EMA50'])

        rsi = round(float(latest['RSI']), 2)

        # -----------------------------
        # SCORING LOGIC
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
            round(ema20, 2),
            round(ema50, 2),
            trend,
            score,
            signal
        ])

    except Exception as e:

        results.append([
            ticker,
            "ERROR",
            str(e),
            "",
            "",
            "",
            "",
            ""
        ])

# -----------------------------------
# UPDATE GOOGLE SHEET
# -----------------------------------

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

print("Sheet Updated Successfully")
