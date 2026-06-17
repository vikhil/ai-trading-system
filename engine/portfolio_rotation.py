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
        key=lambda x: float(x.get("Edge Rating", 0)),
        reverse=True
    )

    replacement_index = 0

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
        
        comments = ""

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
            + (position_risk / 20)
        )
        
        # ----------------------------
        # Assign replacement
        # ----------------------------

        if action in [
            "ROTATE NOW",
            "CONSIDER ROTATION"
        ]:

            if replacement_index < len(top_sorted):

                candidate = top_sorted[
                    replacement_index
                ]

                replacement = candidate["Ticker"]

                replacement_score = candidate["Score"]

                replacement_edge = candidate["Edge Rating"]

                switch_score = round(
                    float(candidate["Score"])
                    - health_score,
                    2
                )

                if switch_score < 20:
                    replacement = ""
                    replacement_score = ""
                    replacement_edge = ""
                    switch_score = ""
    
                replacement_index += 1

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

            comments_list = []
            
            if weight < 1:
                comments_list.append("CONSOLIDATE")
            
            if weight > 10 and health_score >= 80:
                comments = "TRIM PROFITS"
            
            elif weight > 10:
                comments = "OVERWEIGHT"
            
            elif position_risk > 1000:
                comments = "HIGH RISK"
            
            comments = ", ".join(comments_list)

        except:
            pass

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
