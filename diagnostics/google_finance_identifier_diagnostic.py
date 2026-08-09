"""
Google Finance Identifier Diagnostic
------------------------------------

Purpose:
    Diagnose Google Finance identifiers for equity rows that are currently
    unresolved / UNKNOWN in Stock_Master.

Architecture:
    NSE Master / security identity
            ↓
    Multi-source enrichment / diagnostics
            ↓
    Reconciliation / Stock_Master

Google Finance is used here ONLY as a diagnostic / secondary fallback.
This script does NOT modify Stock_Master.

Output worksheet:
    GF_Identifier_Diagnostic

Google Finance identifiers tested:
    NSE -> NSE:<NSE_SYMBOL>
    BSE -> BOM:<BSE_SCRIP_CODE>

Important:
    Do NOT use BSE:<NSE_SYMBOL>.
"""

import os
import re
import time
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials


# ============================================================
# CONFIGURATION
# ============================================================

SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    "credentials/service_account.json"
)

SPREADSHEET_NAME = os.getenv(
    "GOOGLE_SPREADSHEET_NAME",
    "Stock_Master"
)

SOURCE_WORKSHEET = os.getenv(
    "STOCK_MASTER_WORKSHEET",
    "Stock_Master"
)

OUTPUT_WORKSHEET = "GF_Identifier_Diagnostic"

# Number of seconds to wait after writing formulas.
# Google Sheets needs time to calculate GOOGLEFINANCE.
FORMULA_WAIT_SECONDS = 10

# Maximum rows to process.
# None = all unresolved equity rows.
MAX_ROWS = None


# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def connect_to_google_sheet():
    print("Connecting to Google Sheet...")

    credentials = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )

    client = gspread.authorize(credentials)
    spreadsheet = client.open(SPREADSHEET_NAME)

    print("Connected")

    return spreadsheet


# ============================================================
# NORMALIZATION HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def normalize_symbol(value):
    """
    Normalize NSE symbol.

    Examples:
        RELIANCE -> RELIANCE
        RELIANCE.NS -> RELIANCE
        NSE:RELIANCE -> RELIANCE
    """

    value = clean_text(value).upper()

    value = value.replace("NSE:", "")

    if value.endswith(".NS"):
        value = value[:-3]

    return value.strip()


def normalize_bse_code(value):
    """
    Normalize BSE scrip code.

    Examples:
        500325 -> 500325
        BOM:500325 -> 500325
        '500325 -> 500325
    """

    value = clean_text(value).upper()

    value = value.replace("BOM:", "")
    value = value.replace("BSE:", "")

    # Remove Excel/Sheets leading apostrophe
    value = value.lstrip("'")

    # Keep numeric BSE scrip code
    match = re.search(r"\d+", value)

    if not match:
        return ""

    return match.group(0)


def is_equity_row(row):
    """
    Determine whether the row represents an equity.

    Asset Type is preferred.

    If Asset Type is unavailable, the row is treated as an equity
    when it is not explicitly identified as an ETF / REIT / InvIT.
    """

    asset_type = clean_text(
        row.get("Asset Type", "")
    ).upper()

    if asset_type:
        return asset_type in {
            "EQUITY",
            "STOCK",
            "SHARE",
        }

    # Fallback
    instrument = clean_text(
        row.get("Instrument Type", "")
    ).upper()

    if instrument in {
        "ETF",
        "REIT",
        "INVIT",
    }:
        return False

    return True


def is_unresolved(row):
    """
    Identify rows that need Google Finance identifier diagnostics.

    Primary condition:
        Sector / Industry is UNKNOWN

    We also allow common unresolved markers.
    """

    sector = clean_text(row.get("Sector", "")).upper()
    industry = clean_text(row.get("Industry", "")).upper()

    unresolved_values = {
        "",
        "UNKNOWN",
        "N/A",
        "NA",
        "NULL",
        "NONE",
        "-",
    }

    sector_unresolved = sector in unresolved_values
    industry_unresolved = industry in unresolved_values

    return sector_unresolved or industry_unresolved


# ============================================================
# GOOGLE FINANCE FORMULA BUILDERS
# ============================================================

def google_finance_formula(identifier):
    """
    Build a simple GOOGLEFINANCE formula.

    We use PRICE because it is a reliable existence test.

    If Google Finance recognizes the identifier, PRICE should return
    a numeric value.

    If the identifier is not recognized, the formula generally
    returns an error.
    """

    identifier = clean_text(identifier)

    if not identifier:
        return '=""'

    return (
        f'=IFERROR(GOOGLEFINANCE("{identifier}","price"),"GF_NOT_FOUND")'
    )


# ============================================================
# HEADER DETECTION
# ============================================================

def create_header_map(headers):
    return {
        clean_text(header): index
        for index, header in enumerate(headers)
    }


def get_value(row, header_map, header_name):
    index = header_map.get(header_name)

    if index is None:
        return ""

    if index >= len(row):
        return ""

    return clean_text(row[index])


# ============================================================
# LOAD STOCK MASTER
# ============================================================

