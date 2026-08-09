from datetime import datetime
import yfinance as yf
import gspread
import os
import json
import time

from oauth2client.service_account import ServiceAccountCredentials

#from data_loader import load_universe

from engine.nse_master import (
    load_all_nse_universe,
    create_nse_session,
    get_nse_quote_metadata
)
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
            "Ticker": ticker,
            "Sector": "UNKNOWN",
            "Asset Type": "EQUITY"
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

# --------------------------------
# NSE FALLBACK SESSION
# --------------------------------

nse_session = create_nse_session()

print("NSE fallback session created")

nse_fallback_count = 0
nse_sector_fallback_count = 0
nse_industry_fallback_count = 0
nse_market_cap_fallback_count = 0

for row in universe:
    
    ticker = row["Ticker"]

    asset_type = str(
        row.get("Asset Type", "EQUITY")
    ).strip().upper()
    
    existing = existing_master.get(ticker)

    if existing:

        company_name = str(existing.get("Company Name", "")).strip()

        sector = str(existing.get("Sector", "UNKNOWN")).strip()

        industry = str(existing.get("Industry", "UNKNOWN")).strip()

        market_cap = existing.get("Market Cap", 0)

        market_cap_category = str(
            existing.get("Market Cap Category", "UNKNOWN")
        ).strip()

        # Convert market cap safely
        try:

            if isinstance(market_cap, str):

                market_cap = (
                    market_cap
                    .replace("₹", "")
                    .replace(",", "")
                    .strip()
                )

            market_cap = float(market_cap)

        except:

            market_cap = 0

        # Use cache ONLY when everything is valid
        cache_valid = (
            company_name != ""
            and sector != "UNKNOWN"
            and (
                (
                    asset_type == "EQUITY"
                    and industry != "UNKNOWN"
                    and market_cap > 0
                    and market_cap_category != "UNKNOWN"
                )
                or
                (
                    asset_type in ("ETF", "REIT", "INVIT")
                    and market_cap_category == asset_type
                )
            )
        )
        
        if cache_valid:    
            
            stock_master_rows.append([
                ticker,
                company_name,
                sector,
                industry,
                market_cap,
                market_cap_category,
                existing.get("Index", "OTHER"),
                existing.get("First Seen", today),
                today,
                "CACHE"
            ])

            continue

    if ticker == "CPSEETF.NS":
        print("FOUND CPSEETF IN UNIVERSE")

    # --------------------------------
    # NON-EQUITY ASSET HANDLING
    # --------------------------------

    if asset_type in ("ETF", "REIT", "INVIT"):

        company_name = (
            str(row.get("Company Name", "")).strip()
            or ticker.replace(".NS", "")
        )

        sector = asset_type
        industry = asset_type
        market_cap = 0
        market_cap_category = asset_type
        index_name = "OTHER"

        stock_master_rows.append([
            ticker,
            company_name,
            sector,
            industry,
            market_cap,
            market_cap_category,
            index_name,
            existing.get("First Seen", today)
                if existing else today,
            today,
            "NSE_MASTER"
        ])

        continue

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
        
        sector = (
            info.get("sector")
            or ""
        )
        
        industry = (
            info.get("industry")
            or ""
        )
        
        basic_industry = ""
        
        # --------------------------------
        # NSE FALLBACK FOR SECTOR / INDUSTRY
        # --------------------------------
        
        nse_metadata = {}
        
        if (
            not sector
            or not industry
        ):
        
            nse_metadata = get_nse_quote_metadata(
                nse_session,
                ticker
            )
        
            if nse_metadata:
        
                nse_fallback_count += 1
        
                if not sector:
        
                    sector = (
                        nse_metadata.get("Sector")
                        or ""
                    )
        
                    if sector:
        
                        nse_sector_fallback_count += 1
        
                if not industry:
        
                    industry = (
                        nse_metadata.get("Industry")
                        or ""
                    )
        
                    if industry:
        
                        nse_industry_fallback_count += 1
        
                basic_industry = (
                    nse_metadata.get("Basic Industry")
                    or ""
                )
        
        sector = sector or "UNKNOWN"
        
        industry = industry or "UNKNOWN"
        
        # -------------------------
        # Market Cap
        # -------------------------
        
        market_cap = info.get(
            "marketCap"
        )
        
        if isinstance(
            market_cap,
            str
        ):
        
            market_cap = (
                market_cap
                .replace(",", "")
                .replace("₹", "")
                .strip()
            )
        
        try:
        
            market_cap = float(
                market_cap
            )
        
        except:
        
            market_cap = 0
        
        
        # --------------------------------
        # FAST INFO FALLBACK
        # --------------------------------
        
        if not market_cap:
        
            try:
        
                market_cap = (
                    ticker_obj
                    .fast_info
                    .get("market_cap")
                )
        
                market_cap = float(
                    market_cap or 0
                )
        
            except:
        
                market_cap = 0
        
        
        # --------------------------------
        # SHARES OUTSTANDING FALLBACK
        # --------------------------------
        
        if not market_cap:
        
            try:
        
                shares_outstanding = (
                    info.get(
                        "sharesOutstanding"
                    )
                    or
                    info.get(
                        "impliedSharesOutstanding"
                    )
                )
        
                if not shares_outstanding:
        
                    try:
        
                        shares_history = (
                            ticker_obj
                            .get_shares_full()
                        )
        
                        if (
                            shares_history
                            is not None
                        ):
        
                            shares_history = (
                                shares_history
                                .dropna()
                            )
        
                            if not shares_history.empty:
        
                                shares_outstanding = (
                                    float(
                                        shares_history
                                        .iloc[-1]
                                    )
                                )
        
                    except Exception as e:
        
                        print(
                            f"SHARES HISTORY FAILED -> "
                            f"{ticker} -> {e}"
                        )
        
                if shares_outstanding:
        
                    price = None
        
                    try:
        
                        price = (
                            ticker_obj
                            .fast_info
                            .get("last_price")
                        )
        
                    except:
        
                        pass
        
                    if not price:
        
                        try:
        
                            history = (
                                ticker_obj
                                .history(
                                    period="5d"
                                )
                            )
        
                            if not history.empty:
        
                                price = float(
                                    history[
                                        "Close"
                                    ]
                                    .dropna()
                                    .iloc[-1]
                                )
        
                        except:
        
                            pass
        
                    if (
                        shares_outstanding
                        and price
                        and price > 0
                    ):
        
                        market_cap = (
                            float(
                                shares_outstanding
                            )
                            *
                            float(price)
                        )
        
                        if market_cap > 0:
        
                            print(
                                f"SHARES MARKET CAP FALLBACK -> "
                                f"{ticker} -> "
                                f"{market_cap:,.0f}"
                            )
        
            except Exception as e:
        
                print(
                    f"SHARES MARKET CAP FAILED -> "
                    f"{ticker} -> {e}"
                )
        
        
        # --------------------------------
        # NSE FALLBACK
        # --------------------------------
        
        if not market_cap:
        
            if not nse_metadata:
        
                nse_metadata = (
                    get_nse_quote_metadata(
                        nse_session,
                        ticker
                    )
                )
        
                if nse_metadata:
        
                    nse_fallback_count += 1
        
            if nse_metadata:
        
                nse_market_cap = (
                    nse_metadata.get(
                        "Market Cap",
                        0
                    )
                )
        
                try:
        
                    nse_market_cap = float(
                        nse_market_cap or 0
                    )
        
                except:
        
                    nse_market_cap = 0
        
                if nse_market_cap > 0:
        
                    market_cap = (
                        nse_market_cap
                    )
        
                    nse_market_cap_fallback_count += 1
        
                    print(
                        f"NSE MARKET CAP FALLBACK -> "
                        f"{ticker} -> "
                        f"{market_cap:,.0f}"
                    )
        
        
        market_cap = market_cap or 0

        index_name = "OTHER"

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

