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
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
)

ETF_MASTER_URL = (
    "https://nsearchives.nseindia.com/content/equities/eq_etfseclist.csv"
)

REIT_MASTER_URL = (
    "https://nsearchives.nseindia.com/content/equities/REITS_L.csv"
)

INVIT_MASTER_URL = (
    "https://nsearchives.nseindia.com/content/equities/INVITS_L.csv"
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

    df = clean_dataframe(df)
    
    print(df.columns.tolist())
    print(df.head())
    
    print(
        "Downloaded Security Master:",
        len(df)
    )

    return df

def download_etf_master():

    session = create_nse_session()

    try:

        response = session.get(
            ETF_MASTER_URL,
            timeout=30
        )

        response.raise_for_status()

        df = pd.read_csv(
            StringIO(response.text)
        )
        
        df = clean_dataframe(df)
        
        print("\nETF Columns")
        print(df.columns.tolist())
        
        print(df.head())
        
        print(
            "ETF Master:",
            len(df)
        )
        
        return df

    except Exception as e:

        print("ETF download failed:", e)

        return pd.DataFrame()

def download_reit_master():

    session = create_nse_session()

    try:

        response = session.get(
            REIT_MASTER_URL,
            timeout=30
        )

        response.raise_for_status()

        df = pd.read_csv(
            StringIO(response.text)
        )

        df = clean_dataframe(df)

        print("\nREIT Columns")
        print(df.columns.tolist())

        print(df.head())

        print(
            "REIT Master:",
            len(df)
        )

        return df

    except Exception as e:

        print("REIT download failed:", e)

        return pd.DataFrame()

def download_invit_master():

    session = create_nse_session()

    try:

        response = session.get(
            INVIT_MASTER_URL,
            timeout=30
        )

        response.raise_for_status()

        df = pd.read_csv(
            StringIO(response.text)
        )

        df = clean_dataframe(df)

        print("\nInvIT Columns")
        print(df.columns.tolist())

        print(df.head())

        print(
            "InvIT Master:",
            len(df)
        )

        return df

    except Exception as e:

        print("InvIT download failed:", e)

        return pd.DataFrame()
        
def clean_dataframe(df):

    df.columns = df.columns.str.strip()

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()

    return df
    
def load_all_nse_universe():

    equity_df = download_security_master()

    etf_df = download_etf_master()
    
    reit_df = download_reit_master()
    
    invit_df = download_invit_master()
    
    universe = []

    for _, row in equity_df.iterrows():
    
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
    
            "Sector": "",
            
            "Asset Type": "EQUITY",
    
            "Company Name": str(
                row.get("NAME OF COMPANY", "")
            ).strip(),
    
            # NSE PAID UP VALUE is the paid-up value
            # per equity share, NOT total paid-up capital.
            "Paid Up Value Per Share": row.get(
                "PAID UP VALUE",
                0
            ),
    
            "Face Value": row.get(
                "FACE VALUE",
                0
            ),
    
            "ISIN": str(
                row.get("ISIN NUMBER", "")
            ).strip()
    
        })
    
    for _, row in etf_df.iterrows():

        symbol = str(
            row.get("Symbol", "")
        ).strip().upper()
    
        if not symbol:
            continue
    
        universe.append({
    
            "Ticker": symbol + ".NS",
    
            "Sector": "ETF",

            "Asset Type": "ETF"
        })

    # -------------------------
    # ADD REITS
    # -------------------------
    
    for _, row in reit_df.iterrows():
    
        symbol = str(
            row.get("SYMBOL", "")
        ).strip().upper()
    
        if (
            not symbol
            or symbol == "NAN"
            or symbol.startswith("NOTE")
        ):
            continue
    
        universe.append({
    
            "Ticker": symbol + ".NS",
    
            "Sector": "REIT",

            "Asset Type": "REIT"
        })

    # -------------------------
    # ADD INVITS
    # -------------------------
    
    for _, row in invit_df.iterrows():
    
        symbol = str(
            row.get("SYMBOL", "")
        ).strip().upper()
    
        if (
            not symbol
            or symbol == "NAN"
            or symbol.startswith("NOTE")
        ):
            continue
    
        universe.append({
    
            "Ticker": symbol + ".NS",
    
            "Sector": "INVIT",

            "Asset Type": "INVIT"
        })
    
    unique = {}

    for row in universe:
    
        unique[row["Ticker"]] = row

    universe = list(unique.values())
    
    print(
        "Universe Created:",
        len(universe)
    )
    
    return universe

if __name__ == "__main__":

    universe = load_all_nse_universe()

    print(universe[:10])