def load_stock_master(spreadsheet):
    worksheet = spreadsheet.worksheet(SOURCE_WORKSHEET)

    values = worksheet.get_all_values()

    if not values:
        raise RuntimeError(
            f"No data found in worksheet '{SOURCE_WORKSHEET}'."
        )

    headers = values[0]

    rows = []

    for raw_row in values[1:]:
        # Make row same length as headers
        row = raw_row + [""] * (len(headers) - len(raw_row))

        row_dict = {
            headers[i]: clean_text(row[i])
            for i in range(len(headers))
        }

        rows.append(row_dict)

    print(f"Stock Master Rows: {len(rows)}")

    return worksheet, headers, rows


# ============================================================
# IDENTIFY UNRESOLVED EQUITIES
# ============================================================

def get_unresolved_equities(rows):
    unresolved = []

    for row_number, row in enumerate(rows, start=2):

        if not is_equity_row(row):
            continue

        if not is_unresolved(row):
            continue

        nse_symbol = normalize_symbol(
            row.get("NSE Symbol", "")
            or row.get("Symbol", "")
            or row.get("Ticker", "")
        )

        bse_code = normalize_bse_code(
            row.get("BSE Code", "")
            or row.get("BSE Scrip Code", "")
            or row.get("BSE Scrip", "")
        )

        # Skip rows where neither exchange identifier exists.
        if not nse_symbol and not bse_code:
            unresolved.append({
                "source_row": row_number,
                "row": row,
                "nse_symbol": "",
                "bse_code": "",
            })
            continue

        unresolved.append({
            "source_row": row_number,
            "row": row,
            "nse_symbol": nse_symbol,
            "bse_code": bse_code,
        })

    if MAX_ROWS:
        unresolved = unresolved[:MAX_ROWS]

    print(
        f"Unknown-Sector Equity Rows: {len(unresolved)}"
    )

    return unresolved


# ============================================================
# CREATE DIAGNOSTIC WORKSHEET
# ============================================================

def get_or_create_output_worksheet(spreadsheet):
    try:
        worksheet = spreadsheet.worksheet(OUTPUT_WORKSHEET)

        print(
            f"Using existing worksheet: {OUTPUT_WORKSHEET}"
        )

    except gspread.WorksheetNotFound:
        print(
            f"Creating worksheet: {OUTPUT_WORKSHEET}"
        )

        worksheet = spreadsheet.add_worksheet(
            title=OUTPUT_WORKSHEET,
            rows=1000,
            cols=30,
        )

    return worksheet


def clear_output_worksheet(worksheet):
    print("Clearing diagnostic worksheet...")

    worksheet.clear()


# ============================================================
# BUILD DIAGNOSTIC DATA
# ============================================================

OUTPUT_HEADERS = [
    "Source Row",
    "Company Name",
    "NSE Symbol",
    "BSE Code",

    "NSE Identifier",
    "BSE Identifier",

    "NSE Formula",
    "BSE Formula",

    "GF NSE Result",
    "GF BSE Result",

    "NSE Found",
    "BSE Found",

    "GF Identifier Status",
    "Diagnostic Time",
]


def build_diagnostic_rows(unresolved):
    rows = []

    for item in unresolved:

        row = item["row"]

        company_name = (
            row.get("Company Name", "")
            or row.get("Company", "")
            or row.get("Name", "")
        )

        nse_symbol = item["nse_symbol"]
        bse_code = item["bse_code"]

        nse_identifier = (
            f"NSE:{nse_symbol}"
            if nse_symbol
            else ""
        )

        bse_identifier = (
            f"BOM:{bse_code}"
            if bse_code
            else ""
        )

        nse_formula = google_finance_formula(
            nse_identifier
        )

        bse_formula = google_finance_formula(
            bse_identifier
        )

        rows.append([
            item["source_row"],
            company_name,
            nse_symbol,
            bse_code,

            nse_identifier,
            bse_identifier,

            nse_formula,
            bse_formula,

            "",  # GF NSE Result
            "",  # GF BSE Result

            "",  # NSE Found
            "",  # BSE Found

            "",  # Status
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        ])

    return rows


# ============================================================
# WRITE FORMULAS
# ============================================================

def write_diagnostic_formulas(
    worksheet,
    diagnostic_rows,
):
    """
    Write diagnostic rows.

    Columns:
        G = NSE Formula
        H = BSE Formula

    Google Sheets calculates the formulas after they are written.
    """

    if not diagnostic_rows:
        return

    values = [
        OUTPUT_HEADERS
    ] + diagnostic_rows

    worksheet.update(
        range_name="A1:N{}".format(len(values)),
        values=values,
        value_input_option="USER_ENTERED",
    )

    print(
        f"Google Finance formulas written: "
        f"{len(diagnostic_rows)}"
    )


# ============================================================
# READ GOOGLE FINANCE RESULTS
# ============================================================

