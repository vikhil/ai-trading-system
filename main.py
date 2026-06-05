DEBUG = False
DEBUG_LOGS = True 
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
from alerts import send_telegram
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

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
        return "SIDEWAYS", 0, 0, 0, 0.0

    close = nifty["Close"]

    # FIX: handle DataFrame vs Series issue
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = close.dropna()

    ema50 = close.ewm(span=50).mean()
    ema200 = close.ewm(span=200).mean()

    last_close = float(close.iloc[-1])
    last_ema50 = float(ema50.iloc[-1])
    last_ema200 = float(ema200.iloc[-1])

    nifty_return = float((close.iloc[-1] / close.iloc[0]) - 1)

    if last_close > last_ema50 and last_ema50 > last_ema200:
        regime = "BULL"
    elif last_close < last_ema50 and last_ema50 < last_ema200:
        regime = "BEAR"
    else:
        regime = "SIDEWAYS"

    return regime, last_close, last_ema50, last_ema200, nifty_return
        
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

print("Spreadsheet:", sheet.title)
print("URL:", sheet.url)

print("ALL TABS FOUND:")

for ws in sheet.worksheets():
    print(
        ws.title,
        "| ID:",
        ws.id
    )
    
scanner_ws = sheet.worksheet("Scanner")

try:
    failed_ws = sheet.worksheet("FailedLogs")
except:
    failed_ws = sheet.add_worksheet(title="FailedLogs", rows="1000", cols="10")
    
watchlist_ws = sheet.worksheet("Watchlist")

print("========== WORKSHEET CHECK ==========")

print("Spreadsheet URL:", sheet.url)

print("Scanner:", scanner_ws.title, "ID:", scanner_ws.id)

print("Watchlist:", watchlist_ws.title, "ID:", watchlist_ws.id)

print("FailedLogs:", failed_ws.title, "ID:", failed_ws.id)

print("=====================================")

failed_logs = []

print("Connected")

test_ws = sheet.worksheet("Scanner")

test_ws.update(
    values=[
        ["TEST"],
        ["GITHUB ACTIONS WRITE CHECK"]
    ],
    range_name="A1"
)

print("TEST WRITE SUCCESS")

print(
    "A1 VALUE AFTER TEST:",
    test_ws.acell("A1").value
)

# ----------------------------
# LOAD STOCKS
# ----------------------------
stocks = load_universe()

stocks = sorted(list(set(stocks)))

print("Stocks:", len(stocks))

# ----------------------------
# UPDATE WATCHLIST (1 CALL ONLY)
# ----------------------------

watchlist_data = [["Ticker", "CMP", "RSI", "EMA20", "EMA50", "Trend", "Score", "Edge Rating",  "Trade Action", "RS Score", "Volume Spike"]]
watchlist_seen = set()

# ----------------------------
# MARKET REGIME
# ----------------------------

regime, nifty_close, nifty_ema50, nifty_ema200, nifty_return = get_market_regime()

# ----------------------------
# NIFTY DATA FOR RELATIVE STRENGTH
# ----------------------------

nifty_df = yf.download("^NSEI", period="6mo", interval="1d", auto_adjust=True, progress=False)

if nifty_df.empty or "Close" not in nifty_df.columns:
    nifty_return = 0.0
else:
    nifty_series = nifty_df["Close"]

    if isinstance(nifty_series, pd.DataFrame):
        nifty_series = nifty_series.iloc[:, 0]

    nifty_series = nifty_series.dropna()

    if len(nifty_series) < 2:
        nifty_return = 0.0
    else:
        nifty_return = float(
            (nifty_series.iloc[-1] / nifty_series.iloc[0]) - 1)

print("Market Regime:", regime)

# ----------------------------
# MARKET TREND LOGGING
# ----------------------------

try:
    market_ws = sheet.worksheet("Market Trend")
except:
    market_ws = sheet.add_worksheet(
        title="Market Trend",
        rows="5000",
        cols="5"
    )
    
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

print("Market Trend Updated:", timestamp, regime)

def batch_download(tickers, chunk_size=20):
    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i:i + chunk_size]

        data = yf.download(
            tickers=batch,
            period="6mo",
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False
        )

        yield batch, data

results_map = []

for batch, data in batch_download(stocks, chunk_size=20):

    for ticker in batch:

        try:
            if ticker not in data.columns.get_level_values(0):
                results_map.append((ticker, None, "NO_DATA"))
                continue

            df = data[ticker].dropna()

            results_map.append((ticker, df, None))

        except Exception as e:
            results_map.append((ticker, None, str(e)))
            
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

