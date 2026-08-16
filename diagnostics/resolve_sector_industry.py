import os
import csv
import json
from datetime import datetime, timezone

import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# CONFIGURATION
# ============================================================

STOCK_MASTER_SHEET = (
    "Stock_Master"
)

DIAGNOSTIC_SHEET = (
    "NSE_Sector_Industry_Diagnostic"
)

SPREADSHEET_ID = (
    "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"
)


# ============================================================
# FILES
# ============================================================

CLASSIFICATION_FILE = os.getenv(
    "NSE_CLASSIFICATION_FILE",
    "data/nse_industry_classification.csv"
)

CHECKPOINT_FILE = os.getenv(
    "NSE_CLASSIFICATION_CHECKPOINT",
    "data/nse_classification_checkpoint.json"
)


# ============================================================
# CONSTANTS
# ============================================================

HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
NOT_RESOLVED = "NOT_RESOLVED"

CONFLICT = "CONFLICT"

SCRIPT_VERSION = (
    "NSE_CLASSIFICATION_RESOLVER_V2"
)


UNKNOWN_VALUES = {

    "",
    "UNKNOWN",
    "N/A",
    "NA",
    "NULL",
    "NONE",

}


# ============================================================
# GOOGLE SHEETS
# ============================================================

def connect_to_google_sheet():

    print(
        "\nConnecting to Google Sheet..."
    )

    google_credentials = os.getenv(
        "GOOGLE_CREDENTIALS"
    )

    if not google_credentials:

        raise RuntimeError(
            "GOOGLE_CREDENTIALS environment "
            "variable is not configured."
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

    print(
        "Google Sheet connected."
    )

    return spreadsheet


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(value):

    if value is None:

        return ""

    return str(
        value
    ).strip()


def normalize_symbol(value):

    value = normalize_text(
        value
    ).upper()

    if value.startswith(
        "NSE:"
    ):

        value = value[4:]

    if value.endswith(
        ".NS"
    ):

        value = value[:-3]

    return value.strip()


def is_unknown(value):

    return (
        normalize_text(
            value
        ).upper()
        in UNKNOWN_VALUES
    )


# ============================================================
# HEADER HELPERS
# ============================================================

def normalize_header(value):

    return (
        normalize_text(
            value
        )
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )


def find_column(
    headers,
    candidates,
    required=True
):

    normalized = {

        normalize_header(
            header
        ):
            header

        for header in headers

    }

    for candidate in candidates:

        key = normalize_header(
            candidate
        )

        if key in normalized:

            return normalized[key]

    if required:

        raise RuntimeError(
            "Required column not found. "
            f"Tried: {candidates}"
        )

    return None


# ============================================================
# CLASSIFICATION STRUCTURE
# ============================================================

def empty_classification():

    return {

        "Macro-Economic Sector": "",

        "Sector": "",

        "Industry": "",

        "Basic Industry": "",

    }


def classification_has_any_value(
    classification
):

    if not isinstance(
        classification,
        dict
    ):

        return False

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

    if not isinstance(
        classification,
        dict
    ):

        return False

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
# CONFIDENCE
# ============================================================

def calculate_confidence(
    classification
):

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

    # Full hierarchy
    if (
        macro
        and sector
        and industry
        and basic
    ):

        return HIGH_CONFIDENCE

    # Useful three-level NSE classification
    if (
        sector
        and industry
        and basic
    ):

        return MEDIUM_CONFIDENCE

    populated = sum(
        bool(value)
        for value in [
            macro,
            sector,
            industry,
            basic
        ]
    )

    if populated >= 2:

        return MEDIUM_CONFIDENCE

    if populated == 1:

        return LOW_CONFIDENCE

    return NOT_RESOLVED


# ============================================================
# READ STOCK MASTER
# ============================================================

def read_stock_master(
    spreadsheet
):

    print(
        "\nReading Stock_Master..."
    )

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

    records = [

        {

            "Sheet Row":
                row_number,

            "Ticker":
                normalize_text(
                    row.get(
                        ticker_col,
                        ""
                    )
                ),

            "Company Name":
                normalize_text(
                    row.get(
                        company_col,
                        ""
                    )
                ),

            "Sector":
                normalize_text(
                    row.get(
                        sector_col,
                        ""
                    )
                ),

            "Industry":
                normalize_text(
                    row.get(
                        industry_col,
                        ""
                    )
                ),

        }

        for row_number, row in enumerate(
            [
                dict(
                    zip(
                        headers,
                        values[1]
                    )
                )
            ],
            start=2
        )

    ]

    # --------------------------------------------------------
    # Correct record construction
    # --------------------------------------------------------

    records = []

    for row_number, row_values in enumerate(
        values[1:],
        start=2
    ):

        record = dict(
            zip(
                headers,
                row_values
            )
        )

        records.append({

            "Sheet Row":
                row_number,

            "Ticker":
                normalize_text(
                    record.get(
                        ticker_col,
                        ""
                    )
                ),

            "Company Name":
                normalize_text(
                    record.get(
                        company_col,
                        ""
                    )
                ),

            "Sector":
                normalize_text(
                    record.get(
                        sector_col,
                        ""
                    )
                ),

            "Industry":
                normalize_text(
                    record.get(
                        industry_col,
                        ""
                    )
                ),

        })

    print(
        f"Stock_Master records: "
        f"{len(records)}"
    )

    return (
        worksheet,
        headers,
        records,
        sector_col,
        industry_col
    )


# ============================================================
# LOAD CSV CLASSIFICATION MASTER
# ============================================================

def load_classification_master():

    print(
        "\n"
        "============================================================"
    )

    print(
        "LOAD NSE CLASSIFICATION CSV"
    )

    print(
        "============================================================"
    )

    print(
        f"File: {CLASSIFICATION_FILE}"
    )

    classification = {}

    if not os.path.exists(
        CLASSIFICATION_FILE
    ):

        print(
            "CSV does not exist."
        )

        print(
            "CSV source will be skipped."
        )

        return classification

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
                    "WARNING: CSV has no headers."
                )

                return {}

            headers = reader.fieldnames

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

            basic_col = find_column(
                headers,
                [
                    "NSE Basic Industry",
                    "Basic Industry",
                    "Basic_Industry",
                    "Basic Industry Name",
                ]
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

                classification[
                    symbol
                ] = {

                    "Macro-Economic Sector":
                        normalize_text(
                            row.get(
                                macro_col,
                                ""
                            )
                        ),

                    "Sector":
                        normalize_text(
                            row.get(
                                sector_col,
                                ""
                            )
                        ),

                    "Industry":
                        normalize_text(
                            row.get(
                                industry_col,
                                ""
                            )
                        ),

                    "Basic Industry":
                        normalize_text(
                            row.get(
                                basic_col,
                                ""
                            )
                        ),

                    "Classification Source":
                        "NSE_CLASSIFICATION_CSV",

                    "Classification Retrieved At":
                        "",

                }

    except Exception as error:

        print(
            "WARNING: Could not read classification CSV."
        )

        print(
            f"Reason: {error}"
        )

        return {}

    print(
        "CSV classification records: "
        f"{len(classification)}"
    )

    return classification


# ============================================================
# LOAD CHECKPOINT
# ============================================================

def normalize_checkpoint(
    checkpoint
):

    if not isinstance(
        checkpoint,
        dict
    ):

        return {}

    classifications = checkpoint.get(
        "classifications"
    )

    if isinstance(
        classifications,
        dict
    ):

        return classifications

    # Backward compatibility with old format
    converted = {}

    for symbol, value in checkpoint.items():

        if symbol == "metadata":

            continue

        normalized = normalize_symbol(
            symbol
        )

        if (
            normalized
            and isinstance(
                value,
                dict
            )
        ):

            converted[
                normalized
            ] = value

    # Support older nested formats
    if not converted:

        for container_key in [
            "results",
            "records",
            "data",
            "classification",
            "symbols",
        ]:

            container = checkpoint.get(
                container_key
            )

            if not isinstance(
                container,
                dict
            ):

                continue

            for symbol, value in (
                container.items()
            ):

                normalized = normalize_symbol(
                    symbol
                )

                if (
                    normalized
                    and isinstance(
                        value,
                        dict
                    )
                ):

                    converted[
                        normalized
                    ] = value

    return converted


def load_checkpoint():

    print(
        "\nLoading checkpoint..."
    )

    if not os.path.exists(
        CHECKPOINT_FILE
    ):

        print(
            "No checkpoint found."
        )

        return {}

    try:

        with open(
            CHECKPOINT_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            raw = json.load(
                file
            )

    except (
        OSError,
        json.JSONDecodeError
    ) as error:

        print(
            "WARNING: Could not load checkpoint:"
        )

        print(
            f"  {error}"
        )

        return {}

    checkpoint = normalize_checkpoint(
        raw
    )

    print(
        "Checkpoint records: "
        f"{len(checkpoint)}"
    )

    return checkpoint


# ============================================================
# SUCCESS VALIDATION
# ============================================================

def is_successful_classification(
    classification
):

    if not isinstance(
        classification,
        dict
    ):

        return False

    confidence = classification.get(
        "Classification Confidence"
    )

    if confidence in {
        HIGH_CONFIDENCE,
        MEDIUM_CONFIDENCE,
        LOW_CONFIDENCE,
    }:

        return True

    # Backward compatibility:
    # old checkpoint may not contain confidence.
    return (
        calculate_confidence(
            classification
        )
        != NOT_RESOLVED
    )


# ============================================================
# NORMALIZE CHECKPOINT CLASSIFICATION
# ============================================================

def normalize_checkpoint_classification(
    classification
):

    result = empty_classification()

    if not isinstance(
        classification,
        dict
    ):

        return {

            **result,

            "Classification Source":
                "",

            "Classification Confidence":
                NOT_RESOLVED,

            "Diagnosis":
                "INVALID_CHECKPOINT_RECORD",

        }

    for field in result:

        result[field] = normalize_text(
            classification.get(
                field,
                ""
            )
        )

    result[
        "Classification Source"
    ] = normalize_text(
        classification.get(
            "Classification Source",
            "NSE_CHECKPOINT"
        )
    )

    confidence = (
        classification.get(
            "Classification Confidence"
        )
    )

    if confidence not in {
        HIGH_CONFIDENCE,
        MEDIUM_CONFIDENCE,
        LOW_CONFIDENCE,
    }:

        confidence = calculate_confidence(
            result
        )

    result[
        "Classification Confidence"
    ] = confidence

    result[
        "Diagnosis"
    ] = normalize_text(
        classification.get(
            "Diagnosis",
            "NSE_CHECKPOINT_CLASSIFICATION"
        )
    )

    result[
        "Classification Retrieved At"
    ] = normalize_text(
        classification.get(
            "Classification Retrieved At",
            ""
        )
    )

    return result


# ============================================================
# RESOLVE SOURCE
# ============================================================

def resolve_from_sources(
    symbol,
    csv_classification,
    checkpoint_classification
):

    symbol = normalize_symbol(
        symbol
    )

    csv_result = csv_classification.get(
        symbol
    )

    checkpoint_result = (
        checkpoint_classification.get(
            symbol
        )
    )

    csv_valid = (
        csv_result
        and classification_has_any_value(
            csv_result
        )
    )

    checkpoint_valid = (
        checkpoint_result
        and classification_has_any_value(
            checkpoint_result
        )
    )

    # --------------------------------------------------------
    # Both available
    #
    # Prefer checkpoint because it represents a direct NSE
    # quote retrieval and contains a retrieval timestamp.
    # --------------------------------------------------------

    if (
        csv_valid
        and checkpoint_valid
    ):

        csv_normalized = (
            normalize_checkpoint_classification(
                csv_result
            )
        )

        checkpoint_normalized = (
            normalize_checkpoint_classification(
                checkpoint_result
            )
        )

        csv_retrieved = (
            csv_normalized.get(
                "Classification Retrieved At",
                ""
            )
        )

        checkpoint_retrieved = (
            checkpoint_normalized.get(
                "Classification Retrieved At",
                ""
            )
        )

        # If timestamps are available, use the newest.
        if (
            csv_retrieved
            and checkpoint_retrieved
        ):

            if (
                checkpoint_retrieved
                >= csv_retrieved
            ):

                checkpoint_normalized[
                    "Classification Source"
                ] = "NSE_CHECKPOINT"

                return (
                    checkpoint_normalized,
                    "NSE_CHECKPOINT"
                )

            csv_normalized[
                "Classification Source"
            ] = "NSE_CLASSIFICATION_CSV"

            return (
                csv_normalized,
                "NSE_CLASSIFICATION_CSV"
            )

        # No timestamps:
        # direct NSE checkpoint wins.
        checkpoint_normalized[
            "Classification Source"
        ] = "NSE_CHECKPOINT"

        return (
            checkpoint_normalized,
            "NSE_CHECKPOINT"
        )

    # --------------------------------------------------------
    # CSV only
    # --------------------------------------------------------

    if csv_valid:

        result = (
            normalize_checkpoint_classification(
                csv_result
            )
        )

        result[
            "Classification Source"
        ] = "NSE_CLASSIFICATION_CSV"

        return (
            result,
            "NSE_CLASSIFICATION_CSV"
        )

    # --------------------------------------------------------
    # CHECKPOINT only
    # --------------------------------------------------------

    if checkpoint_valid:

        result = (
            normalize_checkpoint_classification(
                checkpoint_result
            )
        )

        result[
            "Classification Source"
        ] = "NSE_CHECKPOINT"

        return (
            result,
            "NSE_CHECKPOINT"
        )

    # --------------------------------------------------------
    # Nothing available
    # --------------------------------------------------------

    return (

        {

            **empty_classification(),

            "Classification Source":
                "",

            "Classification Confidence":
                NOT_RESOLVED,

            "Diagnosis":
                "NSE_CLASSIFICATION_NOT_AVAILABLE",

            "Classification Retrieved At":
                "",

        },

        ""

    )


# ============================================================
# UPDATE STOCK MASTER
# ============================================================

def update_stock_master(
    worksheet,
    headers,
    records,
    sector_col,
    industry_col,
    resolved_by_symbol
):

    print(
        "\n"
        "============================================================"
    )

    print(
        "UPDATING STOCK_MASTER"
    )

    print(
        "============================================================"
    )

    sector_index = (
        headers.index(
            sector_col
        )
    )

    industry_index = (
        headers.index(
            industry_col
        )
    )

    values = worksheet.get_all_values()

    updates = []

    updated_count = 0

    for record in records:

        symbol = normalize_symbol(
            record[
                "Ticker"
            ]
        )

        classification = (
            resolved_by_symbol.get(
                symbol
            )
        )

        if not classification:

            continue

        confidence = classification.get(
            "Classification Confidence"
        )

        if confidence not in {
            HIGH_CONFIDENCE,
            MEDIUM_CONFIDENCE,
        }:

            continue

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

        if not sector:

            continue

        if not industry:

            continue

        row_number = record[
            "Sheet Row"
        ]

        updates.append({

            "range":
                (
                    f"{gspread.utils.rowcol_to_a1("
                    row_number,
                    sector_index + 1
                    )}"
                ),

            "values":
                [[
                    sector
                ]],

        })

        updates.append({

            "range":
                (
                    f"{gspread.utils.rowcol_to_a1("
                    row_number,
                    industry_index + 1
                    )}"
                ),

            "values":
                [[
                    industry
                ]],

        })

        updated_count += 1

        print(
            f"{symbol}:"
        )

        print(
            f"  Sector   = {sector}"
        )

        print(
            f"  Industry = {industry}"
        )

        print(
            f"  Confidence = {confidence}"
        )

    if not updates:

        print(
            "No Stock_Master updates required."
        )

        return 0

    worksheet.batch_update(
        updates
    )

    print(
        "\nStock_Master rows updated: "
        f"{updated_count}"
    )

    return updated_count


