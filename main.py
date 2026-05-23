import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from data_loader import load_universe, fetch_stock_data
from signals import generate_signal
from sheets_writer import safe_update
import yfinance as yf
import numpy as np
from signals import (calculate_institutional_score, classify_signal, calculate_rsi)


def get_market_regime(df):

    close = df["Close"]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = close.dropna()

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
        
print("Script Started")

# ----------------------------
# AUTH
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
watchlist_ws = sheet.worksheet("Watchlist")

print("Connected")

# ----------------------------
# LOAD STOCKS
# ----------------------------
stocks = load_universe()
print("Stocks:", len(stocks))

# ----------------------------
# WATCHLIST (1 CALL ONLY)
# ----------------------------
watchlist_data = [["Ticker"]] + [[s] for s in stocks]
safe_update(watchlist_ws, watchlist_data)

# ----------------------------
# ANALYSIS
# ----------------------------
regime = get_market_regime()

results = []

for ticker in stocks:

    try:
        df = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False
        )

        if df.empty:
            continue

        close = df["Close"]

        ema20 = close.ewm(span=20).mean().iloc[-1]
        ema50 = close.ewm(span=50).mean().iloc[-1]
        rsi = calculate_rsi(close).iloc[-1]
        cmp = close.iloc[-1]

        if pd.isna(ema20) or pd.isna(ema50) or pd.isna(rsi):
            continue

        score = calculate_institutional_score(cmp, rsi, ema20, ema50)
        signal = classify_signal(score, regime)

        trend = "Bullish" if ema20 > ema50 else "Bearish"

        # FILTER LOW QUALITY TRADES
        if score < 40:
            continue

        results.append([
            ticker,
            round(cmp, 2),
            round(rsi, 2),
            round(ema20, 2),
            round(ema50, 2),
            trend,
            score,
            signal
        ])

    except Exception as e:
        print(f"Error Processing {ticker}: {e}")
        continue
        
# ----------------------------
# SORT
# ----------------------------
results = sorted(results, key=lambda x: x[6], reverse=True)

# ----------------------------
# UPDATE SHEET (SAFE)
# ----------------------------
headers = ["Ticker","CMP","RSI","EMA20","EMA50","Trend","Score","Signal"]
scanner_data = [headers] + results

safe_update(scanner_ws, scanner_data)

print("Completed Successfully")
