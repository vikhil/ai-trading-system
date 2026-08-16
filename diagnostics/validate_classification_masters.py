import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials


SPREADSHEET_ID = "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"

STOCK_MASTER_SHEET = "Stock_Master"

NSE_FILE = "data/nse_industry_classification.csv"
BSE_FILE = "data/bse_industry_classification.csv"


INVALID_VALUES = {
    "",
    "UNKNOWN",
    "N/A",
    "NA",
    "NULL",
    "NONE",
}


def normalize(value):

    if value is None:
        return ""

    return str(value).strip().upper()


def connect():

    credentials_json = os.getenv(
        "GOOGLE_CREDENTIALS"
    )

    if not credentials_json:
        raise RuntimeError(
            "GOOGLE_CREDENTIALS is not configured."
        )

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ]

    credentials = (
        ServiceAccountCredentials
        .from_json_keyfile_dict(
            eval(credentials_json),
            scope
        )
    )

    client = gspread.authorize(
        credentials
    )

    return client.open_by_key(
        SPREADSHEET_ID
    )


def find_column(headers, names):

    normalized = {
        normalize(h): h
        for h in headers
    }

    for name in names:

        if normalize(name) in normalized:
            return normalized[
                normalize(name)
            ]

    raise RuntimeError(
        f"Column not found: {names}"
    )


def read_unresolved_symbols(
    spreadsheet
):

    ws = spreadsheet.worksheet(
        STOCK_MASTER_SHEET
    )

    values = ws.get_all_values()

    headers = values[0]

    ticker_col = find_column(
        headers,
        [
            "Ticker",
            "Yahoo Ticker",
            "Symbol",
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

    symbols = set()

    for row in values[1:]:

        record = dict(
            zip(headers, row)
        )

        sector = normalize(
            record.get(sector_col)
        )

        industry = normalize(
            record.get(industry_col)
        )

        if (
            sector not in INVALID_VALUES
            or
            industry not in INVALID_VALUES
        ):
            continue

        ticker = normalize(
            record.get(ticker_col)
        )

        if ticker.endswith(".NS"):
            ticker = ticker[:-3]

        if ticker:
            symbols.add(ticker)

    return symbols


def main():

    print("=" * 70)
    print(
        "CLASSIFICATION MASTER COVERAGE"
    )
    print("=" * 70)

    spreadsheet = connect()

    stock_symbols = read_unresolved_symbols(
        spreadsheet
    )

    nse = pd.read_csv(
        NSE_FILE,
        dtype=str
    ).fillna("")

    bse = pd.read_csv(
        BSE_FILE,
        dtype=str
    ).fillna("")

    nse_symbols = {
        normalize(x)
        for x in nse["NSE Symbol"]
    }

    bse_symbols = {
        normalize(x)
        for x in bse["NSE Symbol"]
    }

    missing_nse = (
        stock_symbols - nse_symbols
    )

    missing_bse = (
        stock_symbols - bse_symbols
    )

    print()
    print(
        f"Stock_Master unresolved : "
        f"{len(stock_symbols)}"
    )

    print(
        f"NSE master records      : "
        f"{len(nse_symbols)}"
    )

    print(
        f"BSE master records      : "
        f"{len(bse_symbols)}"
    )

    print()

    if missing_nse:

        print(
            "Missing from NSE master:"
        )

        for symbol in sorted(
            missing_nse
        ):
            print(
                f"  {symbol}"
            )

    else:

        print(
            "All unresolved stocks "
            "exist in NSE master."
        )

    print()

    if missing_bse:

        print(
            "Missing from BSE master:"
        )

        for symbol in sorted(
            missing_bse
        ):
            print(
                f"  {symbol}"
            )

    else:

        print(
            "All unresolved stocks "
            "exist in BSE master."
        )

    print()

    if missing_nse or missing_bse:

        raise RuntimeError(
            "Classification master coverage FAILED."
        )

    print(
        "Classification master coverage PASSED."
    )


if __name__ == "__main__":
    main()
