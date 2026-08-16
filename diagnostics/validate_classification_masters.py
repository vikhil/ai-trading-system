import os
import pandas as pd


NSE_FILE = "data/nse_industry_classification.csv"
BSE_FILE = "data/bse_industry_classification.csv"


NSE_HEADERS = [
    "NSE Symbol",
    "NSE Macro Sector",
    "NSE Sector",
    "NSE Industry",
    "NSE Basic Industry",
]

BSE_HEADERS = [
    "NSE Symbol",
    "BSE Sector",
    "BSE Industry",
]


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

    return str(value).strip()


def validate_file(
    filename,
    required_columns,
    label
):

    print()
    print("=" * 70)
    print(f"VALIDATING {label}")
    print("=" * 70)

    if not os.path.exists(filename):

        raise RuntimeError(
            f"{filename} does not exist."
        )

    df = pd.read_csv(
        filename,
        dtype=str
    ).fillna("")

    print(
        f"Records found: {len(df)}"
    )

    print(
        f"Columns found: {list(df.columns)}"
    )

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        raise RuntimeError(
            f"{label} missing columns: "
            f"{missing_columns}"
        )

    if df.empty:

        raise RuntimeError(
            f"{label} contains headers but zero records."
        )

    # --------------------------------------------------------
    # Normalize fields
    # --------------------------------------------------------

    for column in required_columns:

        df[column] = (
            df[column]
            .astype(str)
            .str.strip()
        )

    # --------------------------------------------------------
    # Symbol validation
    # --------------------------------------------------------

    empty_symbols = df[
        df["NSE Symbol"]
        .isin(INVALID_VALUES)
    ]

    if not empty_symbols.empty:

        raise RuntimeError(
            f"{label} contains "
            f"{len(empty_symbols)} empty symbols."
        )

    duplicate_symbols = (
        df["NSE Symbol"]
        .duplicated(keep=False)
    )

    if duplicate_symbols.any():

        duplicates = (
            df.loc[
                duplicate_symbols,
                "NSE Symbol"
            ]
            .unique()
            .tolist()
        )

        raise RuntimeError(
            f"{label} contains duplicate symbols: "
            f"{duplicates}"
        )

    # --------------------------------------------------------
    # Classification validation
    # --------------------------------------------------------

    classification_columns = [
        column
        for column in required_columns
        if column != "NSE Symbol"
    ]

    for column in classification_columns:

        invalid = df[
            df[column]
            .str.upper()
            .isin(INVALID_VALUES)
        ]

        if not invalid.empty:

            raise RuntimeError(
                f"{label}: column '{column}' "
                f"has {len(invalid)} invalid records."
            )

    print(
        f"{label}: VALID"
    )

    return df


def main():

    print()
    print("=" * 70)
    print(
        "CLASSIFICATION MASTER VALIDATION"
    )
    print("=" * 70)

    nse_df = validate_file(
        NSE_FILE,
        NSE_HEADERS,
        "NSE CLASSIFICATION"
    )

    bse_df = validate_file(
        BSE_FILE,
        BSE_HEADERS,
        "BSE CLASSIFICATION"
    )

    # --------------------------------------------------------
    # Cross-check symbols
    # --------------------------------------------------------

    nse_symbols = set(
        nse_df["NSE Symbol"]
    )

    bse_symbols = set(
        bse_df["NSE Symbol"]
    )

    missing_from_bse = (
        nse_symbols - bse_symbols
    )

    missing_from_nse = (
        bse_symbols - nse_symbols
    )

    if missing_from_bse:

        raise RuntimeError(
            "Symbols present in NSE master "
            "but missing from BSE master: "
            f"{sorted(missing_from_bse)}"
        )

    if missing_from_nse:

        raise RuntimeError(
            "Symbols present in BSE master "
            "but missing from NSE master: "
            f"{sorted(missing_from_nse)}"
        )

    print()
    print(
        f"NSE records : {len(nse_df)}"
    )

    print(
        f"BSE records : {len(bse_df)}"
    )

    print()
    print(
        "NSE/BSE symbol sets match."
    )

    print()
    print("=" * 70)
    print(
        "CLASSIFICATION MASTERS ARE VALID"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
