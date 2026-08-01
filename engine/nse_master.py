import requests
import pandas as pd

from io import StringIO

def create_nse_session():

    session = requests.Session()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/137.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/"
    }

    session.headers.update(headers)

    session.get(
        "https://www.nseindia.com",
        timeout=30
    )

    return session

SECURITY_MASTER_URL = (
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
)

def download_security_master():

    session = create_nse_session()

    response = session.get(
        SECURITY_MASTER_URL,
        timeout=30
    )

    response.raise_for_status()

    df = pd.read_csv(
        StringIO(response.text)
    )

    print(
        "Downloaded Security Master:",
        len(df)
    )

    return df

def load_all_nse_universe():

    df = download_security_master()

    universe = []

    for _, row in df.iterrows():

        symbol = str(
            row["SYMBOL"]
        ).strip().upper()

        series = str(
            row["SERIES"]
        ).strip().upper()

        if series != "EQ":
            continue

        universe.append({

            "Ticker": symbol + ".NS",

            "Sector": "UNKNOWN"

        })

    print(
        "Universe Created:",
        len(universe)
    )

    return universe

if __name__ == "__main__":

    universe = load_all_nse_universe()

    print(universe[:10])
