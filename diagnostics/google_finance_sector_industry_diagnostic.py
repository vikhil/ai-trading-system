import os
import time
import json
from datetime import datetime

import gspread
import pandas as pd
import yfinance as yf
from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# CONFIGURATION
# ============================================================

STOCK_MASTER_SHEET = "Stock_Master"
DIAGNOSTIC_SHEET = "GF_Sector_Industry_Diagnostic"

# Delay between Yahoo Finance requests.
# Helps reduce throttling for a batch of 70 stocks.
REQUEST_DELAY_SECONDS = 1.0

# Number of retries for temporary Yahoo errors.
MAX_RETRIES = 3

# Minimum confidence threshold for an automatic resolution.
# The script itself does not write to Stock_Master, so this is
# primarily informational.
HIGH_CONFIDENCE = "HIGH"
MEDIUM_CONFIDENCE = "MEDIUM"
LOW_CONFIDENCE = "LOW"
NOT_RESOLVED = "NOT_RESOLVED"


# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

def connect_to_google_sheet():
    """
    Connect to the existing Google Sheet using the project's
    existing GOOGLE_CREDENTIALS environment-variable authentication.
    """

    print("Connecting to Google Sheet...")

    google_credentials = os.getenv("GOOGLE_CREDENTIALS")

    if not google_credentials:
        raise RuntimeError(
            "GOOGLE_CREDENTIALS environment variable is not configured."
        )

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ]

    credentials_dict = json.loads(google_credentials)

    credentials = ServiceAccountCredentials.from_json_keyfile_dict(
        credentials_dict,
        scope
    )

    client = gspread.authorize(credentials)

    spreadsheet = client.open_by_key(
        "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"
    )

    print("Connected")

    return spreadsheet


# ============================================================
# COLUMN HELPERS
# ============================================================

def find_column(headers, candidates, required=True):
    """
    Find a column using case-insensitive and whitespace-insensitive
    matching.

    Example:
        'Company Name'
        'Company_Name'
        'company name'

    are treated as equivalent.
    """

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

        key = normalize_header(candidate)

        if key in normalized:
            return normalized[key]

    if required:
        raise RuntimeError(
            f"Required column not found. "
            f"Tried: {candidates}. "
            f"Available columns: {list(headers)}"
        )

    return None


def normalize_text(value):
    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# READ STOCK MASTER
# ============================================================

def read_stock_master(spreadsheet):
    """
    Read Stock_Master and return only rows where Sector is
    currently UNKNOWN / blank.

    NSE symbol is derived from the Ticker column whenever
    the ticker is in Yahoo Finance format, e.g.:

        3BBLACKBIO.NS -> 3BBLACKBIO
        RELIANCE.NS   -> RELIANCE
        KLBRENG-B.NS  -> KLBRENG-B

    This avoids requiring a dedicated NSE Symbol column
    in Stock_Master.
    """

    worksheet = spreadsheet.worksheet(STOCK_MASTER_SHEET)

    values = worksheet.get_all_values()

    if not values:
        raise RuntimeError("Stock_Master is empty.")

    headers = values[0]

    print("\nStock_Master columns detected:")
    for header in headers:
        print(f"  - {header}")

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

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
            "sector",
        ]
    )

    industry_col = find_column(
        headers,
        [
            "Industry",
            "industry",
        ],
        required=False
    )

    records = [
        dict(zip(headers, row))
        for row in values[1:]
    ]

    selected = []

    for record in records:

        # ----------------------------------------------------
        # Existing sector
        # ----------------------------------------------------

        sector = normalize_text(
            record.get(sector_col, "")
        )

        # ----------------------------------------------------
        # Existing industry
        # ----------------------------------------------------

        industry = ""

        if industry_col:
            industry = normalize_text(
                record.get(industry_col, "")
            )

        # ----------------------------------------------------
        # Ticker
        # ----------------------------------------------------

        ticker = normalize_text(
            record.get(ticker_col, "")
        )

        company_name = normalize_text(
            record.get(company_col, "")
        )

        # ----------------------------------------------------
        # Only process UNKNOWN / blank sectors
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

        # ----------------------------------------------------
        # Derive NSE symbol from Yahoo ticker
        # ----------------------------------------------------

        nse_symbol = ticker

        if ticker.upper().endswith(".NS"):
            nse_symbol = ticker[:-3]

        elif ticker.upper().endswith(".NSE"):
            nse_symbol = ticker[:-4]

        # ----------------------------------------------------
        # If ticker is still empty, skip the row
        # ----------------------------------------------------

        if not nse_symbol:
            continue

        # ----------------------------------------------------
        # Keep equity-like rows
        # ----------------------------------------------------

        equity_type = "EQUITY"

        selected.append({
            "Ticker": ticker,
            "NSE Symbol": nse_symbol,
            "Company Name": company_name,
            "Existing Sector": sector,
            "Existing Industry": industry,
            "Equity Type": equity_type,
        })

    print(
        f"\nStock Master Rows: {len(records)}"
    )

    print(
        f"Unknown-Sector Equity Rows: {len(selected)}"
    )

    return selected


