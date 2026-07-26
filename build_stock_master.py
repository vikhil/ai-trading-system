universe = load_universe()

stock_master_rows = [
    [
        "Ticker",
        "Company Name",
        "Sector",
        "Industry",
        "Market Cap",
        "Market Cap Category",
        "Index",
        "First Seen",
        "Last Updated",
        "Data Source"
    ]
]

for row in universe:

    ticker = row["Ticker"]

    try:

        info = yf.Ticker(ticker).info

        company_name = info.get("longName", "")

        sector = info.get("sector") or "UNKNOWN"

        industry = info.get("industry") or "UNKNOWN"

        market_cap = info.get("marketCap", "")

        if ticker in nifty50:
            index_name = "NIFTY50"

        elif ticker in niftynext50:
            index_name = "NEXT50"

        else:
            index_name = "OTHER"

        stock_master_rows.append([
            ticker,
            company_name,
            sector,
            industry,
            market_cap,
            index_name
        ])

    except Exception as e:

        print(f"FAILED -> {ticker} -> {e}")
    
        stock_master_rows.append([
            ticker,
            "",
            "",
            "",
            "",
            "FAILED"
        ])
