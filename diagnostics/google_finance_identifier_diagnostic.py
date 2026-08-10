import os
import json
import time
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ============================================================
# CONFIGURATION
# ============================================================

SPREADSHEET_ID = "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"

SOURCE_SHEET = "Stock_Master"
DIAGNOSTIC_SHEET = "GF_Identifier_Diagnostic"

EXPECTED_UNKNOWN_EQUITIES = 70

WAIT_SECONDS = 25


# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

print("Connecting to Google Sheet...")

creds_dict = json.loads(
    os.environ["GOOGLE_CREDENTIALS"]
)

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_dict,
    scope
)

client = gspread.authorize(creds)

spreadsheet = client.open_by_key(
    SPREADSHEET_ID
)

print("Connected")


# ============================================================
# LOAD STOCK MASTER
# ============================================================

stock_master_ws = spreadsheet.worksheet(
    SOURCE_SHEET
)

stock_master = stock_master_ws.get_all_records()

print(
    f"Stock Master Rows: {len(stock_master)}"
)


# ============================================================
# HELPERS
# ============================================================

def is_unknown(value):
    """
    Returns True when a field represents an unknown value.
    """

    value = str(value).strip().upper()

    return value in (
        "",
        "UNKNOWN",
        "N/A",
        "NA",
        "NONE",
        "NULL"
    )


def clean_nse_symbol(ticker):
    """
    Convert:
        ABC.NS -> ABC
        ABC -> ABC

    Preserve legitimate symbols containing hyphens.
    """

    ticker = str(ticker).strip()

    if ticker.upper().endswith(".NS"):
        ticker = ticker[:-3]

    return ticker.strip()


def clean_bse_code(value):
    """
    Return a numeric BSE code when available.

    Examples:
        500325 -> 500325
        "500325" -> 500325
        "" -> ""

    Non-numeric values are rejected.
    """

    if value is None:
        return ""

    value = str(value).strip()

    if not value:
        return ""

    # Remove accidental decimal representation such as 500325.0
    if value.endswith(".0"):
        value = value[:-2]

    if value.isdigit():
        return value

    return ""


def formula_value(value):
    """
    Convert a Google Sheets calculated value into a usable
    numeric indicator.

    GOOGLEFINANCE can return numbers formatted with commas,
    currency symbols, etc.
    """

    if value is None:
        return 0

    value = str(value).strip()

    if not value:
        return 0

    cleaned = (
        value
        .replace(",", "")
        .replace("₹", "")
        .replace("$", "")
        .replace("€", "")
        .replace("£", "")
        .strip()
    )

    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0


# ============================================================
# IDENTIFY UNKNOWN-SECTOR EQUITIES
# ============================================================

unresolved = []

for row in stock_master:

    ticker = str(
        row.get("Ticker", "")
    ).strip()

    if not ticker:
        continue

    asset_type = str(
        row.get("Asset Type", "EQUITY")
    ).strip().upper()

    sector = row.get(
        "Sector",
        "UNKNOWN"
    )

    # Only ordinary equities with unknown sector
    if asset_type != "EQUITY":
        continue

    if not is_unknown(sector):
        continue

    unresolved.append(row)


print(
    f"Unknown-Sector Equity Rows: {len(unresolved)}"
)

if len(unresolved) != EXPECTED_UNKNOWN_EQUITIES:

    print(
        "WARNING: Expected "
        f"{EXPECTED_UNKNOWN_EQUITIES} "
        "unknown-sector equities but found "
        f"{len(unresolved)}"
    )


# ============================================================
# CREATE / RESET DIAGNOSTIC SHEET
# ============================================================

try:

    gf_ws = spreadsheet.worksheet(
        DIAGNOSTIC_SHEET
    )

    print(
        f"Using existing worksheet: {DIAGNOSTIC_SHEET}"
    )

except gspread.WorksheetNotFound:

    print(
        f"Creating worksheet: {DIAGNOSTIC_SHEET}"
    )

    gf_ws = spreadsheet.add_worksheet(
        title=DIAGNOSTIC_SHEET,
        rows=200,
        cols=35
    )


print("Clearing diagnostic worksheet...")

gf_ws.clear()


# ============================================================
# HEADERS
# ============================================================

