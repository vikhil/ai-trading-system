from datetime import datetime
import yfinance as yf
import gspread
import os
import json
import time

from oauth2client.service_account import ServiceAccountCredentials

from data_loader import load_universe

from engine.nse_master import load_all_nse_universe

def load_existing_stock_master(sheet):

    ws = sheet.worksheet("Stock_Master")

    data = ws.get_all_records()

    existing = {}

    for row in data:

        ticker = str(row.get("Ticker", "")).strip()

        if ticker:

            existing[ticker] = row

    print(f"Existing Stock Master : {len(existing)}")

    return existing
    
universe = load_all_nse_universe()

print("Universe Size:", len(universe))

cpse_found = any(
    row["Ticker"] == "CPSEETF.NS"
    for row in universe
)

print("CPSEETF Found:", cpse_found)

# -----------------------------------
# ADD PORTFOLIO HOLDINGS TO UNIVERSE
# -----------------------------------

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_dict,
    scope
)

client = gspread.authorize(creds)

sheet = client.open_by_key(
    "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"
)

print("Connecting to Google Sheet...")
print("Connected")

existing_master = load_existing_stock_master(sheet)

portfolio_ws = sheet.worksheet("Portfolio")

portfolio_data = portfolio_ws.get_all_records()

print("Portfolio Rows:", len(portfolio_data))

for row in portfolio_data[:10]:
    print(row)
    
portfolio_tickers = set()

for row in portfolio_data:

    ticker = str(row.get("Ticker", "")).strip()

    if ticker:

        portfolio_tickers.add(ticker)

print("Portfolio Tickers Found:")
print(sorted(portfolio_tickers))

print("Portfolio Tickers Count:", len(portfolio_tickers))

existing_tickers = set(
    row["Ticker"]
    for row in universe
)

for ticker in portfolio_tickers:

    if ticker not in existing_tickers:

        universe.append({
            "Ticker": ticker
        })

print(
    f"Final Universe Size = {len(universe)}"
)

missing = [
    t for t in portfolio_tickers
    if t not in existing_tickers
]

print("Portfolio-only tickers:")
print(missing)

stock_master_rows = [
    [
        "Ticker",
        "Company Name",
        "Sector",
        "Industry",
        "Market Cap",
        "Market Cap Category",
        "Index",
        "First Seen",
        "Last Updated",
        "Data Source"
    ]
]

today = datetime.now().strftime("%Y-%m-%d")

for row in universe:

    ticker = row["Ticker"]

    existing = existing_master.get(ticker)

    if existing:

        market_cap = existing.get("Market Cap", 0)
        sector = existing.get("Sector", "UNKNOWN")
        company_name = existing.get("Company Name", "")

        if (
            market_cap not in [0, "", None]
            and sector != "UNKNOWN"
            and company_name != ""
        ):

            stock_master_rows.append([
                ticker,
                company_name,
                sector,
                existing.get("Industry", "UNKNOWN"),
                market_cap,
                existing.get("Market Cap Category", "UNKNOWN"),
                existing.get("Index", "OTHER"),
                existing.get("First Seen", today),
                today,
                "CACHE"
            ])

            continue

    if ticker == "CPSEETF.NS":
        print("FOUND CPSEETF IN UNIVERSE")
        
    try:

        ticker_obj = yf.Ticker(ticker)

        info = {}
        
        try:
            info = ticker_obj.info
        except:
            pass
        
        # -------------------------
        # Company Name
        # -------------------------
        
        company_name = (
            info.get("longName")
            or info.get("shortName")
            or row.get("Company Name")
            or ticker.replace(".NS", "")
        )
        
        # -------------------------
        # Sector / Industry
        # -------------------------
        
        sector = info.get("sector") or row.get("Sector", "UNKNOWN")
        
        industry = info.get("industry") or "UNKNOWN"
        
        # -------------------------
        # Market Cap
        # -------------------------
        
        market_cap = info.get("marketCap")

        if isinstance(market_cap, str):
        
            market_cap = market_cap.replace(",", "")
        
        try:
        
            market_cap = float(market_cap)
        
        except:
        
            market_cap = 0
        
        # Try fast_info
        
        if not market_cap:
        
            try:
        
                market_cap = ticker_obj.fast_info.get("market_cap")
        
            except:
        
                pass
        
        # Last attempt:
        # Price × Shares Outstanding
        
        if not market_cap:
        
            try:
        
                shares = info.get("sharesOutstanding")
        
                price = ticker_obj.history(period="1d")["Close"].iloc[-1]
        
                if shares:
        
                    market_cap = shares * price
        
            except:
        
                pass
        
        market_cap = market_cap or 0

        index_name = "NIFTY500"

        if market_cap:
            if market_cap >= 200000000000:
                market_cap_category = "LARGE"
            elif market_cap >= 50000000000:
                market_cap_category = "MID"
            else:
                market_cap_category = "SMALL"
        else:
            market_cap_category = "UNKNOWN"
                
        stock_master_rows.append([
            ticker,
            company_name,
            sector,
            industry,
            market_cap,
            market_cap_category,
            index_name,
            existing.get("First Seen", today),
            today,
            "YFINANCE"
        ])

        time.sleep(0.15)
        
    except Exception as e:

        print(f"FAILED -> {ticker} -> {e}")
    
        stock_master_rows.append([
            ticker,          # Ticker
            "",              # Company Name
            "UNKNOWN",       # Sector
            "UNKNOWN",       # Industry
            "",              # Market Cap
            "UNKNOWN",       # Market Cap Category
            "OTHER",         # Index
            "",              # First Seen
            "",              # Last Updated
            "FAILED"         # Data Source
        ])



stock_master_ws = sheet.worksheet(
    "Stock_Master"
)

print("Clearing Stock_Master...")

stock_master_ws.batch_clear(["A:J"])

print("Writing rows:", len(stock_master_rows))

stock_master_ws.update(
    range_name="A1",
    values=stock_master_rows
)

print("Write Complete")

cache_count = sum(
    1
    for row in stock_master_rows[1:]
    if row[-1] == "CACHE"
)

yf_count = sum(
    1
    for row in stock_master_rows[1:]
    if row[-1] == "YFINANCE"
)

print("Cache Used :", cache_count)
print("Yahoo Used :", yf_count)

print(
    f"Stock_Master Updated: {len(stock_master_rows)-1}"
)

print("================================")
print("Stock Master Build Complete")
print("Rows:", len(stock_master_rows)-1)
print("================================")
