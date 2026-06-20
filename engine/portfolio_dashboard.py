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

    # -----------------------
    # Portfolio Risk Gauge
    # -----------------------
    
    risk_score = 0
    
    # Sector concentration
    if largest_sector > 50:
        risk_score += 40
    
    elif largest_sector > 40:
        risk_score += 30
    
    elif largest_sector > 30:
        risk_score += 20
    
    elif largest_sector > 20:
        risk_score += 10
    
    # Portfolio risk exposure
    risk_pct = (total_risk / total_value) * 100
    
    if risk_pct > 8:
        risk_score += 40
    
    elif risk_pct > 5:
        risk_score += 30
    
    elif risk_pct > 3:
        risk_score += 20
    
    elif risk_pct > 1:
        risk_score += 10
    
    # Portfolio health
    
    if avg_health < 40:
        risk_score += 30
    
    elif avg_health < 55:
        risk_score += 20
    
    elif avg_health < 70:
        risk_score += 10

    if risk_score <= 20:

        portfolio_risk = "VERY LOW"
    
    elif risk_score <= 40:
    
        portfolio_risk = "LOW"
    
    elif risk_score <= 60:
    
        portfolio_risk = "MODERATE"
    
    elif risk_score <= 80:
    
        portfolio_risk = "HIGH"
    
    else:
    
        portfolio_risk = "VERY HIGH"

    # -----------------------
    # Suggested Rebalancing
    # -----------------------
    
    recommendations = []
    
    # Sector concentration
    if largest_sector > 30:
    
        top_sector = sector_weights[0]
    
        recommendations.append(
    
            f"Reduce exposure to {top_sector['Sector']} "
            f"({top_sector['Weight']}%)"
    
        )
    
    # Weak holdings
    weak_count = sum(
    
        1
    
        for row in holdings
    
        if row.get("Health Status") in [
    
            "WEAK",
    
            "EXIT_CANDIDATE",
    
            "URGENT_EXIT"
    
        ]
    
    )
    
    if weak_count > 0:
    
        recommendations.append(
    
            f"Review {weak_count} weak holdings"
    
        )
    
    # High risk positions
    high_risk = [
    
        row
    
        for row in holdings
    
        if float(row.get("Position Risk", 0)) > 1000
    
    ]
    
    if len(high_risk):
    
        recommendations.append(
    
            f"Reduce risk in {len(high_risk)} positions"
    
        )
    
    # Portfolio health
    if avg_health < 60:
    
        recommendations.append(
    
            "Increase overall portfolio quality"
    
        )
    
    # Capital available
    rotation_capital = round(
    
        sum(
    
            float(row.get("Current Value", 0))
    
            for row in holdings
    
            if row.get("Health Status") in [
    
                "EXIT_CANDIDATE",
    
                "URGENT_EXIT"
    
            ]
    
        ),
    
        2
    
    )
    
    if rotation_capital > 0:
    
        recommendations.append(
    
            f"Potential rotation capital: ₹{rotation_capital:,.0f}"
    
        )
    
    if not recommendations:
    
        recommendations.append(
    
            "No major rebalancing required"
    
        )
        
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
    
        "Diversification": diversification,

        "Portfolio Risk Score": risk_score,

        "Portfolio Risk Gauge": portfolio_risk,

        "Recommendations": recommendations,

        "Rotation Capital": rotation_capital
    
    }
