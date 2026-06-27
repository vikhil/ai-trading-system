def calculate_replacement_quality(candidate):

    score = float(candidate.get("Score", 0))
    edge = float(candidate.get("Edge Rating", 0))
    rr = float(candidate.get("Risk Reward", 0))
    rs = float(candidate.get("RS Score", 0))
    breakout = str(candidate.get("Breakout", "")).upper()
    volume = float(candidate.get("Volume Spike", 0))
    
    quality = (
        score * 0.40
        + edge * 5
        + rr * 12
        + rs * 0.50
    )

    if breakout == "YES":
        quality += 12

    if volume >= 2:
        quality += 12
    elif volume >= 1.5:
        quality += 6

    return round(quality, 2)


def calculate_switch_score(holding, candidate):

    health = float(holding.get("Health Score", 50))
    pnl = float(holding.get("P/L %", 0))

    score = float(candidate.get("Score", 0))
    edge = float(candidate.get("Edge Rating", 0))
    rr = float(candidate.get("Risk Reward", 0))
    rs = float(candidate.get("RS Score", 0))
    ai = float(candidate.get("AI Rank", 0))
    volume = float(candidate.get("Volume Spike", 0))

    switch_score = 0

    # ---------------------------------
    # Weak holdings should rotate sooner
    # ---------------------------------

    if health < 20:
        switch_score += 35

    elif health < 40:
        switch_score += 25

    elif health < 60:
        switch_score += 15

    # ---------------------------------
    # Book profits only on winners
    # ---------------------------------

    if pnl > 20:
        switch_score += 20

    elif pnl > 10:
        switch_score += 15

    elif pnl > 5:
        switch_score += 10

    # ---------------------------------
    # Candidate quality
    # ---------------------------------

    switch_score += score * 0.15
    switch_score += edge * 2
    switch_score += rr * 4
    switch_score += rs * 0.15
    switch_score += ai * 0.10

    # ---------------------------------
    # Volume confirmation
    # ---------------------------------

    if volume >= 2:
        switch_score += 5

    # ---------------------------------
    # Breakout bonus
    # ---------------------------------

    if str(candidate.get("Breakout", "")).upper() == "YES":
        switch_score += 5

    return round(min(switch_score, 100), 2)


def generate_comments(
    health_score,
    weight,
    position_risk,
    candidate,
    switch_score
):

    comments = []

    # Holding quality
    if health_score < 40:
        comments.append("EXIT CANDIDATE")

    elif health_score < 60:
        comments.append("WEAK HOLD")

    # Position sizing
    if weight > 10:
        comments.append("OVERWEIGHT")

    elif weight < 1:
        comments.append("SMALL POSITION")

    # Risk
    if position_risk > 1000:
        comments.append("HIGH RISK")

    # Replacement quality
    if candidate:

        if str(candidate.get("Breakout", "")).upper() == "YES":
            comments.append("BREAKOUT")

        if float(candidate.get("Volume Spike", 0)) >= 2:
            comments.append("HEAVY VOLUME")

        if switch_score >= 70:
            comments.append("EXCELLENT UPGRADE")

        elif switch_score >= 55:
            comments.append("GOOD UPGRADE")

    return ", ".join(comments)
