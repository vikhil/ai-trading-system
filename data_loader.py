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
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        headers=headers
    )

    if response.status_code != 200:
        raise Exception(
            f"NSE fetch failed: {response.status_code}"
        )

    df = pd.read_csv(StringIO(response.text))

    stocks = []

    for _, row in df.iterrows():

        stocks.append({

            "Ticker": row["Symbol"].strip().upper() + ".NS",

            "Sector": row.get(
                "Industry",
                "UNKNOWN"
            )

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
