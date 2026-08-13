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

NSE_BASE_URL = "https://www.nseindia.com"

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

MIN_DELAY = float(
    os.getenv(
        "NSE_CLASSIFICATION_MIN_DELAY",
        "5"
    )
)

MAX_DELAY = float(
    os.getenv(
        "NSE_CLASSIFICATION_MAX_DELAY",
        "10"
    )
)

CHECKPOINT_EVERY = int(
    os.getenv(
        "NSE_CLASSIFICATION_CHECKPOINT_EVERY",
        "5"
    )
)

# Maximum number of quote attempts for a symbol.
#
# IMPORTANT:
# This is NOT a "retry 5 times on 403" mechanism.
#
# 403 is handled separately through the circuit breaker.
MAX_QUOTE_ATTEMPTS = int(
    os.getenv(
        "NSE_CLASSIFICATION_MAX_RETRIES",
        "5"
    )
)


# ============================================================
# CLASSIFICATION STATES
# ============================================================

HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
NOT_RESOLVED = "NOT_RESOLVED"

NSE_ACCESS_BLOCKED = "NSE_ACCESS_BLOCKED"
NSE_TEMPORARY_ERROR = "NSE_TEMPORARY_ERROR"
SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"


RESOLVED_CONFIDENCES = {
    HIGH_CONFIDENCE,
    MEDIUM_CONFIDENCE,
    LOW_CONFIDENCE,
}


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

def find_column(
    headers,
    candidates,
    required=True
):

    normalized = {

        str(header)
        .strip()
        .lower(): header

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
            "application/json,text/plain,*/*",

        "Accept-Language":
            "en-US,en;q=0.9,hi;q=0.8",

        "Accept-Encoding":
            "gzip, deflate, br",

        "Connection":
            "keep-alive",

        "DNT":
            "1",

        "Sec-Fetch-Dest":
            "empty",

        "Sec-Fetch-Mode":
            "cors",

        "Sec-Fetch-Site":
            "same-origin",

    })

    return session


# ============================================================
# NSE SESSION PROBE
# ============================================================

def probe_nse(session):

    print(
        "\nInitializing / refreshing NSE session..."
    )

    try:

        response = session.get(
            NSE_HOME_URL,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )

        status = response.status_code

        print(
            "NSE homepage status: "
            f"{status}"
        )

        if status == 200:

            print(
                "NSE access probe successful."
            )

            return {
                "accessible": True,
                "status": 200,
                "error": "",
            }

        if status == 403:

            print(
                "WARNING: NSE homepage returned "
                "HTTP 403"
            )

            return {
                "accessible": False,
                "status": 403,
                "error": NSE_ACCESS_BLOCKED,
            }

        print(
            "WARNING: NSE homepage returned "
            f"HTTP {status}"
        )

        return {
            "accessible": False,
            "status": status,
            "error": NSE_TEMPORARY_ERROR,
        }

    except requests.RequestException as error:

        print(
            "WARNING: NSE homepage probe failed:"
        )

        print(
            f"  {error}"
        )

        return {
            "accessible": False,
            "status": 0,
            "error": NSE_TEMPORARY_ERROR,
        }


# ============================================================
# NSE SESSION REFRESH
# ============================================================

def refresh_nse_session():

    print(
        "\nCreating a completely fresh NSE session..."
    )

    session = create_nse_session()

    probe = probe_nse(
        session
    )

    return session, probe


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

def is_resolved_checkpoint(
    value
):

    if not isinstance(
        value,
        dict
    ):

        return False

    return (
        value.get(
            "Classification Confidence"
        )
        in RESOLVED_CONFIDENCES
    )


# ============================================================
# CLASSIFICATION RESULT FACTORIES
# ============================================================

def unresolved_result(
    diagnosis,
    source=""
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

        "Classification Source":
            source,

        "Classification Confidence":
            NOT_RESOLVED,

        "Diagnosis":
            diagnosis,

    }


def blocked_result():

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

    }


# ============================================================
# NSE QUOTE REQUEST
# ============================================================

