# -----------------------------------------
# Sector Classification
# -----------------------------------------

SECTOR_MAP = {

    # Banking
    "ICICIBANK.NS": "BANKING",
    "KOTAKBANK.NS": "BANKING",
    "YESBANK.NS": "BANKING",

    # Financials
    "PFC.NS": "FINANCIALS",
    "RECLTD.NS": "FINANCIALS",
    "JIOFIN.NS": "FINANCIALS",
    "PNBHOUSING.NS": "FINANCIALS",

    # Defence
    "BEL.NS": "DEFENCE",
    "MAZDOCK.NS": "DEFENCE",

    # Infrastructure
    "KEC.NS": "INFRA",
    "KNRCON.NS": "INFRA",
    "RVNL.NS": "INFRA",
    "RITES.NS": "INFRA",

    # Power
    "NHPC.NS": "POWER",
    "NTPC.NS": "POWER",
    "NTPCGREEN.NS": "POWER",

    # Consumer
    "DMART.NS": "CONSUMER",
    "VBL.NS": "CONSUMER",
    "TATACONSUM.NS": "CONSUMER",

    # Healthcare
    "APOLLOHOSP.NS": "HEALTHCARE",

    # Auto
    "OLECTRA.NS": "AUTO",
    "TVSSCS.NS": "AUTO",

    # Capital Goods
    "CGPOWER.NS": "CAPITAL_GOODS",
    "ACE.NS": "CAPITAL_GOODS",

    # Default
}

def get_sector(ticker):

    return SECTOR_MAP.get(
        ticker,
        "OTHER"
    )

def calculate_sector_exposure(portfolio):

    exposure = {}

    for row in portfolio:

        ticker = row.get("Ticker", "")

        sector = get_sector(ticker)

        exposure[sector] = exposure.get(sector, 0) + 1

    return exposure

def sector_penalty(candidate, exposure):

    sector = get_sector(
        candidate.get("Ticker", "")
    )

    count = exposure.get(sector, 0)

    if count >= 5:
        return -25

    if count >= 4:
        return -15

    if count >= 3:
        return -8

    return 0

