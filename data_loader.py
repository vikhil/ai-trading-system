import pandas as pd
import requests
from io import StringIO
import yfinance as yf

def fetch_nse_index_stocks(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"NSE fetch failed: {response.status_code}")

    df = pd.read_csv(StringIO(response.text))
    return [s + ".NS" for s in df["Symbol"].tolist()]

def load_universe():
    nifty50_url = "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"
    niftynext50_url = "https://archives.nseindia.com/content/indices/ind_niftynext50list.csv"

    stocks = list(set(
        fetch_nse_index_stocks(nifty50_url) +
        fetch_nse_index_stocks(niftynext50_url)
    ))

    # CLEAN STOCKS
    stocks = [s.strip().upper() for s in stocks]

    # REMOVE INVALID / DUMMY SYMBOLS
    stocks = [
        s for s in stocks
        if s.endswith(".NS")
        and "DUMMY" not in s
    ]

    # REMOVE DUPLICATES WHILE KEEPING ORDER
    stocks = list(dict.fromkeys(stocks))

    return stocks
    
def fetch_stock_data(ticker):
    df = yf.download(
        ticker,
        period="6mo",
        interval="1d",
        auto_adjust=True,
        progress=False
    )

    return df
