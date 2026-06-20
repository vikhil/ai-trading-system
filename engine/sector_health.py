def calculate_sector_health(portfolio):

    sector_scores = {}

    sector_counts = {}

    for row in portfolio:

        sector = row.get("Sector", "UNKNOWN")

        score = float(row.get("Score", 0))

        rs = float(row.get("RS Score", 0))

        health = float(row.get("Health Score", 0))

        total = (
            score * 0.35 +
            rs * 0.30 +
            health * 0.35
        )

        sector_scores[sector] = sector_scores.get(sector, 0) + total

        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    sector_strength = {}

    for sector in sector_scores:

        avg = sector_scores[sector] / sector_counts[sector]

        if avg >= 80:
            bonus = 8

        elif avg >= 70:
            bonus = 5

        elif avg >= 60:
            bonus = 2

        elif avg >= 50:
            bonus = 0

        elif avg >= 40:
            bonus = -3

        else:
            bonus = -8

        sector_strength[sector] = {
            "Average Health": round(avg,2),
            "Bonus": bonus
        }

    return sector_strength
