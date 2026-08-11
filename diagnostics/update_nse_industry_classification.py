import os
import csv
import json
import time
import random

import requests
import gspread

from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# CONFIGURATION
# ============================================================

STOCK_MASTER_SHEET = "Stock_Master"

CLASSIFICATION_FILE = os.getenv(
    "NSE_CLASSIFICATION_FILE",
    "data/nse_industry_classification.csv"
)

SPREADSHEET_ID = (
    "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"
)

NSE_HOME_URL = "https://www.nseindia.com"

NSE_QUOTE_URL = (
    "https://www.nseindia.com/api/quote-equity"
)


# ============================================================
# GOOGLE SHEETS
# ============================================================

def connect_to_google_sheet():

    print("Connecting to Google Sheet...")

    google_credentials = os.getenv(
        "GOOGLE_CREDENTIALS"
    )

    if not google_credentials:
        raise RuntimeError(
            "GOOGLE_CREDENTIALS environment variable "
            "is not configured."
        )

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ]

    credentials_dict = json.loads(
        google_credentials
    )

    credentials = (
        ServiceAccountCredentials
        .from_json_keyfile_dict(
            credentials_dict,
            scope
        )
    )

    client = gspread.authorize(
        credentials
    )

    spreadsheet = client.open_by_key(
        SPREADSHEET_ID
    )

    print("Connected")

    return spreadsheet


# ============================================================
# HELPERS
# ============================================================

def normalize_text(value):

    if value is None:
        return ""

    return str(value).strip()


def normalize_symbol(value):

    value = normalize_text(value).upper()

    if value.startswith("NSE:"):
        value = value[4:]

    if value.endswith(".NS"):
        value = value[:-3]

    return value.strip()


def is_unknown(value):

    return normalize_text(value).upper() in {
        "",
        "UNKNOWN",
        "N/A",
        "NA",
        "NULL",
        "NONE",
    }


# ============================================================
# READ STOCK MASTER
# ============================================================

def get_unknown_symbols(spreadsheet):

    worksheet = spreadsheet.worksheet(
        STOCK_MASTER_SHEET
    )

    values = worksheet.get_all_values()

    if not values:
        raise RuntimeError(
            "Stock_Master is empty."
        )

    headers = values[0]

    header_map = {
        str(h).strip().lower(): h
        for h in headers
    }

    ticker_col = header_map.get("ticker")
    sector_col = header_map.get("sector")
    industry_col = header_map.get("industry")

    if not ticker_col:
        raise RuntimeError(
            "Ticker column not found in Stock_Master."
        )

    if not sector_col:
        raise RuntimeError(
            "Sector column not found in Stock_Master."
        )

    if not industry_col:
        raise RuntimeError(
            "Industry column not found in Stock_Master."
        )

    unknown_symbols = []

    for row in values[1:]:

        record = dict(
            zip(headers, row)
        )

        ticker = normalize_symbol(
            record.get(ticker_col, "")
        )

        sector = normalize_text(
            record.get(sector_col, "")
        )

        industry = normalize_text(
            record.get(industry_col, "")
        )

        if not ticker:
            continue

        if is_unknown(sector) or is_unknown(industry):

            unknown_symbols.append(ticker)

    # Remove duplicates
    unknown_symbols = list(
        dict.fromkeys(
            unknown_symbols
        )
    )

    print(
        f"Unknown classification symbols: "
        f"{len(unknown_symbols)}"
    )

    return unknown_symbols


# ============================================================
# NSE SESSION
# ============================================================

def create_nse_session():

    session = requests.Session()

    session.headers.update({

        "User-Agent":
            "Mozilla/5.0 "
            "(X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0.0.0 "
            "Safari/537.36",

        "Accept":
            "application/json,text/plain,*/*",

        "Accept-Language":
            "en-US,en;q=0.9",

        "Referer":
            NSE_HOME_URL + "/",

        "Connection":
            "keep-alive",
    })

    # Establish NSE cookies/session
    response = session.get(
        NSE_HOME_URL,
        timeout=20
    )

    response.raise_for_status()

    return session


# ============================================================
# FETCH NSE CLASSIFICATION
# ============================================================

