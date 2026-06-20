def calculate_institutional_rank(row):

    score = 0

    # -----------------------
    # Health Score (40)
    # -----------------------

    health = float(row.get("Health Score", 0))

    score += health * 0.40

    # -----------------------
    # Edge Rating (25)
    # -----------------------

    edge = float(row.get("Edge Rating", 0))

    score += edge * 0.25

    # -----------------------
    # Scanner Score (15)
    # -----------------------

    scanner = float(row.get("Score", 0))

    score += scanner * 0.15

    # -----------------------
    # Risk Reward (10)
    # -----------------------

    rr = float(row.get("Risk Reward", 0))

    score += min(rr, 5) * 2

    # -----------------------
    # Breakout Bonus
    # -----------------------

    if str(row.get("Breakout", "")).upper() == "YES":
        score += 5

    # -----------------------
    # Volume Bonus
    # -----------------------

    volume = float(row.get("Volume Spike", 0))

    if volume >= 2:
        score += 5

    elif volume >= 1.5:
        score += 3

    return round(min(score, 100), 2)
