import os
import pandas as pd

CACHE_FOLDER = "Cache"

# Ensure cache folder exists
os.makedirs(CACHE_FOLDER, exist_ok=True)


def cache_path(ticker):
    """
    Convert ticker to a valid cache filename.
    Example:
        BEL.NS -> Cache/BEL_NS.csv
    """
    filename = ticker.replace(".", "_") + ".csv"
    return os.path.join(CACHE_FOLDER, filename)


def save_cache(ticker, df):
    """
    Save downloaded OHLC data to cache.
    """
    try:
        if df is not None and not df.empty:
            df.to_csv(cache_path(ticker))
    except Exception as e:
        print(f"{ticker}: Cache Save Failed -> {e}")


def load_cache(ticker):
    """
    Load cached OHLC data if available.
    """
    try:
        file = cache_path(ticker)

        if os.path.exists(file):
            df = pd.read_csv(
                file,
                index_col=0,
                parse_dates=True
            )

            if not df.empty:
                print(f"{ticker}: Loaded from Cache")
                return df

    except Exception as e:
        print(f"{ticker}: Cache Load Failed -> {e}")

    return None
