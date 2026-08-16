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

CHECKPOINT_FILE = os.getenv(
    "NSE_CLASSIFICATION_CHECKPOINT",
    "data/nse_classification_checkpoint.json"
)

HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
CONFLICT = "CONFLICT"
NOT_RESOLVED = "NOT_RESOLVED"

UNKNOWN_VALUES = {
    "",
    "UNKNOWN",
    "N/A",
    "NA",
    "NULL",
    "NONE",
}


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


def is_unknown(value):

    return (
        normalize_text(value).upper()
        in UNKNOWN_VALUES
    )


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


def classification_has_any_value(
    classification
):

    return any(
        normalize_text(
            classification.get(
                field,
                ""
            )
        )
        for field in [
            "Macro-Economic Sector",
            "Sector",
            "Industry",
            "Basic Industry",
        ]
    )


def classification_is_complete(
    classification
):

    return all(
        normalize_text(
            classification.get(
                field,
                ""
            )
        )
        for field in [
            "Macro-Economic Sector",
            "Sector",
            "Industry",
            "Basic Industry",
        ]
    )


# ============================================================
# READ STOCK MASTER
# ============================================================

def read_stock_master(
    spreadsheet
):

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

    print(
        "\nStock_Master columns detected:"
    )

    for header in headers:
        print(
            f"  - {header}"
        )

    records = [
        dict(
            zip(
                headers,
                row
            )
        )
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

        # ----------------------------------------------------
        # IMPORTANT:
        # We only resolve currently unresolved sectors.
        # ----------------------------------------------------

        if not is_unknown(
            sector
        ):

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
# EMPTY CLASSIFICATION STRUCTURE
# ============================================================

def empty_classification():

    return {

        "Macro-Economic Sector": "",

        "Sector": "",

        "Industry": "",

        "Basic Industry": "",

    }


# ============================================================
# LOAD CSV CLASSIFICATION MASTER
# ============================================================

def load_classification_master():

    print(
        "\n============================================================"
    )

    print(
        "LOAD NSE CLASSIFICATION MASTER"
    )

    print(
        "============================================================"
    )

    print(
        f"Classification file: "
        f"{CLASSIFICATION_FILE}"
    )

    classification = {}

    # --------------------------------------------------------
    # Missing file
    # --------------------------------------------------------

    if not os.path.exists(
        CLASSIFICATION_FILE
    ):

        print(
            "\nWARNING: NSE classification CSV "
            "does not exist."
        )

        print(
            "This is NOT treated as a fatal error."
        )

        return classification

    # --------------------------------------------------------
    # Read CSV
    # --------------------------------------------------------

    try:

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

                print(
                    "WARNING: Classification CSV "
                    "contains no headers."
                )

                return classification

            headers = reader.fieldnames

            # --------------------------------------------------------
            # Validate required NSE classification columns.
            #
            # Multiple accepted header names are supported by
            # find_column() below.
            # --------------------------------------------------------
            
            symbol_col = find_column(
                headers,
                [
                    "NSE Symbol",
                    "NSE_Symbol",
                    "Symbol",
                    "Ticker",
                ]
            )
            
            macro_col = find_column(
                headers,
                [
                    "NSE Macro Sector",
                    "Macro-Economic Sector",
                    "Macro Economic Sector",
                    "Macro Sector",
                    "Macro_Economic_Sector",
                ]
            )
            
            sector_col = find_column(
                headers,
                [
                    "NSE Sector",
                    "Sector",
                ]
            )
            
            industry_col = find_column(
                headers,
                [
                    "NSE Industry",
                    "Industry",
                ]
            )
            
            basic_industry_col = find_column(
                headers,
                [
                    "NSE Basic Industry",
                    "Basic Industry",
                    "Basic_Industry",
                    "Basic Industry Name",
                ]
            )
    
            print(
                "\nClassification columns detected:"
            )

            for header in headers:

                print(
                    f"  - {header}"
                )

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

    except Exception as error:

        print(
            "\nWARNING: Unable to read NSE "
            "classification CSV."
        )

        print(
            f"Reason: {error}"
        )

        return {}

    # --------------------------------------------------------
    # Empty CSV
    # --------------------------------------------------------

    if not classification:

        print(
            "\nWARNING: NSE classification CSV "
            "contains headers but no records."
        )

        print(
            "CSV will NOT be treated as a valid "
            "classification source."
        )

        return {}

    print(
        "\nNSE CSV classification records: "
        f"{len(classification)}"
    )

    return classification

# ============================================================
# CHECKPOINT CLASSIFICATION LOADER
# ============================================================

def load_checkpoint_classification():

    print(
        "\n============================================================"
    )

    print(
        "LOAD NSE CHECKPOINT"
    )

    print(
        "============================================================"
    )

    print(
        f"Checkpoint file: "
        f"{CHECKPOINT_FILE}"
    )

    checkpoint_classification = {}

    if not os.path.exists(
        CHECKPOINT_FILE
    ):

        print(
            "No NSE checkpoint found."
        )

        return checkpoint_classification

    try:

        with open(
            CHECKPOINT_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            checkpoint = json.load(
                file
            )

    except Exception as error:

        print(
            "WARNING: Unable to read "
            "NSE checkpoint."
        )

        print(
            f"Reason: {error}"
        )

        return checkpoint_classification

    # --------------------------------------------------------
    # The collector may store classifications under different
    # top-level keys depending on the previous implementation.
    #
    # We deliberately support several structures rather than
    # assuming one exact checkpoint schema.
    # --------------------------------------------------------

    possible_containers = []

    if isinstance(
        checkpoint,
        dict
    ):

        for key in [
            "classifications",
            "classification",
            "results",
            "records",
            "data",
            "symbols",
        ]:

            value = checkpoint.get(
                key
            )

            if isinstance(
                value,
                dict
            ):

                possible_containers.append(
                    value
                )

    # The checkpoint itself may already be a
    # symbol -> classification dictionary.
    if isinstance(
        checkpoint,
        dict
    ):

        possible_containers.append(
            checkpoint
        )

    # --------------------------------------------------------
    # Extract symbol-level records.
    # --------------------------------------------------------

    for container in possible_containers:

        for raw_symbol, raw_value in (
            container.items()
        ):

            symbol = normalize_symbol(
                raw_symbol
            )

            if not symbol:

                continue

            if not isinstance(
                raw_value,
                dict
            ):

                continue

            # ------------------------------------------------
            # Some checkpoint formats may contain a nested
            # classification object.
            # ------------------------------------------------

            candidate = raw_value

            for nested_key in [
                "classification",
                "data",
                "result",
            ]:

                nested = raw_value.get(
                    nested_key
                )

                if isinstance(
                    nested,
                    dict
                ):

                    candidate = nested

                    break

            classification = {

                "Macro-Economic Sector":
                    normalize_text(
                        candidate.get(
                            "Macro-Economic Sector",
                            candidate.get(
                                "Macro Economic Sector",
                                candidate.get(
                                    "macro_sector",
                                    ""
                                )
                            )
                        )
                    ),

                "Sector":
                    normalize_text(
                        candidate.get(
                            "Sector",
                            candidate.get(
                                "sector",
                                ""
                            )
                        )
                    ),

                "Industry":
                    normalize_text(
                        candidate.get(
                            "Industry",
                            candidate.get(
                                "industry",
                                ""
                            )
                        )
                    ),

                "Basic Industry":
                    normalize_text(
                        candidate.get(
                            "Basic Industry",
                            candidate.get(
                                "Basic_Industry",
                                candidate.get(
                                    "basic_industry",
                                    ""
                                )
                            )
                        )
                    ),
            }

            if classification_has_any_value(
                classification
            ):

                checkpoint_classification[
                    symbol
                ] = classification

    print(
        "Checkpoint classification records: "
        f"{len(checkpoint_classification)}"
    )

    return checkpoint_classification
        
# ============================================================
# RESOLVE FROM NSE SOURCES
# ============================================================

def resolve_from_sources(
    nse_symbol,
    csv_classification,
    checkpoint_classification
):

    symbol = normalize_symbol(
        nse_symbol
    )

    # --------------------------------------------------------
    # SOURCE 1: NSE classification CSV
    #
    # This is the PRIMARY and AUTHORITATIVE local source.
    # --------------------------------------------------------

    csv_result = csv_classification.get(
        symbol
    )

    if (
        csv_result
        and classification_has_any_value(
            csv_result
        )
    ):

        return (
            csv_result,
            "NSE_CLASSIFICATION_CSV"
        )

    # --------------------------------------------------------
    # SOURCE 2: NSE checkpoint
    #
    # This contains previously collected NSE
    # classification data and is used as a fallback.
    # --------------------------------------------------------

    checkpoint_result = (
        checkpoint_classification.get(
            symbol
        )
    )

    if (
        checkpoint_result
        and classification_has_any_value(
            checkpoint_result
        )
    ):

        return (
            checkpoint_result,
            "NSE_CHECKPOINT"
        )

    # --------------------------------------------------------
    # SOURCE 3: NO LIVE NSE FALLBACK
    #
    # NSE live endpoint is intentionally NOT called.
    #
    # Yahoo Finance is also intentionally NOT used because
    # it does not reliably provide the required NSE
    # four-level classification.
    #
    # BSE classification is NOT substituted for NSE
    # classification because it belongs to a different
    # classification taxonomy.
    # --------------------------------------------------------

    return (
        empty_classification(),
        ""
    )

# ============================================================
# BUILD RESOLUTION RESULT
# ============================================================

def build_resolution_result(
    classification,
    source
):

    if not classification_has_any_value(
        classification
    ):

        return {

            "Macro-Economic Sector": "",

            "Sector": "",

            "Industry": "",

            "Basic Industry": "",

            "Classification Source": "",

            "Classification Confidence":
                NOT_RESOLVED,

            "Diagnosis":
                "NSE_CLASSIFICATION_NOT_AVAILABLE",
        }

    macro = normalize_text(
        classification.get(
            "Macro-Economic Sector",
            ""
        )
    )

    sector = normalize_text(
        classification.get(
            "Sector",
            ""
        )
    )

    industry = normalize_text(
        classification.get(
            "Industry",
            ""
        )
    )

    basic = normalize_text(
        classification.get(
            "Basic Industry",
            ""
        )
    )

    # --------------------------------------------------------
    # Full four-level classification.
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Three-level classification.
    # --------------------------------------------------------

    elif (
        sector
        and industry
        and basic
    ):

        confidence = MEDIUM_CONFIDENCE

        diagnosis = (
            "NSE_CLASSIFICATION_PARTIALLY_RESOLVED"
        )

    # --------------------------------------------------------
    # Partial classification.
    # --------------------------------------------------------

    else:

        confidence = LOW_CONFIDENCE

        diagnosis = (
            "NSE_CLASSIFICATION_INCOMPLETE"
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
            source,

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
    csv_classification,
    checkpoint_classification
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

        existing_sector = record[
            "Existing Sector"
        ]

        existing_industry = record[
            "Existing Industry"
        ]

        print(
            f"[{index}/{total}] "
            f"{nse_symbol} - "
            f"{company_name}"
        )

        classification, source = (
            resolve_from_sources(
                nse_symbol,
                csv_classification,
                checkpoint_classification
            )
        )

        result = build_resolution_result(
            classification,
            source
        )

        # ----------------------------------------------------
        # IMPORTANT:
        # This script is intentionally diagnostic.
        #
        # It does not manufacture classifications.
        # ----------------------------------------------------

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
                existing_sector,

            "Existing Industry":
                existing_industry,

            "NSE Classification Status":
                (
                    "RESOLVED"
                    if result[
                        "Classification Confidence"
                    ] != NOT_RESOLVED
                    else "NOT_AVAILABLE"
                ),

            "Macro-Economic Sector":
                result[
                    "Macro-Economic Sector"
                ],

            "Sector":
                result[
                    "Sector"
                ],

            "Industry":
                result[
                    "Industry"
                ],

            "Basic Industry":
                result[
                    "Basic Industry"
                ],

            "Classification Source":
                result[
                    "Classification Source"
                ],

            "Classification Confidence":
                result[
                    "Classification Confidence"
                ],

            "Diagnosis":
                result[
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
        "Writing NSE sector/industry "
        f"diagnostic rows: {len(rows)}"
    )

    # 14 columns = A:N
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


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    rows,
    csv_count,
    checkpoint_count
):

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

    csv_resolved = sum(
        1
        for row in rows
        if row[
            "Classification Source"
        ] == "NSE_CLASSIFICATION_CSV"
    )

    checkpoint_resolved = sum(
        1
        for row in rows
        if row[
            "Classification Source"
        ] == "NSE_CHECKPOINT"
    )

    print("\n")
    print("=" * 70)
    print(
        "NSE SECTOR & INDUSTRY RESOLUTION"
    )
    print("=" * 70)

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

    print("-" * 70)

    print(
        f"CSV records available  : {csv_count}"
    )

    print(
        f"Checkpoint records     : {checkpoint_count}"
    )

    print(
        f"Resolved from CSV      : {csv_resolved}"
    )

    print(
        f"Resolved from Checkpoint: "
        f"{checkpoint_resolved}"
    )

    print("-" * 70)

    if total:

        resolved = (
            high
            + medium
            + low
        )

        print(
            f"Resolution Rate        : "
            f"{(resolved / total) * 100:.1f}%"
        )

    print("-" * 70)

    print(
        "IMPORTANT:"
    )

    if unresolved == total:

        print(
            "No actual NSE classification was "
            "available for the unresolved stocks."
        )

        print(
            "The resolver did NOT guess or invent "
            "sector/industry values."
        )

    elif unresolved:

        print(
            f"{unresolved} stocks remain unresolved "
            "because no retrieved NSE classification "
            "was available."
        )

    else:

        print(
            "All currently unresolved stocks have "
            "some retrieved NSE classification data."
        )

    print("-" * 70)

    print(
        f"Diagnostic Sheet: "
        f"{DIAGNOSTIC_SHEET}"
    )

    print(
        f"Classification CSV: "
        f"{CLASSIFICATION_FILE}"
    )

    print(
        f"Checkpoint: "
        f"{CHECKPOINT_FILE}"
    )

    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        "============================================================"
    )

    print(
        "Run resolve_sector_industry.py"
    )

    print(
        "============================================================"
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
            "\nNo UNKNOWN-sector equities found."
        )

        return

    # --------------------------------------------------------
    # Load NSE classification sources.
    #
    # The generated NSE classification CSV is the
    # primary source. The checkpoint is the fallback.
    #
    # Neither source is mandatory; absence of either
    # source is treated as a data-availability condition.
    # --------------------------------------------------------

    csv_classification = (
        load_classification_master()
    )

    checkpoint_classification = (
        load_checkpoint_classification()
    )
    
    # --------------------------------------------------------
    # Resolve.
    # --------------------------------------------------------

    diagnostic_rows = (
        create_diagnostic_rows(
            records,
            csv_classification,
            checkpoint_classification
        )
    )

    # --------------------------------------------------------
    # Always write diagnostic output.
    #
    # This is important even when NSE is blocked.
    # --------------------------------------------------------

    write_diagnostic_sheet(
        spreadsheet,
        diagnostic_rows
    )

    # --------------------------------------------------------
    # Summary.
    # --------------------------------------------------------

    print_summary(
        diagnostic_rows,
        len(csv_classification),
        len(checkpoint_classification)
    )

    print(
        "\nResolver completed successfully."
    )

    print(
        "NSE unavailability is treated as a "
        "data-availability condition, not a "
        "workflow-fatal error."
    )


if __name__ == "__main__":

    main()