for ticker, df, error in results_map:
    error_reason = None
    
    try:

        #df, error = safe_download(ticker)
    
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
        df = df.dropna(subset=["Close"])
        
        # 4. Convert all columns to numeric
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # 5. Drop bad rows
        df = df.dropna()
        
        if len(df) < 60:
            print(f"SKIP: {ticker} REASON: INSUFFICIENT_DATA {len(df)}")
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
        
        row = df.iloc[-1]
        
        avg_volume = row.get("Avg Volume", 0)
        volume_spike = row.get("Volume Spike", 0)
        breakout = row.get("Breakout", 0)

        raw_volume = row.get("Volume", 0)
        atr_indicator = row.get("ATR", 0)

        # ---------------------------
        # FILTERS (EARLY EXIT CONDITIONS)
        # ---------------------------
        
        # Safety conversions (important because yfinance + pandas can return NaN/Series)
        current_volume = float(raw_volume) if pd.notna(raw_volume) else 0
        atr_indicator = float(atr_indicator) if pd.notna(atr_indicator) else 0
        
        # B) Liquidity filter
        if current_volume <= 0:
            print(f"SKIP: {ticker} REASON: INVALID_VOLUME {current_volume}")
            continue

        if current_volume < avg_volume * 0.5:   # relaxed threshold
            print(f"SKIP: {ticker} REASON: LOW_VOLUME {current_volume}")
            continue
    
        # C) ATR filter
        if atr_indicator <= 0:
            print(f"SKIP: {ticker} REASON: BAD_ATR {atr_indicator}")
            continue
        
        # =========================
        # FINAL DATA NORMALIZATION FIX
        # =========================
        
        if df.empty:
            continue
        
        stock_close = df["Close"].dropna()

        if len(stock_close) < 2:
            continue
    
        # ----------------------------
        # BASIC RETURNS (RS LOGIC)
        # ----------------------------
        
        stock_return = float((stock_close.iloc[-1] / stock_close.iloc[0]) - 1)

        rs_score = (stock_return - nifty_return)
        rs_score = rs_score * 100
        rs_score = max(min(rs_score, 100), -100)
            
        if rs_score >= 50:
            rs_rank = "ELITE"
        elif rs_score >= 25:
            rs_rank = "STRONG"
        elif rs_score >= 10:
            rs_rank = "AVERAGE"
        else:
            rs_rank = "WEAK"
    
        # ----------------------------
        # SIGNAL ENGINE
        # ----------------------------
        
        try:
            signal_data = generate_signal(df, regime, rs_score)

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

        if DEBUG_LOGS:
            print("SIGNAL OK:", ticker)
    
        rsi = float(rsi) if pd.notna(rsi) else 0
        ema20 = float(ema20) if pd.notna(ema20) else 0
        ema50 = float(ema50) if pd.notna(ema50) else 0
        
        # ----------------------------
        # ATR RISK ENGINE
        # ----------------------------

        last_row = df.iloc[-1]

        risk_values = apply_risk_engine(last_row, df=df)
        
        atr_risk = round(float(risk_values.iloc[0]), 2)
        stop_loss = round(float(risk_values.iloc[1]), 2)
        target = round(float(risk_values.iloc[2]), 2)
        
        #risk_reward = round(float(risk_values.iloc[3]), 2)
        
        risk_reward = float(risk_values.iloc[3]) if pd.notna(risk_values.iloc[3]) else 0
        
        #if risk_reward < 1.5:
            #print(f"SKIP: {ticker} REASON: LOW_RR {risk_reward}")
            #continue

        if pd.isna(risk_reward):
            print(f"SKIP: {ticker} REASON: RR_NAN")
            continue

        if risk_reward < 1.0:   # relax temporarily
            print(f"SKIP: {ticker} REASON: LOW_RR {risk_reward}")
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
        

        # ----------------------------
        # FINAL ROW
        # ----------------------------
    
        edge_score = calculate_edge_score(
            score,
            risk_reward,
            rs_score,
            volume_spike,
            breakout,
            regime
        )

        edge_rating = int(calculate_edge_rating(edge_score))
        trade_action = get_trade_action(edge_rating)

        if regime == "BEAR":

            # Elite setups still allowed
            if score >= 90 and edge_rating >= 8:
                trade_action = "STRONG_BUY"
        
            elif score >= 85 and edge_rating >= 7:
                trade_action = "BUY"
        
            elif trade_action in ["BUY", "STRONG_BUY"]:
                trade_action = "WATCH"
        
        # ----------------------------
        # STREAM ROUTING (FIXED LOGIC)
        # ----------------------------
        
        # Always add WATCHLIST only for WATCH + BUY + STRONG_BUY
        if trade_action in ["WATCH", "BUY", "STRONG_BUY"]:

            if ticker not in watchlist_seen:
                watchlist_data.append([
                    ticker, cmp, rsi, ema20, ema50,
                    trend, score, edge_rating,
                    trade_action, rs_score, volume_spike
                ])
        
                watchlist_seen.add(ticker)
                print(f"📋 Added to Watchlist: {ticker}")

        if trade_action == "BUY":
            
            print("TG_TOKEN EXISTS:", bool(os.getenv("TG_TOKEN")))
            print("TG_CHAT_ID EXISTS:", bool(os.getenv("TG_CHAT_ID")))

            msg = f"📌 BUY: {ticker}\nEdge: {edge_rating}\nScore: {score}"
            print(msg)
            send_telegram(msg)

        elif trade_action == "STRONG_BUY":
            msg = f"🚀 STRONG BUY: {ticker}\nEdge: {edge_rating}\nScore: {score}"
            print(msg)
            send_telegram(msg)

        elif trade_action == "WATCH":
            print(f"👀 WATCH CANDIDATE: {ticker} Edge: {edge_rating}")
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
        
        print(
            f"ADDING RESULT: {ticker} | "
            f"Score={score} | "
            f"RR={risk_reward} | "
            f"Edge={edge_score}"
        )
        
        results.append({
            "ticker": ticker,
            "cmp": cmp,
            "rsi": rsi,
            "ema20": ema20,
            "ema50": ema50,
            "trend": trend,
            "score": score,
            "edge_score": edge_score,
            "edge_rating": edge_rating,
            "trade_action": trade_action,
            "signal": signal,
            "atr_risk": atr_risk,
            "stop_loss": stop_loss,
            "target": target,
            "risk_reward": risk_reward,
            "rs_score": rs_score,
            "rs_rank": rs_rank,
            "avg_volume": avg_volume,
            "current_volume": current_volume,
            "volume_spike": volume_spike,
            "breakout": breakout
        })
        print("RESULTS SIZE:", len(results))
        
    except Exception as e:
        error_reason = str(e)
    
        print(
            f"ERROR: {ticker} | "
            f"{type(e).__name__} | "
            f"{error_reason}"
        )
    
        failed_logs.append([
            ticker,
            "PIPELINE_ERROR",
            error_reason
        ])
    
        continue

