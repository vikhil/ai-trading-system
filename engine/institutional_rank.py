def calculate_institutional_rank(row):

    score = 0

    # -----------------------
    # Relative Strength (15)
    # -----------------------
    
    rs = float(row.get("RS Score", 0))
    
    if rs >= 30:
        score += 15
    
    elif rs >= 20:
        score += 10
    
    elif rs >= 10:
        score += 5
    
    # -----------------------
    # Health Score (30)
    # -----------------------

    health = float(row.get("Health Score", 0))

    score += health * 0.30

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
