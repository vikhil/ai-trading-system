import requests
import pandas as pd
import time

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

def get_nse_quote_metadata(session, symbol):

    """
    Fetch authoritative NSE quote metadata for an equity.

    Used only as a fallback when Yahoo Finance does not
    provide sufficient sector / industry / market-cap data.

    Returns:
        {
            "Company Name": ...,
            "Sector": ...,
            "Industry": ...,
            "Basic Industry": ...,
            "Market Cap": ...
        }

    Returns empty dictionary if NSE cannot provide the data.
    """

    symbol = (
        str(symbol)
        .replace(".NS", "")
        .strip()
        .upper()
    )

    if not symbol:
        return {}

    url = NSE_QUOTE_URL.format(
        symbol=symbol
    )

    try:

        response = session.get(
            url,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": (
                    f"https://www.nseindia.com/"
                    f"get-quote/equity/{symbol}"
                )
            },
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        metadata = {}

        # --------------------------------
        # COMPANY NAME
        # --------------------------------

        info = data.get(
            "info",
            {}
        )

        metadata["Company Name"] = (
            info.get("companyName")
            or ""
        )

        # --------------------------------
        # INDUSTRY INFORMATION
        # --------------------------------

        industry_info = data.get(
            "industryInfo",
            {}
        )

        metadata["Sector"] = (
            industry_info.get("sector")
            or ""
        )

        metadata["Industry"] = (
            industry_info.get("industry")
            or ""
        )

        metadata["Basic Industry"] = (
            industry_info.get("basicIndustry")
            or ""
        )

        # --------------------------------
        # MARKET CAP
        # --------------------------------

        metadata["Market Cap"] = 0

        security_info = data.get(
            "securityInfo",
            {}
        )

        # Some NSE responses expose issued size.
        issued_size = (
            security_info.get("issuedSize")
            or security_info.get("issuedCapital")
        )

        price_info = data.get(
            "priceInfo",
            {}
        )

        last_price = (
            price_info.get("lastPrice")
            or price_info.get("closePrice")
        )

        try:

            issued_size = float(
                issued_size
            )

        except:

            issued_size = 0

        try:

            last_price = float(
                last_price
            )

        except:

            last_price = 0

        if (
            issued_size > 0
            and last_price > 0
        ):

            metadata["Market Cap"] = (
                issued_size
                * last_price
            )

        # --------------------------------
        # VALIDATE
        # --------------------------------

        if not any([
            metadata["Company Name"],
            metadata["Sector"],
            metadata["Industry"],
            metadata["Basic Industry"],
            metadata["Market Cap"] > 0
        ]):

            return {}

        return metadata

    except Exception as e:

        print(
            f"NSE QUOTE FAILED -> "
            f"{symbol} -> {e}"
        )

        return {}

    finally:

        time.sleep(0.25)

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

NSE_QUOTE_URL = (
    "https://www.nseindia.com/api/quote-equity?symbol={symbol}"
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

            "Industry": "UNKNOWN",
            
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

            "Industry": "ETF",
            
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

            "Industry": "REIT",

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

            "Industry": "INVIT",

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
    
    asset_type_counts = {}
    
    for item in universe:
    
        asset_type = item.get(
            "Asset Type",
            "UNKNOWN"
        )
    
        asset_type_counts[asset_type] = (
            asset_type_counts.get(asset_type, 0) + 1
        )
    
    print(
        "Asset Type Counts:",
        asset_type_counts
    )
    
    missing_company_names = sum(
        1
        for item in universe
        if not str(
            item.get("Company Name", "")
        ).strip()
    )
    
    print(
        "Missing Company Names:",
        missing_company_names
    )
    
    return universe

if __name__ == "__main__":

    universe = load_all_nse_universe()

    print(universe[:10])
