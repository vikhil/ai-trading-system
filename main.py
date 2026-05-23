import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from data_loader import load_universe, fetch_stock_data
from signals import generate_signal
from sheets_writer import safe_update

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
results = []

for ticker in stocks:
    try:
        df = fetch_stock_data(ticker)

        if df is None or df.empty:
            continue

        cmp, rsi, ema20, ema50, trend, score, signal = generate_signal(df)

        results.append([
            ticker, cmp, rsi, ema20, ema50, trend, score, signal
        ])

    except Exception as e:
        print("Error:", ticker, e)

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
