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
# FILES
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
# CONFIDENCE
# ============================================================

HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
NOT_RESOLVED = "NOT_RESOLVED"


# ============================================================
# NSE ACCESS STATES
# ============================================================

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
# HTTP
# ============================================================

TRANSIENT_STATUSES = {
    429,
    500,
    502,
    503,
    504,
}


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
# SCRIPT VERSION
# ============================================================

SCRIPT_VERSION = (
    "NSE_CLASSIFICATION_COLLECTOR_V2"
)


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
# HEADER NORMALIZATION
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
# CLASSIFICATION HELPERS
# ============================================================

def classification_fields():

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

        for field in classification_fields()

    )


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

    # Full NSE hierarchy
    if (
        macro
        and sector
        and industry
        and basic
    ):

        return HIGH_CONFIDENCE

    # Meaningful classification:
    # Sector + Industry + Basic Industry
    if (
        sector
        and industry
        and basic
    ):

        return MEDIUM_CONFIDENCE

    # At least two classification fields
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

    # One field
    if populated == 1:

        return LOW_CONFIDENCE

    return NOT_RESOLVED


# ============================================================
# STOCK MASTER
# ============================================================

def read_unknown_stocks(
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

        dict(
            zip(
                headers,
                row
            )
        )

        for row in values[1:]

    ]

    selected = []

    for row_number, record in enumerate(
        records,
        start=2
    ):

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

        if not is_unknown(
            sector
        ):

            continue

        nse_symbol = normalize_symbol(
            ticker
        )

        if not nse_symbol:

            continue

        selected.append({

            "Sheet Row":
                row_number,

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
# NSE HOMEPAGE INITIALIZATION
# ============================================================

def initialize_nse_session(
    session
):

    print(
        "\nInitializing NSE session..."
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
# CHECKPOINT NORMALIZATION
# ============================================================

def normalize_checkpoint(
    checkpoint
):

    if not isinstance(
        checkpoint,
        dict
    ):

        return {

            "metadata": {},

            "classifications": {}

        }

    # --------------------------------------------------------
    # NEW FORMAT
    # --------------------------------------------------------

    classifications = checkpoint.get(
        "classifications"
    )

    metadata = checkpoint.get(
        "metadata",
        {}
    )

    if isinstance(
        classifications,
        dict
    ):

        return {

            "metadata":
                (
                    metadata
                    if isinstance(
                        metadata,
                        dict
                    )
                    else {}
                ),

            "classifications":
                classifications

        }

    # --------------------------------------------------------
    # OLD FORMAT
    #
    # symbol -> classification
    # --------------------------------------------------------

    converted = {}

    for symbol, value in checkpoint.items():

        if symbol in {
            "metadata",
            "classifications",
            "results",
            "records",
            "data",
            "classification",
        }:

            continue

        normalized = normalize_symbol(
            symbol
        )

        if not normalized:

            continue

        if isinstance(
            value,
            dict
        ):

            converted[
                normalized
            ] = value

    # --------------------------------------------------------
    # OTHER OLD NESTED FORMATS
    # --------------------------------------------------------

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

    return {

        "metadata": (
            metadata
            if isinstance(
                metadata,
                dict
            )
            else {}
        ),

        "classifications":
            converted,

    }


# ============================================================
# LOAD CHECKPOINT
# ============================================================

def load_checkpoint():

    if not os.path.exists(
        CHECKPOINT_FILE
    ):

        print(
            "\nNo NSE checkpoint found."
        )

        return {

            "metadata": {},

            "classifications": {}

        }

    try:

        with open(
            CHECKPOINT_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            raw_checkpoint = json.load(
                file
            )

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

        return {

            "metadata": {},

            "classifications": {}

        }

    checkpoint = normalize_checkpoint(
        raw_checkpoint
    )

    print(
        "\nCheckpoint loaded:"
    )

    print(
        "  Records: "
        f"{len(checkpoint['classifications'])}"
    )

    return checkpoint


# ============================================================
# SAVE CHECKPOINT
# ============================================================

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

    checkpoint["metadata"] = {

        "updated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "script_version":
            SCRIPT_VERSION,

        "source":
            "NSE_QUOTE_EQUITY",

        "classification_levels":
            [
                "Macro-Economic Sector",
                "Sector",
                "Industry",
                "Basic Industry",
            ],

    }

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
        "Checkpoint saved:"
        f" {CHECKPOINT_FILE}"
    )


# ============================================================
# CHECKPOINT SUCCESS VALIDATION
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
            LOW_CONFIDENCE,
        }
    )


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
            "    NSE quote request "
            f"(attempt "
            f"{transient_attempt + 1}/"
            f"{MAX_TRANSIENT_RETRIES + 1})"
        )

        try:

            response = session.get(

                NSE_QUOTE_API_URL,

                params={
                    "symbol":
                        symbol
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
                "    Retrying after "
                f"{delay:.1f}s"
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

        # ----------------------------------------------------
        # 403 = HARD CIRCUIT BREAKER
        # ----------------------------------------------------

        if status == 403:

            print(
                "\n"
                "****************************************************"
            )

            print(
                "NSE QUOTE API HTTP 403"
            )

            print(
                "NSE access is BLOCKED."
            )

            print(
                "No retry."
            )

            print(
                "No session refresh."
            )

            print(
                "No additional NSE requests."
            )

            print(
                "****************************************************"
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

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # TRANSIENT
        # ----------------------------------------------------

        if status in TRANSIENT_STATUSES:

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
                "    Temporary HTTP "
                f"{status}. "
                f"Retrying after "
                f"{retry_delay:.1f}s"
            )

            time.sleep(
                retry_delay
            )

            continue

        # ----------------------------------------------------
        # OTHER HTTP
        # ----------------------------------------------------

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
# EXTRACT INDUSTRY INFORMATION
# ============================================================

def extract_industry_info(
    payload
):

    classification = (
        classification_fields()
    )

    if not isinstance(
        payload,
        dict
    ):

        return {

            **classification,

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

            **classification,

            "success":
                False,

            "error":
                "INDUSTRY_INFO_NOT_FOUND",

        }

    classification[
        "Macro-Economic Sector"
    ] = normalize_text(
        industry_info.get(
            "macro",
            ""
        )
    )

    classification[
        "Sector"
    ] = normalize_text(
        industry_info.get(
            "sector",
            ""
        )
    )

    classification[
        "Industry"
    ] = normalize_text(
        industry_info.get(
            "industry",
            ""
        )
    )

    classification[
        "Basic Industry"
    ] = normalize_text(
        industry_info.get(
            "basicIndustry",
            ""
        )
    )

    confidence = calculate_confidence(
        classification
    )

    return {

        **classification,

        "success":
            confidence != NOT_RESOLVED,

        "confidence":
            confidence,

        "error":
            (
                ""
                if confidence != NOT_RESOLVED
                else "INDUSTRY_INFO_EMPTY"
            ),

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
        f"\nResolving {symbol} - "
        f"{record['Company Name']}"
    )

    result = request_nse_quote(
        session,
        symbol
    )

    if result[
        "access_blocked"
    ]:

        return {

            **classification_fields(),

            "Classification Source":
                "",

            "Classification Confidence":
                NOT_RESOLVED,

            "Diagnosis":
                NSE_ACCESS_BLOCKED,

            "_nse_access_blocked":
                True,

        }

    if not result[
        "success"
    ]:

        return {

            **classification_fields(),

            "Classification Source":
                "",

            "Classification Confidence":
                NOT_RESOLVED,

            "Diagnosis":
                result[
                    "error"
                ],

            "_nse_access_blocked":
                False,

        }

    extracted = (
        extract_industry_info(
            result["payload"]
        )
    )

    if not extracted[
        "success"
    ]:

        return {

            **classification_fields(),

            "Classification Source":
                "NSE_QUOTE_EQUITY",

            "Classification Confidence":
                NOT_RESOLVED,

            "Diagnosis":
                extracted[
                    "error"
                ],

            "_nse_access_blocked":
                False,

        }

    return {

        "Macro-Economic Sector":
            extracted[
                "Macro-Economic Sector"
            ],

        "Sector":
            extracted[
                "Sector"
            ],

        "Industry":
            extracted[
                "Industry"
            ],

        "Basic Industry":
            extracted[
                "Basic Industry"
            ],

        "Classification Source":
            "NSE_QUOTE_EQUITY",

        "Classification Confidence":
            extracted[
                "confidence"
            ],

        "Diagnosis":
            (
                "NSE_QUOTE_INDUSTRY_INFO_RESOLVED"
                if extracted[
                    "confidence"
                ] == HIGH_CONFIDENCE
                else
                "NSE_QUOTE_INDUSTRY_INFO_PARTIAL"
            ),

        "Classification Retrieved At":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "_nse_access_blocked":
            False,

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
        "NSE INDUSTRY CLASSIFICATION COLLECTOR"
    )

    print(
        f"Version: {SCRIPT_VERSION}"
    )

    print(
        "Circuit Breaker Mode"
    )

    print(
        "============================================================"
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
            "\nNo UNKNOWN-sector equities require "
            "NSE collection."
        )

        return

    checkpoint = (
        load_checkpoint()
    )

    classifications = checkpoint[
        "classifications"
    ]

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Probe ONLY a stock that does NOT already have a
    # successful checkpoint classification.
    # --------------------------------------------------------

    pending_records = [

        record

        for record in records

        if not is_successful_classification(
            classifications.get(
                record[
                    "NSE Symbol"
                ]
            )
        )

    ]

    print(
        "\nCheckpoint status:"
    )

    print(
        f"  Total unresolved Stock_Master rows: "
        f"{len(records)}"
    )

    print(
        f"  Already classified in checkpoint: "
        f"{len(records) - len(pending_records)}"
    )

    print(
        f"  Requiring NSE request: "
        f"{len(pending_records)}"
    )

    # --------------------------------------------------------
    # NOTHING TO COLLECT
    # --------------------------------------------------------

    if not pending_records:

        print(
            "\nAll selected stocks already have "
            "successful checkpoint classifications."
        )

        save_checkpoint(
            checkpoint
        )

        print(
            "\nCollector completed without "
            "additional NSE requests."
        )

        return

    # --------------------------------------------------------
    # NSE SESSION
    # --------------------------------------------------------

    session = create_nse_session()

    homepage_accessible = (
        initialize_nse_session(
            session
        )
    )

    if not homepage_accessible:

        print(
            "\nNSE homepage is inaccessible."
        )

        print(
            "No quote requests will be attempted."
        )

        save_checkpoint(
            checkpoint
        )

        return

    # --------------------------------------------------------
    # ACTUAL API PROBE
    #
    # ONLY pending stock is used.
    # --------------------------------------------------------

    probe_record = (
        pending_records[0]
    )

    probe_symbol = (
        probe_record[
            "NSE Symbol"
        ]
    )

    print(
        "\n"
        "============================================================"
    )

    print(
        "NSE QUOTE ENDPOINT ACCESS PROBE"
    )

    print(
        f"Probe symbol: {probe_symbol}"
    )

    print(
        "============================================================"
    )

    probe_result = request_nse_quote(
        session,
        probe_symbol
    )

    if probe_result[
        "access_blocked"
    ]:

        print(
            "\nNSE quote API is BLOCKED."
        )

        print(
            "Circuit breaker activated."
        )

        save_checkpoint(
            checkpoint
        )

        return

    if not probe_result[
        "success"
    ]:

        print(
            "\nNSE quote API access could "
            "not be confirmed."
        )

        print(
            f"Reason: "
            f"{probe_result['error']}"
        )

        print(
            "No further requests will be made "
            "in this run."
        )

        save_checkpoint(
            checkpoint
        )

        return

    print(
        "\nNSE quote API access confirmed."
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # The probe already fetched the first pending stock.
    # Reuse it instead of requesting it twice.
    # --------------------------------------------------------

    successful_since_checkpoint = 0

    unresolved_count = 0

    access_blocked = False

    processed_count = 0

    for index, record in enumerate(
        pending_records,
        start=1
    ):

        symbol = record[
            "NSE Symbol"
        ]

        print(
            "\n"
            "------------------------------------------------------------"
        )

        print(
            f"[{index}/{len(pending_records)}] "
            f"{symbol}"
        )

        print(
            f"Company: "
            f"{record['Company Name']}"
        )

        print(
            "------------------------------------------------------------"
        )

        # ----------------------------------------------------
        # Reuse probe response for first stock
        # ----------------------------------------------------

        if index == 1:

            result = probe_result

            if result[
                "success"
            ]:

                extracted = (
                    extract_industry_info(
                        result[
                            "payload"
                        ]
                    )
                )

                if extracted[
                    "success"
                ]:

                    classification = {

                        "Macro-Economic Sector":
                            extracted[
                                "Macro-Economic Sector"
                            ],

                        "Sector":
                            extracted[
                                "Sector"
                            ],

                        "Industry":
                            extracted[
                                "Industry"
                            ],

                        "Basic Industry":
                            extracted[
                                "Basic Industry"
                            ],

                        "Classification Source":
                            "NSE_QUOTE_EQUITY",

                        "Classification Confidence":
                            extracted[
                                "confidence"
                            ],

                        "Diagnosis":
                            (
                                "NSE_QUOTE_INDUSTRY_INFO_RESOLVED"
                                if extracted[
                                    "confidence"
                                ] == HIGH_CONFIDENCE
                                else
                                "NSE_QUOTE_INDUSTRY_INFO_PARTIAL"
                            ),

                        "Classification Retrieved At":
                            datetime.now(
                                timezone.utc
                            ).isoformat(),

                        "_nse_access_blocked":
                            False,

                    }

                else:

                    classification = {

                        **classification_fields(),

                        "Classification Source":
                            "NSE_QUOTE_EQUITY",

                        "Classification Confidence":
                            NOT_RESOLVED,

                        "Diagnosis":
                            extracted[
                                "error"
                            ],

                        "_nse_access_blocked":
                            False,

                    }

            else:

                classification = {

                    **classification_fields(),

                    "Classification Source":
                        "",

                    "Classification Confidence":
                        NOT_RESOLVED,

                    "Diagnosis":
                        result[
                            "error"
                        ],

                    "_nse_access_blocked":
                        False,

                }

        else:

            classification = (
                resolve_stock(
                    session,
                    record
                )
            )

        processed_count += 1

        # ----------------------------------------------------
        # 403 CIRCUIT BREAKER
        # ----------------------------------------------------

        if classification.get(
            "_nse_access_blocked",
            False
        ):

            access_blocked = True

            print(
                "\n"
                "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
            )

            print(
                "GLOBAL NSE CIRCUIT BREAKER ACTIVATED"
            )

            print(
                f"Triggering symbol: {symbol}"
            )

            print(
                "No further NSE requests will be made."
            )

            print(
                "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
            )

            break

        # ----------------------------------------------------
        # SAVE SUCCESSFUL CLASSIFICATION
        # ----------------------------------------------------

        if is_successful_classification(
            classification
        ):

            # Remove internal control field
            classification_to_save = {
                key: value
                for key, value
                in classification.items()
                if not key.startswith("_")
            }

            classifications[
                symbol
            ] = classification_to_save

            successful_since_checkpoint += 1

            print(
                "Classification saved to checkpoint."
            )

            print(
                f"  Sector: "
                f"{classification.get('Sector', '')}"
            )

            print(
                f"  Industry: "
                f"{classification.get('Industry', '')}"
            )

            print(
                f"  Basic Industry: "
                f"{classification.get('Basic Industry', '')}"
            )

            print(
                f"  Confidence: "
                f"{classification.get('Classification Confidence', '')}"
            )

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

            print(
                "Classification NOT resolved."
            )

            print(
                f"  Diagnosis: "
                f"{classification.get('Diagnosis', '')}"
            )

        # ----------------------------------------------------
        # WAIT BEFORE NEXT REQUEST
        # ----------------------------------------------------

        if (
            not access_blocked
            and index
            < len(pending_records)
        ):

            delay = random.uniform(
                MIN_DELAY,
                MAX_DELAY
            )

            print(
                f"Waiting {delay:.1f}s "
                "before next NSE request..."
            )

            time.sleep(
                delay
            )

    # --------------------------------------------------------
    # FINAL CHECKPOINT
    # --------------------------------------------------------

    save_checkpoint(
        checkpoint
    )

    print(
        "\n"
        "============================================================"
    )

    print(
        "COLLECTOR SUMMARY"
    )

    print(
        "============================================================"
    )

    print(
        f"Pending before run     : "
        f"{len(pending_records)}"
    )

    print(
        f"Processed this run     : "
        f"{processed_count}"
    )

    print(
        f"Successful checkpoint  : "
        f"{len(classifications)}"
    )

    print(
        f"Unresolved this run    : "
        f"{unresolved_count}"
    )

    print(
        f"NSE access blocked     : "
        f"{access_blocked}"
    )

    print(
        f"Checkpoint file        : "
        f"{CHECKPOINT_FILE}"
    )

    print(
        "============================================================"
    )

    if access_blocked:

        print(
            "\nCollector stopped because NSE "
            "returned HTTP 403."
        )

    else:

        print(
            "\nNSE classification collection completed."
        )


if __name__ == "__main__":

    main()