# ============================================================
# DIAGNOSTIC SHEET
# ============================================================

def read_existing_diagnostic(
    spreadsheet
):

    try:

        worksheet = spreadsheet.worksheet(
            DIAGNOSTIC_SHEET
        )

    except gspread.WorksheetNotFound:

        return []

    values = worksheet.get_all_values()

    if len(values) <= 1:

        return []

    headers = values[0]

    records = [

        dict(
            zip(
                headers,
                row
            )
        )

        for row in values[1:]

    ]

    return records


def write_diagnostic_sheet(
    spreadsheet,
    rows
):

    headers = [

        "Run Date",

        "Run Timestamp",

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

        "Classification Retrieved At",

        "Resolver Version",

    ]

    try:

        worksheet = spreadsheet.worksheet(
            DIAGNOSTIC_SHEET
        )

    except gspread.WorksheetNotFound:

        worksheet = spreadsheet.add_worksheet(

            title=DIAGNOSTIC_SHEET,

            rows=max(
                len(rows) + 100,
                1000
            ),

            cols=len(headers)

        )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # DO NOT clear history.
    # We append the current run to the diagnostic sheet.
    # --------------------------------------------------------

    existing = (
        read_existing_diagnostic(
            spreadsheet
        )
    )

    data = [

        headers

    ]

    # Keep historical records
    for historical in existing:

        data.append([

            historical.get(
                header,
                ""
            )

            for header in headers

        ])

    # Add current records
    for row in rows:

        data.append([

            row.get(
                header,
                ""
            )

            for header in headers

        ])

    worksheet.clear()

    worksheet.update(

        range_name=(
            f"A1:Q{len(data)}"
        ),

        values=data,

        value_input_option="USER_ENTERED"

    )

    print(
        "\nDiagnostic sheet updated."
    )

    print(
        f"Historical rows retained: "
        f"{len(existing)}"
    )

    print(
        f"Current run rows added: "
        f"{len(rows)}"
    )


