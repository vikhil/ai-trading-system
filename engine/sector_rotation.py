# engine/sector_rotation.py

def calculate_sector_score(sector_row):
    """
    Returns overall sector strength score.
    """

    score = 0

    # Relative strength
    score += float(sector_row.get("RS Score", 0))

    # Momentum
    score += float(sector_row.get("Momentum", 0))

    # Breadth
    score += float(sector_row.get("Breadth", 0))

    # Trend
    if sector_row.get("Trend") == "Bullish":
        score += 15

    # Breakout
    if sector_row.get("Breakout") == "YES":
        score += 10

    return round(score, 2)


def build_sector_rankings(sector_rows):

    for row in sector_rows:
        row["Sector Score"] = calculate_sector_score(row)

    return sorted(
        sector_rows,
        key=lambda x: x["Sector Score"],
        reverse=True,
    )


def get_sector_strength(sector_name, sector_rankings):

    for row in sector_rankings:

        if row.get("Sector") == sector_name:
            return row.get("Sector Score", 0)

    return 0
