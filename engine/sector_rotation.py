def build_sector_rankings(results_sorted):

    sector_map = {}

    for row in results_sorted:

        sector = row.get("sector", "UNKNOWN")

        if sector not in sector_map:
            sector_map[sector] = []

        sector_map[sector].append(row)

    rankings = []

    for sector, stocks in sector_map.items():

        avg_edge = sum(
            x.get("edge_rating", 0)
            for x in stocks
        ) / len(stocks)

        avg_rs = sum(
            x.get("rs_score", 0)
            for x in stocks
        ) / len(stocks)

        avg_score = sum(
            x.get("score", 0)
            for x in stocks
        ) / len(stocks)

        institutional = sum(
            x.get("institutional_rank", 0)
            for x in stocks
        ) / len(stocks)

        sector_strength = round(
            avg_edge * 0.35
            + avg_score * 0.25
            + avg_rs * 0.20
            + institutional * 0.20,
            2
        )

        rankings.append({

            "Sector": sector,

            "Strength": sector_strength,

            "Average Edge": round(avg_edge,2),

            "Average Score": round(avg_score,2),

            "Average RS": round(avg_rs,2),

            "Institutional": round(institutional,2),

            "Stocks": len(stocks)

        })

    rankings.sort(
        key=lambda x: x["Strength"],
        reverse=True
    )

    return rankings

def get_sector_strength(sector_name, sector_rankings):

    for row in sector_rankings:

        if row.get("Sector") == sector_name:
            return row.get("Sector Score", 0)

    return 0
