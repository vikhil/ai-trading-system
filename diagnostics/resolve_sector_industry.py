import os
import csv
import json
from datetime import datetime, timezone

import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# CONFIGURATION
# ============================================================

STOCK_MASTER_SHEET = "Stock_Master"

DIAGNOSTIC_SHEET = "NSE_Sector_Industry_Diagnostic"

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
# VERSION
# ============================================================

SCRIPT_VERSION = (
    "NSE_CLASSIFICATION_RESOLVER_V4"
)


# ============================================================
# LOCAL SYNC DECISION
# ============================================================

def classification_needs_stock_master_sync(
    record,
    classification
):

    if not isinstance(
        classification,
        dict
    ):
        return False

    confidence = classification.get(
        "Classification Confidence",
        NOT_RESOLVED
    )

    if confidence not in {
        HIGH_CONFIDENCE,
        MEDIUM_CONFIDENCE,
    }:
        return False

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

    if not sector or not industry:
        return False

    existing_sector = normalize_text(
        record.get(
            "Sector",
            ""
        )
    )

    existing_industry = normalize_text(
        record.get(
            "Industry",
            ""
        )
    )

    return (
        is_unknown(existing_sector)
        or is_unknown(existing_industry)
        or existing_sector != sector
        or existing_industry != industry
    )


# ============================================================
# CONFIDENCE
# ============================================================

HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
NOT_RESOLVED = "NOT_RESOLVED"


# ============================================================
# UNKNOWN VALUES
# ============================================================

UNKNOWN_VALUES = {
    "",
    "UNKNOWN",
    "N/A",
    "NA",
    "NULL",
    "NONE",
}


# ============================================================
# SOURCE NAMES
# ============================================================

SOURCE_CSV = "NSE_CLASSIFICATION_CSV"

SOURCE_CHECKPOINT = "NSE_CHECKPOINT"


# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

