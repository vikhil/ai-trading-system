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

        row["Queue Rank"] = rank

        row["Priority"] = ""

        row["Status"] = ""

        row["Comments"] = ""

        row["Replacement Candidate"] = ""

        row["Switch Score"] = ""

        row["Recommended Allocation"] = row["position_size"]

        row["Capital Required"] = round(
            float(row["cmp"]) * float(row["position_size"]),
            2,
        )
        
        # -------------------------
        # READY TO BUY
        # -------------------------

        if rank <= available_slots and capital_available > 0:

            row["Status"] = "READY TO BUY"

            row["Priority"] = "HIGH"

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
