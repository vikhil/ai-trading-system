def build_opportunity_queue(
    results_sorted,
    open_tickers,
    available_slots,
    capital_available
):
    """
    Builds a ranked opportunity queue.

    Returns one list containing BOTH

    Immediate BUY candidates

    Future BUY Queue candidates
    """

    queue = []

    rank = 1

    for r in results_sorted:

        if r["trade_action"] not in ["BUY", "STRONG_BUY"]:
            continue

        if r["ticker"].upper() in open_tickers:
            continue

        row = r.copy()

        row["Queue Rank"] = rank

        if rank <= available_slots and capital_available > 0:

            row["Immediate Buy"] = "YES"

            row["Reason"] = "Capital Available"

        else:

            row["Immediate Buy"] = "NO"

            row["Reason"] = "Portfolio Full"

        row["Recommended Allocation"] = row["position_size"]

        row["Comments"] = ""

        queue.append(row)

        rank += 1

    return queue
