import os
import json
import time
import random
from datetime import datetime

import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# CONFIGURATION
# ============================================================

STOCK_MASTER_SHEET = "Stock_Master"

DIAGNOSTIC_SHEET = (
    "NSE_Sector_Industry_Diagnostic"
)

SPREADSHEET_ID = (
    "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"
)

NSE_BASE_URL = (
    "https://www.nseindia.com"
)

NSE_HOME_URL = (
    "https://www.nseindia.com/"
)

NSE_QUOTE_PAGE_URL = (
    "https://www.nseindia.com/get-quotes/equity"
)

NSE_QUOTE_API_URL = (
    "https://www.nseindia.com/api/quote-equity"
)


# ============================================================
# CHECKPOINT
# ============================================================

CHECKPOINT_FILE = os.getenv(
    "NSE_CLASSIFICATION_CHECKPOINT",
    "data/nse_classification_checkpoint.json"
)


# ============================================================
# REQUEST CONTROLS
# ============================================================

REQUEST_TIMEOUT = int(
    os.getenv(
        "NSE_CLASSIFICATION_TIMEOUT",
        "30"
    )
)

# IMPORTANT:
#
# This is NOT the number of retries for 403.
#
# 403 is a circuit-breaker condition and is NEVER retried.
#
# These retries are only for genuinely transient conditions
# such as 429 / 5xx / connection failures.
#
MAX_TRANSIENT_RETRIES = int(
    os.getenv(
        "NSE_CLASSIFICATION_MAX_RETRIES",
        "2"
    )
)

MIN_DELAY = float(
    os.getenv(
        "NSE_CLASSIFICATION_MIN_DELAY",
        "5.0"
    )
)

MAX_DELAY = float(
    os.getenv(
        "NSE_CLASSIFICATION_MAX_DELAY",
        "10.0"
    )
)

CHECKPOINT_EVERY = int(
    os.getenv(
        "NSE_CLASSIFICATION_CHECKPOINT_EVERY",
        "5"
    )
)


# ============================================================
# STATUS / CONFIDENCE CONSTANTS
# ============================================================

HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
NOT_RESOLVED = "NOT_RESOLVED"

NSE_ACCESS_BLOCKED = (
    "NSE_ACCESS_BLOCKED"
)

NSE_ACCESS_AVAILABLE = (
    "NSE_ACCESS_AVAILABLE"
)

NSE_ACCESS_UNKNOWN = (
    "NSE_ACCESS_UNKNOWN"
)


# ============================================================
# TRANSIENT HTTP STATUSES
# ============================================================

TRANSIENT_STATUSES = {
    429,
    500,
    502,
    503,
    504,
}


# ============================================================
# GOOGLE SHEETS
# ============================================================