def fetch_nse_classification(
    session,
    symbol,
    max_attempts=3
):

    print(
        f"  NSE lookup: "
        f"{symbol}"
    )

    for attempt in range(
        1,
        max_attempts + 1
    ):

        try:

            response = session.get(
                NSE_QUOTE_URL,
                params={
                    "symbol": symbol
                },
                timeout=20
            )

            if response.status_code != 200:

                print(
                    f"    HTTP "
                    f"{response.status_code}"
                )

                time.sleep(
                    2 + attempt
                )

                continue

            data = response.json()

            industry_info = (
                data.get(
                    "industryInfo"
                )
            )

            if not industry_info:

                print(
                    "    industryInfo missing"
                )

                time.sleep(
                    2 + attempt
                )

                continue

            macro = normalize_text(
                industry_info.get(
                    "macro"
                )
            )

            sector = normalize_text(
                industry_info.get(
                    "sector"
                )
            )

            industry = normalize_text(
                industry_info.get(
                    "industry"
                )
            )

            basic_industry = normalize_text(
                industry_info.get(
                    "basicIndustry"
                )
            )

            print(
                f"    Macro: "
                f"{macro}"
            )

            print(
                f"    Sector: "
                f"{sector}"
            )

            print(
                f"    Industry: "
                f"{industry}"
            )

            print(
                f"    Basic Industry: "
                f"{basic_industry}"
            )

            return {

                "NSE Symbol":
                    symbol,

                "Macro-Economic Sector":
                    macro,

                "Sector":
                    sector,

                "Industry":
                    industry,

                "Basic Industry":
                    basic_industry,
            }

        except Exception as error:

            print(
                f"    Attempt "
                f"{attempt} failed: "
                f"{error}"
            )

            time.sleep(
                2 + attempt
            )

    return None


# ============================================================
# LOAD EXISTING CSV
# ============================================================

def load_existing_classification():

    os.makedirs(
        os.path.dirname(
            CLASSIFICATION_FILE
        ),
        exist_ok=True
    )

    if not os.path.exists(
        CLASSIFICATION_FILE
    ):

        return {}

    with open(
        CLASSIFICATION_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(
            file
        )

        existing = {}

        for row in reader:

            symbol = normalize_symbol(
                row.get(
                    "NSE Symbol",
                    ""
                )
            )

            if not symbol:
                continue

            existing[symbol] = row

    print(
        f"Existing classification "
        f"records: {len(existing)}"
    )

    return existing


# ============================================================
# WRITE CSV
# ============================================================

def write_classification_csv(
    classifications
):

    headers = [

        "NSE Symbol",

        "Macro-Economic Sector",

        "Sector",

        "Industry",

        "Basic Industry",
    ]

    sorted_records = sorted(
        classifications.values(),
        key=lambda x:
            normalize_symbol(
                x.get(
                    "NSE Symbol",
                    ""
                )
            )
    )

    temp_file = (
        CLASSIFICATION_FILE
        + ".tmp"
    )

    with open(
        temp_file,
        "w",
        encoding="utf-8",
        newline=""
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=headers
        )

        writer.writeheader()

        for record in sorted_records:

            writer.writerow({

                header:
                    normalize_text(
                        record.get(
                            header,
                            ""
                        )
                    )

                for header in headers
            })

    os.replace(
        temp_file,
        CLASSIFICATION_FILE
    )

    print(
        f"\nClassification CSV updated:"
    )

    print(
        f"  {CLASSIFICATION_FILE}"
    )

    print(
        f"  Records: "
        f"{len(sorted_records)}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        "=============================================="
    )

    print(
        "UPDATE NSE INDUSTRY CLASSIFICATION"
    )

    print(
        "=============================================="
    )

    spreadsheet = (
        connect_to_google_sheet()
    )

    symbols = (
        get_unknown_symbols(
            spreadsheet
        )
    )

    classifications = (
        load_existing_classification()
    )

    if not symbols:

        print(
            "No unknown classifications found."
        )

        return

    session = (
        create_nse_session()
    )

    resolved = 0
    failed = 0

    total = len(symbols)

    for index, symbol in enumerate(
        symbols,
        start=1
    ):

        print(
            f"\n[{index}/{total}] "
            f"{symbol}"
        )

        result = (
            fetch_nse_classification(
                session,
                symbol
            )
        )

        if result:

            classifications[
                symbol
            ] = result

            resolved += 1

        else:

            failed += 1

            print(
                "    FAILED"
            )

        # Avoid hammering NSE
        time.sleep(
            random.uniform(
                1.0,
                2.0
            )
        )

    write_classification_csv(
        classifications
    )

    print(
        "\n"
        "=============================================="
    )

    print(
        f"Symbols processed : {total}"
    )

    print(
        f"Resolved          : {resolved}"
    )

    print(
        f"Failed            : {failed}"
    )

    print(
        "=============================================="
    )


if __name__ == "__main__":
    main()
