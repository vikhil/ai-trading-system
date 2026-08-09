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
DIAGNOSTIC_SHEET = "GF_Diagnostic"


# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(
    os.environ["GOOGLE_CREDENTIALS"]
)

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_dict,
    scope
)

client = gspread.authorize(creds)

sheet = client.open_by_key(
    SPREADSHEET_ID
)

print("Connecting to Google Sheet...")
print("Connected")


# ============================================================
# LOAD STOCK MASTER
# ============================================================

stock_master_ws = sheet.worksheet(
    SOURCE_SHEET
)

stock_master = stock_master_ws.get_all_records()

print(
    f"Stock Master Rows: {len(stock_master)}"
)


# ============================================================
# IDENTIFY UNRESOLVED EQUITIES
# ============================================================

def is_unknown(value):

    value = str(value).strip().upper()

    return value in (
        "",
        "UNKNOWN",
        "N/A",
        "NA",
        "NONE",
        "NULL"
    )


def is_zero_market_cap(value):

    if value is None:
        return True

    if isinstance(value, str):

        cleaned = (
            value
            .replace(",", "")
            .replace("₹", "")
            .strip()
        )

        if cleaned == "":
            return True

        try:
            return float(cleaned) <= 0
        except:
            return True

    try:
        return float(value) <= 0
    except:
        return True


unresolved = []

for row in stock_master:

    ticker = str(
        row.get("Ticker", "")
    ).strip()

    asset_type = str(
        row.get("Asset Type", "EQUITY")
    ).strip().upper()

    # Stock_Master currently contains equity rows
    # without an Asset Type column in the displayed
    # architecture, so treat missing Asset Type as EQUITY.
    if asset_type != "EQUITY":
        continue

    sector = row.get(
        "Sector",
        "UNKNOWN"
    )

    industry = row.get(
        "Industry",
        "UNKNOWN"
    )

    market_cap = row.get(
        "Market Cap",
        0
    )

    if (
        is_unknown(sector)
        or is_unknown(industry)
        or is_zero_market_cap(market_cap)
    ):

        unresolved.append(row)


print(
    f"Unresolved Equity Rows: {len(unresolved)}"
)


# ============================================================
# CREATE / RESET DIAGNOSTIC SHEET
# ============================================================

try:

    gf_ws = sheet.worksheet(
        DIAGNOSTIC_SHEET
    )

    print(
        f"Using existing worksheet: {DIAGNOSTIC_SHEET}"
    )

except gspread.WorksheetNotFound:

    print(
        f"Creating worksheet: {DIAGNOSTIC_SHEET}"
    )

    gf_ws = sheet.add_worksheet(
        title=DIAGNOSTIC_SHEET,
        rows=200,
        cols=30
    )


print("Clearing diagnostic worksheet...")

gf_ws.clear()


# ============================================================
# HEADER
# ============================================================

headers = [
    "Run Date",
    "Ticker",
    "NSE Symbol",
    "Yahoo Sector",
    "Yahoo Industry",
    "Yahoo Market Cap",

    "GF NSE Price",
    "GF NSE Market Cap",
    "GF NSE Shares",
    "GF NSE Currency",
    "GF NSE Trade Time",
    "GF NSE Status",

    "GF BSE Price",
    "GF BSE Market Cap",
    "GF BSE Shares",
    "GF BSE Currency",
    "GF BSE Trade Time",
    "GF BSE Status",

    "Diagnosis"
]

gf_ws.update(
    range_name="A1",
    values=[headers]
)


# ============================================================
# WRITE STOCKS + GOOGLE FINANCE FORMULAS
# ============================================================

today = datetime.now().strftime(
    "%Y-%m-%d"
)

diagnostic_rows = []