def request_nse_quote(
    session,
    symbol,
    nse_state
):

    symbol = normalize_symbol(
        symbol
    )

    # --------------------------------------------------------
    # CIRCUIT BREAKER
    # --------------------------------------------------------

    if not nse_state["available"]:

        print(
            "    NSE circuit breaker is OPEN."
        )

        print(
            "    Skipping HTTP request."
        )

        return {

            "success":
                False,

            "payload":
                {},

            "error":
                NSE_ACCESS_BLOCKED,

        }

    url = NSE_QUOTE_API_URL

    headers = {

        "Referer":
            (
                f"{NSE_QUOTE_PAGE_URL}"
                f"?symbol={symbol}"
            ),

        "Accept":
            "application/json,text/plain,*/*",

        "X-Requested-With":
            "XMLHttpRequest",

    }

    # --------------------------------------------------------
    # REQUEST LOOP
    # --------------------------------------------------------

    for attempt in range(
        1,
        MAX_QUOTE_ATTEMPTS + 1
    ):

        try:

            print(
                f"    NSE request "
                f"{attempt}/"
                f"{MAX_QUOTE_ATTEMPTS}"
            )

            response = session.get(

                url,

                params={
                    "symbol": symbol
                },

                headers=headers,

                timeout=REQUEST_TIMEOUT,

                allow_redirects=True

            )

            status = (
                response.status_code
            )

            print(
                f"    HTTP status: "
                f"{status}"
            )

            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------

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
                            "INVALID_NSE_RESPONSE",

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

                    }

                return {

                    "success":
                        False,

                    "payload":
                        {},

                    "error":
                        "INVALID_NSE_PAYLOAD",

                }

            # ------------------------------------------------
            # 403
            # ------------------------------------------------
            #
            # This is NOT treated as an ordinary retry.
            #
            # We refresh the session once and probe NSE again.
            #
            # If NSE remains 403, the circuit breaker opens and
            # all subsequent symbols skip NSE HTTP requests.
            # ------------------------------------------------

            if status == 403:

                print(
                    "    NSE returned "
                    "403 Forbidden."
                )

                print(
                    "    Treating 403 as "
                    "access-state failure."
                )

                print(
                    "    Refreshing NSE session/cookies..."
                )

                new_session, probe = (
                    refresh_nse_session()
                )

                if not probe["accessible"]:

                    print(
                        "    Persistent NSE access "
                        "block confirmed."
                    )

                    print(
                        "    Opening NSE circuit breaker."
                    )

                    nse_state["available"] = False

                    nse_state[
                        "blocked_status"
                    ] = probe["status"]

                    nse_state[
                        "blocked_reason"
                    ] = probe["error"]

                    return {

                        "success":
                            False,

                        "payload":
                            {},

                        "error":
                            NSE_ACCESS_BLOCKED,

                        "session":
                            new_session,

                    }

                # NSE became accessible after refresh.
                #
                # Use the fresh session for the next attempt.
                session = new_session

                print(
                    "    NSE session refreshed "
                    "successfully."
                )

                if attempt < MAX_QUOTE_ATTEMPTS:

                    delay = random.uniform(
                        3,
                        6
                    )

                    print(
                        "    Waiting "
                        f"{delay:.1f}s "
                        "before retrying quote..."
                    )

                    time.sleep(
                        delay
                    )

                    continue

                return {

                    "success":
                        False,

                    "payload":
                        {},

                    "error":
                        NSE_ACCESS_BLOCKED,

                    "session":
                        session,

                }

            # ------------------------------------------------
            # RATE LIMIT / SERVER ERROR
            # ------------------------------------------------

            if status in {

                429,
                500,
                502,
                503,
                504

            }:

                print(
                    "    Temporary NSE/server "
                    f"error: {status}"
                )

                if attempt < MAX_QUOTE_ATTEMPTS:

                    delay = min(

                        60,

                        (
                            5
                            * (
                                2
                                ** (
                                    attempt - 1
                                )
                            )
                        )

                    ) + random.uniform(
                        1,
                        5
                    )

                    print(
                        "    Temporary-error "
                        "backoff: "
                        f"{delay:.1f}s"
                    )

                    time.sleep(
                        delay
                    )

                    continue

                return {

                    "success":
                        False,

                    "payload":
                        {},

                    "error":
                        NSE_TEMPORARY_ERROR,

                }

            # ------------------------------------------------
            # SYMBOL / OTHER CLIENT ERROR
            # ------------------------------------------------

            if status in {
                400,
                404
            }:

                print(
                    "    NSE symbol/quote "
                    f"request returned {status}."
                )

                return {

                    "success":
                        False,

                    "payload":
                        {},

                    "error":
                        SYMBOL_NOT_FOUND,

                }

            # ------------------------------------------------
            # UNEXPECTED STATUS
            # ------------------------------------------------

            print(
                "    Unexpected NSE HTTP "
                f"status: {status}"
            )

            if attempt < MAX_QUOTE_ATTEMPTS:

                delay = random.uniform(
                    3,
                    7
                )

                print(
                    "    Waiting "
                    f"{delay:.1f}s "
                    "before retry..."
                )

                time.sleep(
                    delay
                )

        except requests.RequestException as error:

            print(
                "    NSE request exception:"
            )

            print(
                f"    {error}"
            )

            if attempt < MAX_QUOTE_ATTEMPTS:

                delay = min(

                    60,

                    (
                        5
                        * (
                            2
                            ** (
                                attempt - 1
                            )
                        )
                    )

                ) + random.uniform(
                    1,
                    5
                )

                print(
                    "    Retrying after "
                    f"{delay:.1f}s"
                )

                time.sleep(
                    delay
                )

    return {

        "success":
            False,

        "payload":
            {},

        "error":
            NSE_TEMPORARY_ERROR,

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
    record,
    nse_state
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
        symbol,
        nse_state
    )

    # request_nse_quote can return a refreshed
    # session after a 403 recovery attempt.
    refreshed_session = result.get(
        "session"
    )

    if refreshed_session is not None:

        session = refreshed_session

    if not result["success"]:

        if result["error"] == NSE_ACCESS_BLOCKED:

            return (
                session,
                blocked_result()
            )

        return (

            session,

            unresolved_result(
                result["error"]
            )

        )

    classification = (
        extract_industry_info(
            result["payload"]
        )
    )

    if not classification["success"]:

        return (

            session,

            unresolved_result(
                classification["error"],
                "NSE_QUOTE_EQUITY"
            )

        )

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

        confidence = HIGH_CONFIDENCE

        diagnosis = (
            "NSE_QUOTE_INDUSTRY_INFO_RESOLVED"
        )

    elif populated >= 2:

        confidence = MEDIUM_CONFIDENCE

        diagnosis = (
            "NSE_QUOTE_INDUSTRY_INFO_PARTIAL"
        )

    else:

        confidence = LOW_CONFIDENCE

        diagnosis = (
            "NSE_QUOTE_INDUSTRY_INFO_INCOMPLETE"
        )

    return (

        session,

        {

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

        }

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

    }


