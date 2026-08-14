import os
import csv
import json
import time
from datetime import datetime

import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# CONFIGURATION
# ============================================================

STOCK_MASTER_SHEET = "Stock_Master"

CLASSIFICATION_FILE = os.getenv(
    "BSE_CLASSIFICATION_FILE",
    "data/bse_industry_classification.csv"
)

CHECKPOINT_FILE = os.getenv(
    "BSE_CHECKPOINT_FILE",
    "data/bse_classification_checkpoint.json"
)

# ------------------------------------------------------------
# IMPORTANT
# ------------------------------------------------------------
# This script does NOT update Stock_Master.
#
# Its only purpose is:
#
# Stock_Master
#      ↓
# Identify unresolved stocks
#      ↓
# Obtain BSE classification
#      ↓
# Save classification master CSV
#
# ------------------------------------------------------------

REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 3

HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
NOT_RESOLVED = "NOT_RESOLVED"

BSE_ACCESS_OK = "BSE_ACCESS_OK"
BSE_ACCESS_BLOCKED = "BSE_ACCESS_BLOCKED"

# ------------------------------------------------------------
# BSE API
# ------------------------------------------------------------
#
# BSE exposes public API infrastructure under:
#
# https://api.bseindia.com
#
# We deliberately use the API host rather than attempting
# to scrape the BSE homepage.
#
# The exact company-classification endpoint can change.
# Therefore the endpoint is isolated in one configuration
# constant rather than scattered through the code.
#
# ------------------------------------------------------------

BSE_API_BASE = os.getenv(
    "BSE_API_BASE",
    "https://api.bseindia.com"
)

# Candidate endpoint used by the BSE public API infrastructure.
#
# If BSE changes the endpoint, this is the ONLY configuration
# value that should need changing.
#
BSE_COMPANY_ENDPOINT = os.getenv(
    "BSE_COMPANY_ENDPOINT",
    "/BseIndiaAPI/api/StockReachGraph/w"
)


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

    if value.endswith(".NSE"):

        value = value[:-4]

    return value.strip()


def normalize_bse_code(value):

    value = normalize_text(
        value
    )

    if not value:
        return ""

    # Some BSE responses may return:
    #
    # 500325
    # BSE:500325
    # 500325.XX
    #
    value = value.upper()

    if value.startswith("BSE:"):

        value = value[4:]

    if "." in value:

        value = value.split(
            ".",
            1
        )[0]

    return value.strip()


def find_column(
    headers,
    candidates,
    required=True
):

    def normalize_header(value):

        if value is None:

            return ""

        return (
            str(value)
            .strip()
            .lower()
            .replace("_", " ")
            .replace("-", " ")
        )

    normalized = {
        normalize_header(header): header
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
            f"Tried: {candidates}. "
            f"Available columns: {list(headers)}"
        )

    return None


