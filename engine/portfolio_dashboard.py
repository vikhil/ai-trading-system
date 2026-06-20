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

    sector_summary = {}

    for row in holdings:
    
        sector = row.get("Sector", "UNKNOWN")
    
        value = float(row.get("Current Value", 0))
    
        if sector not in sector_summary:
    
            sector_summary[sector] = 0
    
        sector_summary[sector] += value
    
    sector_weights = []
    
    largest_sector = 0
    
    for sector, value in sector_summary.items():
    
        weight = round(
            (value / total_value) * 100,
            2
        )
    
        largest_sector = max(
            largest_sector,
            weight
        )
    
        sector_weights.append({
    
            "Sector": sector,
    
            "Weight": weight
    
        })
    
    sector_weights = sorted(
        sector_weights,
        key=lambda x: x["Weight"],
        reverse=True
    )
    
    # -----------------------
    # Diversification Score
    # -----------------------
    
    if largest_sector <= 20:
    
        diversification = "EXCELLENT"
    
    elif largest_sector <= 30:
    
        diversification = "GOOD"
    
    elif largest_sector <= 40:
    
        diversification = "AVERAGE"
    
    elif largest_sector <= 50:
    
        diversification = "POOR"
    
    else:
    
        diversification = "HIGHLY CONCENTRATED"
    
    return {
    
        "Portfolio Value": total_value,
    
        "Average Health": avg_health,
    
        "Total Risk": total_risk,
    
        "Total Holdings": len(holdings),
    
        "Top Winners": winners,
    
        "Top Losers": losers,
    
        "Top Risks": risk_positions,
    
        "Sector Weights": sector_weights,
    
        "Largest Sector": largest_sector,
    
        "Diversification": diversification
    
    }