# ============================================================
# YAHOO FINANCE LOOKUP
# ============================================================

def build_yahoo_ticker(nse_symbol):
    """
    Convert NSE symbol into the Yahoo Finance ticker format.
    """

    symbol = normalize_text(nse_symbol)

    if not symbol:
        return ""

    # Already in Yahoo format.
    if symbol.upper().endswith(".NS"):
        return symbol.upper()

    # Stock_Master may contain symbols such as KLBRENG-B.
    return f"{symbol.upper()}.NS"


def get_yahoo_metadata(nse_symbol):
    """
    Retrieve metadata from Yahoo Finance through yfinance.

    Returns:
        dictionary containing sector, industry, price, market cap,
        currency and confidence information.
    """

    yahoo_ticker = build_yahoo_ticker(nse_symbol)

    if not yahoo_ticker:
        return {
            "Yahoo Ticker": "",
            "Yahoo Sector": "",
            "Yahoo Industry": "",
            "Yahoo Price": "",
            "Yahoo Market Cap": "",
            "Yahoo Currency": "",
            "Resolution Source": "",
            "Resolution Confidence": NOT_RESOLVED,
            "Diagnosis": "MISSING_NSE_SYMBOL",
        }

    last_error = ""

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            print(
                f"  Yahoo lookup: {yahoo_ticker} "
                f"(attempt {attempt}/{MAX_RETRIES})"
            )

            ticker = yf.Ticker(yahoo_ticker)

            # ------------------------------------------------
            # Use fast_info where possible for market data.
            # ------------------------------------------------

            price = ""
            market_cap = ""
            currency = ""

            try:
                fast_info = ticker.fast_info

                if fast_info:
                    price = fast_info.get(
                        "last_price",
                        ""
                    )

                    market_cap = fast_info.get(
                        "market_cap",
                        ""
                    )

                    currency = fast_info.get(
                        "currency",
                        ""
                    )

            except Exception:
                pass

            # ------------------------------------------------
            # info contains sector / industry metadata.
            # ------------------------------------------------

            info = {}

            try:
                info = ticker.info or {}
            except Exception as exc:
                last_error = str(exc)

            sector = normalize_text(
                info.get("sector", "")
            )

            industry = normalize_text(
                info.get("industry", "")
            )

            # Some Yahoo responses may contain market data
            # even when fast_info did not return it.
            if not price:
                price = info.get("currentPrice", "")

            if not market_cap:
                market_cap = info.get("marketCap", "")

            if not currency:
                currency = info.get("currency", "")

            # ------------------------------------------------
            # Determine confidence.
            # ------------------------------------------------

            if sector and industry:
                confidence = HIGH_CONFIDENCE
                diagnosis = "SECTOR_INDUSTRY_RESOLVED"
                source = "YAHOO_FINANCE"

            elif sector:
                confidence = MEDIUM_CONFIDENCE
                diagnosis = "SECTOR_RESOLVED_INDUSTRY_MISSING"
                source = "YAHOO_FINANCE"

            elif industry:
                confidence = LOW_CONFIDENCE
                diagnosis = "INDUSTRY_FOUND_SECTOR_MISSING"
                source = "YAHOO_FINANCE"

            else:
                confidence = NOT_RESOLVED
                diagnosis = "SECTOR_INDUSTRY_NOT_RESOLVED"
                source = ""

            return {
                "Yahoo Ticker": yahoo_ticker,
                "Yahoo Sector": sector,
                "Yahoo Industry": industry,
                "Yahoo Price": price,
                "Yahoo Market Cap": market_cap,
                "Yahoo Currency": currency,
                "Resolution Source": source,
                "Resolution Confidence": confidence,
                "Diagnosis": diagnosis,
                "Lookup Error": last_error,
            }

        except Exception as exc:

            last_error = str(exc)

            print(
                f"  Yahoo lookup failed: {last_error}"
            )

            if attempt < MAX_RETRIES:
                wait_time = attempt * 3

                print(
                    f"  Waiting {wait_time} seconds before retry..."
                )

                time.sleep(wait_time)

    return {
        "Yahoo Ticker": yahoo_ticker,
        "Yahoo Sector": "",
        "Yahoo Industry": "",
        "Yahoo Price": "",
        "Yahoo Market Cap": "",
        "Yahoo Currency": "",
        "Resolution Source": "",
        "Resolution Confidence": NOT_RESOLVED,
        "Diagnosis": "YAHOO_LOOKUP_FAILED",
        "Lookup Error": last_error,
    }