# ----------------------------
# SORT WATCHLIST (NEW ADDITION)
# ----------------------------

watchlist_data = [watchlist_data[0]] + sorted(
    watchlist_data[1:],
    key=lambda x: x[7],
    reverse=True
)

# ----------------------------
# SORT RESULTS
# ----------------------------

#results = sorted(results, key=lambda x: x[7] if x[7] is not None else 0, reverse=True)

#results_sorted = sorted(results, key=lambda x: x[7] if x[7] is not None else 0, reverse=True)

results_sorted = sorted(
    results,
    key=lambda x: x["edge_score"],
    reverse=True
)

print("Sample result type:", type(results_sorted[0]) if results_sorted else None)

# SAFETY: ensure no malformed rows
results_sorted = [
    r for r in results_sorted
    if isinstance(r, dict) and "edge_score" in r
]

print("Final Results Count:", len(results_sorted))

# ----------------------------
# BUY COUNT SUMMARY
# ----------------------------

buy_count = len([
    r for r in results_sorted
    if r["trade_action"] in ["BUY", "STRONG_BUY"]
])

watch_count = len([
    r for r in results_sorted
    if r["trade_action"] == "WATCH"
])

print(f"BUY Count: {buy_count}")
print(f"WATCH Count: {watch_count}")

# ----------------------------
# MARKET BREADTH
# ----------------------------

if len(results_sorted) > 0:
    breadth_score = ((buy_count * 1.0) + (watch_count * 0.5)) / len(results_sorted) * 100
else:
    breadth_score = 0

print(f"Breadth Score: {breadth_score}%")

# ----------------------------
# MARKET HEALTH
# ----------------------------

if breadth_score >= 15:
    market_health = "STRONG BULLISH"

elif breadth_score >= 10:
    market_health = "BULLISH"

elif breadth_score >= 5:
    market_health = "IMPROVING"

