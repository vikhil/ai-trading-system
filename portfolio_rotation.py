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

        action = "HOLD"
        replacement = ""
        replacement_score = ""
        replacement_edge = ""
        comments = ""

        # ----------------------------
        # EXIT
        # ----------------------------

        if (
            health_status == "EXIT_CANDIDATE"
            or health_score < 20
        ):
            action = "EXIT"

        # ----------------------------
        # REDUCE
        # ----------------------------

        elif health_score < 50:
            action = "REDUCE"

        # ----------------------------
        # HOLD
        # ----------------------------

        else:
            action = "HOLD"

        # ----------------------------
        # Assign replacement
        # ----------------------------

        if action in ["EXIT", "REDUCE"]:

            if replacement_index < len(top_sorted):

                candidate = top_sorted[
                    replacement_index
                ]

                replacement = candidate["Ticker"]

                replacement_score = candidate["Score"]

                replacement_edge = candidate["Edge Rating"]

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

            if weight < 1:
                comments = "CONSOLIDATE"

        except:
            pass

        rotation_rows.append([
            ticker,
            health_score,
            health_status,
            current_value,
            action,
            replacement,
            replacement_score,
            replacement_edge,
            comments
        ])

    return rotation_rows