headers = [
    "Run Date",
    "Ticker",
    "NSE Symbol",
    "Company Name",
    "Sector",
    "Industry",
    "BSE Code",

    # NSE candidate
    "NSE Candidate",
    "NSE Candidate Type",
    "NSE Price",
    "NSE Market Cap",
    "NSE Shares",
    "NSE Currency",
    "NSE Trade Time",

    # BSE candidate
    "BSE Candidate",
    "BSE Candidate Type",
    "BSE Price",
    "BSE Market Cap",
    "BSE Shares",
    "BSE Currency",
    "BSE Trade Time",

    # Resolution
    "Resolved Identifier",
    "Resolved Identifier Type",
    "Diagnosis"
]


gf_ws.update(
    range_name="A1:X1",
    values=[headers],
    value_input_option="USER_ENTERED"
)


# ============================================================
# BUILD DIAGNOSTIC ROWS
# ============================================================

today = datetime.now().strftime(
    "%Y-%m-%d"
)

diagnostic_rows = []

for row in unresolved:

    ticker = str(
        row.get("Ticker", "")
    ).strip()

    nse_symbol = clean_nse_symbol(
        ticker
    )

    company_name = str(
        row.get("Company Name", "")
    ).strip()

    # Fallback because some existing Stock_Master versions
    # may use "Name" instead of "Company Name".
    if not company_name:

        company_name = str(
            row.get("Name", "")
        ).strip()

    sector = row.get(
        "Sector",
        "UNKNOWN"
    )

    industry = row.get(
        "Industry",
        "UNKNOWN"
    )

    bse_code = clean_bse_code(
        row.get("BSE Code", "")
    )

    nse_candidate = ""

    if nse_symbol:
        nse_candidate = (
            f"NSE:{nse_symbol}"
        )

    bse_candidate = ""

    if bse_code:
        bse_candidate = (
            f"BOM:{bse_code}"
        )

    # --------------------------------------------------------
    # GOOGLEFINANCE FORMULAS
    #
    # IMPORTANT:
    # These are deliberately written as formulas.
    # The worksheet update below uses USER_ENTERED so
    # Google Sheets evaluates them.
    # --------------------------------------------------------

    if nse_candidate:

        nse_price_formula = (
            f'=IFERROR(GOOGLEFINANCE('
            f'"{nse_candidate}","price"),"")'
        )

        nse_market_cap_formula = (
            f'=IFERROR(GOOGLEFINANCE('
            f'"{nse_candidate}","marketcap"),"")'
        )

        nse_shares_formula = (
            f'=IFERROR(GOOGLEFINANCE('
            f'"{nse_candidate}","shares"),"")'
        )

        nse_currency_formula = (
            f'=IFERROR(GOOGLEFINANCE('
            f'"{nse_candidate}","currency"),"")'
        )

        nse_trade_time_formula = (
            f'=IFERROR(GOOGLEFINANCE('
            f'"{nse_candidate}","tradetime"),"")'
        )

    else:

        nse_price_formula = ""
        nse_market_cap_formula = ""
        nse_shares_formula = ""
        nse_currency_formula = ""
        nse_trade_time_formula = ""

    if bse_candidate:

        bse_price_formula = (
            f'=IFERROR(GOOGLEFINANCE('
            f'"{bse_candidate}","price"),"")'
        )

        bse_market_cap_formula = (
            f'=IFERROR(GOOGLEFINANCE('
            f'"{bse_candidate}","marketcap"),"")'
        )

        bse_shares_formula = (
            f'=IFERROR(GOOGLEFINANCE('
            f'"{bse_candidate}","shares"),"")'
        )

        bse_currency_formula = (
            f'=IFERROR(GOOGLEFINANCE('
            f'"{bse_candidate}","currency"),"")'
        )

        bse_trade_time_formula = (
            f'=IFERROR(GOOGLEFINANCE('
            f'"{bse_candidate}","tradetime"),"")'
        )

    else:

        bse_price_formula = ""
        bse_market_cap_formula = ""
        bse_shares_formula = ""
        bse_currency_formula = ""
        bse_trade_time_formula = ""

    diagnostic_rows.append([
        today,
        ticker,
        nse_symbol,
        company_name,
        sector,
        industry,
        bse_code,

        nse_candidate,
        "NSE_SYMBOL" if nse_candidate else "",
        nse_price_formula,
        nse_market_cap_formula,
        nse_shares_formula,
        nse_currency_formula,
        nse_trade_time_formula,

        bse_candidate,
        "BSE_BOM_CODE" if bse_candidate else "",
        bse_price_formula,
        bse_market_cap_formula,
        bse_shares_formula,
        bse_currency_formula,
        bse_trade_time_formula,

        "",
        "",
        ""
    ])


# ============================================================
# WRITE FORMULAS AS ACTUAL GOOGLE SHEETS FORMULAS
# ============================================================

