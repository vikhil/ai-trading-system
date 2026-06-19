def classify_bucket(stock):

    score = float(stock.get("Score", 0))
    edge = float(stock.get("Edge Rating", 0))
    health = float(stock.get("Health Score", score))
    rr = float(stock.get("Risk Reward", 0))
    rs = float(stock.get("RS Score", 0))

    ticker = stock.get("Ticker", "")

    # -------------------------
    # Core
    # -------------------------

    if (
        health >= 85
        and edge >= 7
        and rr >= 2
    ):
        return "CORE"

    # -------------------------
    # Growth
    # -------------------------

    if (
        health >= 70
        and edge >= 6
        and rs >= 70
    ):
        return "GROWTH"

    # -------------------------
    # Tactical
    # -------------------------

    if (
        health >= 50
        and edge >= 5
    ):
        return "TACTICAL"

    # -------------------------
    # Speculative
    # -------------------------

    return "SPECULATIVE"
