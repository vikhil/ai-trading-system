# update_nse_industry_classification.py

import os
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
# CLASSIFICATION STATUS
# ============================================================

HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
NOT_RESOLVED = "NOT_RESOLVED"

STATUS_RESOLVED = "RESOLVED"
STATUS_BLOCKED = "NSE_ACCESS_BLOCKED"
STATUS_FAILED = "NSE_REQUEST_FAILED"
STATUS_NOT_FOUND = "NSE_SYMBOL_NOT_FOUND"
STATUS_INVALID = "NSE_RESPONSE_INVALID"


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

# 403 is deliberately NOT retried repeatedly.
#
# We allow one complete session re-bootstrap after
# the first 403. If the new session is also blocked,
# the symbol is marked NSE_ACCESS_BLOCKED and the
# script moves on.
MAX_403_RETRIES = int(
    os.getenv(
        "NSE_CLASSIFICATION_403_RETRIES",
        "1"
    )
)

# Retry only genuinely transient failures.
MAX_TRANSIENT_RETRIES = int(
    os.getenv(
        "NSE_CLASSIFICATION_TRANSIENT_RETRIES",
        "3"
    )
)

MIN_DELAY = float(
    os.getenv(
        "NSE_CLASSIFICATION_MIN_DELAY",
        "3.0"
    )
)

MAX_DELAY = float(
    os.getenv(
        "NSE_CLASSIFICATION_MAX_DELAY",
        "7.0"
    )
)

