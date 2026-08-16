import os
import re
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# CONFIGURATION
# ============================================================

STOCK_MASTER_SHEET = "Stock_Master"

NSE_OUTPUT_FILE = "data/nse_industry_classification.csv"
BSE_OUTPUT_FILE = "data/bse_industry_classification.csv"

REQUEST_DELAY_SECONDS = 1.5
MAX_RETRIES = 3

SPREADSHEET_ID = "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"

INVALID_VALUES = {
    "",
    "UNKNOWN",
    "N/A",
    "NA",
    "NULL",
    "NONE",
}


# ============================================================
# HTTP SESSION
# ============================================================

def create_session():

    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    })

    return session


# ============================================================
# GOOGLE SHEETS
# ============================================================

def connect_to_google_sheet():

    print("Connecting to Google Sheet...")

    credentials_json = os.getenv("GOOGLE_CREDENTIALS")

    if not credentials_json:
        raise RuntimeError(
            "GOOGLE_CREDENTIALS environment variable is not configured."
        )

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ]

    credentials = (
        ServiceAccountCredentials
        .from_json_keyfile_dict(
            eval(credentials_json)
            if credentials_json.strip().startswith("{")
            else credentials_json,
            scope
        )
    )

    client = gspread.authorize(credentials)

    spreadsheet = client.open_by_key(
        SPREADSHEET_ID
    )

    print("Connected")

    return spreadsheet


# ============================================================
# HEADER NORMALIZATION
# ============================================================

def normalize_header(value):

    return (
        str(value)
        .strip()
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )


def find_column(headers, candidates):

    normalized = {
        normalize_header(header): header
        for header in headers
    }

    for candidate in candidates:

        key = normalize_header(candidate)

        if key in normalized:
            return normalized[key]

    raise RuntimeError(
        f"Required column not found. "
        f"Tried {candidates}. "
        f"Available columns: {headers}"
    )


def normalize_text(value):

    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# READ STOCK MASTER
# ============================================================

def read_unresolved_stocks(spreadsheet):

    worksheet = spreadsheet.worksheet(
        STOCK_MASTER_SHEET
    )

    values = worksheet.get_all_values()

    if not values:
        raise RuntimeError(
            "Stock_Master is empty."
        )

    headers = values[0]

    ticker_col = find_column(
        headers,
        [
            "Ticker",
            "Yahoo Ticker",
            "Yahoo_Ticker",
            "Symbol",
        ]
    )

    company_col = find_column(
        headers,
        [
            "Company Name",
            "Company",
            "Name",
            "Company_Name",
        ]
    )

    sector_col = find_column(
        headers,
        [
            "Sector",
        ]
    )

    industry_col = find_column(
        headers,
        [
            "Industry",
        ]
    )

    records = []

    for row in values[1:]:

        record = dict(
            zip(headers, row)
        )

        sector = normalize_text(
            record.get(sector_col, "")
        )

        industry = normalize_text(
            record.get(industry_col, "")
        )

        if (
            sector.upper() not in INVALID_VALUES
            and
            industry.upper() not in INVALID_VALUES
        ):
            continue

        ticker = normalize_text(
            record.get(ticker_col, "")
        )

        company = normalize_text(
            record.get(company_col, "")
        )

        if not ticker:
            continue

        symbol = ticker.upper()

        if symbol.endswith(".NS"):
            symbol = symbol[:-3]

        elif symbol.endswith(".NSE"):
            symbol = symbol[:-4]

        records.append({
            "NSE Symbol": symbol,
            "Company Name": company,
        })

    print(
        f"Stock Master Rows       : {len(values) - 1}"
    )

    print(
        f"Unknown Sector/Industry : {len(records)}"
    )

    return records


# ============================================================
# SCREENER URL
# ============================================================

def build_screener_url(symbol):

    return (
        "https://www.screener.in/company/"
        f"{symbol}/"
    )


# ============================================================
# EXTRACT CLASSIFICATION
# ============================================================

