from datetime import datetime, timedelta

SYSTEM_VERSION = "2A.1-STABLE"

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")

print(f"[SYSTEM] Version: {SYSTEM_VERSION}")
print(f"[SYSTEM] Run ID: {RUN_ID}")

DEBUG = False
DEBUG_LOGS = True 

# ----------------------------
# GLOBAL RISK SETTINGS
# ----------------------------
capital = 100000

risk_per_trade = 0.005
max_capital_risk = 0.20

STATE_FILE = "trade_state.json"
STATE_EXPIRY_HOURS = 24
    
MAX_BUYS = 999
MAX_WATCH = 10
    
import json
import os
import time
import pandas as pd
import gspread
import yfinance as yf

from oauth2client.service_account import ServiceAccountCredentials
from data_loader import load_universe
from signals import generate_signal, calculate_atr, apply_risk_engine, add_volume_and_breakout
from engine.risk_engine import (
    calculate_position_size,
    calculate_edge_score,
    calculate_edge_rating,
    get_trade_action
)
from engine.scanner_engine import run_scanner
from sheets_writer import safe_update
from alerts import send_telegram
from portfolio_manager import enrich_portfolio
from engine.portfolio_rotation import generate_rotation_plan
from utils.logger import (
    log_scan,
    log_signal,
    log_risk,
    log_exec,
    log_error,
)
from engine.portfolio_dashboard import generate_portfolio_dashboard

def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except:
        print("[STATE] Corrupted file detected. Resetting state.")
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

state = load_state()

def is_state_expired(entry_time):
    try:
        entry_dt = datetime.strptime(entry_time, "%Y-%m-%d %H:%M:%S")
        return datetime.now() - entry_dt > timedelta(hours=STATE_EXPIRY_HOURS)
    except:
        return True
        
def safe_generate_signal(df, regime, rs_score, ticker):
    try:
        result = generate_signal(df, regime, rs_score)

        if result is None:
            log_error(f"{ticker} generate_signal returned None")
            return None

        if not isinstance(result, (list, tuple)) or len(result) < 10:
            log_error(f"{ticker} invalid signal shape: {type(result)}")
            return None

        return result

    except Exception as e:
        log_error(f"{ticker} signal crash: {str(e)}")
        return None

def normalize_trade_action(action):
    action = str(action).upper()

    if "BUY" in action:
        return "BUY"
    if "WATCH" in action:
        return "WATCH"
    if "SELL" in action:
        return "SELL"

    return "NO TRADE"
    
def log_trade(
    action,
    ticker,
    cmp_price="",
    edge_score="",
    edge_rating="",
    position_size="",
    stop_loss="",
    target="",
    risk_reward="",
    rs_score="",
    signal=""
):

    try:
        journal = sheet.worksheet("Trade Journal")

    except:
        journal = sheet.add_worksheet(
            "Trade Journal",
            rows="5000",
            cols="20"
        )

    journal.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ticker,
        action,
        cmp_price,
        edge_score,
        edge_rating,
        position_size,
        stop_loss,
        target,
        risk_reward,
        rs_score,
        signal
    ], value_input_option="RAW")

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

# ============================
# SETTINGS SHEET
# ============================

try:
    settings_ws = sheet.worksheet("Settings")
    settings = settings_ws.get_all_records()
except:
    settings_ws = sheet.add_worksheet(
        title="Settings",
        rows="500",
        cols="10"
    )
    settings = []

print("Settings Sheet Loaded:", len(settings))

scanner_ws = sheet.worksheet("Scanner")

try:
    failed_ws = sheet.worksheet("FailedLogs")
except:
    failed_ws = sheet.add_worksheet(title="FailedLogs", rows="1000", cols="10")
    
watchlist_ws = sheet.worksheet("Watchlist")

try:
    portfolio_ws = sheet.worksheet("Portfolio")
except:
    portfolio_ws = sheet.add_worksheet(
        title="Portfolio",
        rows="1000",
        cols="5"
    )

# ----------------------------
# PORTFOLIO EXPOSURE CONTROL
# ----------------------------

portfolio_data = portfolio_ws.get_all_records()

if not portfolio_data:

    print(
        "WARNING: No holdings found in Portfolio sheet."
    )

    print(
        "Portfolio analytics disabled."
    )
    
print("===== PORTFOLIO DEBUG =====")
print(portfolio_ws.get_all_values()[:10])
print("===========================")

open_positions_data = [
    row for row in portfolio_data
    if row.get("Ticker")
]

open_positions = len(open_positions_data)

