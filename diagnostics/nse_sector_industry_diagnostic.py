import os
import csv
import json
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# CONFIGURATION
# ============================================================

STOCK_MASTER_SHEET = "Stock_Master"
DIAGNOSTIC_SHEET = "NSE_Sector_Industry_Diagnostic"

# Classification master file.
#
# Recommended location:
# data/nse_industry_classification.csv
#
# The file should contain NSE's official classification data
# mapped to individual listed securities.
CLASSIFICATION_FILE = os.getenv(
    "NSE_CLASSIFICATION_FILE",
    "data/nse_industry_classification.csv"
)

HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
NOT_RESOLVED = "NOT_RESOLVED"


# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

def connect_to_google_sheet():
    """
    Connect to the existing Google Sheet using the project's
    GOOGLE_CREDENTIALS environment variable.
    """

    print("Connecting to Google Sheet...")

    google_credentials = os.getenv("GOOGLE_CREDENTIALS")

    if not google_credentials:
        raise RuntimeError(
            "GOOGLE_CREDENTIALS environment variable is not configured."
        )

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ]

    credentials_dict = json.loads(google_credentials)

    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
        credentials_dict,
        scope
    )

    client = gspread.authorize(credentials)

    spreadsheet = client.open_by_key(
        "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"
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
    """
    Normalize NSE symbols for matching.

    Examples:
        3BBLACKBIO
        3BBLACKBIO.NS
        NSE:3BBLACKBIO
    """

    value = normalize_text(value).upper()

    if value.startswith("NSE:"):
        value = value[4:]

    if value.endswith(".NS"):
        value = value[:-3]

    return value.strip()


def find_column(headers, candidates, required=True):
    """
    Case-insensitive column matching.
    """

    normalized = {
        str(header).strip().lower(): header
        for header in headers
    }

    for candidate in candidates:

        key = candidate.strip().lower()

        if key in normalized:
            return normalized[key]

    if required:
        raise RuntimeError(
            f"Required column not found. Tried: {candidates}"
        )

    return None


# ============================================================
# READ STOCK MASTER
# ============================================================

def read_stock_master(spreadsheet):

    print("\nReading Stock_Master...")

    worksheet = spreadsheet.worksheet(
        STOCK_MASTER_SHEET
    )

    values = worksheet.get_all_values()

    if not values:
        raise RuntimeError(
            "Stock_Master is empty."
        )

    headers = values[0]

    print("\nStock_Master columns detected:")

    for header in headers:
        print(f"  - {header}")

    records = [
        dict(zip(headers, row))
        for row in values[1:]
    ]

    ticker_col = find_column(
        headers,
        [
            "Ticker",
            "Yahoo Ticker",
            "Symbol",
        ]
    )

    company_col = find_column(
        headers,
        [
            "Company Name",
            "Company",
            "Name",
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

    selected = []

    for record in records:

        sector = normalize_text(
            record.get(
                sector_col,
                ""
            )
        )

        industry = normalize_text(
            record.get(
                industry_col,
                ""
            )
        )

        ticker = normalize_text(
            record.get(
                ticker_col,
                ""
            )
        )

        company_name = normalize_text(
            record.get(
                company_col,
                ""
            )
        )

        # Only diagnose currently unresolved rows.
        if sector.upper() not in {
            "",
            "UNKNOWN",
            "N/A",
            "NA",
            "NULL",
            "NONE",
        }:
            continue

        if not ticker:
            continue

        selected.append({
            "Ticker": ticker,
            "NSE Symbol": normalize_symbol(ticker),
            "Company Name": company_name,
            "Existing Sector": sector,
            "Existing Industry": industry,
        })

    print(
        f"\nStock Master Rows: {len(records)}"
    )

    print(
        f"Unknown-Sector Equity Rows: "
        f"{len(selected)}"
    )

    return selected


# ============================================================
# CLASSIFICATION MASTER
# ============================================================

def load_classification_master():

    print(
        f"\nLoading NSE classification master: "
        f"{CLASSIFICATION_FILE}"
    )

    if not os.path.exists(
        CLASSIFICATION_FILE
    ):

        raise RuntimeError(
            "NSE classification master file not found.\n"
            f"Expected: {CLASSIFICATION_FILE}\n\n"
            "Create this file before running the diagnostic."
        )

    with open(
        CLASSIFICATION_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise RuntimeError(
                "NSE classification master has no headers."
            )

        headers = reader.fieldnames

        print(
            "\nClassification master columns detected:"
        )

        for header in headers:
            print(f"  - {header}")

        symbol_col = find_column(
            headers,
            [
                "NSE Symbol",
                "Symbol",
                "Ticker",
                "NSE_Symbol",
            ]
        )

        macro_col = find_column(
            headers,
            [
                "Macro-Economic Sector",
                "Macro Economic Sector",
                "Macro Sector",
            ],
            required=False
        )

        sector_col = find_column(
            headers,
            [
                "Sector",
            ],
            required=False
        )

        industry_col = find_column(
            headers,
            [
                "Industry",
            ],
            required=False
        )

        basic_industry_col = find_column(
            headers,
            [
                "Basic Industry",
                "Basic_Industry",
                "Basic Industry Name",
            ],
            required=False
        )

        if not any([
            macro_col,
            sector_col,
            industry_col,
            basic_industry_col
        ]):

            raise RuntimeError(
                "Classification master does not contain "
                "any classification columns."
            )

        classification = {}

        for row in reader:

            symbol = normalize_symbol(
                row.get(
                    symbol_col,
                    ""
                )
            )

            if not symbol:
                continue

            classification[symbol] = {
                "Macro-Economic Sector":
                    normalize_text(
                        row.get(
                            macro_col,
                            ""
                        )
                    ) if macro_col else "",

                "Sector":
                    normalize_text(
                        row.get(
                            sector_col,
                            ""
                        )
                    ) if sector_col else "",

                "Industry":
                    normalize_text(
                        row.get(
                            industry_col,
                            ""
                        )
                    ) if industry_col else "",

                "Basic Industry":
                    normalize_text(
                        row.get(
                            basic_industry_col,
                            ""
                        )
                    ) if basic_industry_col else "",
            }

    print(
        f"Classification master records: "
        f"{len(classification)}"
    )

    return classification


# ============================================================
# CLASSIFICATION RESOLUTION
# ============================================================

def resolve_classification(
    nse_symbol,
    classification_master
):

    symbol = normalize_symbol(
        nse_symbol
    )

    result = classification_master.get(
        symbol
    )

    if not result:

        return {
            "Macro-Economic Sector": "",
            "Sector": "",
            "Industry": "",
            "Basic Industry": "",
            "Classification Source": "",
            "Classification Confidence":
                NOT_RESOLVED,
            "Diagnosis":
                "NSE_CLASSIFICATION_NOT_FOUND",
        }

    macro_sector = result.get(
        "Macro-Economic Sector",
        ""
    )

    sector = result.get(
        "Sector",
        ""
    )

    industry = result.get(
        "Industry",
        ""
    )

    basic_industry = result.get(
        "Basic Industry",
        ""
    )

    # Highest confidence requires the complete
    # four-level NSE classification.
    if (
        macro_sector
        and sector
        and industry
        and basic_industry
    ):

        return {
            "Macro-Economic Sector":
                macro_sector,

            "Sector":
                sector,

            "Industry":
                industry,

            "Basic Industry":
                basic_industry,

            "Classification Source":
                "NSE_INDICES",

            "Classification Confidence":
                HIGH_CONFIDENCE,

            "Diagnosis":
                "NSE_CLASSIFICATION_RESOLVED",
        }

    # Three-level classification.
    if sector and industry and basic_industry:

        return {
            "Macro-Economic Sector":
                macro_sector,

            "Sector":
                sector,

            "Industry":
                industry,

            "Basic Industry":
                basic_industry,

            "Classification Source":
                "NSE_INDICES",

            "Classification Confidence":
                MEDIUM_CONFIDENCE,

            "Diagnosis":
                "NSE_CLASSIFICATION_PARTIALLY_RESOLVED",
        }

    # At least one classification level exists.
    if (
        macro_sector
        or sector
        or industry
        or basic_industry
    ):

        return {
            "Macro-Economic Sector":
                macro_sector,

            "Sector":
                sector,

            "Industry":
                industry,

            "Basic Industry":
                basic_industry,

            "Classification Source":
                "NSE_INDICES",

            "Classification Confidence":
                LOW_CONFIDENCE,

            "Diagnosis":
                "NSE_CLASSIFICATION_INCOMPLETE",
        }

    return {
        "Macro-Economic Sector": "",
        "Sector": "",
        "Industry": "",
        "Basic Industry": "",
        "Classification Source": "",
        "Classification Confidence":
            NOT_RESOLVED,
        "Diagnosis":
            "NSE_CLASSIFICATION_EMPTY",
    }


# ============================================================
# CREATE DIAGNOSTIC ROWS
# ============================================================

def create_diagnostic_rows(
    records,
    classification_master
):

    run_date = datetime.now().strftime(
        "%Y-%m-%d"
    )

    rows = []

    total = len(records)

    for index, record in enumerate(
        records,
        start=1
    ):

        ticker = record["Ticker"]

        nse_symbol = record["NSE Symbol"]

        company_name = record[
            "Company Name"
        ]

        print(
            f"[{index}/{total}] "
            f"{nse_symbol} - "
            f"{company_name}"
        )

        classification = resolve_classification(
            nse_symbol,
            classification_master
        )

        rows.append({

            "Run Date":
                run_date,

            "Ticker":
                ticker,

            "NSE Symbol":
                nse_symbol,

            "Company Name":
                company_name,

            "Existing Sector":
                record[
                    "Existing Sector"
                ],

            "Existing Industry":
                record[
                    "Existing Industry"
                ],

            "NSE Classification Status":
                "CHECKED",

            "Macro-Economic Sector":
                classification[
                    "Macro-Economic Sector"
                ],

            "Sector":
                classification[
                    "Sector"
                ],

            "Industry":
                classification[
                    "Industry"
                ],

            "Basic Industry":
                classification[
                    "Basic Industry"
                ],

            "Classification Source":
                classification[
                    "Classification Source"
                ],

            "Classification Confidence":
                classification[
                    "Classification Confidence"
                ],

            "Diagnosis":
                classification[
                    "Diagnosis"
                ],
        })

    return rows


# ============================================================
# GOOGLE SHEET WRITE
# ============================================================

def write_diagnostic_sheet(
    spreadsheet,
    rows
):

    headers = [

        "Run Date",

        "Ticker",

        "NSE Symbol",

        "Company Name",

        "Existing Sector",

        "Existing Industry",

        "NSE Classification Status",

        "Macro-Economic Sector",

        "Sector",

        "Industry",

        "Basic Industry",

        "Classification Source",

        "Classification Confidence",

        "Diagnosis",
    ]

    try:

        worksheet = spreadsheet.worksheet(
            DIAGNOSTIC_SHEET
        )

        print(
            f"\nUsing existing worksheet: "
            f"{DIAGNOSTIC_SHEET}"
        )

    except gspread.WorksheetNotFound:

        print(
            f"\nCreating worksheet: "
            f"{DIAGNOSTIC_SHEET}"
        )

        worksheet = spreadsheet.add_worksheet(
            title=DIAGNOSTIC_SHEET,
            rows=max(
                len(rows) + 2,
                100
            ),
            cols=len(headers)
        )

    print(
        "Clearing diagnostic worksheet..."
    )

    worksheet.clear()

    data = [headers]

    for row in rows:

        data.append([
            row.get(
                header,
                ""
            )
            for header in headers
        ])

    print(
        "Writing NSE sector/industry "
        f"diagnostic rows: {len(rows)}"
    )

    end_column = "N"

    worksheet.update(
        range_name=(
            f"A1:{end_column}"
            f"{len(data)}"
        ),
        values=data,
        value_input_option="USER_ENTERED"
    )

    print(
        f"Diagnostic rows written: "
        f"{len(rows)}"
    )

    return worksheet


# ============================================================
# SUMMARY
# ============================================================

def print_summary(rows):

    total = len(rows)

    high = sum(
        1
        for row in rows
        if row[
            "Classification Confidence"
        ] == HIGH_CONFIDENCE
    )

    medium = sum(
        1
        for row in rows
        if row[
            "Classification Confidence"
        ] == MEDIUM_CONFIDENCE
    )

    low = sum(
        1
        for row in rows
        if row[
            "Classification Confidence"
        ] == LOW_CONFIDENCE
    )

    unresolved = sum(
        1
        for row in rows
        if row[
            "Classification Confidence"
        ] == NOT_RESOLVED
    )

    print("\n")
    print("=" * 60)
    print(
        "NSE SECTOR & INDUSTRY RESOLUTION DIAGNOSTIC"
    )
    print("=" * 60)

    print(
        f"Unknown-Sector Equities : {total}"
    )

    print(
        f"High Confidence        : {high}"
    )

    print(
        f"Medium Confidence      : {medium}"
    )

    print(
        f"Low Confidence         : {low}"
    )

    print(
        f"Not Resolved           : {unresolved}"
    )

    print("-" * 60)

    if total:

        resolved = (
            high
            + medium
        )

        print(
            f"Resolution Rate        : "
            f"{(resolved / total) * 100:.1f}%"
        )

    print("-" * 60)

    print(
        f"Diagnostic Sheet       : "
        f"{DIAGNOSTIC_SHEET}"
    )

    print(
        f"Classification Source  : "
        f"NSE Indices"
    )

    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Run "
        "nse_sector_industry_diagnostic.py"
    )

    spreadsheet = (
        connect_to_google_sheet()
    )

    records = read_stock_master(
        spreadsheet
    )

    if not records:

        print(
            "No UNKNOWN-sector equities found."
        )

        return

    classification_master = (
        load_classification_master()
    )

    diagnostic_rows = (
        create_diagnostic_rows(
            records,
            classification_master
        )
    )

    write_diagnostic_sheet(
        spreadsheet,
        diagnostic_rows
    )

    print_summary(
        diagnostic_rows
    )


if __name__ == "__main__":
    main()