# --------------------------------
# VALIDATION REPORT
# --------------------------------

data_rows = stock_master_rows[1:]

unknown_sector_count = sum(
    1
    for row in data_rows
    if str(row[2]).strip().upper()
    in ("", "UNKNOWN")
)

unknown_industry_count = sum(
    1
    for row in data_rows
    if str(row[3]).strip().upper()
    in ("", "UNKNOWN")
)

# --------------------------------
# MARKET CAP VALIDATION
# EQUITIES ONLY
# --------------------------------

equity_rows = [
    row
    for row in data_rows
    if str(row[2]).strip().upper()
    not in ("ETF", "REIT", "INVIT")
]

zero_market_cap_count = sum(
    1
    for row in equity_rows
    if not row[4]
    or float(row[4] or 0) <= 0
)

# --------------------------------
# UNRESOLVED EQUITIES ONLY
# --------------------------------

unresolved_count = sum(
    1
    for row in equity_rows
    if (
        str(row[2]).strip().upper()
        in ("", "UNKNOWN")
        or
        str(row[3]).strip().upper()
        in ("", "UNKNOWN")
        or
        not row[4]
        or
        float(row[4] or 0) <= 0
    )
)

print("")
print("================================")
print("STOCK MASTER VALIDATION")
print("================================")

print(
    "Total Rows:",
    len(data_rows)
)

print(
    "Equity Rows:",
    len(equity_rows)
)

print(
    "Unknown Sector:",
    unknown_sector_count
)

print(
    "Unknown Industry:",
    unknown_industry_count
)

print(
    "Equity Zero Market Cap:",
    zero_market_cap_count
)

print(
    "Unresolved Equities:",
    unresolved_count
)

print(
    "NSE Fallback Used:",
    nse_fallback_count
)

print(
    "NSE Sector Fallback:",
    nse_sector_fallback_count
)

print(
    "NSE Industry Fallback:",
    nse_industry_fallback_count
)

print(
    "NSE Market Cap Fallback:",
    nse_market_cap_fallback_count
)

print("================================")
print("Cache Used :", cache_count)
print("Yahoo Used :", yf_count)

print(
    f"Stock_Master Updated: {len(stock_master_rows)-1}"
)

print("================================")
print("Stock Master Build Complete")
print("Rows:", len(stock_master_rows)-1)
print("================================")