open_tickers = {
    str(row.get("Ticker")).strip().upper()
    for row in portfolio_data
    if row.get("Ticker") and str(row.get("Quantity", "1")) != "0"
}

current_portfolio_size = open_positions

# Dynamic portfolio sizing
MAX_OPEN_POSITIONS = min(
    30,
    max(
        15,
        round(current_portfolio_size * 1.10)
    )
)

available_slots = max(
    0,
    MAX_OPEN_POSITIONS - open_positions
)

# ----------------------------
# PORTFOLIO RISK TRACKING (NEW)
# ----------------------------

current_portfolio_risk = 0.0

for row in open_positions_data:
    try:
        position_risk = float(row.get("Position Risk") or 0)
        current_portfolio_risk += position_risk

    except Exception:
        log_error(f"Bad portfolio risk row: {row}")
        
print("Current Portfolio Size:", current_portfolio_size)
print("Max Portfolio Size:", MAX_OPEN_POSITIONS)
print("Open Positions:", open_positions)
print("Available Slots:", available_slots)

print("Open Tickers:", open_tickers)

print("========== WORKSHEET CHECK ==========")

print("Spreadsheet URL:", sheet.url)

print("Scanner:", scanner_ws.title, "ID:", scanner_ws.id)

print("Watchlist:", watchlist_ws.title, "ID:", watchlist_ws.id)

print("FailedLogs:", failed_ws.title, "ID:", failed_ws.id)

print("===== PORTFOLIO RAW =====")

for row in portfolio_data:
    if row.get("Ticker") in [
        "OLAELEC.NS",
        "OLECTRA.NS"
    ]:
        print(row)
        
print("=====================================")

failed_logs = []

print("Connected")

# ----------------------------
# LOAD UNIVERSE
# ----------------------------
universe = load_universe()

# ----------------------------
# SORT BY TICKER
# ----------------------------

universe = sorted(
    universe,
    key=lambda x: x["Ticker"]
)

# ----------------------------
# FAST LOOKUP TABLE
# ----------------------------

sector_lookup = {
    row["Ticker"]: row["Sector"]
    for row in universe
}

# ----------------------------
# TICKER LIST FOR YFINANCE
# ----------------------------

stocks = [
    row["Ticker"]
    for row in universe
]

print("Universe Loaded:", len(universe))
print("Stocks:", len(stocks))
    
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
# PORTFOLIO ENRICHMENT
# ----------------------------

try:
    enriched_portfolio = enrich_portfolio(
        portfolio_data
    )
    
    print(
        "Portfolio Holdings:",
        len(enriched_portfolio)
    )

    total_portfolio_value = 0

    for row in enriched_portfolio:
    
        try:
            total_portfolio_value += float(
                row.get("Current Value", 0)
            )
    
        except:
            pass

        
    print(
        "Portfolio Value:",
        total_portfolio_value
    )
    
    # ---------------------------------
    # DYNAMIC CAPITAL
    # ---------------------------------
    
    if total_portfolio_value > 0:
        capital = total_portfolio_value
    
    print("Capital For Position Sizing:", capital)

    print(
        "Risk Capital:",
        capital
    )

    # ----------------------------
    # DYNAMIC CAPITAL BASE
    # ----------------------------
    
    capital = max(
        total_portfolio_value,
        100000
    )
    
    print("Capital Base:", capital)
    print("Risk Per Trade:", capital * risk_per_trade)
    print("Max Portfolio Risk:", capital * max_capital_risk)

    for row in enriched_portfolio:

        try:
    
            market_value = float(
                row.get("Current Value", 0)
            )
    
            if total_portfolio_value > 0:
    
                weight = (
                    market_value
                    / total_portfolio_value
                ) * 100
    
            else:
                weight = 0
    
            row["Portfolio Weight %"] = round(
                weight,
                2
            )
    
        except:
    
            row["Portfolio Weight %"] = 0
    
    # ----------------------------
    # WRITE PORTFOLIO ALWAYS
    # ----------------------------
    
    portfolio_headers = [
        "Ticker",
        "Buy Price",
        "Quantity",
        "LTP",
        "Invested",
        "Current Value",
        "P/L ₹",
        "P/L %",
        "ATR Risk",
        "Position Risk",
        "Stop Loss",
        "Target",
        "Risk Reward",
        "RSI",
        "Trend",
        "Score",
        "Health Score",
        "Health Status",
        "Portfolio Weight %",
        "Sector"
    ]

    print("===== PORTFOLIO SAMPLE =====")
    print(enriched_portfolio[0])
    print("============================")

    portfolio_sheet_data = [portfolio_headers]
    
    for row in enriched_portfolio:
        portfolio_sheet_data.append(
            [row.get(col, "") for col in portfolio_headers]
        )

    print("===== PORTFOLIO SHEET SAMPLE =====")

    for r in portfolio_sheet_data[:3]:
        print(r)
    
    print("==================================")

    try:
        portfolio_analytics_ws = sheet.worksheet(
            "Portfolio Analytics"
        )

    except:
        portfolio_analytics_ws = sheet.add_worksheet(
            title="Portfolio Analytics",
            rows="2000",
            cols="50"
        )
    try:
        portfolio_dashboard_ws = sheet.worksheet(
            "Portfolio Dashboard"
        )
    
    except:
        portfolio_dashboard_ws = sheet.add_worksheet(
            title="Portfolio Dashboard",
            rows="500",
            cols="20"
        )
    
    # Update Portfolio tab

    safe_update(
        portfolio_ws,
        portfolio_sheet_data
    )

    # Update Portfolio Analytics tab

    safe_update(
        portfolio_analytics_ws,
        portfolio_sheet_data
    )
    
    print(
        f"Portfolio Updated: {len(enriched_portfolio)} holdings"
    )
    
