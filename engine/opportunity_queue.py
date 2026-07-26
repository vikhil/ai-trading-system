def build_opportunity_queue(
    results_sorted,
    open_tickers,
    available_slots,
    capital_available
):

    queue = []

    rank = 1

    for r in results_sorted:

        if r["trade_action"] not in ["BUY", "STRONG_BUY"]:
            continue

        if r["ticker"].upper() in open_tickers:
            continue

        row = r.copy()

        row["Optimizer Score"] = round(

            row["score"] * 0.30 +
        
            row["edge_rating"] * 8 +
        
            row["ai_rank"] * 5 +
        
            row["sector_strength"] * 0.20 +
        
            row["rs_score"] * 0.20,
        
            2
        
        )
        

        row["Queue Rank"] = rank

        row["Priority"] = ""

        row["Status"] = ""

        row["Comments"] = ""

        row["Replacement Candidate"] = ""

        row["Replacement Holding"] = ""

        row["Switch Edge"] = ""

        row["Optimizer Score"] = ""
        
        row["Risk Reward"] = row["risk_reward"]

        row["Recommended Allocation"] = row["position_size"]

        row["Capital Required"] = round(
            float(row["cmp"]) * float(row["position_size"]),
            2
        )
        
        # -------------------------
        # READY TO BUY
        # -------------------------

        if rank <= available_slots and capital_available > 0:

            row["Status"] = "READY TO BUY"

            if row["edge_rating"] >= 9:

                row["Priority"] = "VERY HIGH"
            
            elif row["edge_rating"] >= 8:
            
                row["Priority"] = "HIGH"
            
            elif row["edge_rating"] >= 7:
            
                row["Priority"] = "MEDIUM"
            
            else:
            
                row["Priority"] = "LOW"

            row["Comments"] = "Capital available immediately"

        # -------------------------
        # WAITING
        # -------------------------

        else:

            row["Status"] = "WAITING FOR CAPITAL"

            row["Priority"] = "HIGH"

            row["Comments"] = "Portfolio full"

        queue.append(row)

        rank += 1

    return queue