CHECKPOINT_EVERY = int(
    os.getenv(
        "NSE_CLASSIFICATION_CHECKPOINT_EVERY",
        "5"
    )
)


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
        normalize_text(header).lower():
            header
        for header in headers
    }

    for candidate in candidates:

        key = (
            normalize_text(candidate)
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
        ["Sector"]
    )

    industry_col = find_column(
        headers,
        ["Industry"]
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

        # Only process rows where Sector is
        # currently unknown/empty.
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

    user_agent = (
        "Mozilla/5.0 "
        "(Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 "
        "Safari/537.36"
    )

    session.headers.update({

        "User-Agent":
            user_agent,

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

        "Upgrade-Insecure-Requests":
            "1",

    })

    return session


def initialize_nse_session():

    print(
        "\nInitializing NSE session..."
    )

    session = create_nse_session()

    try:

        # ----------------------------------------------------
        # Step 1: NSE homepage
        # ----------------------------------------------------

        response = session.get(
            NSE_HOME_URL,
            timeout=REQUEST_TIMEOUT
        )

        print(
            "NSE homepage status: "
            f"{response.status_code}"
        )

        # ----------------------------------------------------
        # Step 2: NSE quote page
        #
        # This is important because the quote API may
        # expect cookies/context established by the page.
        # ----------------------------------------------------

        response = session.get(
            NSE_QUOTE_PAGE_URL,
            timeout=REQUEST_TIMEOUT,
            headers={
                "Referer": NSE_HOME_URL
            }
        )

        print(
            "NSE quote page status: "
            f"{response.status_code}"
        )

        if response.status_code >= 400:

            print(
                "WARNING: NSE quote page returned "
                f"HTTP {response.status_code}"
            )

        # ----------------------------------------------------
        # Display cookies for diagnostics.
        # ----------------------------------------------------

        print(
            "NSE session cookies: "
            f"{len(session.cookies)}"
        )

    except requests.RequestException as error:

        print(
            "WARNING: NSE session initialization "
            "failed:"
        )

        print(
            f"  {error}"
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
            "\nNo checkpoint file found."
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
# CLASSIFICATION HELPERS
# ============================================================

def build_classification_result(
    macro="",
    sector="",
    industry="",
    basic="",
    source="",
    confidence=NOT_RESOLVED,
    diagnosis="",
    status=STATUS_FAILED,
    http_status=""
):

    return {

        "Macro-Economic Sector":
            normalize_text(macro),

        "Sector":
            normalize_text(sector),

        "Industry":
            normalize_text(industry),

        "Basic Industry":
            normalize_text(basic),

        "Classification Source":
            normalize_text(source),

        "Classification Confidence":
            confidence,

        "Diagnosis":
            diagnosis,

        "Status":
            status,

        "HTTP Status":
            http_status,

        "Resolved At":
            datetime.now(
                timezone.utc
            ).isoformat(),

    }


# ============================================================
# NSE QUOTE REQUEST
# ============================================================

def request_nse_quote(
    session,
    symbol
):

    symbol = normalize_symbol(
        symbol
    )

    # --------------------------------------------------------
    # The quote page is requested before the API.
    #
    # This gives the API request the same session/cookie
    # context that a normal browser visit would establish.
    # --------------------------------------------------------

    referer = (
        f"{NSE_QUOTE_PAGE_URL}"
        f"?symbol={symbol}"
    )

    api_headers = {

        "Referer":
            referer,

        "Accept":
            "application/json, text/plain, */*",

        "X-Requested-With":
            "XMLHttpRequest",

        "Sec-Fetch-Dest":
            "empty",

        "Sec-Fetch-Mode":
            "cors",

        "Sec-Fetch-Site":
            "same-origin",

    }

    transient_attempt = 0
    forbidden_attempt = 0

    while True:

        try:

            print(
                "    Requesting NSE quote..."
            )

            response = session.get(

                NSE_QUOTE_API_URL,

                params={
                    "symbol": symbol
                },

                headers=api_headers,

                timeout=REQUEST_TIMEOUT

            )

            status = (
                response.status_code
            )

            print(
                f"    HTTP status: "
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

                    return {

                        "success":
                            False,

                        "payload":
                            {},

                        "status":
                            STATUS_INVALID,

                        "error":
                            "NSE_RESPONSE_NOT_JSON",

                        "http_status":
                            status,

                    }

                if not isinstance(
                    payload,
                    dict
                ):

                    return {

                        "success":
                            False,

                        "payload":
                            {},

                        "status":
                            STATUS_INVALID,

                        "error":
                            "NSE_RESPONSE_NOT_OBJECT",

                        "http_status":
                            status,

                    }

                return {

                    "success":
                        True,

                    "payload":
                        payload,

                    "status":
                        STATUS_RESOLVED,

                    "error":
                        "",

                    "http_status":
                        status,

                }

            # =================================================
            # 403 FORBIDDEN
            # =================================================
            #
            # IMPORTANT:
            #
            # Do NOT repeatedly retry 403.
            #
            # The previous implementation spent several
            # minutes retrying the same blocked endpoint.
            #
            # Instead:
            #
            # 1. Recreate the entire session once.
            # 2. Bootstrap homepage + quote page again.
            # 3. Retry the API once.
            # 4. If still 403 -> mark blocked.
            #
            # =================================================

            if status == 403:

                forbidden_attempt += 1

                print(
                    "    NSE returned "
                    "403 Forbidden."
                )

                if (
                    forbidden_attempt
                    > MAX_403_RETRIES
                ):

                    print(
                        "    NSE quote endpoint "
                        "remains blocked."
                    )

                    return {

                        "success":
                            False,

                        "payload":
                            {},

                        "status":
                            STATUS_BLOCKED,

                        "error":
                            "NSE_ACCESS_BLOCKED",

                        "http_status":
                            status,

                    }

                print(
                    "    Recreating NSE session "
                    "after 403..."
                )

                time.sleep(
                    random.uniform(
                        3,
                        6
                    )
                )

                # Return a special state so the
                # caller can actually recreate
                # the session object.
                return {

                    "success":
                        False,

                    "payload":
                        {},

                    "status":
                        STATUS_BLOCKED,

                    "error":
                        "NSE_SESSION_REINITIALIZE_REQUIRED",

                    "http_status":
                        status,

                    "reinitialize":
                        True,

                }

            # =================================================
            # TRANSIENT HTTP ERRORS
            # =================================================

            if status in {
                429,
                500,
                502,
                503,
                504
            }:

                transient_attempt += 1

                print(
                    "    Temporary NSE/server "
                    f"error: {status}"
                )

                if (
                    transient_attempt
                    > MAX_TRANSIENT_RETRIES
                ):

                    return {

                        "success":
                            False,

                        "payload":
                            {},

                        "status":
                            STATUS_FAILED,

                        "error":
                            (
                                "NSE_TRANSIENT_ERROR_"
                                f"{status}"
                            ),

                        "http_status":
                            status,

                    }

                backoff = min(
                    45,
                    5
                    * (
                        2
                        ** (
                            transient_attempt
                            - 1
                        )
                    )
                )

                jitter = random.uniform(
                    1,
                    4
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

            return {

                "success":
                    False,

                "payload":
                    {},

                "status":
                    STATUS_FAILED,

                "error":
                    (
                        "NSE_HTTP_ERROR_"
                        f"{status}"
                    ),

                "http_status":
                    status,

            }

        except requests.RequestException as error:

            transient_attempt += 1

            print(
                "    NSE request exception:"
            )

            print(
                f"    {error}"
            )

            if (
                transient_attempt
                > MAX_TRANSIENT_RETRIES
            ):

                return {

                    "success":
                        False,

                    "payload":
                        {},

                    "status":
                        STATUS_FAILED,

                    "error":
                        "NSE_REQUEST_EXCEPTION",

                    "http_status":
                        "",

                }

            sleep_for = (
                min(
                    45,
                    5
                    * (
                        2
                        ** (
                            transient_attempt
                            - 1
                        )
                    )
                )
                + random.uniform(
                    1,
                    4
                )
            )

            print(
                "    Retrying after "
                f"{sleep_for:.1f}s"
            )

            time.sleep(
                sleep_for
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

        return build_classification_result(

            diagnosis=
                "INVALID_NSE_PAYLOAD",

            status=
                STATUS_INVALID

        )

    industry_info = (
        payload.get(
            "industryInfo"
        )
    )

    if not isinstance(
        industry_info,
        dict
    ):

        return build_classification_result(

            diagnosis=
                "INDUSTRY_INFO_NOT_FOUND",

            status=
                STATUS_NOT_FOUND

        )

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

    if populated == 4:

        return build_classification_result(

            macro=macro,

            sector=sector,

            industry=industry,

            basic=basic,

            source=
                "NSE_QUOTE_EQUITY",

            confidence=
                HIGH_CONFIDENCE,

            diagnosis=
                "NSE_QUOTE_INDUSTRY_INFO_RESOLVED",

            status=
                STATUS_RESOLVED

        )

    if populated >= 2:

        return build_classification_result(

            macro=macro,

            sector=sector,

            industry=industry,

            basic=basic,

            source=
                "NSE_QUOTE_EQUITY",

            confidence=
                MEDIUM_CONFIDENCE,

            diagnosis=
                "NSE_QUOTE_INDUSTRY_INFO_PARTIAL",

            status=
                STATUS_RESOLVED

        )

    if populated == 1:

        return build_classification_result(

            macro=macro,

            sector=sector,

            industry=industry,

            basic=basic,

            source=
                "NSE_QUOTE_EQUITY",

            confidence=
                LOW_CONFIDENCE,

            diagnosis=
                "NSE_QUOTE_INDUSTRY_INFO_INCOMPLETE",

            status=
                STATUS_RESOLVED

        )

    return build_classification_result(

        diagnosis=
            "NSE_QUOTE_INDUSTRY_INFO_EMPTY",

        status=
            STATUS_NOT_FOUND

    )


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

    # --------------------------------------------------------
    # First request.
    # --------------------------------------------------------

    result = request_nse_quote(
        session,
        symbol
    )

    # --------------------------------------------------------
    # 403 requires a genuine new session.
    #
    # This is different from merely printing
    # "Reinitializing NSE session".
    # --------------------------------------------------------

    if result.get(
        "reinitialize"
    ):

        print(
            "    Creating a completely "
            "new NSE session..."
        )

        session = (
            initialize_nse_session()
        )

        result = request_nse_quote(
            session,
            symbol
        )

    # --------------------------------------------------------
    # Failed request.
    # --------------------------------------------------------

    if not result["success"]:

        status = result.get(
            "status",
            STATUS_FAILED
        )

        error = result.get(
            "error",
            "NSE_REQUEST_FAILED"
        )

        if status == STATUS_BLOCKED:

            return session, build_classification_result(

                diagnosis=
                    "NSE_ACCESS_BLOCKED",

                status=
                    STATUS_BLOCKED,

                http_status=
                    result.get(
                        "http_status",
                        403
                    )

            )

        if status == STATUS_NOT_FOUND:

            return session, build_classification_result(

                diagnosis=
                    error,

                status=
                    STATUS_NOT_FOUND,

                http_status=
                    result.get(
                        "http_status",
                        ""
                    )

            )

        return session, build_classification_result(

            diagnosis=
                error,

            status=
                STATUS_FAILED,

            http_status=
                result.get(
                    "http_status",
                    ""
                )

        )

    # --------------------------------------------------------
    # Parse NSE response.
    # --------------------------------------------------------

    classification = (
        extract_industry_info(
            result["payload"]
        )
    )

    classification[
        "HTTP Status"
    ] = result.get(
        "http_status",
        200
    )

    return session, classification


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

        "Status":
            classification.get(
                "Status",
                STATUS_FAILED
            ),

        "HTTP Status":
            classification.get(
                "HTTP Status",
                ""
            ),

        "Resolved At":
            classification.get(
                "Resolved At",
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

        "Status",

        "HTTP Status",

        "Resolved At",

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

    # 16 columns = P
    worksheet.update(

        range_name=(
            f"A1:P{len(data)}"
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
        row.get(
            "Classification Confidence"
        ) == HIGH_CONFIDENCE
        for row in rows
    )

    medium = sum(
        row.get(
            "Classification Confidence"
        ) == MEDIUM_CONFIDENCE
        for row in rows
    )

    low = sum(
        row.get(
            "Classification Confidence"
        ) == LOW_CONFIDENCE
        for row in rows
    )

    unresolved = sum(
        row.get(
            "Classification Confidence"
        ) == NOT_RESOLVED
        for row in rows
    )

    blocked = sum(
        row.get(
            "Status"
        ) == STATUS_BLOCKED
        for row in rows
    )

    failed = sum(
        row.get(
            "Status"
        ) == STATUS_FAILED
        for row in rows
    )

    not_found = sum(
        row.get(
            "Status"
        ) == STATUS_NOT_FOUND
        for row in rows
    )

    resolved = (
        high
        + medium
        + low
    )

    print("\n")
    print("=" * 70)

    print(
        "NSE SECTOR & INDUSTRY DIAGNOSTIC"
    )

    print("=" * 70)

    print(
        f"Processed Rows          : {total}"
    )

    print(
        f"High Confidence         : {high}"
    )

    print(
        f"Medium Confidence       : {medium}"
    )

    print(
        f"Low Confidence          : {low}"
    )

    print(
        f"Not Resolved            : {unresolved}"
    )

    print(
        f"NSE Access Blocked      : {blocked}"
    )

    print(
        f"Request Failed          : {failed}"
    )

    print(
        f"Symbol/Info Not Found   : {not_found}"
    )

    print("-" * 70)

    if total:

        print(
            "Resolution Rate         : "
            f"{(resolved / total) * 100:.1f}%"
        )

        print(
            "NSE Access Block Rate   : "
            f"{(blocked / total) * 100:.1f}%"
        )

    print("-" * 70)

    print(
        f"Diagnostic Sheet        : "
        f"{DIAGNOSTIC_SHEET}"
    )

    print(
        f"Checkpoint File         : "
        f"{CHECKPOINT_FILE}"
    )

    print("=" * 70)


# ============================================================
# CHECKPOINT RESULT VALIDATION
# ============================================================

def is_reusable_checkpoint(
    checkpoint_result
):

    if not isinstance(
        checkpoint_result,
        dict
    ):
        return False

    status = checkpoint_result.get(
        "Status",
        ""
    )

    confidence = checkpoint_result.get(
        "Classification Confidence",
        NOT_RESOLVED
    )

    # Successful classifications are reusable.
    if (
        status == STATUS_RESOLVED
        and confidence in {
            HIGH_CONFIDENCE,
            MEDIUM_CONFIDENCE,
            LOW_CONFIDENCE
        }
    ):
        return True

    # We also deliberately retain blocked status
    # so repeated GitHub Actions runs don't hammer
    # the same NSE-blocked symbols every 30 minutes.
    if status == STATUS_BLOCKED:

        return True

    # Symbol-not-found can also be reused.
    if status == STATUS_NOT_FOUND:

        return True

    return False


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

    session = (
        initialize_nse_session()
    )

    diagnostic_rows = []

    completed_since_checkpoint = 0

    blocked_count = 0

    resolved_count = 0

    print(
        "\nBeginning NSE company classification..."
    )

    print(
        f"Symbols to process: "
        f"{len(records)}"
    )

    for index, record in enumerate(
        records,
        start=1
    ):

        symbol = record[
            "NSE Symbol"
        ]

        # ====================================================
        # CHECKPOINT
        # ====================================================

        checkpoint_result = (
            checkpoint.get(symbol)
        )

        if is_reusable_checkpoint(
            checkpoint_result
        ):

            print(
                f"\n[{index}/{len(records)}] "
                f"{symbol} "
                "reusing checkpoint."
            )

            classification = (
                checkpoint_result
            )

        else:

            print(
                f"\n[{index}/{len(records)}]"
            )

            session, classification = (
                resolve_stock(
                    session,
                    record
                )
            )

            # =================================================
            # CHECKPOINT EVERY RESULT
            #
            # This is intentional.
            #
            # Previously only successful classifications
            # were checkpointed.
            #
            # Now a persistent 403 is also remembered.
            # =================================================

            checkpoint[symbol] = (
                classification
            )

            completed_since_checkpoint += 1

            if (
                completed_since_checkpoint
                >= CHECKPOINT_EVERY
            ):

                save_checkpoint(
                    checkpoint
                )

                completed_since_checkpoint = 0

        # ====================================================
        # COUNTERS
        # ====================================================

        status = classification.get(
            "Status",
            STATUS_FAILED
        )

        confidence = classification.get(
            "Classification Confidence",
            NOT_RESOLVED
        )

        if (
            confidence in {
                HIGH_CONFIDENCE,
                MEDIUM_CONFIDENCE,
                LOW_CONFIDENCE
            }
        ):

            resolved_count += 1

        if status == STATUS_BLOCKED:

            blocked_count += 1

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
        # DELAY
        #
        # Don't delay after the final symbol.
        # ====================================================

        if index < len(records):

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
    # WRITE DIAGNOSTIC
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
        "\nResolved this run: "
        f"{resolved_count}"
    )

    print(
        "NSE-blocked this run: "
        f"{blocked_count}"
    )

    print(
        "\nNSE classification update complete."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