# ============================================================
# BUILD DIAGNOSTIC ROW
# ============================================================

def build_diagnostic_row(
    record,
    classification
):

    now = datetime.now(
        timezone.utc
    )

    confidence = classification.get(
        "Classification Confidence",
        NOT_RESOLVED
    )

    return {

        "Run Date":
            now.strftime(
                "%Y-%m-%d"
            ),

        "Run Timestamp":
            now.isoformat(),

        "Ticker":
            record[
                "Ticker"
            ],

        "NSE Symbol":
            normalize_symbol(
                record[
                    "Ticker"
                ]
            ),

        "Company Name":
            record[
                "Company Name"
            ],

        "Existing Sector":
            record[
                "Sector"
            ],

        "Existing Industry":
            record[
                "Industry"
            ],

        "NSE Classification Status":
            (
                "RESOLVED"
                if confidence
                != NOT_RESOLVED
                else "NOT_AVAILABLE"
            ),

        "Macro-Economic Sector":
            classification.get(
                "Macro-Economic Sector",
                ""
            ),

        "Sector":
            classification.get(
                "Sector",
                ""
            ),

        "Industry":
            classification.get(
                "Industry",
                ""
            ),

        "Basic Industry":
            classification.get(
                "Basic Industry",
                ""
            ),

        "Classification Source":
            classification.get(
                "Classification Source",
                ""
            ),

        "Classification Confidence":
            confidence,

        "Diagnosis":
            classification.get(
                "Diagnosis",
                ""
            ),

        "Classification Retrieved At":
            classification.get(
                "Classification Retrieved At",
                ""
            ),

        "Resolver Version":
            SCRIPT_VERSION,

    }


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        "============================================================"
    )

    print(
        "NSE SECTOR & INDUSTRY RESOLVER"
    )

    print(
        f"Version: {SCRIPT_VERSION}"
    )

    print(
        "============================================================"
    )

    spreadsheet = (
        connect_to_google_sheet()
    )

    (
        worksheet,
        headers,
        records,
        sector_col,
        industry_col
    ) = read_stock_master(
        spreadsheet
    )

    checkpoint = (
        load_checkpoint()
    )

    csv_classification = (
        load_classification_master()
    )

    resolved_by_symbol = {}

    diagnostic_rows = []

    processed = 0

    resolved = 0

    unresolved = 0

    stock_master_updated = 0

    # --------------------------------------------------------
    # Process every Stock_Master record that has a ticker.
    #
    # This allows checkpoint classifications to synchronize
    # into Stock_Master even if Stock_Master currently says
    # UNKNOWN.
    # --------------------------------------------------------

    for record in records:

        ticker = record[
            "Ticker"
        ]

        if not ticker:

            continue

        symbol = normalize_symbol(
            ticker
        )

        if not symbol:

            continue

        # ----------------------------------------------------
        # Only interesting if:
        #
        # 1. Sector is UNKNOWN
        # OR
        # 2. Checkpoint has classification
        #
        # This avoids unnecessary processing.
        # ----------------------------------------------------

        checkpoint_result = (
            checkpoint.get(
                symbol
            )
        )

        csv_result = (
            csv_classification.get(
                symbol
            )
        )

        has_checkpoint = (
            checkpoint_result
            and classification_has_any_value(
                checkpoint_result
            )
        )

        has_csv = (
            csv_result
            and classification_has_any_value(
                csv_result
            )
        )

        needs_sync = (
            is_unknown(
                record[
                    "Sector"
                ]
            )
            or has_checkpoint
            or has_csv
        )

        if not needs_sync:

            continue

        processed += 1

        print(
            "\n"
            "------------------------------------------------------------"
        )

        print(
            f"[{processed}] "
            f"{symbol} - "
            f"{record['Company Name']}"
        )

        classification, source = (
            resolve_from_sources(
                symbol,
                csv_classification,
                checkpoint
            )
        )

        confidence = calculate_confidence(
            classification
        )

        classification[
            "Classification Confidence"
        ] = confidence

        # ----------------------------------------------------
        # If classification came from CSV/checkpoint but did
        # not have a diagnosis, create one.
        # ----------------------------------------------------

        if not classification.get(
            "Diagnosis"
        ):

            classification[
                "Diagnosis"
            ] = (
                "NSE_CLASSIFICATION_RESOLVED"
                if confidence
                != NOT_RESOLVED
                else
                "NSE_CLASSIFICATION_NOT_AVAILABLE"
            )

        classification[
            "Classification Source"
        ] = source

        resolved_by_symbol[
            symbol
        ] = classification

        if confidence != NOT_RESOLVED:

            resolved += 1

        else:

            unresolved += 1

        diagnostic_rows.append(
            build_diagnostic_row(
                record,
                classification
            )
        )

    # --------------------------------------------------------
    # UPDATE STOCK MASTER
    # --------------------------------------------------------

    stock_master_updated = (
        update_stock_master(
            worksheet,
            headers,
            records,
            sector_col,
            industry_col,
            resolved_by_symbol
        )
    )

    # --------------------------------------------------------
    # WRITE DIAGNOSTICS
    # --------------------------------------------------------

    write_diagnostic_sheet(
        spreadsheet,
        diagnostic_rows
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print(
        "\n"
        "============================================================"
    )

    print(
        "FINAL RESOLUTION SUMMARY"
    )

    print(
        "============================================================"
    )

    print(
        f"Records processed       : "
        f"{processed}"
    )

    print(
        f"Resolved                : "
        f"{resolved}"
    )

    print(
        f"Not resolved            : "
        f"{unresolved}"
    )

    print(
        f"Stock_Master updated    : "
        f"{stock_master_updated}"
    )

    if processed:

        print(
            "Resolution rate         : "
            f"{(resolved / processed) * 100:.1f}%"
        )

    print(
        "------------------------------------------------------------"
    )

    print(
        f"Checkpoint file         : "
        f"{CHECKPOINT_FILE}"
    )

    print(
        f"Classification CSV      : "
        f"{CLASSIFICATION_FILE}"
    )

    print(
        f"Diagnostic sheet        : "
        f"{DIAGNOSTIC_SHEET}"
    )

    print(
        "============================================================"
    )

    print(
        "\nResolver completed."
    )


if __name__ == "__main__":

    main()
