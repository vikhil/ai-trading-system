def generate_portfolio_dashboard(portfolio):

    holdings = [
        x for x in portfolio
        if float(x.get("Current Value", 0)) > 0
    ]

    if not holdings:
        return {}

    total_value = sum(
        float(x["Current Value"])
        for x in holdings
    )

    avg_health = round(
        sum(
            float(x["Health Score"])
            for x in holdings
        ) / len(holdings),
        2
    )

    total_risk = round(
        sum(
            float(x["Position Risk"])
            for x in holdings
        ),
        2
    )

    winners = sorted(
        holdings,
        key=lambda x: float(x["P/L %"]),
        reverse=True
    )[:5]

    losers = sorted(
        holdings,
        key=lambda x: float(x["P/L %"])
    )[:5]

    risk_positions = sorted(
        holdings,
        key=lambda x: float(x["Position Risk"]),
        reverse=True
    )[:5]

    return {

        "Portfolio Value": total_value,

        "Average Health": avg_health,

        "Total Risk": total_risk,

        "Total Holdings": len(holdings),

        "Top Winners": winners,

        "Top Losers": losers,

        "Top Risks": risk_positions

    }
