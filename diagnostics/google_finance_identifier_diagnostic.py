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

WAIT_SECONDS = 20


# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

def connect_to_google_sheet():

    print("Connecting to Google Sheet...")

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    credentials_json = os.environ["GOOGLE_CREDENTIALS"]

    creds_dict = json.loads(
        credentials_json
    )

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict,
        scope
    )

    client = gspread.authorize(
        creds
    )

    spreadsheet = client.open_by_key(
        SPREADSHEET_ID
    )

    print("Connected")

    return spreadsheet


# ============================================================
# HELPERS
# ============================================================

def clean(value):

    if value is None:
        return ""

    return str(value).strip()


def normalize_symbol(value):

    value = clean(value).upper()

    if not value:
        return ""

    # Remove common Yahoo suffixes
    value = value.replace(".NS", "")
    value = value.replace(".BO", "")

    # Remove spaces
    value = value.strip()

    return value


def is_unknown(value):

    value = clean(value).upper()

    return value in (
        "",
        "UNKNOWN",
        "N/A",
        "NA",
        "NONE",
        "NULL"
    )


def first_available(row, column_names):

    for column in column_names:

        value = clean(
            row.get(column, "")
        )

        if value:
            return value

    return ""


def escape_formula_text(value):

    return clean(value).replace(
        '"',
        '""'
    )


# ============================================================
# IDENTIFIER CANDIDATES
# ============================================================

def build_identifier_candidates(row):

    ticker = normalize_symbol(
        row.get("Ticker", "")
    )

    candidates = []

    def add(
        identifier,
        identifier_type
    ):

        identifier = clean(identifier)

        if not identifier:
            return

        # Avoid duplicate identifiers
        for existing in candidates:

            if existing["identifier"].upper() == identifier.upper():
                return

        candidates.append({
            "identifier": identifier,
            "type": identifier_type
        })

    # --------------------------------------------------------
    # 1. Existing Google Finance identifier
    # --------------------------------------------------------

    existing_gf = first_available(
        row,
        [
            "Google Finance Identifier",
            "Google Finance ID",
            "GF Identifier",
            "GF ID",
            "GoogleFinance Identifier"
        ]
    )

    if existing_gf:

        add(
            existing_gf,
            "EXISTING_GF_IDENTIFIER"
        )

    # --------------------------------------------------------
    # 2. NSE identifier
    # --------------------------------------------------------

    if ticker:

        add(
            f"NSE:{ticker}",
            "NSE_SYMBOL"
        )

    # --------------------------------------------------------
    # 3. BSE numeric code
    #
    # This is particularly important because Google Finance
    # generally expects the BSE numeric security code rather
    # than the NSE ticker for BSE-listed securities.
    # --------------------------------------------------------

    bse_code = first_available(
        row,
        [
            "BSE Code",
            "BSE_Code",
            "BSECode",
            "BSE Security Code",
            "BSE SecurityCode",
            "BSE ID",
            "BSE ID Code"
        ]
    )

    if bse_code:

        # Remove decimal representation such as 500325.0
        try:

            numeric_bse = float(
                str(bse_code).strip()
            )

            if numeric_bse.is_integer():

                bse_code = str(
                    int(numeric_bse)
                )

        except Exception:
            pass

        add(
            f"BSE:{bse_code}",
            "BSE_CODE"
        )

    # --------------------------------------------------------
    # 4. BSE using same symbol
    # --------------------------------------------------------

    if ticker:

        add(
            f"BSE:{ticker}",
            "BSE_SYMBOL"
        )

    # --------------------------------------------------------
    # 5. Raw ticker
    #
    # This tests whether Google Finance can resolve the
    # security without an explicit exchange prefix.
    # --------------------------------------------------------

    if ticker:

        add(
            ticker,
            "RAW_TICKER"
        )

    # --------------------------------------------------------
    # 6. Company name
    #
    # Only used as a fallback diagnostic.
    # --------------------------------------------------------

    company_name = first_available(
        row,
        [
            "Company Name",
            "Company",
            "Name",
            "CompanyName",
            "Security Name"
        ]
    )

    if company_name:

        add(
            company_name,
            "COMPANY_NAME"
        )

    return candidates


