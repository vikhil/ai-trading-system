def generate_portfolio_summary(portfolio):

    if not portfolio:

        return {}

    total_value = 0
    total_risk = 0

    total_health = 0
    total_score = 0
    total_rs = 0
    total_rr = 0
    total_edge = 0
    total_weight = 0

    count = 0

    for row in portfolio:

        value = float(row.get("Current Value", 0))
        health = float(row.get("Health Score", 0))
        score = float(row.get("Score", 0))
        rs = float(row.get("RS Score", 0))
        rr = float(row.get("Risk Reward", 0))
        edge = float(row.get("Edge Rating", 0))
        weight = float(row.get("Portfolio Weight %", 0))
        risk = float(row.get("Position Risk", 0))

        total_value += value
        total_risk += risk

        total_health += health
        total_score += score
        total_rs += rs
        total_rr += rr
        total_edge += edge
        total_weight += weight

        count += 1

    average_health = total_health / count
    average_score = total_score / count
    average_rs = total_rs / count
    average_rr = total_rr / count
    average_edge = total_edge / count
    average_weight = total_weight / count

    weighted_health = 0

    if total_value > 0:

        for row in portfolio:

            value = float(row.get("Current Value", 0))
            health = float(row.get("Health Score", 0))

            weighted_health += (
                value / total_value
            ) * health

    if weighted_health >= 80:
        rating = "EXCELLENT"

    elif weighted_health >= 70:
        rating = "GOOD"

    elif weighted_health >= 60:
        rating = "AVERAGE"

    elif weighted_health >= 50:
        rating = "WEAK"

    else:
        rating = "POOR"

    return {

        "Portfolio Value": round(total_value, 2),

        "Portfolio Health": round(weighted_health, 2),

        "Health Rating": rating,

        "Average Health": round(average_health, 2),

        "Average Score": round(average_score, 2),

        "Average RS": round(average_rs, 2),

        "Average RR": round(average_rr, 2),

        "Average Edge": round(average_edge, 2),

        "Average Weight": round(average_weight, 2),

        "Total Portfolio Risk": round(total_risk, 2),

        "Total Holdings": count
    }
