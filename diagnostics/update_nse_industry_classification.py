import os
import csv
import json
import re
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# CONFIGURATION
# ============================================================

STOCK_MASTER_SHEET = "Stock_Master"

CLASSIFICATION_DIAGNOSTIC_SHEET = (
    "NSE_Sector_Industry_Diagnostic"
)

CLASSIFICATION_FILE = os.getenv(
    "NSE_CLASSIFICATION_FILE",
    "data/nse_industry_classification.csv"
)

# Optional company-classification mapping file.
#
# This is deliberately separate from the NSE taxonomy file.
#
# Expected columns:
# NSE Symbol
# Macro-Economic Sector
# Sector
# Industry
# Basic Industry
#
# If this file does not exist, the script will NOT fail.
# It will simply report that no company mappings are available.
COMPANY_CLASSIFICATION_FILE = os.getenv(
    "NSE_COMPANY_CLASSIFICATION_FILE",
    "data/nse_company_classification.csv"
)

HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
NOT_RESOLVED = "NOT_RESOLVED"


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

    client = gspread.authorize(credentials)

    spreadsheet = client.open_by_key(
        "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"
    )

    print("Connected")

    return spreadsheet


# ============================================================
# NORMALIZATION
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


def normalize_header(value):

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        normalize_text(value).lower()
    ).strip()


def find_column(
    headers,
    candidates,
    required=True
):

    normalized = {
        normalize_header(header): header
        for header in headers
    }

    for candidate in candidates:

        key = normalize_header(candidate)

        if key in normalized:
            return normalized[key]

    if required:

        raise RuntimeError(
            "Required column not found. "
            f"Tried: {candidates}"
        )

    return None


# ============================================================
# STOCK MASTER
# ============================================================

def read_unknown_stocks(spreadsheet):

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
        ["Sector"]
    )

    industry_col = find_column(
        headers,
        ["Industry"]
    )

    records = [
        dict(zip(headers, row))
        for row in values[1:]
    ]

    selected = []

    for record in records:

        ticker = normalize_text(
            record.get(ticker_col, "")
        )

        company_name = normalize_text(
            record.get(company_col, "")
        )

        sector = normalize_text(
            record.get(sector_col, "")
        )

        industry = normalize_text(
            record.get(industry_col, "")
        )

        if not ticker:
            continue

        if sector.upper() not in {
            "",
            "UNKNOWN",
            "N/A",
            "NA",
            "NULL",
            "NONE"
        }:
            continue

        selected.append({
            "Ticker": ticker,
            "NSE Symbol": normalize_symbol(ticker),
            "Company Name": company_name,
            "Existing Sector": sector,
            "Existing Industry": industry,
        })

    print(
        f"Stock Master Rows: {len(records)}"
    )

    print(
        f"Unknown-Sector Equity Rows: "
        f"{len(selected)}"
    )

    return selected


# ============================================================
# LOAD CLASSIFICATION TAXONOMY
# ============================================================

def load_classification_taxonomy():

    print(
        "\nLoading NSE classification taxonomy:"
    )

    print(
        f"  {CLASSIFICATION_FILE}"
    )

    if not os.path.exists(
        CLASSIFICATION_FILE
    ):

        print(
            "WARNING: Classification taxonomy "
            "file does not exist."
        )

        return {}

    with open(
        CLASSIFICATION_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        if not reader.fieldnames:

            raise RuntimeError(
                "Classification CSV has no headers."
            )

        headers = reader.fieldnames

        symbol_col = find_column(
            headers,
            [
                "NSE Symbol",
                "NSE_Symbol",
                "Symbol",
                "Ticker"
            ],
            required=False
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
            ["Sector"],
            required=False
        )

        industry_col = find_column(
            headers,
            ["Industry"],
            required=False
        )

        basic_col = find_column(
            headers,
            [
                "Basic Industry",
                "Basic_Industry",
                "Basic Industry Name"
            ],
            required=False
        )

        taxonomy = []

        for row in reader:

            record = {
                "NSE Symbol":
                    normalize_symbol(
                        row.get(symbol_col, "")
                    )
                    if symbol_col
                    else "",

                "Macro-Economic Sector":
                    normalize_text(
                        row.get(macro_col, "")
                    )
                    if macro_col
                    else "",

                "Sector":
                    normalize_text(
                        row.get(sector_col, "")
                    )
                    if sector_col
                    else "",

                "Industry":
                    normalize_text(
                        row.get(industry_col, "")
                    )
                    if industry_col
                    else "",

                "Basic Industry":
                    normalize_text(
                        row.get(basic_col, "")
                    )
                    if basic_col
                    else "",
            }

            # Ignore completely empty rows.
            if not any(
                record.values()
            ):
                continue

            taxonomy.append(record)

    print(
        f"Classification taxonomy records: "
        f"{len(taxonomy)}"
    )

    return taxonomy


# ============================================================
# LOAD COMPANY CLASSIFICATION MAPPING
# ============================================================

def load_company_classification():

    print(
        "\nLoading company classification mapping:"
    )

    print(
        f"  {COMPANY_CLASSIFICATION_FILE}"
    )

    if not os.path.exists(
        COMPANY_CLASSIFICATION_FILE
    ):

        print(
            "Company classification mapping "
            "file not found."
        )

        print(
            "No company-level classifications "
            "will be applied in this run."
        )

        return {}

    with open(
        COMPANY_CLASSIFICATION_FILE,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(file)

        if not reader.fieldnames:

            raise RuntimeError(
                "Company classification CSV "
                "has no headers."
            )

        headers = reader.fieldnames

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
                "Macro Sector"
            ],
            required=False
        )

        sector_col = find_column(
            headers,
            ["Sector"],
            required=False
        )

        industry_col = find_column(
            headers,
            ["Industry"],
            required=False
        )

        basic_col = find_column(
            headers,
            [
                "Basic Industry",
                "Basic_Industry"
            ],
            required=False
        )

        mapping = {}

        for row in reader:

            symbol = normalize_symbol(
                row.get(symbol_col, "")
            )

            if not symbol:
                continue

            mapping[symbol] = {
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
                            basic_col,
                            ""
                        )
                    )
                    if basic_col
                    else "",
            }

    print(
        f"Company classification records: "
        f"{len(mapping)}"
    )

    return mapping