def connect_to_google_sheet():

    print(
        "\n============================================================"
    )

    print(
        "CONNECTING TO GOOGLE SHEETS"
    )

    print(
        "============================================================"
    )

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

    print(
        "Google Sheet connected successfully."
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

    if value.startswith("NSE:"):

        value = value[4:]

    if value.endswith(".NS"):

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
# HEADER NORMALIZATION
# ============================================================

def normalize_header(value):

    return (
        normalize_text(value)
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )


def find_column(
    headers,
    candidates,
    required=True
):

    normalized_headers = {

        normalize_header(header):
            header

        for header in headers

    }

    for candidate in candidates:

        normalized_candidate = (
            normalize_header(
                candidate
            )
        )

        if normalized_candidate in normalized_headers:

            return normalized_headers[
                normalized_candidate
            ]

    if required:

        raise RuntimeError(
            "Required column not found. "
            f"Tried: {candidates}"
        )

    return None


# ============================================================
# EMPTY CLASSIFICATION
# ============================================================

def empty_classification():

    return {

        "Macro-Economic Sector": "",

        "Sector": "",

        "Industry": "",

        "Basic Industry": "",

        "Classification Source": "",

        "Classification Retrieved At": "",

        "Classification Confidence":
            NOT_RESOLVED,

        "Diagnosis":
            "NSE_CLASSIFICATION_NOT_AVAILABLE",

    }


# ============================================================
# CLASSIFICATION HELPERS
# ============================================================

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


def classification_has_sector_and_industry(
    classification
):

    if not isinstance(
        classification,
        dict
    ):

        return False

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

    return bool(
        sector
        and industry
    )


# ============================================================
# CONFIDENCE
# ============================================================

def calculate_confidence(
    classification
):

    if not isinstance(
        classification,
        dict
    ):

        return NOT_RESOLVED

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
    # COMPLETE NSE FOUR-LEVEL CLASSIFICATION
    # --------------------------------------------------------

    if (
        macro
        and sector
        and industry
        and basic
    ):

        return HIGH_CONFIDENCE

    # --------------------------------------------------------
    # USABLE THREE-LEVEL CLASSIFICATION
    #
    # Sector + Industry + Basic Industry
    # --------------------------------------------------------

    if (
        sector
        and industry
        and basic
    ):

        return MEDIUM_CONFIDENCE

    # --------------------------------------------------------
    # SECTOR + INDUSTRY AVAILABLE
    #
    # This is sufficient for Stock_Master synchronization.
    # --------------------------------------------------------

    if (
        sector
        and industry
    ):

        return MEDIUM_CONFIDENCE

    # --------------------------------------------------------
    # PARTIAL DATA
    # --------------------------------------------------------

    populated = sum(

        bool(value)

        for value in [

            macro,
            sector,
            industry,
            basic,

        ]

    )

    if populated >= 2:

        return MEDIUM_CONFIDENCE

    if populated == 1:

        return LOW_CONFIDENCE

    return NOT_RESOLVED


# ============================================================
# NORMALIZE CLASSIFICATION RECORD
# ============================================================

def normalize_classification(
    classification,
    default_source=""
):

    result = empty_classification()

    if not isinstance(
        classification,
        dict
    ):

        return result

    result[
        "Macro-Economic Sector"
    ] = normalize_text(
        classification.get(
            "Macro-Economic Sector",
            classification.get(
                "Macro Economic Sector",
                classification.get(
                    "macro",
                    ""
                )
            )
        )
    )

    result[
        "Sector"
    ] = normalize_text(
        classification.get(
            "Sector",
            classification.get(
                "sector",
                ""
            )
        )
    )

    result[
        "Industry"
    ] = normalize_text(
        classification.get(
            "Industry",
            classification.get(
                "industry",
                ""
            )
        )
    )

    result[
        "Basic Industry"
    ] = normalize_text(
        classification.get(
            "Basic Industry",
            classification.get(
                "Basic_Industry",
                classification.get(
                    "basic_industry",
                    ""
                )
            )
        )
    )

    result[
        "Classification Source"
    ] = normalize_text(
        classification.get(
            "Classification Source",
            classification.get(
                "source",
                default_source
            )
        )
    )

    result[
        "Classification Retrieved At"
    ] = normalize_text(
        classification.get(
            "Classification Retrieved At",
            classification.get(
                "retrieved_at",
                classification.get(
                    "timestamp",
                    ""
                )
            )
        )
    )

    result[
        "Classification Confidence"
    ] = calculate_confidence(
        result
    )

    result[
        "Diagnosis"
    ] = normalize_text(
        classification.get(
            "Diagnosis",
            ""
        )
    )

    return result


# ============================================================
# READ STOCK MASTER
# ============================================================

def read_stock_master(
    spreadsheet
):

    print(
        "\n============================================================"
    )

    print(
        "READING STOCK_MASTER"
    )

    print(
        "============================================================"
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
        "\nStock_Master columns:"
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

        ticker = normalize_text(
            record.get(
                ticker_col,
                ""
            )
        )

        if not ticker:

            continue

        records.append({

            "Sheet Row":
                row_number,

            "Ticker":
                ticker,

            "NSE Symbol":
                normalize_symbol(
                    ticker
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
        f"\nStock_Master valid ticker rows: "
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
        "\n============================================================"
    )

    print(
        "LOADING NSE CLASSIFICATION CSV"
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
            "CSV not found."
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
                    "WARNING: CSV contains no headers."
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
                    "Macro",
                ],
                required=False
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
                ],
                required=False
            )

            retrieved_col = find_column(
                headers,
                [
                    "Classification Retrieved At",
                    "Retrieved At",
                    "Timestamp",
                    "Retrieved Timestamp",
                ],
                required=False
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

                record = {

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
                        )
                        if basic_col
                        else "",

                    "Classification Source":
                        SOURCE_CSV,

                    "Classification Retrieved At":
                        normalize_text(
                            row.get(
                                retrieved_col,
                                ""
                            )
                        )
                        if retrieved_col
                        else "",

                }

                record[
                    "Classification Confidence"
                ] = calculate_confidence(
                    record
                )

                classification[
                    symbol
                ] = record

    except Exception as error:

        print(
            "WARNING: Unable to read NSE "
            "classification CSV."
        )

        print(
            f"Reason: {error}"
        )

        return {}

    print(
        f"CSV classification records: "
        f"{len(classification)}"
    )

    return classification


# ============================================================
# CHECKPOINT NORMALIZATION
# ============================================================

def normalize_checkpoint(
    raw_checkpoint
):

    if not isinstance(
        raw_checkpoint,
        dict
    ):

        return {}

    # --------------------------------------------------------
    # Preferred current format
    # --------------------------------------------------------

    classifications = (
        raw_checkpoint.get(
            "classifications"
        )
    )

    if isinstance(
        classifications,
        dict
    ):

        source = classifications

    else:

        source = {}

    # --------------------------------------------------------
    # Backward-compatible formats
    # --------------------------------------------------------

    containers = []

    if source:

        containers.append(
            source
        )

    containers.append(
        raw_checkpoint
    )

    for key in [

        "results",
        "records",
        "data",
        "classification",
        "symbols",

    ]:

        container = raw_checkpoint.get(
            key
        )

        if isinstance(
            container,
            dict
        ):

            containers.append(
                container
            )

    normalized = {}

    for container in containers:

        for raw_symbol, raw_value in (
            container.items()
        ):

            if raw_symbol == "metadata":

                continue

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

            classification = (
                normalize_classification(
                    candidate,
                    SOURCE_CHECKPOINT
                )
            )

            if classification_has_any_value(
                classification
            ):

                classification[
                    "Classification Source"
                ] = SOURCE_CHECKPOINT

                normalized[
                    symbol
                ] = classification

    return normalized


# ============================================================
# LOAD CHECKPOINT
# ============================================================

def load_checkpoint():

    print(
        "\n============================================================"
    )

    print(
        "LOADING NSE CHECKPOINT"
    )

    print(
        "============================================================"
    )

    print(
        f"File: {CHECKPOINT_FILE}"
    )

    if not os.path.exists(
        CHECKPOINT_FILE
    ):

        print(
            "Checkpoint not found."
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
            "WARNING: Unable to load checkpoint."
        )

        print(
            f"Reason: {error}"
        )

        return {}

    checkpoint = normalize_checkpoint(
        raw
    )

    print(
        f"Checkpoint classification records: "
        f"{len(checkpoint)}"
    )

    return checkpoint


# ============================================================
# SOURCE QUALITY
# ============================================================

def source_quality(
    classification
):

    """
    Higher number = better source.

    4 = complete CSV
    3 = complete checkpoint
    2 = partial CSV
    1 = partial checkpoint
    0 = unusable
    """

    if not classification_has_any_value(
        classification
    ):

        return 0

    source = normalize_text(
        classification.get(
            "Classification Source",
            ""
        )
    )

    complete = classification_is_complete(
        classification
    )

    if (
        source == SOURCE_CSV
        and complete
    ):

        return 4

    if (
        source == SOURCE_CHECKPOINT
        and complete
    ):

        return 3

    if (
        source == SOURCE_CSV
        and classification_has_sector_and_industry(
            classification
        )
    ):

        return 2

    if (
        source == SOURCE_CHECKPOINT
        and classification_has_sector_and_industry(
            classification
        )
    ):

        return 1

    # A source with only macro/basic etc.
    # is not sufficient to update Stock_Master.

    return 0


# ============================================================
# RESOLUTION HIERARCHY
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

    csv_result = normalize_classification(
        csv_result,
        SOURCE_CSV
    ) if csv_result else None

    checkpoint_result = (
        normalize_classification(
            checkpoint_result,
            SOURCE_CHECKPOINT
        )
        if checkpoint_result
        else None
    )

    candidates = []

    if csv_result:

        csv_result[
            "Classification Source"
        ] = SOURCE_CSV

        candidates.append(
            csv_result
        )

    if checkpoint_result:

        checkpoint_result[
            "Classification Source"
        ] = SOURCE_CHECKPOINT

        candidates.append(
            checkpoint_result
        )

    if not candidates:

        return empty_classification()

    # --------------------------------------------------------
    # Sort by strict source hierarchy.
    #
    # Complete CSV
    #     ↓
    # Complete checkpoint
    #     ↓
    # Partial CSV
    #     ↓
    # Partial checkpoint
    #     ↓
    # NOT_RESOLVED
    # --------------------------------------------------------

    candidates.sort(
        key=lambda item: (
            source_quality(item),
            normalize_text(
                item.get(
                    "Classification Retrieved At",
                    ""
                )
            )
        ),
        reverse=True
    )

    best = candidates[0]

    if source_quality(best) == 0:

        return empty_classification()

    best[
        "Classification Confidence"
    ] = calculate_confidence(
        best
    )

    if classification_is_complete(
        best
    ):

        best[
            "Diagnosis"
        ] = (
            "NSE_CLASSIFICATION_COMPLETE"
        )

    elif classification_has_sector_and_industry(
        best
    ):

        best[
            "Diagnosis"
        ] = (
            "NSE_CLASSIFICATION_PARTIAL"
        )

    else:

        best[
            "Classification Confidence"
        ] = NOT_RESOLVED

        best[
            "Diagnosis"
        ] = (
            "NSE_CLASSIFICATION_NOT_USABLE"
        )

    return best


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
        "\n============================================================"
    )

    print(
        "SYNCHRONIZING STOCK_MASTER"
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

    updates = []

    updated_symbols = set()

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
            "Classification Confidence",
            NOT_RESOLVED
        )

        # ----------------------------------------------------
        # Only HIGH or MEDIUM classifications can synchronize
        # Sector/Industry.
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # NEVER write incomplete Sector/Industry data.
        # ----------------------------------------------------

        if not sector:

            continue

        if not industry:

            continue

        row_number = record[
            "Sheet Row"
        ]

        existing_sector = normalize_text(
            record[
                "Sector"
            ]
        )

        existing_industry = normalize_text(
            record[
                "Industry"
            ]
        )

        # ----------------------------------------------------
        # Do not rewrite identical values.
        # ----------------------------------------------------

        sector_changed = (
            existing_sector
            != sector
        )

        industry_changed = (
            existing_industry
            != industry
        )

        if not sector_changed and not industry_changed:

            print(
                f"{symbol}: Stock_Master already "
                "contains correct classification."
            )

            continue

        if sector_changed:

            updates.append({

                "range":
                    gspread.utils.rowcol_to_a1(
                        row_number,
                        sector_index + 1
                    ),

                "values":
                    [[
                        sector
                    ]],

            })

        if industry_changed:

            updates.append({

                "range":
                    gspread.utils.rowcol_to_a1(
                        row_number,
                        industry_index + 1
                    ),

                "values":
                    [[
                        industry
                    ]],

            })

        updated_symbols.add(
            symbol
        )

        print(
            f"{symbol}:"
        )

        print(
            f"  Sector       : {sector}"
        )

        print(
            f"  Industry     : {industry}"
        )

        print(
            f"  Confidence   : {confidence}"
        )

        print(
            f"  Source       : "
            f"{classification.get('Classification Source', '')}"
        )

    if not updates:

        print(
            "\nNo Stock_Master changes required."
        )

        return 0

    worksheet.batch_update(
        updates
    )

    print(
        "\nStock_Master successfully updated."
    )

    print(
        f"Rows changed: "
        f"{len(updated_symbols)}"
    )

    return len(updated_symbols)


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
            record[
                "NSE Symbol"
            ],

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
# READ EXISTING DIAGNOSTIC
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

    records = []

    for row in values[1:]:

        records.append(
            dict(
                zip(
                    headers,
                    row
                )
            )
        )

    return records


# ============================================================
# WRITE DIAGNOSTIC
# ============================================================

def write_diagnostic_sheet(
    spreadsheet,
    rows
):

    print(
        "\n============================================================"
    )

    print(
        "UPDATING DIAGNOSTIC SHEET"
    )

    print(
        "============================================================"
    )

    if not rows:

        print(
            "No new diagnostic rows. Existing diagnostic history "
            "will not be rewritten."
        )

        return

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

        print(
            f"Creating worksheet: "
            f"{DIAGNOSTIC_SHEET}"
        )

        worksheet = spreadsheet.add_worksheet(

            title=DIAGNOSTIC_SHEET,

            rows=max(
                len(rows) + 100,
                1000
            ),

            cols=len(headers)

        )

    existing = (
        read_existing_diagnostic(
            spreadsheet
        )
    )

    data = [
        headers
    ]

    # --------------------------------------------------------
    # Preserve history.
    # --------------------------------------------------------

    for historical in existing:

        data.append([

            historical.get(
                header,
                ""
            )

            for header in headers

        ])

    # --------------------------------------------------------
    # Add current run.
    # --------------------------------------------------------

    for row in rows:

        data.append([

            row.get(
                header,
                ""
            )

            for header in headers

        ])

    worksheet.clear()

    end_row = max(
        len(data),
        1
    )

    worksheet.update(

        range_name=(
            f"A1:Q{end_row}"
        ),

        values=data,

        value_input_option="USER_ENTERED"

    )

    print(
        f"Historical diagnostic rows retained: "
        f"{len(existing)}"
    )

    print(
        f"Current diagnostic rows added: "
        f"{len(rows)}"
    )


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

    # --------------------------------------------------------
    # 1. CONNECT TO GOOGLE SHEETS
    # --------------------------------------------------------

    spreadsheet = (
        connect_to_google_sheet()
    )

    # --------------------------------------------------------
    # 2. READ STOCK MASTER
    # --------------------------------------------------------

    (
        worksheet,
        headers,
        records,
        sector_col,
        industry_col
    ) = read_stock_master(
        spreadsheet
    )

    # --------------------------------------------------------
    # 3. LOAD SOURCES
    # --------------------------------------------------------

    checkpoint = (
        load_checkpoint()
    )

    csv_classification = (
        load_classification_master()
    )

    # --------------------------------------------------------
    # 4. RESOLVE
    # --------------------------------------------------------

    resolved_by_symbol = {}

    diagnostic_rows = []

    processed = 0

    resolved = 0

    unresolved = 0

    source_csv = 0

    source_checkpoint = 0

    high = 0

    medium = 0

    low = 0

    # --------------------------------------------------------
    # Process only records that:
    #
    #   A. currently have UNKNOWN Sector
    #
    # OR
    #
    #   B. have an NSE classification available for sync
    #
    # This allows a previously collected NSE classification
    # to repair Stock_Master without processing every stock.
    # --------------------------------------------------------

    for record in records:

        symbol = record[
            "NSE Symbol"
        ]

        if not symbol:

            continue

        current_sector = record[
            "Sector"
        ]

        current_industry = record[
            "Industry"
        ]

        csv_result = (
            csv_classification.get(
                symbol
            )
        )

        checkpoint_result = (
            checkpoint.get(
                symbol
            )
        )

        # ----------------------------------------------------
        # Resolve the local sources first. This is cheap and does
        # NOT make an NSE request.
        #
        # IMPORTANT: Do NOT use "has_csv or has_checkpoint" as a
        # processing trigger. That caused every already-resolved
        # stock to be processed on every 30-minute workflow run.
        # ----------------------------------------------------

        local_classification = (
            resolve_from_sources(
                symbol,
                csv_classification,
                checkpoint
            )
        )

        needs_processing = (
            is_unknown(current_sector)
            or is_unknown(current_industry)
            or classification_needs_stock_master_sync(
                record,
                local_classification
            )
        )

        if not needs_processing:

            continue

        processed += 1

        print(
            "\n------------------------------------------------------------"
        )

        print(
            f"[{processed}] "
            f"{symbol} - "
            f"{record['Company Name']}"
        )

        print(
            f"Existing Sector   : "
            f"{current_sector}"
        )

        print(
            f"Existing Industry : "
            f"{current_industry}"
        )

        # ----------------------------------------------------
        # SOURCE RESOLUTION
        # ----------------------------------------------------

        classification = local_classification

        confidence = calculate_confidence(
            classification
        )

        classification[
            "Classification Confidence"
        ] = confidence

        # ----------------------------------------------------
        # Diagnosis
        # ----------------------------------------------------

        if confidence == NOT_RESOLVED:

            classification[
                "Diagnosis"
            ] = (
                "NSE_CLASSIFICATION_NOT_AVAILABLE"
            )

        elif classification_is_complete(
            classification
        ):

            classification[
                "Diagnosis"
            ] = (
                "NSE_CLASSIFICATION_COMPLETE"
            )

        elif classification_has_sector_and_industry(
            classification
        ):

            classification[
                "Diagnosis"
            ] = (
                "NSE_CLASSIFICATION_PARTIAL"
            )

        else:

            classification[
                "Diagnosis"
            ] = (
                "NSE_CLASSIFICATION_INCOMPLETE"
            )

            classification[
                "Classification Confidence"
            ] = NOT_RESOLVED

            confidence = NOT_RESOLVED

        resolved_by_symbol[
            symbol
        ] = classification

        # ----------------------------------------------------
        # Statistics
        # ----------------------------------------------------

        if confidence == HIGH_CONFIDENCE:

            high += 1

        elif confidence == MEDIUM_CONFIDENCE:

            medium += 1

        elif confidence == LOW_CONFIDENCE:

            low += 1

        else:

            unresolved += 1

        if confidence != NOT_RESOLVED:

            resolved += 1

        source = classification.get(
            "Classification Source",
            ""
        )

        if source == SOURCE_CSV:

            source_csv += 1

        elif source == SOURCE_CHECKPOINT:

            source_checkpoint += 1

        # ----------------------------------------------------
        # Display result
        # ----------------------------------------------------

        print(
            f"Resolved Sector   : "
            f"{classification.get('Sector', '')}"
        )

        print(
            f"Resolved Industry : "
            f"{classification.get('Industry', '')}"
        )

        print(
            f"Basic Industry    : "
            f"{classification.get('Basic Industry', '')}"
        )

        print(
            f"Source            : "
            f"{source}"
        )

        print(
            f"Confidence        : "
            f"{confidence}"
        )

        print(
            f"Diagnosis         : "
            f"{classification.get('Diagnosis', '')}"
        )

        # ----------------------------------------------------
        # Diagnostic record
        # ----------------------------------------------------

        diagnostic_rows.append(
            build_diagnostic_row(
                record,
                classification
            )
        )

    # --------------------------------------------------------
    # 5. UPDATE STOCK MASTER
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
    # 6. WRITE DIAGNOSTICS
    # --------------------------------------------------------

    write_diagnostic_sheet(
        spreadsheet,
        diagnostic_rows
    )

    # --------------------------------------------------------
    # 7. SUMMARY
    # --------------------------------------------------------

    print(
        "\n"
        "============================================================"
    )

    print(
        "FINAL NSE CLASSIFICATION SUMMARY"
    )

    print(
        "============================================================"
    )

    print(
        f"Records processed       : "
        f"{processed}"
    )

    print(
        f"High Confidence        : "
        f"{high}"
    )

    print(
        f"Medium Confidence      : "
        f"{medium}"
    )

    print(
        f"Low Confidence         : "
        f"{low}"
    )

    print(
        f"Not Resolved            : "
        f"{unresolved}"
    )

    print(
        "------------------------------------------------------------"
    )

    print(
        f"Resolved from CSV       : "
        f"{source_csv}"
    )

    print(
        f"Resolved from Checkpoint: "
        f"{source_checkpoint}"
    )

    print(
        "------------------------------------------------------------"
    )

    print(
        f"Stock_Master rows updated: "
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
        f"Classification CSV      : "
        f"{CLASSIFICATION_FILE}"
    )

    print(
        f"Checkpoint              : "
        f"{CHECKPOINT_FILE}"
    )

    print(
        f"Diagnostic Sheet        : "
        f"{DIAGNOSTIC_SHEET}"
    )

    print(
        f"Resolver Version        : "
        f"{SCRIPT_VERSION}"
    )

    print(
        "============================================================"
    )

    print(
        "\nResolver completed successfully."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