def extract_classification(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    text = soup.get_text(
        "\n",
        strip=True
    )

    # --------------------------------------------------------
    # Screener's peer/comparison information may expose
    # classification terms in structured text.
    # --------------------------------------------------------

    classification = {
        "Macro": "",
        "Sector": "",
        "Industry": "",
        "Basic Industry": "",
    }

    # --------------------------------------------------------
    # First try structured HTML text.
    # --------------------------------------------------------

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    # Search for known four-level labels.
    labels = {
        "Macro": [
            "Macro Economic Sector",
            "Macro Sector",
        ],
        "Sector": [
            "Sector",
        ],
        "Industry": [
            "Industry",
        ],
        "Basic Industry": [
            "Basic Industry",
        ],
    }

    for i, line in enumerate(lines):

        for field, possible_labels in labels.items():

            for label in possible_labels:

                if line.lower() == label.lower():

                    if i + 1 < len(lines):

                        candidate = lines[i + 1].strip()

                        if candidate:
                            classification[field] = candidate

    # --------------------------------------------------------
    # Try page links / market classification links.
    # --------------------------------------------------------

    for anchor in soup.find_all("a"):

        href = anchor.get("href", "") or ""
        value = anchor.get_text(
            " ",
            strip=True
        )

        if not value:
            continue

        # Screener classification links frequently point
        # to /market/... paths.
        if "/market/" in href:

            lower_value = value.lower()

            if (
                not classification["Industry"]
                and "industry" not in lower_value
            ):
                pass

    return classification


# ============================================================
# SCRAPE ONE STOCK
# ============================================================

def scrape_stock(
    session,
    symbol,
    company_name
):

    url = build_screener_url(symbol)

    print(
        f"  Screener lookup: "
        f"{symbol} -> {url}"
    )

    last_error = ""

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            response = session.get(
                url,
                timeout=30
            )

            if response.status_code == 404:

                return {
                    "NSE Symbol": symbol,
                    "Company Name": company_name,
                    "Status": "NOT_FOUND",
                    "Macro": "",
                    "Sector": "",
                    "Industry": "",
                    "Basic Industry": "",
                    "Source URL": url,
                }

            response.raise_for_status()

            classification = extract_classification(
                response.text
            )

            macro = classification["Macro"]
            sector = classification["Sector"]
            industry = classification["Industry"]
            basic = classification["Basic Industry"]

            if (
                macro
                and sector
                and industry
                and basic
            ):

                status = "RESOLVED"

            else:

                status = "PARTIAL"

            return {
                "NSE Symbol": symbol,
                "Company Name": company_name,
                "Status": status,
                "Macro": macro,
                "Sector": sector,
                "Industry": industry,
                "Basic Industry": basic,
                "Source URL": url,
            }

        except Exception as exc:

            last_error = str(exc)

            print(
                f"  Attempt {attempt} failed: "
                f"{last_error}"
            )

            if attempt < MAX_RETRIES:

                time.sleep(
                    attempt * 3
                )

    return {
        "NSE Symbol": symbol,
        "Company Name": company_name,
        "Status": "FAILED",
        "Macro": "",
        "Sector": "",
        "Industry": "",
        "Basic Industry": "",
        "Source URL": url,
        "Error": last_error,
    }


# ============================================================
# WRITE CSV
# ============================================================

def write_csvs(results):

    os.makedirs(
        os.path.dirname(NSE_OUTPUT_FILE),
        exist_ok=True
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # Do NOT write incomplete classifications.
    # --------------------------------------------------------

    unresolved = [
        row
        for row in results
        if row["Status"] != "RESOLVED"
    ]

    if unresolved:

        print()
        print(
            "WARNING: Some classifications "
            "could not be completely resolved."
        )

        for row in unresolved:

            print(
                f"  {row['NSE Symbol']}: "
                f"{row['Status']} | "
                f"{row.get('Error', '')}"
            )

        raise RuntimeError(
            f"{len(unresolved)} classification records "
            "are incomplete. CSV files were NOT replaced."
        )

    # --------------------------------------------------------
    # NSE CSV
    # --------------------------------------------------------

    nse_rows = []

    for row in results:

        nse_rows.append({
            "NSE Symbol": row["NSE Symbol"],
            "NSE Macro Sector": row["Macro"],
            "NSE Sector": row["Sector"],
            "NSE Industry": row["Industry"],
            "NSE Basic Industry": row["Basic Industry"],
        })

    nse_df = pd.DataFrame(
        nse_rows,
        columns=[
            "NSE Symbol",
            "NSE Macro Sector",
            "NSE Sector",
            "NSE Industry",
            "NSE Basic Industry",
        ]
    )

    # --------------------------------------------------------
    # BSE CSV
    #
    # Screener uses the common India Industry
    # Classification framework. Therefore the first
    # two hierarchy levels are used for the BSE master.
    # --------------------------------------------------------

    bse_rows = []

    for row in results:

        bse_rows.append({
            "NSE Symbol": row["NSE Symbol"],
            "BSE Sector": row["Sector"],
            "BSE Industry": row["Industry"],
        })

    bse_df = pd.DataFrame(
        bse_rows,
        columns=[
            "NSE Symbol",
            "BSE Sector",
            "BSE Industry",
        ]
    )

    nse_df.to_csv(
        NSE_OUTPUT_FILE,
        index=False
    )

    bse_df.to_csv(
        BSE_OUTPUT_FILE,
        index=False
    )

    print()
    print(
        f"NSE CSV written: "
        f"{NSE_OUTPUT_FILE}"
    )

    print(
        f"BSE CSV written: "
        f"{BSE_OUTPUT_FILE}"
    )

    print(
        f"NSE records: {len(nse_df)}"
    )

    print(
        f"BSE records: {len(bse_df)}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "POPULATE CLASSIFICATION MASTERS"
    )
    print("=" * 70)

    spreadsheet = connect_to_google_sheet()

    records = read_unresolved_stocks(
        spreadsheet
    )

    if not records:

        print(
            "No unresolved stocks found."
        )

        return

    session = create_session()

    results = []

    total = len(records)

    for index, record in enumerate(
        records,
        start=1
    ):

        print()
        print(
            f"[{index}/{total}] "
            f"{record['NSE Symbol']} - "
            f"{record['Company Name']}"
        )

        result = scrape_stock(
            session,
            record["NSE Symbol"],
            record["Company Name"]
        )

        results.append(result)

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    write_csvs(
        results
    )

    print()
    print("=" * 70)
    print("CLASSIFICATION MASTER POPULATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