# ============================================================
# IDENTIFY UNKNOWN-SECTOR EQUITIES
# ============================================================

def load_unresolved_equities(
    stock_master
):

    unresolved = []

    for row in stock_master:

        ticker = clean(
            row.get("Ticker", "")
        )

        if not ticker:
            continue

        asset_type = clean(
            row.get(
                "Asset Type",
                "EQUITY"
            )
        ).upper()

        sector = row.get(
            "Sector",
            "UNKNOWN"
        )

        # Only EQUITY
        if asset_type != "EQUITY":
            continue

        # Only UNKNOWN sector
        if not is_unknown(sector):
            continue

        unresolved.append(row)

    return unresolved


# ============================================================
# CREATE / RESET DIAGNOSTIC SHEET
# ============================================================

def prepare_diagnostic_sheet(
    spreadsheet
):

    try:

        ws = spreadsheet.worksheet(
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

        ws = spreadsheet.add_worksheet(
            title=DIAGNOSTIC_SHEET,
            rows=200,
            cols=50
        )

    print(
        "Clearing diagnostic worksheet..."
    )

    ws.clear()

    return ws


# ============================================================
# WRITE HEADERS
# ============================================================

def write_headers(ws):

    headers = [
        "Run Date",
        "Ticker",
        "NSE Symbol",
        "Company Name",
        "Sector",
        "Industry",
        "BSE Code",

        "Candidate 1",
        "Candidate 1 Type",
        "Candidate 1 Result",

        "Candidate 2",
        "Candidate 2 Type",
        "Candidate 2 Result",

        "Candidate 3",
        "Candidate 3 Type",
        "Candidate 3 Result",

        "Candidate 4",
        "Candidate 4 Type",
        "Candidate 4 Result",

        "Candidate 5",
        "Candidate 5 Type",
        "Candidate 5 Result",

        "Candidate 6",
        "Candidate 6 Type",
        "Candidate 6 Result",

        "Candidate 7",
        "Candidate 7 Type",
        "Candidate 7 Result",

        "Resolved Identifier",
        "Resolved Identifier Type",
        "Diagnosis"
    ]

    ws.update(
        range_name="A1",
        values=[headers]
    )


# ============================================================
# BUILD DIAGNOSTIC ROW
# ============================================================

def build_diagnostic_row(
    row,
    run_date
):

    ticker = clean(
        row.get("Ticker", "")
    )

    nse_symbol = normalize_symbol(
        ticker
    )

    company_name = first_available(
        row,
        [
            "Company Name",
            "Company",
            "Name",
            "CompanyName",
            "Security Name"
        ]
    )

    sector = clean(
        row.get(
            "Sector",
            "UNKNOWN"
        )
    )

    industry = clean(
        row.get(
            "Industry",
            "UNKNOWN"
        )
    )

    bse_code = first_available(
        row,
        [
            "BSE Code",
            "BSE_Code",
            "BSECode",
            "BSE Security Code",
            "BSE SecurityCode",
            "BSE ID",
            "BSE ID Code"
        ]
    )

    candidates = build_identifier_candidates(
        row
    )

    # Maximum seven candidates
    candidates = candidates[:7]

    output = [
        run_date,
        ticker,
        nse_symbol,
        company_name,
        sector,
        industry,
        bse_code
    ]

    # --------------------------------------------------------
    # Each candidate consists of:
    #
    # Identifier
    # Identifier Type
    # GOOGLEFINANCE result
    # --------------------------------------------------------

    for candidate in candidates:

        identifier = candidate["identifier"]
        identifier_type = candidate["type"]

        escaped_identifier = (
            escape_formula_text(
                identifier
            )
        )

        formula = (
            f'=IFERROR('
            f'GOOGLEFINANCE('
            f'"{escaped_identifier}",'
            f'"price"'
            f'),"")'
        )

        output.extend([
            identifier,
            identifier_type,
            formula
        ])

    # Pad remaining candidate slots
    while len(output) < 28:

        output.extend([
            "",
            "",
            ""
        ])

    # Resolved Identifier
    output.extend([
        "",
        "",
        ""
    ])

    return output


# ============================================================
# NUMERIC VALUE
# ============================================================

def numeric_value(value):

    if value is None:
        return 0

    try:

        cleaned = (
            str(value)
            .replace(",", "")
            .replace("₹", "")
            .replace("$", "")
            .strip()
        )

        if cleaned == "":
            return 0

        return float(
            cleaned
        )

    except Exception:

        return 0


# ============================================================
# FIND RESOLVED IDENTIFIER
# ============================================================

def diagnose_rows(
    values
):

    diagnosis_updates = []

    resolved_count = 0
    unresolved_count = 0

    candidate_type_counts = {}

    # --------------------------------------------------------
    # Candidate result columns:
    #
    # J, M, P, S, V, Y, AB
    #
    # 1-based:
    # 10, 13, 16, 19, 22, 25, 28
    # --------------------------------------------------------

    result_columns = [
        9,   # Candidate 1 Result
        12,  # Candidate 2 Result
        15,  # Candidate 3 Result
        18,  # Candidate 4 Result
        21,  # Candidate 5 Result
        24,  # Candidate 6 Result
        27   # Candidate 7 Result
    ]

    # Type columns
    type_columns = [
        8,
        11,
        14,
        17,
        20,
        23,
        26
    ]

    # Identifier columns
    identifier_columns = [
        7,
        10,
        13,
        16,
        19,
        22,
        25
    ]

    for sheet_row_number, row in enumerate(
        values[1:],
        start=2
    ):

        if len(row) < 31:
            continue

        resolved_identifier = ""
        resolved_type = ""

        # ----------------------------------------------------
        # Find first working candidate
        # ----------------------------------------------------

        for (
            result_col,
            type_col,
            identifier_col
        ) in zip(
            result_columns,
            type_columns,
            identifier_columns
        ):

            result = numeric_value(
                row[result_col]
            )

            if result > 0:

                resolved_identifier = (
                    clean(
                        row[identifier_col]
                    )
                )

                resolved_type = (
                    clean(
                        row[type_col]
                    )
                )

                break

        if resolved_identifier:

            diagnosis = (
                "GF_IDENTIFIER_FOUND"
            )

            resolved_count += 1

            candidate_type_counts[
                resolved_type
            ] = (
                candidate_type_counts.get(
                    resolved_type,
                    0
                ) + 1
            )

        else:

            diagnosis = (
                "GF_IDENTIFIER_NOT_FOUND"
            )

            unresolved_count += 1

        diagnosis_updates.append([
            sheet_row_number,
            resolved_identifier,
            resolved_type,
            diagnosis
        ])

    return (
        diagnosis_updates,
        resolved_count,
        unresolved_count,
        candidate_type_counts
    )


# ============================================================
# WRITE DIAGNOSIS
# ============================================================

def write_diagnosis(
    ws,
    diagnosis_updates
):

    if not diagnosis_updates:
        return

    output_values = []

    for (
        row_number,
        identifier,
        identifier_type,
        diagnosis
    ) in diagnosis_updates:

        output_values.append([
            identifier,
            identifier_type,
            diagnosis
        ])

    start_row = 2

    end_row = (
        start_row
        + len(output_values)
        - 1
    )

    ws.update(
        range_name=f"AC{start_row}:AE{end_row}",
        values=output_values
    )

    print(
        "Identifier diagnosis written "
        f"in one batch: {len(output_values)} rows"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    spreadsheet = connect_to_google_sheet()

    # --------------------------------------------------------
    # LOAD STOCK MASTER
    # --------------------------------------------------------

    stock_master_ws = spreadsheet.worksheet(
        SOURCE_SHEET
    )

    stock_master = (
        stock_master_ws.get_all_records()
    )

    print(
        f"Stock Master Rows: "
        f"{len(stock_master)}"
    )

    # --------------------------------------------------------
    # IDENTIFY UNKNOWN-SECTOR EQUITIES
    # --------------------------------------------------------

    unresolved = (
        load_unresolved_equities(
            stock_master
        )
    )

    print(
        f"Unknown-Sector Equity Rows: "
        f"{len(unresolved)}"
    )

    if len(unresolved) != 70:

        print(
            "WARNING: Expected 70 "
            "unknown-sector equities "
            f"but found {len(unresolved)}"
        )

    if not unresolved:

        print(
            "No unresolved equities found."
        )

        return

    # --------------------------------------------------------
    # PREPARE DIAGNOSTIC SHEET
    # --------------------------------------------------------

    gf_ws = prepare_diagnostic_sheet(
        spreadsheet
    )

    write_headers(
        gf_ws
    )

    # --------------------------------------------------------
    # BUILD DIAGNOSTIC ROWS
    # --------------------------------------------------------

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    diagnostic_rows = []

    for row in unresolved:

        diagnostic_rows.append(
            build_diagnostic_row(
                row,
                today
            )
        )

    # --------------------------------------------------------
    # WRITE FORMULAS
    # --------------------------------------------------------

    if diagnostic_rows:

        gf_ws.update(
            range_name=(
                f"A2:AE"
                f"{len(diagnostic_rows) + 1}"
            ),
            values=diagnostic_rows
        )

    print(
        "Google Finance identifier "
        "formulas written: "
        f"{len(diagnostic_rows)}"
    )

    # --------------------------------------------------------
    # WAIT FOR GOOGLE FINANCE
    # --------------------------------------------------------

    print(
        "Waiting for Google Finance "
        f"formulas to calculate "
        f"({WAIT_SECONDS} seconds)..."
    )

    time.sleep(
        WAIT_SECONDS
    )

    # --------------------------------------------------------
    # READ RESULTS
    # --------------------------------------------------------

    values = (
        gf_ws.get_all_values()
    )

    print(
        "Diagnostic rows read: "
        f"{len(values) - 1}"
    )

    # --------------------------------------------------------
    # DIAGNOSE
    # --------------------------------------------------------

    (
        diagnosis_updates,
        resolved_count,
        unresolved_count,
        candidate_type_counts
    ) = diagnose_rows(
        values
    )

    # --------------------------------------------------------
    # WRITE RESULTS
    # --------------------------------------------------------

    write_diagnosis(
        gf_ws,
        diagnosis_updates
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    print("")
    print(
        "=========================================="
    )
    print(
        "GOOGLE FINANCE IDENTIFIER DIAGNOSTIC"
    )
    print(
        "=========================================="
    )

    print(
        f"Unknown-Sector Equities : "
        f"{len(unresolved)}"
    )

    print(
        f"GF Identifier Found     : "
        f"{resolved_count}"
    )

    print(
        f"GF Identifier Not Found : "
        f"{unresolved_count}"
    )

    print(
        "------------------------------------------"
    )

    if candidate_type_counts:

        print(
            "Successful Identifier Types:"
        )

        for (
            identifier_type,
            count
        ) in sorted(
            candidate_type_counts.items(),
            key=lambda x: (-x[1], x[0])
        ):

            print(
                f"  {identifier_type:<28} "
                f": {count}"
            )

    print(
        "=========================================="
    )

    print(
        f"Diagnostic Sheet: "
        f"{DIAGNOSTIC_SHEET}"
    )

    print(
        "==========================================" 
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
