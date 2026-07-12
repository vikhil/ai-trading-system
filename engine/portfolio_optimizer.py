import pandas as pd


def calculate_optimizer_score(row):

    health = float(row.get("Health Score", row.get("score", 0)))

    edge = float(row.get("Edge Rating", row.get("edge_rating", 0))) * 10

    ai = float(row.get("AI Rank", row.get("ai_rank", 0))) * 10

    sector = float(
        row.get(
            "Sector Strength",
            row.get("sector_strength", 50)
        )
    )

    rs = float(
        row.get(
            "RS Score",
            row.get("rs_score", 0)
        )
    )

    trend = str(
        row.get(
            "Trend",
            row.get("trend", "")
        )
    ).upper()

    if trend == "BULL":
        trend_score = 100

    elif trend == "SIDEWAYS":
        trend_score = 60

    else:
        trend_score = 20

    score = (

        health * 0.30 +

        edge * 0.25 +

        ai * 0.15 +

        sector * 0.10 +

        trend_score * 0.10 +

        rs * 0.10

    )

    return round(score, 2)

def build_reason(old, new, switch_edge):

    reasons = []

    if new["Optimizer Score"] > old["Optimizer Score"]:
        reasons.append(
            f"Optimizer +{round(new['Optimizer Score'] - old['Optimizer Score'],1)}"
        )

    if float(new.get("edge_rating", new.get("Edge Rating", 0))) > \
       float(old.get("edge_rating", old.get("Edge Rating", 0))):
        reasons.append("Better Edge")

    if float(new.get("ai_rank", new.get("AI Rank", 0))) > \
       float(old.get("ai_rank", old.get("AI Rank", 0))):
        reasons.append("Higher AI Rank")

    if float(new.get("sector_strength", new.get("Sector Strength", 0))) > \
       float(old.get("sector_strength", old.get("Sector Strength", 0))):
        reasons.append("Stronger Sector")

    if float(new.get("rs_score", new.get("RS Score", 0))) > \
       float(old.get("rs_score", old.get("RS Score", 0))):
        reasons.append("Higher Relative Strength")

    if float(new.get("risk_reward", 0)) >= 2.5:
        reasons.append(f"RR {new['risk_reward']}")

    if switch_edge >= 25:
        reasons.append("High Conviction")

    return " | ".join(reasons)
    
def recommendation(score):

    if score >= 90:
        return "STRONG HOLD"

    if score >= 80:
        return "HOLD"

    if score >= 65:
        return "WATCH"

    if score >= 50:
        return "REDUCE"

    return "EXIT"


def optimize_portfolio(
    enriched_portfolio,
    buy_queue,
    sector_rankings
):

    sector_strength = {
        x["Sector"]: x["Strength"]
        for x in sector_rankings
    }

    portfolio = []

    for row in enriched_portfolio:

        r = dict(row)

        r["Sector Strength"] = sector_strength.get(
            r.get("Sector"),
            50
        )

        r["Optimizer Score"] = calculate_optimizer_score(r)

        r["Recommendation"] = recommendation(
            r["Optimizer Score"]
        )

        portfolio.append(r)

    portfolio = sorted(
        portfolio,
        key=lambda x: (
            x["Optimizer Score"],
            x.get("Current Value",0)
        )
    )

    candidates = []

    for row in buy_queue:

        c = dict(row)
    
        c["Optimizer Score"] = calculate_optimizer_score(c)
    
        candidates.append(c)

    candidates = sorted(
        candidates,
        key=lambda x: x["Optimizer Score"],
        reverse=True
    )

    output = []

    n = min(len(portfolio), len(candidates))

    for i in range(n):

        old = portfolio[i]
        new = candidates[i]

        switch_edge = round(
            new["Optimizer Score"] -
            old["Optimizer Score"],
            2
        )
        
        if (
            switch_edge >= 15
            and new["Optimizer Score"] >= 80
            and float(new.get("risk_reward", 0)) >= 2
            and float(new.get("edge_rating", 0)) >= 7
        ):
            action = "SWITCH"
        
        else:
            action = old["Recommendation"]
        
        # -----------------------------------
        # Build dynamic explanation
        # -----------------------------------
        
        reason = build_reason(
            old,
            new,
            switch_edge
        )
        
        output.append({
        
            "Holding": old["Ticker"],
        
            "Holding Score": old["Optimizer Score"],
        
            "Holding Sector": old.get("Sector",""),
        
            "Candidate": new["ticker"],
        
            "Candidate Score": new["Optimizer Score"],
        
            "Candidate Sector": new.get("sector",""),
        
            "Switch Edge": switch_edge,
        
            "Risk Reward": new.get("risk_reward",""),
        
            "Recommendation": action,
        
            "Reason": reason
        
        })

    return output
