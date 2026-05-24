import json
import os
import pandas as pd
import gspread
import yfinance as yf

from oauth2client.service_account import ServiceAccountCredentials

from data_loader import load_universe
from signals import generate_signal
from sheets_writer import safe_update


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

# ----------------------------
# NIFTY DATA FOR RELATIVE STRENGTH
# ----------------------------

nifty_df = yf.download("^NSEI", period="6mo", interval="1d", auto_adjust=True, progress=False)

nifty_close = nifty_df["Close"].dropna()

nifty_return = (nifty_close.iloc[-1] / nifty_close.iloc[0]) - 1

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
        
        stock_close = df["Close"]

        if isinstance(stock_close, pd.DataFrame):
            stock_close = stock_close.iloc[:, 0]

        stock_close = pd.Series(stock_close).dropna()
        
        # ----------------------------
        # BASIC RETURNS (RS LOGIC)
        # ----------------------------
        
        stock_return = (stock_close.iloc[-1] / stock_close.iloc[0]) - 1

        if nifty_return != 0:
            rs_score = stock_return / nifty_return
        else:
            rs_score = 0

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
        
        signal_data = generate_signal(df, regime)

        if signal_data is None:
            continue

        cmp, rsi, ema20, ema50, trend, score, signal = signal_data

        # FILTER LOW QUALITY
        if score < 40:
            continue

        # ----------------------------
        # PLACEHOLDERS (NO CRASH VERSION)
        # ----------------------------
        atr = 0
        stop_loss = 0
        target = 0
        risk_reward = 0

        avg_volume = 0
        current_volume = 0
        volume_spike = "NA"
        breakout = "NA"

        # ----------------------------
        # FINAL ROW
        # ----------------------------
        results.append([
            ticker,
            cmp,
            rsi,
            ema20,
            ema50,
            trend,
            score,
            signal,
            atr,
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
        print(f"Error Processing {ticker}: {e}")
        continue
        
# ----------------------------
# SORT RESULTS
# ----------------------------

results = sorted(results, key=lambda x: x[6], reverse=True)

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

safe_update(scanner_ws, scanner_data)

print("Completed Successfully")
