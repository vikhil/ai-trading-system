"""
Central definition of worksheet schemas.

Every engine returns List[Dict].
Only sheets_writer.py converts dictionaries into sheet rows.
"""

ROTATION_COLUMNS = [
    "Ticker",
    "Health Score",
    "Health Status",
    "Current Value",
    "Portfolio Weight %",
    "P/L %",
    "Position Risk",
    "Action",
    "Priority",
    "Priority Label",
    "Replacement",
    "Replacement Score",
    "Replacement Edge",
    "Switch Score",
    "Capital Freed",
    "Comments",
]

PORTFOLIO_COLUMNS = [
    "Ticker",
    "Buy Price",
    "Quantity",
    "LTP",
    "Invested",
    "Current Value",
    "P/L ₹",
    "P/L %",
    "ATR Risk",
    "Position Risk",
    "Stop Loss",
    "Target",
    "Risk Reward",
    "RSI",
    "Trend",
    "Score",
    "Health Score",
    "Health Status",
    "Portfolio Weight %",
    "Sector",
]

TOP_PICKS_COLUMNS = []

BUY_QUEUE_COLUMNS = []

WATCHLIST_COLUMNS = []

FAILEDLOG_COLUMNS = [
    "Ticker",
    "Reason",
    "Value",
]