elif breadth_score >= 2:
    market_health = "WEAK"

else:
    market_health = "VERY WEAK"

print("Market Health:", market_health)

# ----------------------------
# MARKET TREND LOGGING
# ----------------------------

headers_market = [
    "Timestamp",
    "Regime",
    "Nifty Close",
    "EMA50",
    "EMA200",
    "BUY Count",
    "WATCH Count",
    "Breadth %",
    "Market Health"
]

breadth_score = round(float(breadth_score), 2)

market_trend_row = [
    str(timestamp),
    str(regime),
    float(nifty_close),
    float(nifty_ema50),
    float(nifty_ema200),
    int(buy_count),
    int(watch_count),
    float(breadth_score),
    str(market_health)
]

existing = market_ws.get_all_values()

print("===== MARKET TREND DEBUG =====")

try:
    for i, v in enumerate(market_trend_row):
        print(f"Col {i}:", type(v), v)
except Exception as e:
    print("Market Trend Debug Error:", e)

print("==============================")

if len(existing) == 0:
    market_ws.append_row(
        headers_market,
        value_input_option="RAW"
    )

try:
    market_ws.append_row(
        market_trend_row,
        value_input_option="RAW"
    )

    print(
        "Market Trend Updated:",
        timestamp,
        regime,
        breadth_score,
        market_health
    )

except Exception as e:
    print("Market Trend Update Failed:", e)

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

scanner_data = [headers]

for r in results_sorted:
    scanner_data.append([
        r["ticker"],
        r["cmp"],
        r["rsi"],
        r["ema20"],
        r["ema50"],
        r["trend"],
        r["score"],
        r["edge_score"],
        r["edge_rating"],
        r["trade_action"],
        r["signal"],
        r["atr_risk"],
        r["stop_loss"],
        r["target"],
        r["risk_reward"],
        r["rs_score"],
        r["rs_rank"],
        r["avg_volume"],
        r["current_volume"],
        r["volume_spike"],
        r["breakout"]
    ])

print("Scanner sample row:")
print(scanner_data[:3])

try:
    print("Writing Scanner...")
    safe_update(scanner_ws, scanner_data)
    
    if DEBUG_LOGS:
        import time
        time.sleep(1)
        
        values = scanner_ws.get("A1:A5")
        for i, row in enumerate(values, start=1):
            print(f"Row {i}:", row)

    print("Scanner Updated")

except Exception as e:
    print("Scanner Update Failed:", e)

print("Scanner Rows:", len(scanner_data))

print("Watchlist sample row:")
print(watchlist_data[:3])

try:
    print("Writing Watchlist...")
    #watchlist_ws.clear()

    safe_update(watchlist_ws, watchlist_data)

    print(
        "Watchlist A1:",
        watchlist_ws.acell("A1").value
    )

    print(
        "Watchlist A2:",
        watchlist_ws.acell("A2").value
    )
    
    print("Watchlist Updated")

except Exception as e:
    print("Watchlist Update Failed:", e)

print("Watchlist Rows:", len(watchlist_data))

print("Failed sample row:")
print(failed_logs[:3])

try:
    print("Writing FailedLogs...")
    #failed_ws.clear()

    failed_data = ["Ticker", "Error Type", "Reason"]
    
    for row in failed_logs:
       failed_data.append(row)

    safe_update(failed_ws, failed_data)
    
    print("FailedLogs Updated")
    
except Exception as e:
    print("FailedLogs Update Failed:", e)

print("Unique Trade Actions:")
print(set(r["trade_action"] for r in results_sorted))

top_picks = [headers]

for r in results_sorted:
    if (
        r["edge_rating"] >= 7
        and r["score"] >= 80
    ):
        top_picks.append([
            r["ticker"],
            r["cmp"],
            r["rsi"],
            r["ema20"],
            r["ema50"],
            r["trend"],
            r["score"],
            r["edge_score"],
            r["edge_rating"],
            r["trade_action"],
            r["signal"],
            r["atr_risk"],
            r["stop_loss"],
            r["target"],
            r["risk_reward"],
            r["rs_score"],
            r["rs_rank"],
            r["avg_volume"],
            r["current_volume"],
            r["volume_spike"],
            r["breakout"]
        ])

try:
    top_ws = sheet.worksheet("Top Picks")
except:
    top_ws = sheet.add_worksheet(
        title="Top Picks",
        rows="1000",
        cols="25"
    )

safe_update(top_ws, top_picks)

print("Completed Successfully")