for row in unresolved:

    ticker = str(
        row.get("Ticker", "")
    ).strip()

    nse_symbol = (
        ticker
        .replace(".NS", "")
        .strip()
    )

    yahoo_sector = row.get(
        "Sector",
        "UNKNOWN"
    )

    yahoo_industry = row.get(
        "Industry",
        "UNKNOWN"
    )

    yahoo_market_cap = row.get(
        "Market Cap",
        0
    )

    diagnostic_rows.append([
        today,
        ticker,
        nse_symbol,
        yahoo_sector,
        yahoo_industry,
        yahoo_market_cap,

        # NSE GOOGLEFINANCE
        f'=IFERROR(GOOGLEFINANCE("NSE:{nse_symbol}","price"),"")',

        f'=IFERROR(GOOGLEFINANCE("NSE:{nse_symbol}","marketcap"),"")',

        f'=IFERROR(GOOGLEFINANCE("NSE:{nse_symbol}","shares"),"")',

        f'=IFERROR(GOOGLEFINANCE("NSE:{nse_symbol}","currency"),"")',

        f'=IFERROR(GOOGLEFINANCE("NSE:{nse_symbol}","tradetime"),"")',

        f'=IFERROR(GOOGLEFINANCE("NSE:{nse_symbol}","price"),"")',

        # BSE GOOGLEFINANCE
        # We intentionally test the same symbol on BSE.
        f'=IFERROR(GOOGLEFINANCE("BSE:{nse_symbol}","price"),"")',

        f'=IFERROR(GOOGLEFINANCE("BSE:{nse_symbol}","marketcap"),"")',

        f'=IFERROR(GOOGLEFINANCE("BSE:{nse_symbol}","shares"),"")',

        f'=IFERROR(GOOGLEFINANCE("BSE:{nse_symbol}","currency"),"")',

        f'=IFERROR(GOOGLEFINANCE("BSE:{nse_symbol}","tradetime"),"")',

        f'=IFERROR(GOOGLEFINANCE("BSE:{nse_symbol}","price"),"")',

        ""
    ])


if diagnostic_rows:

    gf_ws.update(
        range_name=f"A2:S{len(diagnostic_rows)+1}",
        values=diagnostic_rows
    )


print(
    f"Google Finance formulas written: {len(diagnostic_rows)}"
)


# ============================================================
# ALLOW GOOGLE SHEETS TO CALCULATE
# ============================================================

print(
    "Waiting for Google Finance formulas to calculate..."
)

time.sleep(15)


# ============================================================
# READ CALCULATED VALUES
# ============================================================

values = gf_ws.get_all_values()

print(
    f"Diagnostic rows read: {len(values)-1}"
)


# ============================================================
# CLASSIFY RESULTS
# ============================================================

def numeric_value(value):

    if value is None:
        return 0

    try:

        cleaned = (
            str(value)
            .replace(",", "")
            .replace("₹", "")
            .strip()
        )

        if cleaned == "":
            return 0

        return float(cleaned)

    except:

        return 0


diagnosis_updates = []

gf_nse_found = 0
gf_bse_found = 0
gf_neither_found = 0
gf_both_found = 0


for index, row in enumerate(values[1:], start=2):

    if len(row) < 19:
        continue

    ticker = row[1]

    nse_price = numeric_value(row[6])
    nse_market_cap = numeric_value(row[7])

    bse_price = numeric_value(row[12])
    bse_market_cap = numeric_value(row[13])

    nse_found = (
        nse_price > 0
        or nse_market_cap > 0
    )

    bse_found = (
        bse_price > 0
        or bse_market_cap > 0
    )

    if nse_found and bse_found:

        diagnosis = (
            "GF_BOTH_NSE_BSE"
        )

        gf_both_found += 1

    elif nse_found:

        diagnosis = (
            "GF_NSE_FOUND"
        )

        gf_nse_found += 1

    elif bse_found:

        diagnosis = (
            "GF_BSE_FOUND"
        )

        gf_bse_found += 1

    else:

        diagnosis = (
            "GF_NEITHER_FOUND"
        )

        gf_neither_found += 1

    diagnosis_updates.append([
        index,
        diagnosis
    ])


# ============================================================
# WRITE DIAGNOSIS
# ============================================================

for row_number, diagnosis in diagnosis_updates:

    gf_ws.update(
        range_name=f"S{row_number}",
        values=[[diagnosis]]
    )


# ============================================================
# SUMMARY
# ============================================================

print("")
print("================================")
print("GOOGLE FINANCE DIAGNOSTIC")
print("================================")

print(
    f"Unresolved Equities : {len(unresolved)}"
)

print(
    f"GF NSE Found        : {gf_nse_found}"
)

print(
    f"GF BSE Found        : {gf_bse_found}"
)

print(
    f"GF Both NSE/BSE     : {gf_both_found}"
)

print(
    f"GF Neither Found    : {gf_neither_found}"
)

print("================================")

print(
    f"Diagnostic Sheet: {DIAGNOSTIC_SHEET}"
)

print("================================")
