def calculate_replacement_quality(candidate):

    score = float(
        get_value(candidate,
                  "Score",
                  "score")
    )
    
    edge = float(
        get_value(candidate,
                  "Edge Rating",
                  "edge_rating")
    )
    
    rr = float(
        get_value(candidate,
                  "Risk Reward",
                  "risk_reward")
    )
    
    rs = float(
        get_value(candidate,
                  "RS Score",
                  "rs_score")
    )
    
    ai = float(
        get_value(candidate,
                  "AI Rank",
                  "ai_rank")
    )
    
    inst = float(
        get_value(candidate,
                  "Institutional Rank",
                  "institutional_rank")
    )
    
    sector = float(
        get_value(candidate,
                  "Sector Strength",
                  "sector_strength")
    )
    
    trend = float(
        get_value(candidate,
                  "Trend Persistence",
                  "trend_persistence")
    )

    breakout = str(
        get_value(candidate,
                  "Breakout",
                  "breakout",
                  default="")
    ).upper()=="Yes"
    
    confidence = str(
        get_value(candidate,
                  "AI Confidence",
                  "ai_confidence",
                  default="")
    ).upper()

    volume = float(
        get_value(candidate,
                  "Volume Spike",
                  "volume_spike")
    )

    quality = 0

    quality += score * 0.25
    quality += edge * 5
    quality += rr * 10
    quality += rs * 0.40

    quality += ai * 0.35
    quality += inst * 0.35

    quality += sector * 0.60

    quality += trend * 0.15

    if breakout == "YES":
        quality += 10

    if volume >= 3:
        quality += 12

    elif volume >= 2:
        quality += 8

    elif volume >= 1.5:
        quality += 4

    if confidence == "HIGH":
        quality += 8

    elif confidence == "MEDIUM":
        quality += 4

    return round(min(quality, 100), 2)

def get_value(data, *keys, default=0):
    """
    Returns the first matching key.
    Supports both BUY Queue and Scanner formats.
    Safe against None objects.
    """

    if not isinstance(data, dict):
        return default

    for key in keys:
        if key in data:
            value = data[key]
            if value not in ("", None):
                return value

    return default

def calculate_switch_score(holding, candidate):

    # -----------------------------
    # Current Holding
    # -----------------------------

    health = float(holding.get("Health Score", 50))
    pnl = float(holding.get("P/L %", 0))
    holding_score = float(holding.get("Score", 0))
    holding_rs = float(holding.get("RSI", 50))
    holding_weight = float(holding.get("Portfolio Weight %", 0))

    # -----------------------------
    # Candidate
    # -----------------------------

    score = float(
        get_value(candidate,
                  "Score",
                  "score")
    )
    edge = float(
        get_value(candidate,
                  "Edge Rating",
                  "edge_rating")
    )
    rr = float(
        get_value(candidate,
                  "Risk Reward",
                  "risk_reward")
    )
    rs = float(
        get_value(candidate,
                  "RS Score",
                  "rs_score")
    )
    ai = float(
        get_value(candidate,
                  "AI Rank",
                  "ai_rank")
    )
    sector = float(
    get_value(candidate,
              "Sector Strength",
              "sector_strength")
)
    
    volume = float(
        get_value(candidate,
                  "Volume Spike",
                  "volume_spike")
    )

    breakout = str(
        get_value(candidate,
                  "Breakout",
                  "breakout",
                  default="")
    ).upper()

    switch_score = 0.0

    # ----------------------------------
    # Holding Weakness
    # ----------------------------------
    
    switch_score += (100 - health) * 0.40

    # ----------------------------------
    # Profit Booking
    # ----------------------------------
    
    if pnl > 30:
        switch_score += 12
    
    elif pnl > 20:
        switch_score += 8
    
    elif pnl > 10:
        switch_score += 5

    # ----------------------------------
    # Candidate Quality
    # ----------------------------------
    
    inst = float(
    get_value(candidate,
              "Institutional Rank",
              "institutional_rank")
)
    trend = float(
        get_value(candidate,
                  "Trend Persistence",
                  "trend_persistence")
    )
    
    switch_score += score * 0.18
    switch_score += edge * 4
    switch_score += rr * 6
    
    switch_score += rs * 0.30
    switch_score += ai * 0.35
    switch_score += inst * 0.30
    
    switch_score += sector * 5
    switch_score += trend * 0.15

    # ----------------------------------
    # Relative Improvement
    # ----------------------------------
    
    score_gap = score - holding_score
    
    switch_score += max(score_gap, 0) * 0.50
    
    rs_gap = rs - holding_rs
    
    switch_score += max(rs_gap, 0) * 0.20

    # ----------------------------------
    # Diversification Bonus
    # ----------------------------------
    
    if holding_weight > 10:
        switch_score += 5
    
    elif holding_weight > 15:
        switch_score += 10
    
    # ---------------------------------
    # Volume confirmation
    # ---------------------------------

    if volume >= 3:
        switch_score += 8
    
    elif volume >= 2:
        switch_score += 5
    
    elif volume >= 1.5:
        switch_score += 2

    # ---------------------------------
    # Breakout bonus
    # ---------------------------------

    if breakout == "YES":
        switch_score += 6
    
    confidence = str(
        get_value(candidate,
                  "AI Confidence",
                  "ai_confidence",
                  default="")
    ).upper()
    
    if confidence == "HIGH":
        switch_score += 4
    
    elif confidence == "MEDIUM":
        switch_score += 2

    return round(min(switch_score, 100), 2)


def generate_comments(
    health_score,
    weight,
    position_risk,
    candidate,
    switch_score
):

    comments = []

    if health_score < 40:
        comments.append("Exit candidate")

    elif health_score < 60:
        comments.append("Weak holding")

    else:
        comments.append("Healthy holding")

    if weight > 10:
        comments.append("Portfolio overweight")

    elif weight < 1:
        comments.append("Small allocation")

    if position_risk > 1000:
        comments.append("High portfolio risk")

    if candidate:

        if str(candidate.get("Breakout", "")).upper() == "YES":
            comments.append("Breakout confirmed")

        if float(candidate.get("Volume Spike", 0)) >= 2:
            comments.append("Strong volume confirmation")

        if str(candidate.get("AI Confidence", "")).upper() == "HIGH":
            comments.append("High AI confidence")

        if float(candidate.get("Institutional Rank", 0)) >= 70:
            comments.append("Institutional buying")

        if float(candidate.get("Sector Strength", 0)) >= 40:
            comments.append("Leading sector")

        if switch_score >= 80:
            comments.append("SWITCH IMMEDIATELY")
        
        elif switch_score >= 65:
            comments.append("STRONG UPGRADE")
        
        elif switch_score >= 50:
            comments.append("GOOD UPGRADE")

        elif switch_score >= 40:
            comments.append("Moderate upgrade")

        else:
            comments.append("Monitor only")

    return ", ".join(comments)
