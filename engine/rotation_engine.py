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


def generate_comments(weight,
                      position_risk,
                      breakout,
                      volume,
                      health):

    comments = []

    if weight < 1:
        comments.append("CONSOLIDATE")

    if weight > 10:

        if health >= 80:
            comments.append("TRIM PROFITS")
        else:
            comments.append("OVERWEIGHT")

    if position_risk > 1000:
        comments.append("HIGH RISK")

    if str(breakout).upper() == "YES":
        comments.append("BREAKOUT")

    if volume >= 2:
        comments.append("VOLUME SURGE")

    return ", ".join(comments)

calculate_replacement_quality()

calculate_holding_quality()

calculate_switch_score()

generate_rotation_comments()