except Exception as e:
    print("Portfolio Enrichment Failed:", e)
    raise
    
# ----------------------------
# PORTFOLIO DASHBOARD
# ----------------------------

dashboard = generate_portfolio_dashboard(
    enriched_portfolio
)

dashboard_data = [

    ["Metric", "Value"],
    
    ["Portfolio Value", dashboard["Portfolio Value"]],
    
    ["Average Health", dashboard["Average Health"]],
    
    ["Total Portfolio Risk", dashboard["Total Risk"]],
    
    ["Total Holdings", dashboard["Total Holdings"]],
    
    [],
    
    ["Top Winners"],
    
    ["Ticker", "P/L %"]
    
]

for row in dashboard["Top Winners"]:

    dashboard_data.append([
        row["Ticker"],
        row["P/L %"]
    ])

dashboard_data.append([])

dashboard_data.append(["Top Losers"])

dashboard_data.append([
    "Ticker",
    "P/L %"
])

for row in dashboard["Top Losers"]:

    dashboard_data.append([
        row["Ticker"],
        row["P/L %"]
    ])

dashboard_data.append([])

dashboard_data.append(["Highest Risk Positions"])

dashboard_data.append([
    "Ticker",
    "Position Risk"
])

for row in dashboard["Top Risks"]:

    dashboard_data.append([
        row["Ticker"],
        row["Position Risk"]
    ])

dashboard_data.append([])

dashboard_data.append(["Sector Allocation"])

dashboard_data.append([
    "Sector",
    "Weight %"
])

for row in dashboard["Sector Weights"]:

    dashboard_data.append([

        row["Sector"],

        row["Weight"]

    ])

dashboard_data.append([])

dashboard_data.append([

    "Largest Sector",

    dashboard["Largest Sector"]

])

dashboard_data.append([

    "Diversification",

    dashboard["Diversification"]

])

dashboard_data.append([])

dashboard_data.append([

    "Portfolio Risk Score",

    dashboard["Portfolio Risk Score"]

])

dashboard_data.append([

    "Portfolio Risk Gauge",

    dashboard["Portfolio Risk Gauge"]

])

safe_update(
    portfolio_dashboard_ws,
    dashboard_data
)

print("Portfolio Dashboard Updated")

# ----------------------------
# PORTFOLIO ROTATION
# ----------------------------

try:
    rotation_ws = sheet.worksheet(
        "Portfolio Rotation"
    )

except:
    rotation_ws = sheet.add_worksheet(
        title="Portfolio Rotation",
        rows="2000",
        cols="20"
    )
    
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
            tickers=tickers,
            period="6mo",
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False
        )

        yield batch, data

results_map = []

for batch, data in batch_download(stocks, chunk_size=20):

    # ----------------------------
    # EMPTY DOWNLOAD SAFETY
    # ----------------------------

    if data is None or data.empty:

        print("Batch download returned no data.")

        for ticker in batch:

            results_map.append(
                (
                    ticker,
                    sector_lookup.get(ticker, "UNKNOWN"),
                    None,
                    "DOWNLOAD_EMPTY"
                )
            )

        continue
        
    for ticker in batch:

        sector = sector_lookup.get(ticker, "UNKNOWN")
        
        try:
            if ticker not in data.columns.get_level_values(0):
                results_map.append(
                    (
                        ticker,
                        sector,
                        None,
                        "NO_DATA"
                    )
                )
                continue

            df = data[ticker].dropna()

            if df.empty:
            
                results_map.append(
                    (
                        ticker,
                        sector,
                        None,
                        "EMPTY_DF"
                    )
                )
            
                continue
            
            results_map.append(
                (
                    ticker,
                    sector,
                    df,
                    None
                )
            )

        except Exception as e:
            
            results_map.append(
                (
                    ticker,
                    sector,
                    None,
                    str(e)
                )
            )
            