def connect_to_google_sheet():

    print(
        "Connecting to Google Sheet..."
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

    value = normalize_text(
        value
    ).upper()

    if value.startswith("NSE:"):

        value = value[4:]

    if value.endswith(".NS"):

        value = value[:-3]

    return value.strip()


# ============================================================
# COLUMN HELPER
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

    normalized = {

        normalize_header(header):
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
# READ STOCK MASTER
# ============================================================

def read_unknown_stocks(
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

        if not ticker:
            continue

        # Only process currently unresolved
        # sector records.

        if sector.upper() not in {

            "",
            "UNKNOWN",
            "N/A",
            "NA",
            "NULL",
            "NONE"

        }:

            continue

        nse_symbol = normalize_symbol(
            ticker
        )

        if not nse_symbol:
            continue

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

        })

    print(
        f"\nStock Master Rows: "
        f"{len(records)}"
    )

    print(
        "Unknown-Sector Equity Rows: "
        f"{len(selected)}"
    )

    return selected


# ============================================================
# NSE SESSION
# ============================================================

def create_nse_session():

    session = requests.Session()

    session.headers.update({

        "User-Agent":
            (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 "
                "Safari/537.36"
            ),

        "Accept":
            "application/json,text/plain,*/*",

        "Accept-Language":
            "en-US,en;q=0.9",

        "Accept-Encoding":
            "gzip, deflate",

        "Connection":
            "keep-alive",

        "DNT":
            "1",

    })

    return session


# ============================================================
# NSE SESSION INITIALIZATION
# ============================================================

def initialize_nse_session(
    session
):

    print(
        "\nInitializing / refreshing NSE session..."
    )

    try:

        response = session.get(
            NSE_HOME_URL,
            timeout=REQUEST_TIMEOUT
        )

        print(
            "NSE homepage status: "
            f"{response.status_code}"
        )

        if response.status_code == 200:

            print(
                "NSE homepage accessible."
            )

            return True

        print(
            "WARNING: NSE homepage returned "
            f"HTTP {response.status_code}"
        )

        return False

    except requests.RequestException as error:

        print(
            "WARNING: NSE homepage request failed:"
        )

        print(
            f"  {error}"
        )

        return False


# ============================================================
# CHECKPOINT
# ============================================================

def load_checkpoint():

    if not os.path.exists(
        CHECKPOINT_FILE
    ):

        print(
            "\nNo NSE checkpoint found."
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

        if not isinstance(
            checkpoint,
            dict
        ):

            print(
                "WARNING: Invalid checkpoint "
                "format. Starting fresh."
            )

            return {}

        print(
            "\nCheckpoint loaded:"
        )

        print(
            f"  Records: "
            f"{len(checkpoint)}"
        )

        return checkpoint

    except (
        OSError,
        json.JSONDecodeError
    ) as error:

        print(
            "WARNING: Could not load "
            "checkpoint:"
        )

        print(
            f"  {error}"
        )

        return {}


def save_checkpoint(
    checkpoint
):

    directory = os.path.dirname(
        CHECKPOINT_FILE
    )

    if directory:

        os.makedirs(
            directory,
            exist_ok=True
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

    print(
        "Checkpoint saved."
    )


# ============================================================
# CHECKPOINT CLASSIFICATION VALIDATION
# ============================================================

def is_successful_classification(
    classification
):

    if not isinstance(
        classification,
        dict
    ):

        return False

    return (
        classification.get(
            "Classification Confidence"
        )
        in {
            HIGH_CONFIDENCE,
            MEDIUM_CONFIDENCE,
            LOW_CONFIDENCE
        }
    )


# ============================================================
# NSE QUOTE API REQUEST
# ============================================================

def request_nse_quote(
    session,
    symbol
):

    symbol = normalize_symbol(
        symbol
    )

    headers = {

        "Referer":
            (
                f"{NSE_QUOTE_PAGE_URL}"
                f"?symbol={symbol}"
            ),

        "Accept":
            (
                "application/json,"
                "text/plain,*/*"
            ),

        "X-Requested-With":
            "XMLHttpRequest",

    }

    transient_attempt = 0

    while True:

        print(
            f"    NSE quote request "
            f"(transient attempt "
            f"{transient_attempt + 1}/"
            f"{MAX_TRANSIENT_RETRIES + 1})"
        )

        try:

            response = session.get(

                NSE_QUOTE_API_URL,

                params={
                    "symbol": symbol
                },

                headers=headers,

                timeout=REQUEST_TIMEOUT

            )

        except requests.RequestException as error:

            print(
                "    NSE request exception:"
            )

            print(
                f"    {error}"
            )

            if (
                transient_attempt
                >= MAX_TRANSIENT_RETRIES
            ):

                return {

                    "success":
                        False,

                    "access_blocked":
                        False,

                    "payload":
                        {},

                    "error":
                        "NSE_REQUEST_EXCEPTION",

                }

            transient_attempt += 1

            delay = min(
                30,
                (
                    3
                    * (
                        2
                        ** (
                            transient_attempt - 1
                        )
                    )
                )
                + random.uniform(
                    1,
                    3
                )
            )

            print(
                "    Retrying transient "
                f"error after {delay:.1f}s"
            )

            time.sleep(
                delay
            )

            continue

        status = (
            response.status_code
        )

        print(
            f"    HTTP status: {status}"
        )

        # ====================================================
        # CRITICAL: 403 CIRCUIT BREAKER
        # ====================================================

        if status == 403:

            print(
                "\n"
                "    ************************************************"
            )

            print(
                "    NSE QUOTE API RETURNED 403."
            )

            print(
                "    Treating NSE quote access as BLOCKED."
            )

            print(
                "    NO RETRY."
            )

            print(
                "    NO SESSION REFRESH."
            )

            print(
                "    NO ADDITIONAL NSE REQUESTS."
            )

            print(
                "    ************************************************"
            )

            return {

                "success":
                    False,

                "access_blocked":
                    True,

                "payload":
                    {},

                "error":
                    NSE_ACCESS_BLOCKED,

            }

        # ====================================================
        # SUCCESS
        # ====================================================

        if status == 200:

            try:

                payload = response.json()

            except ValueError:

                return {

                    "success":
                        False,

                    "access_blocked":
                        False,

                    "payload":
                        {},

                    "error":
                        "NSE_NON_JSON_RESPONSE",

                }

            if isinstance(
                payload,
                dict
            ):

                return {

                    "success":
                        True,

                    "access_blocked":
                        False,

                    "payload":
                        payload,

                    "error":
                        "",

                }

            return {

                "success":
                    False,

                "access_blocked":
                    False,

                "payload":
                    {},

                "error":
                    "NSE_INVALID_JSON_PAYLOAD",

            }

        # ====================================================
        # TRANSIENT HTTP ERRORS
        # ====================================================

        if status in TRANSIENT_STATUSES:

            print(
                "    Temporary NSE/server "
                f"condition: HTTP {status}"
            )

            if (
                transient_attempt
                >= MAX_TRANSIENT_RETRIES
            ):

                return {

                    "success":
                        False,

                    "access_blocked":
                        False,

                    "payload":
                        {},

                    "error":
                        (
                            "NSE_TRANSIENT_HTTP_"
                            f"{status}"
                        ),

                }

            transient_attempt += 1

            retry_delay = min(
                30,
                (
                    3
                    * (
                        2
                        ** (
                            transient_attempt - 1
                        )
                    )
                )
                + random.uniform(
                    1,
                    3
                )
            )

            print(
                "    Retrying after "
                f"{retry_delay:.1f}s"
            )

            time.sleep(
                retry_delay
            )

            continue

        # ====================================================
        # OTHER HTTP ERRORS
        # ====================================================

        return {

            "success":
                False,

            "access_blocked":
                False,

            "payload":
                {},

            "error":
                (
                    "NSE_HTTP_STATUS_"
                    f"{status}"
                ),

        }


# ============================================================
# ACTUAL NSE ACCESS PROBE
# ============================================================

def probe_nse_quote_access(
    session,
    symbol
):

    print(
        "\n============================================================"
    )

    print(
        "NSE QUOTE ENDPOINT ACCESS PROBE"
    )

    print(
        f"Probe symbol: {symbol}"
    )

    print(
        "This probe tests the ACTUAL quote API."
    )

    print(
        "Homepage HTTP 200 alone is NOT considered sufficient."
    )

    print(
        "============================================================"
    )

    result = request_nse_quote(
        session,
        symbol
    )

    if result["success"]:

        print(
            "\nNSE quote endpoint probe: SUCCESS"
        )

        return (
            NSE_ACCESS_AVAILABLE,
            result
        )

    if result["access_blocked"]:

        print(
            "\n"
            "============================================================"
        )

        print(
            "NSE QUOTE ACCESS: BLOCKED"
        )

        print(
            "Circuit breaker activated."
        )

        print(
            "The workflow will NOT issue additional "
            "NSE quote requests."
        )

        print(
            "============================================================"
        )

        return (
            NSE_ACCESS_BLOCKED,
            result
        )

    print(
        "\nNSE quote endpoint probe did not succeed:"
    )

    print(
        f"  {result['error']}"
    )

    return (
        NSE_ACCESS_UNKNOWN,
        result
    )


# ============================================================
# EXTRACT INDUSTRY INFORMATION
# ============================================================

def extract_industry_info(
    payload
):

    if not isinstance(
        payload,
        dict
    ):

        return {

            "Macro-Economic Sector":
                "",

            "Sector":
                "",

            "Industry":
                "",

            "Basic Industry":
                "",

            "success":
                False,

            "error":
                "INVALID_NSE_PAYLOAD",

        }

    industry_info = payload.get(
        "industryInfo"
    )

    if not isinstance(
        industry_info,
        dict
    ):

        return {

            "Macro-Economic Sector":
                "",

            "Sector":
                "",

            "Industry":
                "",

            "Basic Industry":
                "",

            "success":
                False,

            "error":
                "INDUSTRY_INFO_NOT_FOUND",

        }

    macro = normalize_text(
        industry_info.get(
            "macro",
            ""
        )
    )

    sector = normalize_text(
        industry_info.get(
            "sector",
            ""
        )
    )

    industry = normalize_text(
        industry_info.get(
            "industry",
            ""
        )
    )

    basic = normalize_text(
        industry_info.get(
            "basicIndustry",
            ""
        )
    )

    populated = sum(
        bool(value)
        for value in [
            macro,
            sector,
            industry,
            basic
        ]
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

        "success":
            populated > 0,

        "error":
            ""
            if populated > 0
            else "INDUSTRY_INFO_EMPTY",

    }


# ============================================================
# RESOLVE ONE STOCK
# ============================================================

def resolve_stock(
    session,
    record
):

    symbol = record[
        "NSE Symbol"
    ]

    print(
        f"\nResolving: "
        f"{symbol} - "
        f"{record['Company Name']}"
    )

    result = request_nse_quote(
        session,
        symbol
    )

    if result["access_blocked"]:

        return {

            "Macro-Economic Sector":
                "",

            "Sector":
                "",

            "Industry":
                "",

            "Basic Industry":
                "",

            "Classification Source":
                "",

            "Classification Confidence":
                NOT_RESOLVED,

            "Diagnosis":
                NSE_ACCESS_BLOCKED,

            "_nse_access_blocked":
                True,

        }

    if not result["success"]:

        return {

            "Macro-Economic Sector":
                "",

            "Sector":
                "",

            "Industry":
                "",

            "Basic Industry":
                "",

            "Classification Source":
                "",

            "Classification Confidence":
                NOT_RESOLVED,

            "Diagnosis":
                result["error"],

            "_nse_access_blocked":
                False,

        }

    classification = (
        extract_industry_info(
            result["payload"]
        )
    )

    if not classification["success"]:

        return {

            "Macro-Economic Sector":
                "",

            "Sector":
                "",

            "Industry":
                "",

            "Basic Industry":
                "",

            "Classification Source":
                "NSE_QUOTE_EQUITY",

            "Classification Confidence":
                NOT_RESOLVED,

            "Diagnosis":
                classification["error"],

            "_nse_access_blocked":
                False,

        }

    macro = classification[
        "Macro-Economic Sector"
    ]

    sector = classification[
        "Sector"
    ]

    industry = classification[
        "Industry"
    ]

    basic = classification[
        "Basic Industry"
    ]

    populated = sum(
        bool(value)
        for value in [
            macro,
            sector,
            industry,
            basic
        ]
    )

    if populated == 4:

        confidence = (
            HIGH_CONFIDENCE
        )

        diagnosis = (
            "NSE_QUOTE_INDUSTRY_INFO_RESOLVED"
        )

    elif populated >= 2:

        confidence = (
            MEDIUM_CONFIDENCE
        )

        diagnosis = (
            "NSE_QUOTE_INDUSTRY_INFO_PARTIAL"
        )

    else:

        confidence = (
            LOW_CONFIDENCE
        )

        diagnosis = (
            "NSE_QUOTE_INDUSTRY_INFO_INCOMPLETE"
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
            "NSE_QUOTE_EQUITY",

        "Classification Confidence":
            confidence,

        "Diagnosis":
            diagnosis,

        "_nse_access_blocked":
            False,

    }


# ============================================================
# BUILD DIAGNOSTIC ROW
# ============================================================

def build_diagnostic_row(
    record,
    classification
):

    return {

        "Run Date":
            datetime.now().strftime(
                "%Y-%m-%d"
            ),

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
                "Existing Sector"
            ],

        "Existing Industry":
            record[
                "Existing Industry"
            ],

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
            classification.get(
                "Classification Confidence",
                NOT_RESOLVED
            ),

        "Diagnosis":
            classification.get(
                "Diagnosis",
                ""
            ),

    }


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

    data = [
        headers
    ]

    for row in rows:

        data.append([

            row.get(
                header,
                ""
            )

            for header in headers

        ])

    worksheet.update(

        range_name=(
            f"A1:M{len(data)}"
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
    access_state
):

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

    blocked = sum(
        row[
            "Diagnosis"
        ] == NSE_ACCESS_BLOCKED
        for row in rows
    )

    print("\n")
    print("=" * 60)

    print(
        "NSE SECTOR & INDUSTRY DIAGNOSTIC"
    )

    print("=" * 60)

    print(
        f"Processed Rows         : {total}"
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

    print(
        f"NSE Access Blocked     : {blocked}"
    )

    print("-" * 60)

    print(
        f"NSE Access State       : "
        f"{access_state}"
    )

    if total:

        resolved = (
            high
            + medium
            + low
        )

        print(
            "Resolution Rate        : "
            f"{(resolved / total) * 100:.1f}%"
        )

    print("-" * 60)

    print(
        f"Diagnostic Sheet       : "
        f"{DIAGNOSTIC_SHEET}"
    )

    print(
        f"Checkpoint File        : "
        f"{CHECKPOINT_FILE}"
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
        "CIRCUIT-BREAKER MODE"
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

    checkpoint = (
        load_checkpoint()
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # We create the session once.
    #
    # We DO NOT continually create new sessions after 403.
    # --------------------------------------------------------

    session = create_nse_session()

    homepage_accessible = (
        initialize_nse_session(
            session
        )
    )

    if not homepage_accessible:

        print(
            "\n"
            "NSE homepage itself is currently inaccessible."
        )

        print(
            "Activating circuit breaker."
        )

        access_state = (
            NSE_ACCESS_BLOCKED
        )

        diagnostic_rows = []

        for record in records:

            classification = {

                "Macro-Economic Sector":
                    "",

                "Sector":
                    "",

                "Industry":
                    "",

                "Basic Industry":
                    "",

                "Classification Source":
                    "",

                "Classification Confidence":
                    NOT_RESOLVED,

                "Diagnosis":
                    NSE_ACCESS_BLOCKED,

            }

            diagnostic_rows.append(
                build_diagnostic_row(
                    record,
                    classification
                )
            )

        save_checkpoint(
            checkpoint
        )

        write_diagnostic_sheet(
            spreadsheet,
            diagnostic_rows
        )

        print_summary(
            diagnostic_rows,
            access_state
        )

        print(
            "\nNSE classification update "
            "stopped safely."
        )

        return

    # --------------------------------------------------------
    # ACTUAL QUOTE API PROBE
    #
    # This is the critical improvement.
    #
    # Homepage 200 does NOT mean quote API access exists.
    #
    # We test one real unresolved symbol before processing
    # the remaining 70 stocks.
    # --------------------------------------------------------

    probe_symbol = records[0][
        "NSE Symbol"
    ]

    access_state, probe_result = (
        probe_nse_quote_access(
            session,
            probe_symbol
        )
    )

    # ========================================================
    # GLOBAL CIRCUIT BREAKER
    # ========================================================

    if access_state == NSE_ACCESS_BLOCKED:

        print(
            "\n"
            "============================================================"
        )

        print(
            "GLOBAL NSE CIRCUIT BREAKER ACTIVATED"
        )

        print(
            "The quote API is returning HTTP 403."
        )

        print(
            "No additional NSE quote requests will be made "
            "during this workflow."
        )

        print(
            "Previously successful checkpoint records "
            "will be preserved."
        )

        print(
            "Unresolved records will remain unresolved "
            "and will be retried on a future scheduled run."
        )

        print(
            "============================================================"
        )

        diagnostic_rows = []

        for index, record in enumerate(
            records,
            start=1
        ):

            symbol = record[
                "NSE Symbol"
            ]

            checkpoint_result = (
                checkpoint.get(symbol)
            )

            # Preserve an already successful
            # classification.

            if is_successful_classification(
                checkpoint_result
            ):

                classification = (
                    checkpoint_result
                )

            else:

                classification = {

                    "Macro-Economic Sector":
                        "",

                    "Sector":
                        "",

                    "Industry":
                        "",

                    "Basic Industry":
                        "",

                    "Classification Source":
                        "",

                    "Classification Confidence":
                        NOT_RESOLVED,

                    "Diagnosis":
                        NSE_ACCESS_BLOCKED,

                }

            diagnostic_rows.append(
                build_diagnostic_row(
                    record,
                    classification
                )
            )

        # No new successful data was obtained,
        # so the existing checkpoint remains intact.

        save_checkpoint(
            checkpoint
        )

        write_diagnostic_sheet(
            spreadsheet,
            diagnostic_rows
        )

        print_summary(
            diagnostic_rows,
            access_state
        )

        print(
            "\nCircuit breaker completed safely."
        )

        return

    # ========================================================
    # ACCESS AVAILABLE
    # ========================================================

    if access_state == NSE_ACCESS_AVAILABLE:

        print(
            "\n"
            "============================================================"
        )

        print(
            "NSE QUOTE API ACCESS CONFIRMED"
        )

        print(
            "Beginning stock-by-stock classification."
        )

        print(
            "============================================================"
        )

    else:

        print(
            "\n"
            "NSE quote endpoint could not be confirmed."
        )

        print(
            "To avoid wasting the workflow run, "
            "activating safety circuit breaker."
        )

        diagnostic_rows = []

        for record in records:

            symbol = record[
                "NSE Symbol"
            ]

            checkpoint_result = (
                checkpoint.get(symbol)
            )

            if is_successful_classification(
                checkpoint_result
            ):

                classification = (
                    checkpoint_result
                )

            else:

                classification = {

                    "Macro-Economic Sector":
                        "",

                    "Sector":
                        "",

                    "Industry":
                        "",

                    "Basic Industry":
                        "",

                    "Classification Source":
                        "",

                    "Classification Confidence":
                        NOT_RESOLVED,

                    "Diagnosis":
                        (
                            "NSE_ACCESS_PROBE_FAILED"
                        ),

                }

            diagnostic_rows.append(
                build_diagnostic_row(
                    record,
                    classification
                )
            )

        save_checkpoint(
            checkpoint
        )

        write_diagnostic_sheet(
            spreadsheet,
            diagnostic_rows
        )

        print_summary(
            diagnostic_rows,
            NSE_ACCESS_UNKNOWN
        )

        return

    # ========================================================
    # STOCK-BY-STOCK PROCESSING
    # ========================================================

    diagnostic_rows = []

    successful_since_checkpoint = 0

    unresolved_count = 0

    access_blocked_during_run = False

    for index, record in enumerate(
        records,
        start=1
    ):

        symbol = record[
            "NSE Symbol"
        ]

        print(
            "\n"
            "============================================================"
        )

        print(
            f"[{index}/{len(records)}] "
            f"{symbol}"
        )

        print(
            f"Company: "
            f"{record['Company Name']}"
        )

        print(
            "============================================================"
        )

        # ----------------------------------------------------
        # Reuse successful checkpoint.
        # ----------------------------------------------------

        checkpoint_result = (
            checkpoint.get(symbol)
        )

        if is_successful_classification(
            checkpoint_result
        ):

            print(
                "Using successful checkpoint "
                "classification."
            )

            classification = (
                checkpoint_result
            )

        else:

            classification = (
                resolve_stock(
                    session,
                    record
                )
            )

            # ------------------------------------------------
            # If 403 occurs at any point:
            #
            # STOP ALL FURTHER NSE REQUESTS.
            # ------------------------------------------------

            if classification.get(
                "_nse_access_blocked",
                False
            ):

                print(
                    "\n"
                    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
                )

                print(
                    "GLOBAL NSE CIRCUIT BREAKER ACTIVATED MID-RUN"
                )

                print(
                    f"Triggering symbol: {symbol}"
                )

                print(
                    "No further NSE quote requests will be attempted."
                )

                print(
                    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
                )

                access_blocked_during_run = True

                # Store the current unresolved
                # classification only in memory.
                #
                # We do NOT put a blocked result into
                # the successful checkpoint.

                diagnostic_rows.append(
                    build_diagnostic_row(
                        record,
                        classification
                    )
                )

                unresolved_count += 1

                # Remaining records are added directly
                # as blocked without contacting NSE.

                for remaining_record in records[
                    index:
                ]:

                    remaining_symbol = (
                        remaining_record[
                            "NSE Symbol"
                        ]
                    )

                    remaining_checkpoint = (
                        checkpoint.get(
                            remaining_symbol
                        )
                    )

                    if is_successful_classification(
                        remaining_checkpoint
                    ):

                        remaining_classification = (
                            remaining_checkpoint
                        )

                    else:

                        remaining_classification = {

                            "Macro-Economic Sector":
                                "",

                            "Sector":
                                "",

                            "Industry":
                                "",

                            "Basic Industry":
                                "",

                            "Classification Source":
                                "",

                            "Classification Confidence":
                                NOT_RESOLVED,

                            "Diagnosis":
                                NSE_ACCESS_BLOCKED,

                        }

                        unresolved_count += 1

                    diagnostic_rows.append(
                        build_diagnostic_row(
                            remaining_record,
                            remaining_classification
                        )
                    )

                break

            # ------------------------------------------------
            # Save only successful classifications.
            # ------------------------------------------------

            if is_successful_classification(
                classification
            ):

                checkpoint[symbol] = (
                    classification
                )

                successful_since_checkpoint += 1

                if (
                    successful_since_checkpoint
                    >= CHECKPOINT_EVERY
                ):

                    save_checkpoint(
                        checkpoint
                    )

                    successful_since_checkpoint = 0

            else:

                unresolved_count += 1

        if (
            classification[
                "Classification Confidence"
            ]
            == NOT_RESOLVED
            and not classification.get(
                "_nse_access_blocked",
                False
            )
        ):

            unresolved_count += 1

        diagnostic_rows.append(
            build_diagnostic_row(
                record,
                classification
            )
        )

        # ----------------------------------------------------
        # Delay only if we are continuing.
        # ----------------------------------------------------

        if not access_blocked_during_run:

            delay = random.uniform(
                MIN_DELAY,
                MAX_DELAY
            )

            print(
                f"Waiting {delay:.1f}s "
                "before next symbol..."
            )

            time.sleep(
                delay
            )

    # ========================================================
    # FINAL CHECKPOINT
    # ========================================================

    save_checkpoint(
        checkpoint
    )

    # ========================================================
    # WRITE DIAGNOSTIC SHEET
    # ========================================================

    write_diagnostic_sheet(
        spreadsheet,
        diagnostic_rows
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    final_access_state = (
        NSE_ACCESS_BLOCKED
        if access_blocked_during_run
        else NSE_ACCESS_AVAILABLE
    )

    print_summary(
        diagnostic_rows,
        final_access_state
    )

    print(
        "\nUnresolved rows in this run: "
        f"{unresolved_count}"
    )

    print(
        "\nNSE classification update complete."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
