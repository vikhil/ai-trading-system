def classify_zone(edge_score, trend, rs_score):
    
    if edge_score >= 75 and trend == "UP" and rs_score >= 60:
        return "STRONG"

    elif edge_score >= 55 and trend != "DOWN":
        return "NEUTRAL"

    else:
        return "WEAK"

def can_average_down(zone, trend):

    if zone == "STRONG" and trend == "UP":
        return "YES"

    return "NO"

def generate_action(zone, edge_score, trend, rs_score, scanner_better_exists):

    # STRONG STOCKS
    if zone == "STRONG":
        if scanner_better_exists:
            return "HOLD (WATCH SWITCH)"
        return "HOLD"

    # NEUTRAL STOCKS
    if zone == "NEUTRAL":
        return "HOLD"

    # WEAK STOCKS
    if zone == "WEAK":
        if trend == "DOWN" and edge_score < 55:
             return "SELL / SWITCH"
        return "HOLD (RECOVERY WATCH)"
      
def check_switch(current_edge, best_scanner_edge):

    if best_scanner_edge >= 75 and best_scanner_edge > current_edge + 10:
        return True

    return False

def decision_engine(row, scanner_best_score):

    edge_score = row.get("Edge Score", 0)
    trend = row.get("Trend", "SIDEWAYS")
    rs_score = row.get("RS Score", 0)

    zone = classify_zone(edge_score, trend, rs_score)

    avg_down = can_average_down(zone, trend)

    switch_flag = check_switch(edge_score, scanner_best_score)

    action = generate_action(
        zone,
        edge_score,
        trend,
        rs_score,
        switch_flag
    )

    return {
        "Zone": zone,
        "Action": action,
        "AvgDownAllowed": avg_down,
        "SwitchFlag": switch_flag
    }