def is_google_finance_found(value):
    """
    Interpret the calculated GOOGLEFINANCE result.

    A valid numeric price means the identifier was resolved.

    We deliberately do not depend on a particular stock price
    because the diagnostic is only checking identifier resolution.
    """

    value = clean_text(value).upper()

    if not value:
        return False

    if value in {
        "GF_NOT_FOUND",
        "#N/A",
        "#VALUE!",
        "#REF!",
        "#ERROR!",
        "#NAME?",
        "N/A",
    }:
        return False

    # Google Sheets may return a numeric value.
    try:
        float(
            value.replace(",", "")
        )
        return True

    except ValueError:
        return False


def read_and_diagnose_results(worksheet):
    """
    Read calculated worksheet values and determine whether
    NSE/BSE identifiers were found.
    """

    values = worksheet.get_all_values()

    if len(values) <= 1:
        return []

    print(
        f"Diagnostic rows read: {len(values) - 1}"
    )

    results = []

    for row in values[1:]:

        row = row + [""] * (
            len(OUTPUT_HEADERS) - len(row)
        )

        nse_result = row[8]
        bse_result = row[9]

        nse_found = is_google_finance_found(
            nse_result
        )

        bse_found = is_google_finance_found(
            bse_result
        )

        if nse_found and bse_found:
            status = "GF_BOTH_FOUND"

        elif nse_found:
            status = "GF_NSE_FOUND"

        elif bse_found:
            status = "GF_BSE_FOUND"

        else:
            status = "GF_NEITHER_FOUND"

        results.append({
            "row": row,
            "nse_found": nse_found,
            "bse_found": bse_found,
            "status": status,
        })

    return results


# ============================================================
# WRITE FINAL DIAGNOSIS
# ============================================================

def write_final_diagnosis(
    worksheet,
    results,
):
    """
    Write NSE Found / BSE Found / Status columns.

    Columns:
        K = NSE Found
        L = BSE Found
        M = GF Identifier Status
    """

    if not results:
        return

    updates = []

    for index, result in enumerate(results, start=2):

        updates.append([
            result["nse_found"],
            result["bse_found"],
            result["status"],
        ])

    worksheet.update(
        range_name=f"K2:M{len(results) + 1}",
        values=updates,
        value_input_option="USER_ENTERED",
    )

    print(
        f"Diagnosis written in one batch: "
        f"{len(results)} rows"
    )


# ============================================================
# SUMMARY
# ============================================================

def print_summary(results):

    unresolved = len(results)

    nse_found = sum(
        1 for r in results
        if r["nse_found"]
    )

    bse_found = sum(
        1 for r in results
        if r["bse_found"]
    )

    both_found = sum(
        1 for r in results
        if r["nse_found"] and r["bse_found"]
    )

    neither_found = sum(
        1 for r in results
        if not r["nse_found"]
        and not r["bse_found"]
    )

    print()
    print("================================")
    print("GOOGLE FINANCE IDENTIFIER DIAGNOSTIC")
    print("================================")
    print(f"Unresolved Equities : {unresolved}")
    print(f"GF NSE Found        : {nse_found}")
    print(f"GF BSE Found        : {bse_found}")
    print(f"GF Both NSE/BSE     : {both_found}")
    print(f"GF Neither Found    : {neither_found}")
    print("================================")
    print(
        f"Diagnostic Sheet: {OUTPUT_WORKSHEET}"
    )
    print("================================")


# ============================================================
# MAIN
# ============================================================

def main():

    spreadsheet = connect_to_google_sheet()

    # --------------------------------------------------------
    # Load Stock_Master
    # --------------------------------------------------------

    (
        source_worksheet,
        headers,
        stock_master_rows,
    ) = load_stock_master(spreadsheet)

    # --------------------------------------------------------
    # Find unresolved equity rows
    # --------------------------------------------------------

    unresolved = get_unresolved_equities(
        stock_master_rows
    )

    # --------------------------------------------------------
    # Prepare diagnostic worksheet
    # --------------------------------------------------------

    diagnostic_worksheet = (
        get_or_create_output_worksheet(
            spreadsheet
        )
    )

    clear_output_worksheet(
        diagnostic_worksheet
    )

    # --------------------------------------------------------
    # Build diagnostic rows
    # --------------------------------------------------------

    diagnostic_rows = build_diagnostic_rows(
        unresolved
    )

    # --------------------------------------------------------
    # Write Google Finance formulas
    # --------------------------------------------------------

    write_diagnostic_formulas(
        diagnostic_worksheet,
        diagnostic_rows,
    )

    # --------------------------------------------------------
    # Wait for Google Finance
    # --------------------------------------------------------

    print(
        "Waiting for Google Finance formulas "
        "to calculate..."
    )

    time.sleep(
        FORMULA_WAIT_SECONDS
    )

    # --------------------------------------------------------
    # Read calculated results
    # --------------------------------------------------------

    results = read_and_diagnose_results(
        diagnostic_worksheet
    )

    # --------------------------------------------------------
    # Write diagnosis
    # --------------------------------------------------------

    write_final_diagnosis(
        diagnostic_worksheet,
        results,
    )

    # --------------------------------------------------------
    # Print summary
    # --------------------------------------------------------

    print_summary(results)


if __name__ == "__main__":
    main()