results, failed_logs = run_scanner(
    results_map,
    open_tickers,
    regime,
    nifty_return,
    capital,
    risk_per_trade,
    DEBUG_LOGS,
    failed_logs,
    safe_generate_signal,
    log_scan,
    log_signal
)

# ----------------------------
# FINAL RESULTS SORTING
# ----------------------------

results_sorted = sorted(
    results,
    key=lambda x: x.get("edge_score", 0),
    reverse=True
)

results_sorted = [
    r for r in results_sorted
    if isinstance(r, dict)
    and "ticker" in r
    and "edge_score" in r
]

# ----------------------------
# BUY + WATCH CANDIDATES
# ----------------------------

buy_candidates = [
    r for r in results_sorted
    if (
        r["trade_action"] in ["BUY", "STRONG_BUY"]
        and r["ticker"].upper() not in open_tickers
        and r["edge_rating"] >= 7
        and r["score"] >= 75
        and r["risk_reward"] >= 1.5
        and r["rs_score"] >= 15
    )
]

watch_candidates = [
    r for r in results_sorted
    if r["trade_action"] == "WATCH"
    and r["ticker"].upper() not in open_tickers
]

# ----------------------------
# CAPITAL-AWARE EXECUTION ENGINE
# ----------------------------

executed_buys = []
allocated_risk = 0

max_total_risk = capital * max_capital_risk

sorted_buys = sorted(
    buy_candidates,
    key=lambda x: x["edge_score"],
    reverse=True
)

for r in sorted_buys:

    ticker = r["ticker"]
    
    # ----------------------------
    # STATE CHECK (NEW LOGIC)
    # ----------------------------
    if ticker in state:
        entry = state.get(ticker, {})
    
        if entry and not is_state_expired(entry.get("timestamp", "")):
            continue
    
    trade_risk = r["position_size"] * r["atr_risk"]
    if (allocated_risk + trade_risk + current_portfolio_risk) > max_total_risk:
        continue

    executed_buys.append(r)
    allocated_risk += trade_risk
    
    if len(executed_buys) >= available_slots:
        break
        
executed_watches = watch_candidates[:MAX_WATCH]

# ----------------------------
# PORTFOLIO UPDATE
# ----------------------------

print(
    "Portfolio sheet left unchanged "
    f"({len(portfolio_data)} holdings loaded)"
)

# ----------------------------
# EXECUTION LAYER (CONTROLLED)
# ----------------------------

for r in executed_buys:

    msg = f"📌 BUY: {r['ticker']}\nEdge: {r['edge_rating']}\nScore: {r['score']}"
    print(msg)
    
try:
    alerts_ws = sheet.worksheet("Alerts")
except:
    alerts_ws = sheet.add_worksheet(
        title="Alerts",
        rows="5000",
        cols="10"
    )

