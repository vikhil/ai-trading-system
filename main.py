import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from data_loader import load_universe, fetch_stock_data
from signals import generate_signal
from sheets_writer import safe_update
import yfinance as yf

print("Script Started")

def get_market_regime(df):

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
watchlist_ws = sheet.worksheet("Watchlist")

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

watchlist_data = [["Ticker"]] + [[s] for s in stocks]

safe_update(watchlist_ws, watchlist_data)

# ----------------------------
# MARKET REGIME
# ----------------------------

regime = get_market_regime()

print("Market Regime:", regime)

# ----------------------------
# ANALYSIS
# ----------------------------
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

        signal_data = generate_signal(df, regime)

        if signal_data is None:
            continue

        cmp, rsi, ema20, ema50, trend, score, signal = signal_data

        # FILTER LOW QUALITY
        if score < 40:
            continue

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

    except Exception as e:

        print(f"Error Processing {ticker}: {e}")

        continue
        
# ----------------------------
# SORT RESULTS
# ----------------------------

results = sorted(results, key=lambda x: x[6], reverse=True)

# ----------------------------
# UPDATE SCANNER
# ----------------------------

headers = ["Ticker","CMP","RSI","EMA20","EMA50","Trend","Score","Signal"]

scanner_data = [headers] + results

safe_update(scanner_ws, scanner_data)

print("Completed Successfully")