def ensure_parent_directory(
    filepath
):

    directory = os.path.dirname(
        filepath
    )

    if directory:

        os.makedirs(
            directory,
            exist_ok=True
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
        ],
        required=False
    )

    bse_code_col = find_column(
        headers,
        [
            "BSE Code",
            "BSE_Code",
            "BSE Scrip Code",
            "Scrip Code",
            "BSE",
        ],
        required=False
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

    selected = []

    for record in records:

        sector = normalize_text(
            record.get(
                sector_col,
                ""
            )
        )

        industry = ""

        if industry_col:

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

        bse_code = ""

        if bse_code_col:

            bse_code = normalize_bse_code(
                record.get(
                    bse_code_col,
                    ""
                )
            )

        # ----------------------------------------------------
        # Only unresolved sector rows
        # ----------------------------------------------------

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

        nse_symbol = normalize_symbol(
            ticker
        )

        selected.append({

            "Ticker":
                ticker,

            "NSE Symbol":
                nse_symbol,

            "Company Name":
                company_name,

            "Existing Sector":
                sector,

            "Existing Industry":
                industry,

            "BSE Code":
                bse_code,
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
# BSE HTTP SESSION
# ============================================================

def create_bse_session():

    print(
        "\nInitializing BSE session..."
    )

    session = requests.Session()

    headers = {

        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            ),

        "Accept":
            "application/json, text/plain, */*",

        "Accept-Language":
            "en-US,en;q=0.9",

        "Referer":
            "https://www.bseindia.com/",

        "Origin":
            "https://www.bseindia.com",

        "Cache-Control":
            "no-cache",
    }

    session.headers.update(
        headers
    )

    return session


# ============================================================
# LOAD CHECKPOINT
# ============================================================

def load_checkpoint():

    if not os.path.exists(
        CHECKPOINT_FILE
    ):

        print(
            "\nNo BSE checkpoint found."
        )

        return {}

    try:

        with open(
            CHECKPOINT_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            checkpoint = json.load(
                file
            )

        print(
            "\nCheckpoint loaded:"
        )

        print(
            f"  Records: "
            f"{len(checkpoint)}"
        )

        return checkpoint

    except Exception as exc:

        print(
            "\nWARNING: Unable to load "
            f"checkpoint: {exc}"
        )

        return {}


# ============================================================
# SAVE CHECKPOINT
# ============================================================

def save_checkpoint(
    checkpoint
):

    ensure_parent_directory(
        CHECKPOINT_FILE
    )

    temporary_file = (
        CHECKPOINT_FILE
        + ".tmp"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            checkpoint,
            file,
            indent=2,
            ensure_ascii=False
        )

    os.replace(
        temporary_file,
        CHECKPOINT_FILE
    )


# ============================================================
# BSE RESPONSE EXTRACTION
# ============================================================

def recursive_find_values(
    obj,
    keys
):

    """
    Recursively search a JSON object for
    candidate field names.

    This makes the resolver more tolerant
    of BSE response-schema changes.
    """

    found = {}

    wanted = {
        key.lower()
        for key in keys
    }

    if isinstance(
        obj,
        dict
    ):

        for key, value in obj.items():

            if (
                str(key).strip().lower()
                in wanted
            ):

                found[
                    str(key).strip().lower()
                ] = value

            nested = recursive_find_values(
                value,
                keys
            )

            for nested_key, nested_value in nested.items():

                if nested_key not in found:

                    found[
                        nested_key
                    ] = nested_value

    elif isinstance(
        obj,
        list
    ):

        for item in obj:

            nested = recursive_find_values(
                item,
                keys
            )

            for nested_key, nested_value in nested.items():

                if nested_key not in found:

                    found[
                        nested_key
                    ] = nested_value

    return found


# ============================================================
# BSE CLASSIFICATION LOOKUP
# ============================================================

def get_bse_classification(
    session,
    record
):

    """
    Attempt to obtain BSE/IICS classification.

    IMPORTANT:
    This function never derives classification
    from the company name.

    A classification is accepted only when it
    is actually returned by the BSE source.
    """

    nse_symbol = record[
        "NSE Symbol"
    ]

    bse_code = record[
        "BSE Code"
    ]

    company_name = record[
        "Company Name"
    ]

    # --------------------------------------------------------
    # If Stock_Master has no BSE code, we cannot safely query
    # a BSE company-specific endpoint.
    # --------------------------------------------------------

    if not bse_code:

        return {

            "BSE Code": "",

            "BSE Macro-Economic Sector": "",

            "BSE Sector": "",

            "BSE Industry": "",

            "BSE Basic Industry": "",

            "BSE Classification Source": "",

            "BSE Classification Confidence":
                NOT_RESOLVED,

            "BSE Diagnosis":
                "BSE_CODE_NOT_AVAILABLE",

            "BSE Lookup Error": "",
        }

    url = (
        BSE_API_BASE
        + BSE_COMPANY_ENDPOINT
    )

    params = {

        "scripcode":
            bse_code,
    }

    last_error = ""

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            print(
                f"  BSE lookup: "
                f"{company_name} "
                f"[{bse_code}] "
                f"(attempt "
                f"{attempt}/{MAX_RETRIES})"
            )

            response = session.get(
                url,
                params=params,
                timeout=20
            )

            # ------------------------------------------------
            # HTTP status validation
            # ------------------------------------------------

            if response.status_code == 403:

                return {

                    "BSE Code":
                        bse_code,

                    "BSE Macro-Economic Sector":
                        "",

                    "BSE Sector":
                        "",

                    "BSE Industry":
                        "",

                    "BSE Basic Industry":
                        "",

                    "BSE Classification Source":
                        "",

                    "BSE Classification Confidence":
                        NOT_RESOLVED,

                    "BSE Diagnosis":
                        "BSE_ACCESS_BLOCKED",

                    "BSE Lookup Error":
                        "HTTP 403",
                }

            if response.status_code != 200:

                last_error = (
                    f"HTTP "
                    f"{response.status_code}"
                )

                print(
                    f"  BSE request failed: "
                    f"{last_error}"
                )

                if attempt < MAX_RETRIES:

                    time.sleep(
                        attempt * 3
                    )

                    continue

                return {

                    "BSE Code":
                        bse_code,

                    "BSE Macro-Economic Sector":
                        "",

                    "BSE Sector":
                        "",

                    "BSE Industry":
                        "",

                    "BSE Basic Industry":
                        "",

                    "BSE Classification Source":
                        "",

                    "BSE Classification Confidence":
                        NOT_RESOLVED,

                    "BSE Diagnosis":
                        "BSE_LOOKUP_FAILED",

                    "BSE Lookup Error":
                        last_error,
                }

            # ------------------------------------------------
            # Parse JSON
            # ------------------------------------------------

            try:

                payload = response.json()

            except Exception:

                last_error = (
                    "BSE response was not valid JSON"
                )

                return {

                    "BSE Code":
                        bse_code,

                    "BSE Macro-Economic Sector":
                        "",

                    "BSE Sector":
                        "",

                    "BSE Industry":
                        "",

                    "BSE Basic Industry":
                        "",

                    "BSE Classification Source":
                        "",

                    "BSE Classification Confidence":
                        NOT_RESOLVED,

                    "BSE Diagnosis":
                        "BSE_INVALID_JSON",

                    "BSE Lookup Error":
                        last_error,
                }

            # ------------------------------------------------
            # Candidate field names.
            #
            # BSE schemas can use different casing /
            # naming conventions.
            # ------------------------------------------------

            values = recursive_find_values(

                payload,

                [

                    "Macro-Economic Sector",
                    "Macro Economic Sector",
                    "MacroSector",
                    "Macro_Sector",

                    "Sector",
                    "SectorName",
                    "Sector_Name",

                    "Industry",
                    "IndustryName",
                    "Industry_Name",

                    "Basic Industry",
                    "BasicIndustry",
                    "Basic_Industry",
                    "BasicIndustryName",
                    "Basic Industry Name",
                ]
            )

            macro = ""

            sector = ""

            industry = ""

            basic = ""

            for key, value in values.items():

                normalized_key = (
                    key
                    .lower()
                    .replace("_", "")
                    .replace("-", "")
                    .replace(" ", "")
                )

                text_value = normalize_text(
                    value
                )

                if not text_value:

                    continue

                if normalized_key in {
                    "macroeconomicsector",
                    "macrosector",
                }:

                    macro = text_value

                elif normalized_key in {
                    "sector",
                    "sectorname",
                }:

                    sector = text_value

                elif normalized_key in {
                    "industry",
                    "industryname",
                }:

                    industry = text_value

                elif normalized_key in {
                    "basicindustry",
                    "basicindustryname",
                }:

                    basic = text_value

            # ------------------------------------------------
            # Confidence
            # ------------------------------------------------

            if (
                macro
                and sector
                and industry
                and basic
            ):

                confidence = HIGH_CONFIDENCE

                diagnosis = (
                    "BSE_IICS_CLASSIFICATION_RESOLVED"
                )

            elif (
                sector
                and industry
                and basic
            ):

                confidence = MEDIUM_CONFIDENCE

                diagnosis = (
                    "BSE_IICS_CLASSIFICATION_PARTIAL"
                )

            elif (
                macro
                or sector
                or industry
                or basic
            ):

                confidence = LOW_CONFIDENCE

                diagnosis = (
                    "BSE_IICS_CLASSIFICATION_INCOMPLETE"
                )

            else:

                confidence = NOT_RESOLVED

                diagnosis = (
                    "BSE_CLASSIFICATION_NOT_FOUND"
                )

            return {

                "BSE Code":
                    bse_code,

                "BSE Macro-Economic Sector":
                    macro,

                "BSE Sector":
                    sector,

                "BSE Industry":
                    industry,

                "BSE Basic Industry":
                    basic,

                "BSE Classification Source":
                    "BSE_IICS",

                "BSE Classification Confidence":
                    confidence,

                "BSE Diagnosis":
                    diagnosis,

                "BSE Lookup Error":
                    "",
            }

        except Exception as exc:

            last_error = str(exc)

            print(
                f"  BSE lookup error: "
                f"{last_error}"
            )

            if attempt < MAX_RETRIES:

                time.sleep(
                    attempt * 3
                )

    return {

        "BSE Code":
            bse_code,

        "BSE Macro-Economic Sector":
            "",

        "BSE Sector":
            "",

        "BSE Industry":
            "",

        "BSE Basic Industry":
            "",

        "BSE Classification Source":
            "",

        "BSE Classification Confidence":
            NOT_RESOLVED,

        "BSE Diagnosis":
            "BSE_LOOKUP_FAILED",

        "BSE Lookup Error":
            last_error,
    }


# ============================================================
# CREATE CLASSIFICATION RECORDS
# ============================================================

def create_classification_records(
    records,
    session,
    checkpoint
):

    run_date = datetime.now().strftime(
        "%Y-%m-%d"
    )

    classification_records = []

    total = len(records)

    for index, record in enumerate(
        records,
        start=1
    ):

        nse_symbol = record[
            "NSE Symbol"
        ]

        print(
            f"\n[{index}/{total}] "
            f"{nse_symbol} - "
            f"{record['Company Name']}"
        )

        # ----------------------------------------------------
        # Reuse checkpoint
        # ----------------------------------------------------

        if nse_symbol in checkpoint:

            result = checkpoint[
                nse_symbol
            ]

            print(
                "  Using checkpoint result."
            )

        else:

            result = get_bse_classification(
                session,
                record
            )

            checkpoint[
                nse_symbol
            ] = result

            save_checkpoint(
                checkpoint
            )

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

        classification_records.append({

            "Run Date":
                run_date,

            "Ticker":
                record["Ticker"],

            "NSE Symbol":
                nse_symbol,

            "Company Name":
                record["Company Name"],

            "BSE Code":
                result.get(
                    "BSE Code",
                    ""
                ),

            "Macro-Economic Sector":
                result.get(
                    "BSE Macro-Economic Sector",
                    ""
                ),

            "Sector":
                result.get(
                    "BSE Sector",
                    ""
                ),

            "Industry":
                result.get(
                    "BSE Industry",
                    ""
                ),

            "Basic Industry":
                result.get(
                    "BSE Basic Industry",
                    ""
                ),

            "Classification Source":
                result.get(
                    "BSE Classification Source",
                    ""
                ),

            "Classification Confidence":
                result.get(
                    "BSE Classification Confidence",
                    NOT_RESOLVED
                ),

            "Diagnosis":
                result.get(
                    "BSE Diagnosis",
                    ""
                ),

            "Lookup Error":
                result.get(
                    "BSE Lookup Error",
                    ""
                ),
        })

    return classification_records


# ============================================================
# WRITE BSE CLASSIFICATION CSV
# ============================================================

def write_classification_csv(
    rows
):

    ensure_parent_directory(
        CLASSIFICATION_FILE
    )

    headers = [

        "Run Date",

        "Ticker",

        "NSE Symbol",

        "Company Name",

        "BSE Code",

        "Macro-Economic Sector",

        "Sector",

        "Industry",

        "Basic Industry",

        "Classification Source",

        "Classification Confidence",

        "Diagnosis",

        "Lookup Error",
    ]

    temporary_file = (
        CLASSIFICATION_FILE
        + ".tmp"
    )

    with open(
        temporary_file,
        "w",
        encoding="utf-8",
        newline=""
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=headers
        )

        writer.writeheader()

        for row in rows:

            writer.writerow({

                header:
                    row.get(
                        header,
                        ""
                    )

                for header in headers
            })

    os.replace(
        temporary_file,
        CLASSIFICATION_FILE
    )

    print(
        "\nBSE classification CSV written:"
    )

    print(
        f"  {CLASSIFICATION_FILE}"
    )

    print(
        f"  Records: {len(rows)}"
    )


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    rows
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

    blocked = sum(
        1
        for row in rows
        if row[
            "Diagnosis"
        ] == "BSE_ACCESS_BLOCKED"
    )

    found = (
        high
        + medium
        + low
    )

    print("\n")
    print("=" * 60)
    print(
        "BSE CLASSIFICATION ACQUISITION"
    )
    print("=" * 60)

    print(
        f"Stock_Master Rows           : "
        f"{'N/A'}"
    )

    print(
        f"Unknown-Sector Equities     : "
        f"{total}"
    )

    print(
        f"BSE Classification Found    : "
        f"{found}"
    )

    print(
        f"High Confidence             : "
        f"{high}"
    )

    print(
        f"Medium Confidence           : "
        f"{medium}"
    )

    print(
        f"Low Confidence              : "
        f"{low}"
    )

    print(
        f"BSE Classification Missing  : "
        f"{unresolved}"
    )

    print(
        f"BSE Access Blocked          : "
        f"{blocked}"
    )

    print("-" * 60)

    if total:

        print(
            f"Resolution Rate             : "
            f"{(found / total) * 100:.1f}%"
        )

    print("-" * 60)

    print(
        f"CSV                         : "
        f"{CLASSIFICATION_FILE}"
    )

    print(
        f"Checkpoint                  : "
        f"{CHECKPOINT_FILE}"
    )

    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        "=============================================="
    )

    print(
        "UPDATE BSE INDUSTRY CLASSIFICATION"
    )

    print(
        "=============================================="
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

    checkpoint = (
        load_checkpoint()
    )

    session = (
        create_bse_session()
    )

    classification_records = (
        create_classification_records(
            records,
            session,
            checkpoint
        )
    )

    write_classification_csv(
        classification_records
    )

    print_summary(
        classification_records
    )


if __name__ == "__main__":

    main()
