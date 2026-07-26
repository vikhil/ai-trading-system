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

        if market_cap:
            if market_cap >= 200000000000:
                market_cap_category = "LARGE"
            elif market_cap >= 50000000000:
                market_cap_category = "MID"
            else:
                market_cap_category = "SMALL"
        else:
            market_cap_category = "UNKNOWN"
        
        stock_master_rows.append([
            ticker,
            company_name,
            sector,
            industry,
            market_cap,
            market_cap_category,
            index_name,
            "",
            "",
            "YFINANCE"
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
