from datetime import datetime
import yfinance as yf
import gspread
from data_loader import load_universe

universe = load_universe()

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

    try:

        info = yf.Ticker(ticker).info

        company_name = info.get("longName", "")

        sector = info.get("sector") or "UNKNOWN"

        industry = info.get("industry") or "UNKNOWN"

        market_cap = info.get("marketCap") or 0

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
            today,
            today,
            "YFINANCE"
        ])

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

gc = gspread.service_account(
    filename="credentials.json"
)

print("Connecting to Google Sheet...")

sheet = gc.open("AI_Trading_System")

print("Connected")

stock_master_ws = sheet.worksheet(
    "Stock_Master"
)

print("Clearing Stock_Master...")

stock_master_ws.clear()

print("Writing rows:", len(stock_master_rows))

stock_master_ws.update(
    range_name="A1",
    values=stock_master_rows
)

print("Write Complete")

print(
    f"Stock_Master Updated: {len(stock_master_rows)-1}"
)

print("================================")
print("Stock Master Build Complete")
print("Rows:", len(stock_master_rows)-1)
print("================================")
