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

    return round(quality,2)

calculate_replacement_quality()

calculate_holding_quality()

calculate_switch_score()

generate_rotation_comments()