# ============================================================
# WRITE GOOGLE SHEET
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
    nse_state
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
        "NSE Access State       : "
        + (
            "AVAILABLE"
            if nse_state["available"]
            else "BLOCKED"
        )
    )

    if not nse_state["available"]:

        print(
            "NSE Block Reason       : "
            f"{nse_state['blocked_reason']}"
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

    checkpoint = (
        load_checkpoint()
    )

    # --------------------------------------------------------
    # INITIAL NSE PROBE
    # --------------------------------------------------------

    session = create_nse_session()

    probe = probe_nse(
        session
    )

    nse_state = {

        "available":
            probe["accessible"],

        "blocked_status":
            probe["status"],

        "blocked_reason":
            probe["error"],

    }

    if not nse_state["available"]:

        print("\n" + "=" * 60)

        print(
            "NSE CIRCUIT BREAKER ACTIVATED"
        )

        print("=" * 60)

        print(
            "NSE is not accessible from this runner."
        )

        print(
            "No further NSE HTTP requests will be made "
            "during this run."
        )

        print(
            "All unresolved stocks will be retained "
            "for a future run."
        )

        print("=" * 60)

    diagnostic_rows = []

    unresolved_count = 0
    blocked_count = 0
    checkpoint_counter = 0

    total_records = len(records)

    # ========================================================
    # PROCESS ALL UNKNOWN STOCKS
    # ========================================================

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
            f"[{index}/{total_records}] "
            f"{symbol}"
        )

        print(
            f"Company: "
            f"{record['Company Name']}"
        )

        print(
            "=" * 60
        )

        # ----------------------------------------------------
        # Reuse successful checkpoint.
        # ----------------------------------------------------

        checkpoint_result = (
            checkpoint.get(symbol)
        )

        if is_resolved_checkpoint(
            checkpoint_result
        ):

            print(
                "Using successful checkpoint "
                "classification."
            )

            classification = (
                checkpoint_result
            )

        # ----------------------------------------------------
        # If NSE is blocked, don't make another request.
        # ----------------------------------------------------

        elif not nse_state["available"]:

            print(
                "NSE unavailable."
            )

            print(
                "Marking symbol as "
                "NSE_ACCESS_BLOCKED."
            )

            classification = (
                blocked_result()
            )

            blocked_count += 1

        # ----------------------------------------------------
        # Actual NSE retrieval.
        # ----------------------------------------------------

        else:

            session, classification = (
                resolve_stock(
                    session,
                    record,
                    nse_state
                )
            )

            if (
                classification[
                    "Diagnosis"
                ]
                == NSE_ACCESS_BLOCKED
            ):

                blocked_count += 1

        # ----------------------------------------------------
        # Track unresolved results.
        # ----------------------------------------------------

        if (
            classification[
                "Classification Confidence"
            ]
            == NOT_RESOLVED
        ):

            unresolved_count += 1

        # ----------------------------------------------------
        # Save classification to checkpoint.
        #
        # Successful classifications are reusable.
        #
        # NSE_ACCESS_BLOCKED is also recorded, but is NOT
        # considered a successful checkpoint and therefore
        # will be retried automatically on a future run.
        # ----------------------------------------------------

        checkpoint[symbol] = {

            **classification,

            "Last Attempt":
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),

        }

        checkpoint_counter += 1

        # ----------------------------------------------------
        # Build diagnostic row immediately.
        # ----------------------------------------------------

        diagnostic_rows.append(
            build_diagnostic_row(
                record,
                classification
            )
        )

        # ----------------------------------------------------
        # Save checkpoint periodically.
        # ----------------------------------------------------

        if (
            checkpoint_counter
            >= CHECKPOINT_EVERY
        ):

            save_checkpoint(
                checkpoint
            )

            checkpoint_counter = 0

        # ----------------------------------------------------
        # If circuit breaker opened during this symbol,
        # immediately classify remaining symbols as blocked.
        # ----------------------------------------------------

        if not nse_state["available"]:

            print(
                "\nNSE circuit breaker is now OPEN."
            )

            print(
                "Remaining stocks will be processed "
                "without NSE HTTP requests."
            )

        # ----------------------------------------------------
        # Delay only when NSE is actually being used.
        #
        # No unnecessary 5-10 second delays for a run where
        # NSE was already known to be blocked.
        # ----------------------------------------------------

        if (
            nse_state["available"]
            and index < total_records
        ):

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

    print_summary(
        diagnostic_rows,
        nse_state
    )

    print(
        "\nUnresolved rows in this run: "
        f"{unresolved_count}"
    )

    print(
        "NSE access-blocked rows in this run: "
        f"{blocked_count}"
    )

    print(
        "\nNSE classification update complete."
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # A controlled NSE 403 is NOT treated as a workflow
    # failure. The trading workflow can continue.
    # --------------------------------------------------------

    if not nse_state["available"]:

        print(
            "\nNOTE:"
        )

        print(
            "NSE was inaccessible during this run."
        )

        print(
            "The unresolved classifications remain "
            "eligible for retry on a future run."
        )

        print(
            "No repeated NSE requests were made after "
            "the circuit breaker opened."
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()

