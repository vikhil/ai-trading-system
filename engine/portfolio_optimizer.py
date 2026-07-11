import pandas as pd


def calculate_optimizer_score(row):

    health = float(row.get("Health Score", 0))
    edge = float(row.get("Edge Rating", 0)) * 10
    ai = float(row.get("AI Rank", 0)) * 10
    sector = float(row.get("Sector Strength", 50))
    rs = float(row.get("RS Score", 0))

    trend = str(row.get("Trend", "")).upper()

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


def recommendation(score):

    if score >= 90:
        return "ADD"

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
        key=lambda x: x["Optimizer Score"]
    )

    candidates = []

    for row in buy_queue:

        c = dict(row)

        score = (
            float(c.get("score", 0)) * 0.50 +
            float(c.get("edge_rating", 0)) * 5 +
            float(c.get("ai_rank", 0)) * 5
        )

        c["Optimizer Score"] = round(score, 2)

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
            switch_edge >= 20 and
            float(new.get("edge_rating", 0)) >= 7
        ):
            action = "SWITCH"

        else:
            action = old["Recommendation"]

        output.append({

            "Holding":
                old["Ticker"],

            "Holding Score":
                old["Optimizer Score"],

            "Candidate":
                new["ticker"],

            "Candidate Score":
                new["Optimizer Score"],

            "Switch Edge":
                switch_edge,

            "Action":
                action

        })

    return output