# ============================================================
# RESOLUTION VALIDATION
# ============================================================

def validate_resolution(row):
    """
    Additional validation layer.

    We deliberately do NOT guess sector from the company name.

    A successful classification requires a non-empty sector from
    the external classification source.
    """

    sector = normalize_text(row.get("Yahoo Sector"))
    industry = normalize_text(row.get("Yahoo Industry"))

    if sector and industry:
        return (
            sector,
            industry,
            HIGH_CONFIDENCE,
            "SECTOR_INDUSTRY_RESOLVED"
        )

    if sector:
        return (
            sector,
            industry,
            MEDIUM_CONFIDENCE,
            "SECTOR_RESOLVED_INDUSTRY_MISSING"
        )

    return (
        "",
        "",
        NOT_RESOLVED,
        "SECTOR_NOT_RESOLVED"
    )


# ============================================================
# CREATE DIAGNOSTIC DATA
# ============================================================

def create_diagnostic_rows(records):

    run_date = datetime.now().strftime("%Y-%m-%d")

    diagnostic_rows = []

    total = len(records)

    for index, record in enumerate(records, start=1):

        ticker = record["Ticker"]
        nse_symbol = record["NSE Symbol"]
        company_name = record["Company Name"]

        print(
            f"\n[{index}/{total}] "
            f"{nse_symbol} - {company_name}"
        )

        yahoo_data = get_yahoo_metadata(
            nse_symbol
        )

        resolved_sector, resolved_industry, \
            confidence, diagnosis = validate_resolution(
                yahoo_data
            )

        row = {
            "Run Date": run_date,
            "Ticker": ticker,
            "NSE Symbol": nse_symbol,
            "Company Name": company_name,

            "Existing Sector": record["Existing Sector"],
            "Existing Industry": record["Existing Industry"],

            "GF Identifier": f"NSE:{nse_symbol}",
            "Yahoo Ticker": yahoo_data.get(
                "Yahoo Ticker",
                ""
            ),

            "GF Identifier Status": "CONFIRMED",

            "GF Price": "",
            "GF Market Cap": "",

            "Yahoo Price": yahoo_data.get(
                "Yahoo Price",
                ""
            ),

            "Yahoo Market Cap": yahoo_data.get(
                "Yahoo Market Cap",
                ""
            ),

            "Currency": yahoo_data.get(
                "Yahoo Currency",
                ""
            ),

            "Yahoo Sector": yahoo_data.get(
                "Yahoo Sector",
                ""
            ),
            
            "Yahoo Industry": yahoo_data.get(
                "Yahoo Industry",
                ""
            ),
            
            "Resolved Sector": resolved_sector,
            
            "Resolved Industry": resolved_industry,
            
            "Resolution Source": yahoo_data.get(
                "Resolution Source",
                ""
            ),

            "Resolution Confidence": confidence,

            "Diagnosis": diagnosis,

            "Lookup Error": yahoo_data.get(
                "Lookup Error",
                ""
            ),
        }

        diagnostic_rows.append(row)

        time.sleep(REQUEST_DELAY_SECONDS)

    return diagnostic_rows


# ============================================================
# GOOGLE FINANCE SUPPORT FORMULAS
# ============================================================

def add_google_finance_formulas(rows):
    """
    Add Google Finance validation formulas.

    Google Finance is used only for market-data validation.
    Sector and Industry are NOT assumed to be available
    through GOOGLEFINANCE().
    """

    for row in rows:

        identifier = row["GF Identifier"]

        # ----------------------------------------------------
        # Google Finance price
        # ----------------------------------------------------

        row["GF Price Formula"] = (
            f'=IFERROR('
            f'GOOGLEFINANCE("{identifier}","price"),'
            f'""'
            f')'
        )

        # ----------------------------------------------------
        # Google Finance market capitalization
        # ----------------------------------------------------

        row["GF Market Cap Formula"] = (
            f'=IFERROR('
            f'GOOGLEFINANCE("{identifier}","marketcap"),'
            f'""'
            f')'
        )

        # ----------------------------------------------------
        # Google Finance identifier validation
        # ----------------------------------------------------

        row["GF Identifier Formula"] = (
            f'=IFERROR('
            f'GOOGLEFINANCE("{identifier}","price"),'
            f'""'
            f')'
        )

    return rows


