# engine/ai_rank.py

def calculate_ai_rank(row):
    """
    Composite AI Ranking Score (0-100)
    """

    edge = float(row.get("edge_score", 0))

    institutional = float(row.get("institutional_rank", 0))

    sector = float(row.get("sector_strength", 0))

    rs = float(row.get("rs_score", 0))

    trend = float(row.get("trend_persistence", 0))

    ai_rank = (
        edge * 0.35
        + institutional * 0.25
        + sector * 0.20
        + rs * 0.10
        + trend * 0.10
    )

    return round(min(ai_rank, 100), 2)

def get_ai_confidence(ai_rank):

    if ai_rank >= 85:
        return "VERY HIGH"

    elif ai_rank >= 70:
        return "HIGH"

    elif ai_rank >= 55:
        return "MEDIUM"

    elif ai_rank >= 40:
        return "LOW"

    else:
        return "VERY LOW"
