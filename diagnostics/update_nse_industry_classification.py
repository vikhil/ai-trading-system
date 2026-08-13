import os
import csv
import json
import time
import random
from datetime import datetime, timezone

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
# OUTPUT FILES
# ============================================================

CHECKPOINT_FILE = os.getenv(
    "NSE_CLASSIFICATION_CHECKPOINT",
    "data/nse_classification_checkpoint.json"
)

COMPANY_CLASSIFICATION_FILE = os.getenv(
    "NSE_COMPANY_CLASSIFICATION_FILE",
    "data/nse_company_classification.csv"
)


# ============================================================
# CLASSIFICATION STATUS
# ============================================================

HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
NOT_RESOLVED = "NOT_RESOLVED"


# ============================================================
# DIAGNOSTIC STATUS
# ============================================================

STATUS_RESOLVED = "RESOLVED"
STATUS_UNRESOLVED = "UNRESOLVED"
STATUS_BLOCKED_403 = "BLOCKED_403"


# ============================================================
# REQUEST CONFIGURATION
# ============================================================

MAX_RETRIES_PER_SYMBOL = int(
    os.getenv(
        "NSE_CLASSIFICATION_MAX_RETRIES",
        "5"
    )
)

REQUEST_TIMEOUT = int(
    os.getenv(
        "NSE_CLASSIFICATION_TIMEOUT",
        "30"
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

# Maximum number of 403 retries before the symbol is
# deliberately marked as blocked for this run.
#
# This is intentionally smaller than MAX_RETRIES_PER_SYMBOL.
#
# A persistent 403 is generally not fixed by repeatedly
# sending the exact same request.
MAX_403_RETRIES = int(
    os.getenv(
        "NSE_CLASSIFICATION_MAX_403_RETRIES",
        "2"
    )
)

# Minimum delay after a 403 before trying again.
FORBIDDEN_MIN_DELAY = float(
    os.getenv(
        "NSE_CLASSIFICATION_403_MIN_DELAY",
        "20"
    )
)

# Maximum delay after a 403.
FORBIDDEN_MAX_DELAY = float(
    os.getenv(
        "NSE_CLASSIFICATION_403_MAX_DELAY",
        "45"
    )
)

# How long a successfully resolved classification is
# considered reusable before another NSE lookup.
#
# Default: 7 days.
SUCCESS_RECHECK_DAYS = int(
    os.getenv(
        "NSE_CLASSIFICATION_SUCCESS_RECHECK_DAYS",
        "7"
    )
)


# ============================================================
# COMMON HELPERS
# ============================================================

def utc_now_iso():
    """
    Return current UTC time in ISO format.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


def normalize_text(value):
    """
    Convert a value to clean text.
    """

    if value is None:
        return ""

    return str(value).strip()


def normalize_symbol(value):
    """
    Normalize NSE/Yahoo-style symbols.

    Examples:
        NSE:RELIANCE -> RELIANCE
        RELIANCE.NS -> RELIANCE
    """

    value = normalize_text(
        value
    ).upper()

    if value.startswith("NSE:"):
        value = value[4:]

    if value.endswith(".NS"):
        value = value[:-3]

    return value.strip()


def is_resolved_confidence(
    confidence
):
    """
    Determine whether a classification is usable.
    """

    return confidence in {
        HIGH_CONFIDENCE,
        MEDIUM_CONFIDENCE,
        LOW_CONFIDENCE,
    }


def safe_int(value, default=0):
    """
    Safely convert a value to integer.
    """

    try:
        return int(value)
    except (
        TypeError,
        ValueError
    ):
        return default


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

    print(
        "Connected"
    )

    return spreadsheet


# ============================================================
# COLUMN HELPER
# ============================================================

def find_column(
    headers,
    candidates,
    required=True
):
    """
    Find a column using case-insensitive matching.
    """

    normalized = {
        str(header).strip().lower():
            header
        for header in headers
    }

    for candidate in candidates:

        key = (
            candidate
            .strip()
            .lower()
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

        # Only process stocks whose current sector
        # is unresolved.
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
                "(Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 "
                "Safari/537.36"
            ),

        "Accept":
            "application/json, text/plain, */*",

        "Accept-Language":
            "en-US,en;q=0.9",

        "Connection":
            "keep-alive",

        "DNT":
            "1",

    })

    return session


def warm_nse_session(
    session
):
    """
    Establish a fresh NSE web session.

    The quote API is not treated as an isolated request.

    We first visit the NSE homepage and then an equity
    quote page so that the session has the cookies/context
    normally associated with browsing the NSE site.
    """

    print(
        "\nInitializing / refreshing NSE session..."
    )

    session.cookies.clear()

    try:

        home_response = session.get(

            NSE_HOME_URL,

            headers={

                "Accept":
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8",

            },

            timeout=REQUEST_TIMEOUT

        )

        print(
            "NSE homepage status: "
            f"{home_response.status_code}"
        )

    except requests.RequestException as error:

        print(
            "WARNING: NSE homepage request failed:"
        )

        print(
            f"  {error}"
        )

        return False

    if home_response.status_code >= 400:

        print(
            "WARNING: NSE homepage returned "
            f"HTTP {home_response.status_code}"
        )

        return False

    # --------------------------------------------------------
    # Open the equity quote page.
    # --------------------------------------------------------

    try:

        quote_page_response = session.get(

            NSE_QUOTE_PAGE_URL,

            params={
                "symbol": "RELIANCE"
            },

            headers={

                "Referer":
                    NSE_HOME_URL,

                "Accept":
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8",

            },

            timeout=REQUEST_TIMEOUT

        )

        print(
            "NSE quote page status: "
            f"{quote_page_response.status_code}"
        )

    except requests.RequestException as error:

        print(
            "WARNING: NSE quote page request failed:"
        )

        print(
            f"  {error}"
        )

        return False

    if quote_page_response.status_code >= 400:

        print(
            "WARNING: NSE quote page returned "
            f"HTTP {quote_page_response.status_code}"
        )

        return False

    print(
        "NSE session initialized."
    )

    return True


def refresh_nse_session():
    """
    Create and warm a completely new session.
    """

    print(
        "\nCreating a completely fresh NSE session..."
    )

    session = create_nse_session()

    warm_nse_session(
        session
    )

    return session


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
                "structure. Starting fresh."
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
# CHECKPOINT HELPERS
# ============================================================

def checkpoint_is_resolved(
    checkpoint_result
):
    """
    A symbol is reusable from checkpoint only if:

    1. It contains a valid classification.
    2. It was resolved successfully.
    3. It has not exceeded the configured refresh period.
    """

    if not isinstance(
        checkpoint_result,
        dict
    ):
        return False

    confidence = (
        checkpoint_result.get(
            "Classification Confidence",
            NOT_RESOLVED
        )
    )

    if not is_resolved_confidence(
        confidence
    ):
        return False

    resolved_at = (
        checkpoint_result.get(
            "Resolved At",
            ""
        )
    )

    if not resolved_at:

        return True

    try:

        resolved_datetime = (
            datetime.fromisoformat(
                resolved_at
            )
        )

        if (
            resolved_datetime.tzinfo
            is None
        ):

            resolved_datetime = (
                resolved_datetime.replace(
                    tzinfo=timezone.utc
                )
            )

        age_seconds = (
            (
                datetime.now(timezone.utc)
                - resolved_datetime
            ).total_seconds()
        )

        max_age = (
            SUCCESS_RECHECK_DAYS
            * 86400
        )

        return age_seconds < max_age

    except (
        ValueError,
        TypeError
    ):

        return True


# ============================================================
# NSE QUOTE REQUEST
# ============================================================

def request_nse_quote(
    session,
    symbol
):
    """
    Request one NSE equity quote.

    403 handling is intentionally different from
    ordinary transient errors.

    We do NOT repeatedly send the same request five times.

    On 403:

        1. Wait.
        2. Refresh session.
        3. Re-establish cookies.
        4. Re-open the NSE quote page.
        5. Retry only a small number of times.

    If NSE continues returning 403, return a specific
    NSE_403_BLOCKED error and let the caller continue
    with the next symbol.
    """

    symbol = normalize_symbol(
        symbol
    )

    if not symbol:

        return {

            "success":
                False,

            "payload":
                {},

            "error":
                "INVALID_NSE_SYMBOL",

            "status":
                None,

            "blocked":
                False,

        }

    total_attempts = 0

    forbidden_attempts = 0

    temporary_attempts = 0

    while (
        total_attempts
        < MAX_RETRIES_PER_SYMBOL
    ):

        total_attempts += 1

        print(
            f"    NSE request "
            f"{total_attempts}/"
            f"{MAX_RETRIES_PER_SYMBOL}"
        )

        headers = {

            "Referer":
                (
                    f"{NSE_QUOTE_PAGE_URL}"
                    f"?symbol={symbol}"
                ),

            "Accept":
                "application/json, text/plain, */*",

            "X-Requested-With":
                "XMLHttpRequest",

        }

        try:

            response = session.get(

                NSE_QUOTE_API_URL,

                params={
                    "symbol": symbol
                },

                headers=headers,

                timeout=REQUEST_TIMEOUT

            )

            status = (
                response.status_code
            )

            print(
                "    HTTP status: "
                f"{status}"
            )

            # =================================================
            # SUCCESS
            # =================================================

            if status == 200:

                try:

                    payload = (
                        response.json()
                    )

                except ValueError:

                    print(
                        "    NSE returned "
                        "non-JSON response."
                    )

                    return {

                        "success":
                            False,

                        "payload":
                            {},

                        "error":
                            "NSE_NON_JSON_RESPONSE",

                        "status":
                            status,

                        "blocked":
                            False,

                    }

                if isinstance(
                    payload,
                    dict
                ):

                    return {

                        "success":
                            True,

                        "payload":
                            payload,

                        "error":
                            "",

                        "status":
                            status,

                        "blocked":
                            False,

                    }

                return {

                    "success":
                        False,

                    "payload":
                        {},

                    "error":
                        "NSE_INVALID_JSON_OBJECT",

                    "status":
                        status,

                    "blocked":
                        False,

                }

            # =================================================
            # 403 FORBIDDEN
            # =================================================

            if status == 403:

                forbidden_attempts += 1

                print(
                    "    NSE returned "
                    "403 Forbidden."
                )

                # ---------------------------------------------
                # Persistent 403
                # ---------------------------------------------

                if (
                    forbidden_attempts
                    >= MAX_403_RETRIES
                ):

                    print(
                        "    Persistent 403 detected."
                    )

                    print(
                        "    Stopping retries for "
                        f"{symbol}."
                    )

                    return {

                        "success":
                            False,

                        "payload":
                            {},

                        "error":
                            "NSE_403_BLOCKED",

                        "status":
                            403,

                        "blocked":
                            True,

                    }

                # ---------------------------------------------
                # Intelligent recovery
                # ---------------------------------------------

                sleep_for = random.uniform(
                    FORBIDDEN_MIN_DELAY,
                    FORBIDDEN_MAX_DELAY
                )

                print(
                    "    403 recovery delay: "
                    f"{sleep_for:.1f}s"
                )

                time.sleep(
                    sleep_for
                )

                print(
                    "    Refreshing NSE "
                    "session/cookies..."
                )

                session = refresh_nse_session()

                continue

            # =================================================
            # RATE LIMIT / SERVER ERROR
            # =================================================

            if status in {

                429,
                500,
                502,
                503,
                504

            }:

                temporary_attempts += 1

                print(
                    "    Temporary NSE/server "
                    f"error: {status}"
                )

                if (
                    total_attempts
                    >= MAX_RETRIES_PER_SYMBOL
                ):

                    break

                backoff = min(

                    60,

                    5
                    * (
                        2
                        ** (
                            temporary_attempts - 1
                        )
                    )

                )

                jitter = random.uniform(
                    1,
                    5
                )

                sleep_for = (
                    backoff
                    + jitter
                )

                print(
                    "    Backing off for "
                    f"{sleep_for:.1f}s"
                )

                time.sleep(
                    sleep_for
                )

                continue

            # =================================================
            # OTHER HTTP ERROR
            # =================================================

            print(
                "    Unexpected HTTP "
                f"status: {status}"
            )

            return {

                "success":
                    False,

                "payload":
                    {},

                "error":
                    f"NSE_HTTP_{status}",

                "status":
                    status,

                "blocked":
                    False,

            }

        except requests.RequestException as error:

            print(
                "    NSE request exception:"
            )

            print(
                f"    {error}"
            )

            if (
                total_attempts
                >= MAX_RETRIES_PER_SYMBOL
            ):

                return {

                    "success":
                        False,

                    "payload":
                        {},

                    "error":
                        "NSE_REQUEST_EXCEPTION",

                    "status":
                        None,

                    "blocked":
                        False,

                }

            sleep_for = (

                5
                * (
                    2
                    ** (
                        total_attempts - 1
                    )
                )

                + random.uniform(
                    1,
                    5
                )

            )

            sleep_for = min(
                sleep_for,
                60
            )

            print(
                "    Retrying after "
                f"{sleep_for:.1f}s"
            )

            time.sleep(
                sleep_for
            )

    return {

        "success":
            False,

        "payload":
            {},

        "error":
            "NSE_QUOTE_REQUEST_FAILED",

        "status":
            None,

        "blocked":
            False,

    }


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

    industry_info = (
        payload.get(
            "industryInfo"
        )
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

    company_name = record[
        "Company Name"
    ]

    print(
        f"\nResolving: "
        f"{symbol} - "
        f"{company_name}"
    )

    result = request_nse_quote(
        session,
        symbol
    )

    # ========================================================
    # REQUEST FAILED
    # ========================================================

    if not result["success"]:

        error = result[
            "error"
        ]

        if result.get(
            "blocked"
        ):

            status = (
                STATUS_BLOCKED_403
            )

        else:

            status = (
                STATUS_UNRESOLVED
            )

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
                error,

            "Status":
                status,

            "Resolved At":
                "",

            "Last Attempt At":
                utc_now_iso(),

            "HTTP Status":
                result.get(
                    "status"
                ),

        }

    # ========================================================
    # EXTRACT CLASSIFICATION
    # ========================================================

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
                "",

            "Classification Confidence":
                NOT_RESOLVED,

            "Diagnosis":
                classification["error"],

            "Status":
                STATUS_UNRESOLVED,

            "Resolved At":
                "",

            "Last Attempt At":
                utc_now_iso(),

            "HTTP Status":
                200,

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

        "Status":
            STATUS_RESOLVED,

        "Resolved At":
            utc_now_iso(),

        "Last Attempt At":
            utc_now_iso(),

        "HTTP Status":
            200,

    }


# ============================================================
# WRITE COMPANY CLASSIFICATION CSV
# ============================================================

def write_company_classification_csv(
    checkpoint
):
    """
    Generate the downstream company classification file.

    IMPORTANT:

    This file is generated automatically from successful
    NSE responses.

    It is NOT a manual classification source.
    """

    directory = os.path.dirname(
        COMPANY_CLASSIFICATION_FILE
    )

    if directory:

        os.makedirs(
            directory,
            exist_ok=True
        )

    headers = [

        "NSE Symbol",

        "Macro-Economic Sector",

        "Sector",

        "Industry",

        "Basic Industry",

        "Classification Source",

        "Classification Confidence",

        "Diagnosis",

        "Resolved At",

    ]

    rows = []

    for symbol, result in sorted(
        checkpoint.items()
    ):

        if not isinstance(
            result,
            dict
        ):

            continue

        if not is_resolved_confidence(
            result.get(
                "Classification Confidence"
            )
        ):

            continue

        rows.append({

            "NSE Symbol":
                symbol,

            "Macro-Economic Sector":
                result.get(
                    "Macro-Economic Sector",
                    ""
                ),

            "Sector":
                result.get(
                    "Sector",
                    ""
                ),

            "Industry":
                result.get(
                    "Industry",
                    ""
                ),

            "Basic Industry":
                result.get(
                    "Basic Industry",
                    ""
                ),

            "Classification Source":
                result.get(
                    "Classification Source",
                    ""
                ),

            "Classification Confidence":
                result.get(
                    "Classification Confidence",
                    ""
                ),

            "Diagnosis":
                result.get(
                    "Diagnosis",
                    ""
                ),

            "Resolved At":
                result.get(
                    "Resolved At",
                    ""
                ),

        })

    temporary_file = (
        COMPANY_CLASSIFICATION_FILE
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

        writer.writerows(
            rows
        )

    os.replace(
        temporary_file,
        COMPANY_CLASSIFICATION_FILE
    )

    print(
        "\nGenerated company classification file:"
    )

    print(
        f"  {COMPANY_CLASSIFICATION_FILE}"
    )

    print(
        f"  Resolved companies: "
        f"{len(rows)}"
    )


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
    rows
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

        row.get(
            "Diagnosis"
        ) == "NSE_403_BLOCKED"

        for row in rows

    )

    print("\n")
    print("=" * 65)

    print(
        "NSE SECTOR & INDUSTRY DIAGNOSTIC"
    )

    print("=" * 65)

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
        f"403 Blocked            : {blocked}"
    )

    print("-" * 65)

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

    print("-" * 65)

    print(
        f"Diagnostic Sheet       : "
        f"{DIAGNOSTIC_SHEET}"
    )

    print(
        f"Classification File    : "
        f"{COMPANY_CLASSIFICATION_FILE}"
    )

    print("=" * 65)


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

    # ========================================================
    # CONNECT GOOGLE SHEETS
    # ========================================================

    spreadsheet = (
        connect_to_google_sheet()
    )

    # ========================================================
    # READ UNKNOWN STOCKS
    # ========================================================

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

    # ========================================================
    # LOAD CHECKPOINT
    # ========================================================

    checkpoint = (
        load_checkpoint()
    )

    # ========================================================
    # CREATE INITIAL NSE SESSION
    # ========================================================

    session = create_nse_session()

    warm_nse_session(
        session
    )

    # ========================================================
    # PROCESS STOCKS
    # ========================================================

    diagnostic_rows = []

    resolved_this_run = 0

    unresolved_this_run = 0

    blocked_this_run = 0

    processed_this_run = 0

    checkpoint_counter = 0

    total = len(records)

    for index, record in enumerate(
        records,
        start=1
    ):

        symbol = record[
            "NSE Symbol"
        ]

        print(
            "\n"
            + "=" * 60
        )

        print(
            f"[{index}/{total}] "
            f"{symbol}"
        )

        print(
            f"Company: "
            f"{record['Company Name']}"
        )

        print(
            "=" * 60
        )

        # ====================================================
        # REUSE RECENT SUCCESSFUL CHECKPOINT
        # ====================================================

        checkpoint_result = (
            checkpoint.get(
                symbol
            )
        )

        if checkpoint_is_resolved(
            checkpoint_result
        ):

            print(
                "Using recent successful "
                "NSE checkpoint."
            )

            classification = (
                checkpoint_result
            )

            resolved_this_run += 1

        else:

            # =================================================
            # IMPORTANT:
            #
            # An unresolved/403 checkpoint is NOT treated as
            # resolved.
            #
            # Therefore it gets another attempt on the next
            # workflow run.
            # =================================================

            classification = (
                resolve_stock(
                    session,
                    record
                )
            )

            confidence = (
                classification[
                    "Classification Confidence"
                ]
            )

            # -----------------------------------------------
            # Store every result.
            #
            # This includes unresolved and 403 results.
            # -----------------------------------------------

            checkpoint[symbol] = (
                classification
            )

            if is_resolved_confidence(
                confidence
            ):

                resolved_this_run += 1

            else:

                unresolved_this_run += 1

            if (
                classification.get(
                    "Diagnosis"
                )
                == "NSE_403_BLOCKED"
            ):

                blocked_this_run += 1

            processed_this_run += 1

            checkpoint_counter += 1

            # -----------------------------------------------
            # Persist checkpoint.
            # -----------------------------------------------

            if (
                checkpoint_counter
                >= CHECKPOINT_EVERY
            ):

                save_checkpoint(
                    checkpoint
                )

                checkpoint_counter = 0

        # ====================================================
        # DIAGNOSTIC ROW
        # ====================================================

        diagnostic_rows.append(

            build_diagnostic_row(

                record,

                classification

            )

        )

        # ====================================================
        # SAVE AFTER EVERY SYMBOL
        #
        # This makes the process resilient to:
        #
        # - GitHub runner termination
        # - timeout
        # - Python exception
        # - network failure
        # ====================================================

        save_checkpoint(
            checkpoint
        )

        # ====================================================
        # DELAY
        # ====================================================

        if index < total:

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
    # GENERATE DOWNSTREAM CLASSIFICATION FILE
    # ========================================================

    write_company_classification_csv(
        checkpoint
    )

    # ========================================================
    # WRITE GOOGLE DIAGNOSTIC SHEET
    # ========================================================

    write_diagnostic_sheet(
        spreadsheet,
        diagnostic_rows
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    print_summary(
        diagnostic_rows
    )

    print(
        "\nThis run:"
    )

    print(
        f"  Newly processed       : "
        f"{processed_this_run}"
    )

    print(
        f"  Resolved/reused       : "
        f"{resolved_this_run}"
    )

    print(
        f"  Unresolved             : "
        f"{unresolved_this_run}"
    )

    print(
        f"  403 blocked            : "
        f"{blocked_this_run}"
    )

    print(
        "\nNSE classification update complete."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