# ============================================================
# GOOGLE SHEET WRITE
# ============================================================

def write_diagnostic_sheet(spreadsheet, rows):

    headers = [
        "Run Date",
        "Ticker",
        "NSE Symbol",
        "Company Name",
    
        "Existing Sector",
        "Existing Industry",
    
        "GF Identifier",
        "Yahoo Ticker",
        "GF Identifier Status",
    
        "GF Price",
        "GF Market Cap",
    
        "Yahoo Price",
        "Yahoo Market Cap",
        "Currency",
    
        "Yahoo Sector",
        "Yahoo Industry",
    
        "Resolved Sector",
        "Resolved Industry",
    
        "Resolution Source",
        "Resolution Confidence",
    
        "Diagnosis",
        "Lookup Error",
    
        "GF Identifier Formula",
        "GF Price Formula",
        "GF Market Cap Formula",
    ]

    try:
        worksheet = spreadsheet.worksheet(
            DIAGNOSTIC_SHEET
        )

        print(
            f"Using existing worksheet: "
            f"{DIAGNOSTIC_SHEET}"
        )

    except gspread.WorksheetNotFound:

        print(
            f"Creating worksheet: "
            f"{DIAGNOSTIC_SHEET}"
        )

        worksheet = spreadsheet.add_worksheet(
            title=DIAGNOSTIC_SHEET,
            rows=max(len(rows) + 2, 100),
            cols=len(headers)
        )

    print("Clearing diagnostic worksheet...")

    worksheet.clear()

    data = [headers]

    for row in rows:

        data.append([
            row.get(header, "")
            for header in headers
        ])

    print(
        f"Writing sector/industry diagnostic rows: "
        f"{len(rows)}"
    )

    # One batch write.
    worksheet.update(
        range_name=f"A1:X{len(data)}",
        values=data,
        value_input_option="USER_ENTERED"
    )

    print(
        f"Diagnostic rows written: {len(rows)}"
    )

    return worksheet


# ============================================================
# DIAGNOSTIC SUMMARY
# ============================================================

def print_summary(rows):

    total = len(rows)

    high = sum(
        1
        for row in rows
        if row["Resolution Confidence"] == HIGH_CONFIDENCE
    )

    medium = sum(
        1
        for row in rows
        if row["Resolution Confidence"] == MEDIUM_CONFIDENCE
    )

    low = sum(
        1
        for row in rows
        if row["Resolution Confidence"] == LOW_CONFIDENCE
    )

    unresolved = sum(
        1
        for row in rows
        if row["Resolution Confidence"] == NOT_RESOLVED
    )

    yahoo_failed = sum(
        1
        for row in rows
        if row["Diagnosis"] == "YAHOO_LOOKUP_FAILED"
    )

    print("\n")
    print("=" * 50)
    print("SECTOR & INDUSTRY RESOLUTION DIAGNOSTIC")
    print("=" * 50)

    print(
        f"Unknown-Sector Equities : {total}"
    )

    print(
        f"Sector + Industry Found : {high}"
    )

    print(
        f"Sector Found Only       : {medium}"
    )

    print(
        f"Low Confidence          : {low}"
    )

    print(
        f"Not Resolved            : {unresolved}"
    )

    print(
        f"Yahoo Lookup Failed     : {yahoo_failed}"
    )

    print("-" * 50)

    if total:
        print(
            f"Resolution Rate         : "
            f"{((high + medium) / total) * 100:.1f}%"
        )

    print("-" * 50)

    print(
        f"Diagnostic Sheet: "
        f"{DIAGNOSTIC_SHEET}"
    )

    print("=" * 50)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Run "
        "google_finance_sector_industry_diagnostic.py"
    )

    spreadsheet = connect_to_google_sheet()

    records = read_stock_master(
        spreadsheet
    )

    if not records:

        print(
            "No UNKNOWN-sector equities found."
        )

        return

    diagnostic_rows = create_diagnostic_rows(
        records
    )

    diagnostic_rows = add_google_finance_formulas(
        diagnostic_rows
    )

    write_diagnostic_sheet(
        spreadsheet,
        diagnostic_rows
    )

    print_summary(
        diagnostic_rows
    )


if __name__ == "__main__":
    main()
