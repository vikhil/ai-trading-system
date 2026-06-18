def generate_rotation_plan(portfolio_data, top_picks):

    rotation_rows = []

    # ----------------------------
    # Sort weakest holdings first
    # ----------------------------

    holdings_sorted = sorted(
        portfolio_data,
        key=lambda x: float(x.get("Health Score", 0)),
    )

    # ----------------------------
    # Sort best opportunities first
    # ----------------------------

    top_sorted = sorted(
        top_picks,
        key=lambda x: (
            float(x.get("Score", 0)),
            float(x.get("Edge Rating", 0)),
            float(x.get("RS Score", 0)),
            float(x.get("Risk Reward", 0)),
            float(x.get("Volume Spike", 0))
        ),
        reverse=True
    )

    for row in holdings_sorted:

        ticker = row.get("Ticker", "")

        health_score = float(
            row.get("Health Score", 0)
        )

        health_status = str(
            row.get("Health Status", "")
        )

        current_value = float(
            row.get("Current Value", 0)
        )

        weight = float(
            row.get("Portfolio Weight %", 0)
        )
        
        pl_pct = float(
            row.get("P/L %", 0)
        )
        
        position_risk = float(
            row.get("Position Risk", 0)
        )

        action = "HOLD"

        priority = 0
        
        replacement = ""
        replacement_score = ""
        
        replacement_edge = ""
        
        switch_score = ""
        
        #comments = ""
        comments_list = []
        
        # EXIT immediately
        if (
            health_status == "EXIT_CANDIDATE"
            and current_value > 0
        ):
            action = "ROTATE NOW"
        
        # Weak stocks
        elif health_status == "WEAK":
            action = "CONSIDER ROTATION"
        
        # Healthy & Strong
        else:
            action = "HOLD"

        capital_freed = 0

        if action in ["ROTATE NOW", "CONSIDER ROTATION"]:
            capital_freed = current_value
            
        priority = (
            (100 - health_score)
            + abs(pl_pct)
            + (position_risk / 100)
        )
        
        # ----------------------------
        # Assign replacement
        # ----------------------------

        if action in ["ROTATE NOW", "CONSIDER ROTATION"]:

            best_candidate = None
            best_switch_score = -9999
        
            for candidate in top_sorted:
        
                candidate_score = float(candidate.get("Score", 0))
                candidate_edge = float(candidate.get("Edge Rating", 0))
                candidate_rs = float(candidate.get("RS Score", 0))
                candidate_rr = float(candidate.get("Risk Reward", 0))
                candidate_volume = float(candidate.get("Volume Spike", 0))
        
                current_switch = round(
                    (candidate_score - health_score)
                    + (candidate_edge * 2)
                    + (candidate_rs / 5)
                    + (candidate_rr * 3)
                    + (candidate_volume / 25),
                    2
                )
        
                if current_switch > best_switch_score:
                    best_switch_score = current_switch
                    best_candidate = candidate
        
            if best_candidate is not None and best_switch_score >= 40:
        
                candidate = best_candidate
        
                replacement = candidate["Ticker"]

                top_sorted.remove(candidate)
                
                replacement_score = candidate["Score"]
                replacement_edge = candidate["Edge Rating"]
                switch_score = best_switch_score

        # ----------------------------
        # Concentration check
        # ----------------------------

        try:

            weight = float(
                row.get(
                    "Portfolio Weight %",
                    0
                )
            )

            if weight < 1:
                comments_list.append("CONSOLIDATE")
            
            if weight > 10:
                if health_score >= 80:
                    comments_list.append("TRIM PROFITS")
                else:
                    comments_list.append("OVERWEIGHT")
            
            if position_risk > 1000:
                comments_list.append("HIGH RISK")

            # Candidate quality notes

            if replacement != "":
            
                if candidate.get("Trend", "") == "Bullish":
                    comments_list.append("STRONG REPLACEMENT")
            
                if candidate.get("Breakout", "") == "YES":
                    comments_list.append("BREAKOUT")
            
                if candidate.get("Volume Spike", 0) >= 2:
                    comments_list.append("VOLUME SURGE")
        except:
            pass
            
        comments = ", ".join(comments_list)
        
        rotation_rows.append([
            ticker,
            health_score,
            health_status,
            current_value,
            weight,
            pl_pct,
            position_risk,
            action,
            round(priority, 2),
            replacement,
            replacement_score,
            replacement_edge,
            switch_score,
            round(capital_freed, 2),
            comments
        ])

    return rotation_rows
