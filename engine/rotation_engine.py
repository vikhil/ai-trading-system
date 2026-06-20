def calculate_replacement_quality(candidate):

    score = float(candidate.get("Score", 0))
    edge = float(candidate.get("Edge Rating", 0))
    rr = float(candidate.get("Risk Reward", 0))
    rs = float(candidate.get("RS Score", 0))
    breakout = str(candidate.get("Breakout", "")).upper()
    volume = float(candidate.get("Volume Spike", 0))

    quality = (
        edge * 4
        + score * 0.30
        + rr * 10
        + rs * 0.40
    )

    if breakout == "YES":
        quality += 10

    if volume >= 2:
        quality += 10
    elif volume >= 1.5:
        quality += 5

    return round(quality, 2)


def calculate_switch_score(holding, candidate):

    health = float(holding.get("Health Score", 0))

    score = float(candidate.get("Score", 0))
    edge = float(candidate.get("Edge Rating", 0))
    rr = float(candidate.get("Risk Reward", 0))
    rs = float(candidate.get("RS Score", 0))
    volume = float(candidate.get("Volume Spike", 0))

    return round(
        (score - health)
        + (edge * 2)
        + (rs / 5)
        + (rr * 3)
        + (volume / 25),
        2
    )


def generate_comments(
    health_score,
    weight,
    position_risk,
    candidate,
    switch_score
):

    comments = []

    if health_score < 40:
        comments.append("Very weak holding")

    elif health_score < 60:
        comments.append("Weak momentum")

    if weight > 10:
        comments.append("Large allocation")

    if position_risk > 1000:
        comments.append("High portfolio risk")

    if candidate:

        if candidate.get("Breakout") == "YES":
            comments.append("Replacement breakout")

        if float(candidate.get("Volume Spike",0)) >= 2:
            comments.append("Strong volume")

        if switch_score >= 70:
            comments.append("Excellent upgrade")

        elif switch_score >= 55:
            comments.append("Good upgrade")

    return ", ".join(comments)
