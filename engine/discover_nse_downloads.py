"""
Central location for all NSE download URLs.

Later this file will automatically discover
the latest URLs from NSE.

For now we keep them fixed.
"""

EQUITY_MASTER = (
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
)

ETF_MASTER = (
    "https://nsearchives.nseindia.com/content/equities/ETF_L.csv"
)

REIT_MASTER = (
    "https://nsearchives.nseindia.com/content/equities/REIT_L.csv"
)

INVIT_MASTER = (
    "https://nsearchives.nseindia.com/content/equities/INVIT_L.csv"
)


def get_download_links():

    return {
        "equity": EQUITY_MASTER,
        "etf": ETF_MASTER,
        "reit": REIT_MASTER,
        "invit": INVIT_MASTER,
    }


if __name__ == "__main__":

    for k, v in get_download_links().items():
        print(k, "->", v)