for r in executed_buys:

    alerts_ws.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "BUY",
        r["ticker"],
        r["edge_rating"],
        r["score"]
    ])

    msg = (
        f"📌 BUY: {r['ticker']}\n"
        f"Edge: {r['edge_rating']}\n"
        f"Score: {r['score']}\n"
        f"RR: {r['risk_reward']}"
    )

    send_telegram(msg)
    
    state[r["ticker"]] = {
        "status": "RECENT_BUY",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    save_state(state)
    
    log_trade(
        action="BUY",
        ticker=r["ticker"],
        cmp_price=r["cmp"],
        edge_score=r["edge_score"],
        edge_rating=r["edge_rating"],
        position_size=r["position_size"],
        stop_loss=r["stop_loss"],
        target=r["target"],
        risk_reward=r["risk_reward"],
        rs_score=r["rs_score"],
        signal=r["signal"]
    )
    
# ----------------------------
# PORTFOLIO SLOT CONTROL
# ----------------------------

print(f"Available Slots: {available_slots}")

print(f"Max Portfolio Risk Allowed: {max_total_risk}")
print(f"Allocated Risk: {allocated_risk}")
print(f"Remaining Risk Capacity: {max_total_risk - allocated_risk}")
print(f"Executed Buy Count: {len(executed_buys)}")

# ----------------------------
# UPDATE WATCHLIST (1 CALL ONLY)
# ----------------------------

watchlist_data = [["Ticker", "CMP", "RSI", "EMA20", "EMA50", "Trend", "Score", "Edge Rating",  "Trade Action", "RS Score", "Volume Spike"]]

for r in executed_buys + executed_watches:
    
    watchlist_data.append([
        r["ticker"],
        r["cmp"],
        r["rsi"],
        r["ema20"],
        r["ema50"],
        r["trend"],
        r["score"],
        r["edge_rating"],
        r["trade_action"],
        r["rs_score"],
        r["volume_spike"]
    ])
    
print("Sample result type:", type(results_sorted[0]) if results_sorted else None)

print("Final Results Count:", len(results_sorted))

# ----------------------------
# BUY COUNT SUMMARY
# ----------------------------

buy_count = len(executed_buys)

watch_count = len(executed_watches)

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

if breadth_score >= 40:
    market_health = "STRONG INTERNALS"

elif breadth_score >= 25:
    market_health = "BULLISH INTERNALS"

elif breadth_score >= 15:
    market_health = "IMPROVING INTERNALS"

elif breadth_score >= 5:
    market_health = "WEAK INTERNALS"

else:
    market_health = "VERY WEAK INTERNALS"

# ----------------------------
# MARKET INTERNAL STRENGTH
# ----------------------------

if regime == "BEAR" and breadth_score >= 25:
    internal_strength = "POSITIVE_DIVERGENCE"

elif regime == "BULL" and breadth_score < 10:
    internal_strength = "NEGATIVE_DIVERGENCE"

elif regime == "BULL" and breadth_score >= 25:
    internal_strength = "CONFIRMED_BULL"

elif regime == "BEAR" and breadth_score < 10:
    internal_strength = "CONFIRMED_BEAR"

else:
    internal_strength = "NEUTRAL"

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
    "Market Health",
    "Internal Strength"
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
    str(market_health),
    str(internal_strength)
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
    "Sector",
    "CMP",
    "RSI",
    "EMA20",
    "EMA50",
    "Trend",
    "Score",
    "Edge Score",
    "Edge Rating",
    "Trade Action",
    "Position Size",
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
scanner_ws.clear()
scanner_data = [headers]

for r in results_sorted:
    scanner_data.append([
        r["ticker"],
        r["sector"],
        r["cmp"],
        r["rsi"],
        r["ema20"],
        r["ema50"],
        r["trend"],
        r["score"],
        r["edge_score"],
        r["edge_rating"],
        r["trade_action"],
        r["position_size"],        
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
    
    watchlist_ws.clear()
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
    
    failed_data = [["Ticker", "Error Type", "Reason"]]

    if failed_logs:
        failed_data.extend(failed_logs)
    
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
        and r["score"] >= 75
    ):
        top_picks.append([
            r["ticker"],
            r["sector"],
            r["cmp"],
            r["rsi"],
            r["ema20"],
            r["ema50"],
            r["trend"],
            r["score"],
            r["edge_score"],
            r["edge_rating"],
            r["trade_action"],
            r["position_size"],
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

# ----------------------------
# EXCLUDE EXISTING HOLDINGS
# ----------------------------

owned_tickers = {
    str(x.get("Ticker", "")).strip().upper()
    for x in enriched_portfolio
}

rotation_candidates = []

for r in results_sorted:

    ticker = str(r["ticker"]).strip().upper()

    if ticker in owned_tickers:
        continue

    rotation_candidates.append({

        "Ticker": r["ticker"],

        "Sector": r["sector"],

        "Score": float(r["score"]),

        "Edge Rating": float(r["edge_rating"]),

        "RS Score": float(r["rs_score"]),

        "Trend": r["trend"],

        "RSI": float(r["rsi"]),

        "Risk Reward": float(r["risk_reward"]),

        "Volume Spike": float(r["volume_spike"]),

        "Breakout": r["breakout"]

    })

rotation_rows = generate_rotation_plan(
    enriched_portfolio,
    rotation_candidates
)

rotation_data = [[
    "Ticker",
    "Health Score",
    "Health Status",
    "Current Value",
    "Portfolio Weight %",
    "P/L %",
    "Position Risk",
    "Action",
    "Priority Score",
    "Priority",
    "Replacement",
    "Replacement Score",
    "Replacement Edge",
    "Switch Score",
    "Capital Freed",
    "Comments"
]]

rotation_data.extend(rotation_rows)

safe_update(
    rotation_ws,
    rotation_data
)

print(
    f"Portfolio Rotation Updated: "
    f"{len(rotation_rows)} rows"
)

save_state(state)
    
print("Completed Successfully")
