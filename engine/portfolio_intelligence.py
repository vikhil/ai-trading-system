from collections import defaultdict


def build_sector_exposure(enriched_portfolio):
    """
    Returns sector allocation percentages based on Current Value.
    """

    sector_values = defaultdict(float)
    total_value = 0.0

    for row in enriched_portfolio:

        try:
            sector = str(row.get("Sector", "Unknown")).strip()

            current_value = float(row.get("Current Value", 0))

            sector_values[sector] += current_value

            total_value += current_value

        except Exception:
            continue

    exposure = {}

    if total_value == 0:
        return exposure

    for sector, value in sector_values.items():

        exposure[sector] = round(
            (value / total_value) * 100,
            2
        )

    return exposure


def calculate_sector_bonus(candidate_sector, sector_exposure):

    exposure = sector_exposure.get(candidate_sector, 0)

    if exposure < 5:
        return 20

    elif exposure < 10:
        return 10

    elif exposure < 15:
        return 5

    elif exposure < 20:
        return 0

    elif exposure < 25:
        return -10

    else:
        return -20


def calculate_portfolio_fit(ai_rank, sector_bonus):

    try:
        return round(float(ai_rank) + float(sector_bonus), 2)

    except Exception:
        return 0


def recommendation(portfolio_fit):

    if portfolio_fit >= 90:
        return "STRONG BUY"

    elif portfolio_fit >= 75:
        return "BUY"

    elif portfolio_fit >= 60:
        return "WATCH"

    else:
        return "SKIP"
