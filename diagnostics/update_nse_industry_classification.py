import os
import csv
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

# ------------------------------------------------------------
# Checkpoint file
# ------------------------------------------------------------

CHECKPOINT_FILE = os.getenv(
    "NSE_CLASSIFICATION_CHECKPOINT",
    "data/nse_classification_checkpoint.json"
)

# ------------------------------------------------------------
# Request controls
# ------------------------------------------------------------

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
        "2.0"
    )
)

MAX_DELAY = float(
    os.getenv(
        "NSE_CLASSIFICATION_MAX_DELAY",
        "5.0"
    )
)

# Number of successful symbols after which
# checkpoint is persisted.
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

        # Only process stocks whose sector
        # is currently unknown.
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

    # Browser-like headers.
    #
    # These are intentionally kept at the
    # session level so all NSE requests share
    # the same browser context.

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

        if response.status_code == 403:

            print(
                "WARNING: NSE homepage returned "
                "403 during session initialization."
            )

            print(
                "Quote requests may also be blocked "
                "from this GitHub Actions runner."
            )

        elif response.status_code >= 400:

            print(
                "WARNING: NSE homepage returned "
                f"HTTP {response.status_code}"
            )

    except requests.RequestException as error:

        print(
            "WARNING: NSE homepage request failed:"
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
# NSE QUOTE
# ============================================================

def request_nse_quote(
    session,
    symbol
):

    symbol = normalize_symbol(
        symbol
    )

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

    for attempt in range(
        1,
        MAX_RETRIES_PER_SYMBOL + 1
    ):

        try:

            print(
                f"    NSE request "
                f"{attempt}/"
                f"{MAX_RETRIES_PER_SYMBOL}"
            )

            response = session.get(

                url,

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

                    payload = None

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

                print(
                    "    NSE response "
                    "did not contain JSON object."
                )

            # ------------------------------------------------
            # FORBIDDEN
            # ------------------------------------------------

            elif status == 403:

                print(
                    "    NSE returned "
                    "403 Forbidden."
                )

                if attempt < MAX_RETRIES_PER_SYMBOL:

                    backoff = min(
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

                    # Reinitialize session after
                    # repeated 403 responses.
                    if attempt >= 2:

                        print(
                            "    Reinitializing "
                            "NSE session..."
                        )

                    continue

            # ------------------------------------------------
            # RATE LIMIT
            # ------------------------------------------------

            elif status in {
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

                if attempt < MAX_RETRIES_PER_SYMBOL:

                    backoff = min(
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

            else:

                print(
                    "    Unexpected HTTP "
                    f"status: {status}"
                )

        except requests.RequestException as error:

            print(
                "    NSE request exception:"
            )

            print(
                f"    {error}"
            )

            if attempt < MAX_RETRIES_PER_SYMBOL:

                sleep_for = (
                    5
                    * (
                        2
                        ** (
                            attempt - 1
                        )
                    )
                    + random.uniform(
                        1,
                        5
                    )
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
            (
                "NSE_QUOTE_REQUEST_FAILED"
            ),

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
                "",

            "Classification Confidence":
                NOT_RESOLVED,

            "Diagnosis":
                classification["error"],

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

        confidence = "HIGH"

        diagnosis = (
            "NSE_QUOTE_INDUSTRY_INFO_RESOLVED"
        )

    elif populated >= 2:

        confidence = "MEDIUM"

        diagnosis = (
            "NSE_QUOTE_INDUSTRY_INFO_PARTIAL"
        )

    else:

        confidence = "LOW"

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

    session = (
        create_nse_session()
    )

    diagnostic_rows = []

    successful_since_checkpoint = 0

    unresolved_count = 0

    for index, record in enumerate(
        records,
        start=1
    ):

        symbol = record[
            "NSE Symbol"
        ]

        # ----------------------------------------------------
        # Reuse successful checkpoint
        # ----------------------------------------------------

        checkpoint_result = (
            checkpoint.get(symbol)
        )

        if (
            isinstance(
                checkpoint_result,
                dict
            )
            and checkpoint_result.get(
                "Classification Confidence"
            )
            in {
                HIGH_CONFIDENCE,
                MEDIUM_CONFIDENCE,
                LOW_CONFIDENCE
            }
        ):

            print(
                f"\n[{index}/{len(records)}] "
                f"{symbol} "
                "already resolved in checkpoint."
            )

            classification = (
                checkpoint_result
            )

        else:

            print(
                f"\n[{index}/{len(records)}]"
            )

            classification = (
                resolve_stock(
                    session,
                    record
                )
            )

            # ------------------------------------------------
            # Store result immediately.
            # ------------------------------------------------

            if (
                classification[
                    "Classification Confidence"
                ]
                in {
                    HIGH_CONFIDENCE,
                    MEDIUM_CONFIDENCE,
                    LOW_CONFIDENCE
                }
            ):
            
                checkpoint[symbol] = classification

            successful_since_checkpoint += 1

            # ------------------------------------------------
            # Persist checkpoint periodically.
            # ------------------------------------------------

            if (
                successful_since_checkpoint
                >= CHECKPOINT_EVERY
            ):

                save_checkpoint(
                    checkpoint
                )

                successful_since_checkpoint = 0

        if (
            classification[
                "Classification Confidence"
            ]
            == NOT_RESOLVED
        ):

            unresolved_count += 1

        diagnostic_rows.append(
            build_diagnostic_row(
                record,
                classification
            )
        )

        # ----------------------------------------------------
        # Random delay between symbols.
        # ----------------------------------------------------

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
    # FINAL CHECKPOINT SAVE
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

    print_summary(
        diagnostic_rows
    )

    print(
        "\nUnresolved rows in this run: "
        f"{unresolved_count}"
    )

    print(
        "\nNSE classification update complete."
    )


if __name__ == "__main__":

    main()