# ============================================================
# RESOLUTION
# ============================================================

def resolve_classification(
    nse_symbol,
    company_mapping
):

    symbol = normalize_symbol(
        nse_symbol
    )

    result = company_mapping.get(
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
                "COMPANY_CLASSIFICATION_NOT_FOUND",
        }

    macro = normalize_text(
        result.get(
            "Macro-Economic Sector",
            ""
        )
    )

    sector = normalize_text(
        result.get(
            "Sector",
            ""
        )
    )

    industry = normalize_text(
        result.get(
            "Industry",
            ""
        )
    )

    basic = normalize_text(
        result.get(
            "Basic Industry",
            ""
        )
    )

    populated = sum(
        bool(x)
        for x in [
            macro,
            sector,
            industry,
            basic
        ]
    )

    if populated == 4:

        confidence = HIGH_CONFIDENCE

        diagnosis = (
            "COMPANY_CLASSIFICATION_RESOLVED"
        )

    elif populated >= 2:

        confidence = MEDIUM_CONFIDENCE

        diagnosis = (
            "COMPANY_CLASSIFICATION_PARTIAL"
        )

    elif populated == 1:

        confidence = LOW_CONFIDENCE

        diagnosis = (
            "COMPANY_CLASSIFICATION_INCOMPLETE"
        )

    else:

        confidence = NOT_RESOLVED

        diagnosis = (
            "COMPANY_CLASSIFICATION_EMPTY"
        )

    return {
        "Macro-Economic Sector": macro,
        "Sector": sector,
        "Industry": industry,
        "Basic Industry": basic,
        "Classification Source":
            "NSE_INDICES_COMPANY_MAPPING",
        "Classification Confidence":
            confidence,
        "Diagnosis": diagnosis,
    }


# ============================================================
# DIAGNOSTIC ROWS
# ============================================================

def create_diagnostic_rows(
    records,
    company_mapping
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
                company_mapping
            )
        )

        rows.append({

            "Run Date":
                run_date,

            "Ticker":
                record["Ticker"],

            "NSE Symbol":
                nse_symbol,

            "Company Name":
                company_name,

            "Existing Sector":
                record["Existing Sector"],

            "Existing Industry":
                record["Existing Industry"],

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
            CLASSIFICATION_DIAGNOSTIC_SHEET
        )

        print(
            f"\nUsing existing worksheet: "
            f"{CLASSIFICATION_DIAGNOSTIC_SHEET}"
        )

    except gspread.WorksheetNotFound:

        print(
            f"\nCreating worksheet: "
            f"{CLASSIFICATION_DIAGNOSTIC_SHEET}"
        )

        worksheet = spreadsheet.add_worksheet(
            title=CLASSIFICATION_DIAGNOSTIC_SHEET,
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
        row[
            "Classification Confidence"
        ] == HIGH_CONFIDENCE
        for row in rows
    )

    medium = sum(
        row[
            "Classification Confidence"
        ] == MEDIUM_CONFIDENCE
        for row in rows
    )

    low = sum(
        row[
            "Classification Confidence"
        ] == LOW_CONFIDENCE
        for row in rows
    )

    unresolved = sum(
        row[
            "Classification Confidence"
        ] == NOT_RESOLVED
        for row in rows
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

        resolved = high + medium + low

        print(
            f"Resolution Rate        : "
            f"{(resolved / total) * 100:.1f}%"
        )

    print("-" * 60)

    print(
        f"Diagnostic Sheet       : "
        f"{CLASSIFICATION_DIAGNOSTIC_SHEET}"
    )

    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n=============================================="
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

    records = (
        read_unknown_stocks(
            spreadsheet
        )
    )

    if not records:

        print(
            "\nNo UNKNOWN-sector equities found."
        )

        return

    # Load taxonomy only for validation/
    # architecture visibility.
    #
    # It is NOT used to guess a company's
    # classification.
    taxonomy = (
        load_classification_taxonomy()
    )

    if taxonomy:

        print(
            f"\nTaxonomy loaded successfully: "
            f"{len(taxonomy)} records"
        )

    company_mapping = (
        load_company_classification()
    )

    diagnostic_rows = (
        create_diagnostic_rows(
            records,
            company_mapping
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