if diagnostic_rows:

    end_row = len(diagnostic_rows) + 1

    gf_ws.update(
        range_name=f"A2:X{end_row}",
        values=diagnostic_rows,
        value_input_option="USER_ENTERED"
    )


print(
    "Google Finance identifier formulas written: "
    f"{len(diagnostic_rows)}"
)


# ============================================================
# WAIT FOR GOOGLE FINANCE
# ============================================================

print(
    "Waiting for Google Finance formulas to calculate "
    f"({WAIT_SECONDS} seconds)..."
)

time.sleep(WAIT_SECONDS)


# ============================================================
# READ CALCULATED VALUES
# ============================================================

values = gf_ws.get_all_values()

print(
    f"Diagnostic rows read: {max(0, len(values) - 1)}"
)


# ============================================================
# CLASSIFY GOOGLE FINANCE RESULTS
# ============================================================

diagnosis_updates = []

gf_nse_found = 0
gf_bse_found = 0
gf_both_found = 0
gf_neither_found = 0


for index, row in enumerate(
    values[1:],
    start=2
):

    if len(row) < 24:
        continue

    # --------------------------------------------------------
    # Column positions
    #
    # A  Run Date
    # B  Ticker
    # C  NSE Symbol
    # D  Company Name
    # E  Sector
    # F  Industry
    # G  BSE Code
    #
    # H  NSE Candidate
    # I  NSE Candidate Type
    # J  NSE Price
    # K  NSE Market Cap
    # L  NSE Shares
    # M  NSE Currency
    # N  NSE Trade Time
    #
    # O  BSE Candidate
    # P  BSE Candidate Type
    # Q  BSE Price
    # R  BSE Market Cap
    # S  BSE Shares
    # T  BSE Currency
    # U  BSE Trade Time
    #
    # V  Resolved Identifier
    # W  Resolved Identifier Type
    # X  Diagnosis
    # --------------------------------------------------------

    nse_candidate = row[7]
    bse_candidate = row[14]

    nse_price = formula_value(row[9])
    nse_market_cap = formula_value(row[10])

    bse_price = formula_value(row[16])
    bse_market_cap = formula_value(row[17])

    nse_found = (
        nse_price > 0
        or nse_market_cap > 0
    )

    bse_found = (
        bse_price > 0
        or bse_market_cap > 0
    )

    # --------------------------------------------------------
    # RESOLUTION
    # --------------------------------------------------------

    if nse_found and bse_found:

        diagnosis = "GF_BOTH_NSE_BSE"

        resolved_identifier = nse_candidate
        resolved_identifier_type = (
            "NSE_SYMBOL_PRIMARY"
        )

        gf_both_found += 1

    elif nse_found:

        diagnosis = "GF_NSE_FOUND"

        resolved_identifier = nse_candidate
        resolved_identifier_type = (
            "NSE_SYMBOL"
        )

        gf_nse_found += 1

    elif bse_found:

        diagnosis = "GF_BSE_FOUND"

        resolved_identifier = bse_candidate
        resolved_identifier_type = (
            "BSE_BOM_CODE"
        )

        gf_bse_found += 1

    else:

        diagnosis = "GF_NEITHER_FOUND"

        resolved_identifier = ""
        resolved_identifier_type = ""

        gf_neither_found += 1

    diagnosis_updates.append([
        resolved_identifier,
        resolved_identifier_type,
        diagnosis
    ])


# ============================================================
# WRITE RESOLUTION
# ============================================================

if diagnosis_updates:

    start_row = 2

    end_row = (
        start_row
        + len(diagnosis_updates)
        - 1
    )

    gf_ws.update(
        range_name=f"V{start_row}:X{end_row}",
        values=diagnosis_updates,
        value_input_option="USER_ENTERED"
    )

    print(
        "Identifier diagnosis written in one batch: "
        f"{len(diagnosis_updates)} rows"
    )


# ============================================================
# SUMMARY
# ============================================================

print("")
print("==========================================")
print("GOOGLE FINANCE IDENTIFIER DIAGNOSTIC")
print("==========================================")

print(
    f"Unknown-Sector Equities : {len(unresolved)}"
)

print(
    f"GF NSE Found            : {gf_nse_found}"
)

print(
    f"GF BSE Found            : {gf_bse_found}"
)

print(
    f"GF Both NSE/BSE         : {gf_both_found}"
)

print(
    f"GF Neither Found        : {gf_neither_found}"
)

print("------------------------------------------")

print(
    f"Diagnostic Sheet: {DIAGNOSTIC_SHEET}"
)

print("==========================================")
