import pandas as pd
import requests
from io import StringIO
import yfinance as yf

# ==========================
# UNIVERSE CONFIGURATION
# ==========================

UNIVERSE = "NIFTY500"

NIFTY50_URL = (
    "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
)

NIFTYNEXT50_URL = (
    "https://archives.nseindia.com/content/indices/ind_niftynext50list.csv"
)

NIFTY500_URL = (
    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
)

def fetch_nse_index_stocks(url):

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0 Safari/537.36"
        ),
        "Accept": "text/csv,*/*",
        "Referer": "https://www.nseindia.com/",
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        df = pd.read_csv(StringIO(response.text))

    except Exception as e:

        print(f"NSE download failed ({e})")

        print("Loading local fallback_universe.csv")
        
        return load_fallback_universe()

    stocks = []

    for _, row in df.iterrows():

        stocks.append({

            "Ticker": row["Symbol"].strip().upper() + ".NS",

            sector = row.get("Industry")

            if pd.isna(sector):
                sector = "UNKNOWN"
            
            stocks.append({
            
                "Ticker": row["Symbol"].strip().upper() + ".NS",
            
                "Sector": str(sector).strip()
            
            })

        })

    return stocks

def load_fallback_universe():

    fallback = pd.read_csv("fallback_universe.csv")

    stocks = []

    for _, row in fallback.iterrows():

        stocks.append({

            "Ticker": row["Ticker"].strip().upper(),

            "Sector": row["Sector"]

        })

    return stocks
    
def load_universe():

    if UNIVERSE == "NIFTY50":

        universe = fetch_nse_index_stocks(
            NIFTY50_URL
        )

    elif UNIVERSE == "NIFTY100":

        universe = (
            fetch_nse_index_stocks(NIFTY50_URL)
            +
            fetch_nse_index_stocks(NIFTYNEXT50_URL)
        )

    elif UNIVERSE == "NIFTY500":

        universe = fetch_nse_index_stocks(
            NIFTY500_URL
        )

    else:

        raise Exception(
            f"Unknown Universe: {UNIVERSE}"
        )

    cleaned = []
    seen = set()

    for stock in universe:

        ticker = stock["Ticker"].strip().upper()

        if (
            ticker.endswith(".NS")
            and "DUMMY" not in ticker
            and ticker not in seen
        ):

            stock["Ticker"] = ticker

            cleaned.append(stock)

            seen.add(ticker)

    return cleaned
    
def fetch_stock_data(ticker):
    df = yf.download(
        ticker,
        period="6mo",
        interval="1d",
        auto_adjust=True,
        progress=False
    )

    return df
