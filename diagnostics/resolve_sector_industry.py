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

    value = normalize_text(
        value
    ).upper()

    if value.startswith("NSE:"):
        value = value[4:]

    if value.endswith(".NS"):
        value = value[:-3]

    return value.strip()


def find_column(
    headers,
    candidates,
    required=True
):

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
            f"Required column not found. "
            f"Tried: {candidates}"
        )

    return None


# ============================================================
# READ STOCK MASTER
# ============================================================

def read_stock_master(
    spreadsheet
):

    worksheet = spreadsheet.worksheet(
        STOCK_MASTER_SHEET
    )

    values = worksheet.get_all_values()

    if not values:

        raise RuntimeError(
            "Stock_Master is empty."
        )

    headers = values[0]

    print(
        "\nStock_Master columns detected:"
    )

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
            "Symbol"
        ]
    )

    company_col = find_column(
        headers,
        [
            "Company Name",
            "Company",
            "Name"
        ]
    )

    sector_col = find_column(
        headers,
        [
            "Sector"
        ]
    )

    industry_col = find_column(
        headers,
        [
            "Industry"
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

        industry = normalize_text(
            record.get(
                industry_col,
                ""
            )
        )

        if sector.upper() not in {
            "",
            "UNKNOWN",
            "N/A",
            "NA",
            "NULL",
            "NONE"
        }:

            continue

        if not ticker:
            continue

        selected.append({

            "Ticker":
                ticker,

            "NSE Symbol":
                normalize_symbol(
                    ticker
                ),

            "Company Name":
                company_name,

            "Existing Sector":
                sector,

            "Existing Industry":
                industry,
        })

    print(
        f"\nStock Master Rows: "
        f"{len(records)}"
    )

    print(
        f"Unknown-Sector Equity Rows: "
        f"{len(selected)}"
    )

    return selected


# ============================================================
# LOAD NSE CLASSIFICATION MASTER
# ============================================================

def load_classification_master():

    print(
        "\nLoading NSE classification master:"
    )

    print(
        f"  {CLASSIFICATION_FILE}"
    )

    if not os.path.exists(
        CLASSIFICATION_FILE
    ):

        raise RuntimeError(
            "NSE classification master "
            "file not found.\n"
            f"Expected: {CLASSIFICATION_FILE}"
        )

    with open(
        CLASSIFICATION_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(
            file
        )

        if not reader.fieldnames:

            raise RuntimeError(
                "Classification CSV has "
                "no headers."
            )

        headers = reader.fieldnames

        print(
            "\nClassification columns detected:"
        )

        for header in headers:
            print(
                f"  - {header}"
            )

        symbol_col = find_column(
            headers,
            [
                "NSE Symbol",
                "NSE_Symbol",
                "Symbol",
                "Ticker"
            ]
        )

        macro_col = find_column(
            headers,
            [
                "Macro-Economic Sector",
                "Macro Economic Sector",
                "Macro Sector",
                "Macro_Economic_Sector"
            ],
            required=False
        )

        sector_col = find_column(
            headers,
            [
                "Sector"
            ],
            required=False
        )

        industry_col = find_column(
            headers,
            [
                "Industry"
            ],
            required=False
        )

        basic_industry_col = find_column(
            headers,
            [
                "Basic Industry",
                "Basic_Industry",
                "Basic Industry Name"
            ],
            required=False
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
                    )
                    if macro_col
                    else "",

                "Sector":
                    normalize_text(
                        row.get(
                            sector_col,
                            ""
                        )
                    )
                    if sector_col
                    else "",

                "Industry":
                    normalize_text(
                        row.get(
                            industry_col,
                            ""
                        )
                    )
                    if industry_col
                    else "",

                "Basic Industry":
                    normalize_text(
                        row.get(
                            basic_industry_col,
                            ""
                        )
                    )
                    if basic_industry_col
                    else "",
            }

    # ========================================================
    # VALIDATE CLASSIFICATION MASTER
    # ========================================================

    if not classification:

        raise RuntimeError(
            "NSE classification master is empty. "
            f"{CLASSIFICATION_FILE} contains headers "
            "but no records."
        )
        
    print(
        "\nClassification master records: "
        f"{len(classification)}"
    )

    return classification


# ============================================================
# RESOLVE CLASSIFICATION
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

    macro = result.get(
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

    basic = result.get(
        "Basic Industry",
        ""
    )

    if (
        macro
        and sector
        and industry
        and basic
    ):

        confidence = HIGH_CONFIDENCE

        diagnosis = (
            "NSE_CLASSIFICATION_RESOLVED"
        )

    elif (
        sector
        and industry
        and basic
    ):

        confidence = MEDIUM_CONFIDENCE

        diagnosis = (
            "NSE_CLASSIFICATION_PARTIALLY_RESOLVED"
        )

    elif (
        macro
        or sector
        or industry
        or basic
    ):

        confidence = LOW_CONFIDENCE

        diagnosis = (
            "NSE_CLASSIFICATION_INCOMPLETE"
        )

    else:

        confidence = NOT_RESOLVED

        diagnosis = (
            "NSE_CLASSIFICATION_EMPTY"
        )

    return {

        "Macro-Economic Sector":
            macro,

        "Sector":
            sector,

        "Industry":
            industry,

        "Basic Industry":
            basic,

        "Classification Source":
            "NSE_INDICES",

        "Classification Confidence":
            confidence,

        "Diagnosis":
            diagnosis,
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

        ticker = record[
            "Ticker"
        ]

        nse_symbol = record[
            "NSE Symbol"
        ]

        company_name = record[
            "Company Name"
        ]

        print(
            f"[{index}/{total}] "
            f"{nse_symbol} - "
            f"{company_name}"
        )

        classification = (
            resolve_classification(
                nse_symbol,
                classification_master
            )
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
# WRITE DIAGNOSTIC SHEET
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
        "\nClearing diagnostic worksheet..."
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
        "Writing diagnostic rows: "
        f"{len(rows)}"
    )

    end_column = "M"

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
        "NSE SECTOR & INDUSTRY DIAGNOSTIC"
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

    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Run "
        "resolve_sector_industry.py"
    )

    spreadsheet = (
        connect_to_google_sheet()
    )

    records = (
        read_stock_master(
            spreadsheet
        )
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
