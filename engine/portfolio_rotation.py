from engine.rotation_engine import (
    calculate_replacement_quality,
    calculate_switch_score,
    generate_comments,
)

from engine.portfolio_classifier import classify_bucket
from engine.sector_rotation import get_sector_strength
from engine.rotation_engine import get_value

def safe_number(value, default=0.0):
    try:
        if value is None:
            return default

        if value == "":
            return default

        return float(value)

    except:
        return default

print("PORTFOLIO_ROTATION VERSION = SAFE_NUMBER_FIX")

def generate_rotation_plan(
    portfolio_data,
    buy_queue,
    sector_rankings
):
    rotation_rows = []

    # ----------------------------
    # Sort weakest holdings first
    # ----------------------------

    holdings_sorted = sorted(
        portfolio_data,
        key=lambda x: safe_number(
            x.get("Health Score", 0)
        ),
    )

    # ----------------------------
    # Sort best opportunities first
    # ----------------------------

    top_sorted = sorted(
        buy_queue,
        key=calculate_replacement_quality,
        reverse=True,
    )

    current_holdings = {
        row.get("Ticker", "")
        for row in portfolio_data
    }

    sector_replacement_count = {}
    MAX_REPLACEMENTS_PER_SECTOR = 2

    for row in holdings_sorted:

        ticker = row.get("Ticker", "")

        health_score = safe_number(row.get("Health Score"))

        health_status = str(
            row.get("Health Status", "")
        ).strip().upper()

        bucket = classify_bucket(row)

        qty = safe_number(row.get("Quantity"))
        
        current_value = safe_number(row.get("Current Value"))
        
        weight = safe_number(row.get("Portfolio Weight %"))
        
        pl_pct = safe_number(row.get("P/L %"))
        
        position_risk = safe_number(row.get("Position Risk"))
        
        # --------------------------------------------------
        # Skip stocks that are not active holdings
        # --------------------------------------------------
        
        if qty <= 0 or current_value <= 0:
        
            rotation_rows.append({
        
                "Ticker": ticker,
                "Health Score": health_score,
                "Health Status": health_status,
                "Current Value": current_value,
                "Portfolio Weight %": weight,
                "P/L %": pl_pct,
                "Position Risk": position_risk,
        
                "Action": "N/A",
                "Priority": 0,
                "Priority Label": "N/A",
                "Replacement": "",
                "Replacement Score": 0,
                "Replacement Edge": 0,
                "Switch Score": 0,
                "Capital Freed": 0,
                "Comments": ""
        
            })
        
            continue

        action = "HOLD"

        priority = 0
        
        replacement = ""
        replacement_score = 0.0
        
        replacement_edge = 0.0
        
        switch_score = 0.0

        selected_candidate = None
        
        # EXIT immediately
        if health_status in {"URGENT_EXIT", "EXIT_CANDIDATE"}:
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

        MIN_ROTATION_VALUE = 5000

        if capital_freed < MIN_ROTATION_VALUE:
            action = "MONITOR"
    
        # ----------------------------
        # Assign replacement
        # ----------------------------

        if action in ["ROTATE NOW", "CONSIDER ROTATION"]:

            best_candidate = None
            best_switch_score = float("-inf")
        
            for candidate in top_sorted:
                
                candidate_ticker = get_value(
                    candidate,
                    "Ticker",
                    "ticker"
                )

                replacement_sector = get_value(
                    selected_candidate,
                    "Sector",
                    "sector"
                )
                
                sector_replacement_count[replacement_sector] = (
                    sector_replacement_count.get(replacement_sector, 0) + 1
                )

                candidate_sector = get_value(
                    candidate,
                    "Sector",
                    "sector"
                )
                
                if sector_replacement_count.get(candidate_sector, 0) >= MAX_REPLACEMENTS_PER_SECTOR:
                    continue
    
                if candidate_ticker in current_holdings:
                    continue

                candidate_bucket = classify_bucket(candidate)

                sector_bonus = 0

                breakout = str(
                    get_value(
                        candidate,
                        "Breakout",
                        "breakout",
                        default="NO"
                    )
                ).upper()
                
                if breakout == "YES":
                    sector_bonus += 5

                volume_spike = safe_number(
                    get_value(
                        candidate,
                        "Volume Spike",
                        "volume_spike"
                    )
                )
                
                if volume_spike >= 2:
                    sector_bonus += 3
    
                # Prefer same bucket
                if candidate_bucket == bucket:
                    sector_bonus += 8
                
                # Prefer same sector
                if get_value(candidate, "Sector", "sector") == row.get("Sector"):
                    sector_bonus += 5

                # Reject weak replacement candidates
                if safe_number(
                        get_value(candidate, "Score", "score")
                    ) < 75:
                    continue
                
                if safe_number(
                        get_value(candidate, "Edge Rating", "edge_rating")
                    ) < 7:
                    continue
                
                if safe_number(
                        get_value(candidate, "Risk Reward", "risk_reward")
                    ) < 1.5:
                    continue
                
                if safe_number(
                        get_value(candidate, "RS Score", "rs_score")
                    ) < 15:
                    continue
    
                sector_strength = get_sector_strength(
                    get_value(candidate, "Sector", "sector"),
                    sector_rankings
                )
                
                current_switch = (
                    calculate_switch_score(
                        row,
                        candidate,
                    )
                    + (sector_strength * 0.20)
                    + sector_bonus
                )

                if current_switch < 60:
                    continue
    
                if current_switch > best_switch_score:

                    print(
                        "NEW BEST:",
                        ticker,
                        "->",
                        get_value(candidate, "Ticker", "ticker"),
                        current_switch
                    )
                    
                    best_switch_score = current_switch
                    best_candidate = candidate
        
            if best_candidate is not None:
                
                print(
                    "FINAL SELECTED:",
                    ticker,
                    "->",
                    get_value(best_candidate, "Ticker", "ticker"),
                    best_switch_score
                )
                
                selected_candidate = best_candidate
        
                replacement = get_value(
                    selected_candidate,
                    "Ticker",
                    "ticker"
                )

                current_holdings.add(replacement)
                
                if selected_candidate in top_sorted:
                    top_sorted.remove(selected_candidate)
                
                replacement_score = calculate_replacement_quality(selected_candidate)
                
                replacement_edge = safe_number(
                    get_value(
                        selected_candidate,
                        "Edge Rating",
                        "edge_rating",
                    )
                )
                switch_score = safe_number(best_switch_score, 0.0)
                
        priority_score = (
            (100 - health_score)
            + max(0, -pl_pct)
            + (position_risk / 100)
            + (weight * 2)
            + min(30, switch_score * 0.25)
        )

        priority = round(priority_score, 2)
                
        # ----------------------------
        # Concentration check
        # ----------------------------

        try:

            if selected_candidate:
        
                breakout = str(
                    get_value(
                        selected_candidate,
                        "Breakout",
                        "breakout",
                        default="NO",
                    )
                ).upper()
        
                volume = float(
                    get_value(
                        selected_candidate,
                        "Volume Spike",
                        "volume_spike",
                    )
                )
        
            else:
        
                breakout = "NO"
                volume = 0
        
            comments = generate_comments(
                health_score,
                weight,
                position_risk,
                selected_candidate,
                switch_score
            )
            
        except Exception:
            comments = ""

        switch_score = float(switch_score or 0)
        switch_score = safe_number(switch_score, 0.0)
        
        if action == "ROTATE NOW":

            if switch_score >= 55:
                action = "ROTATE NOW"
        
            elif switch_score >= 40:
                action = "CONSIDER ROTATION"

            else:
                action = "MONITOR"

        elif action == "CONSIDER ROTATION":

            if switch_score < 35:
                action = "MONITOR"
    
        if priority >= 180:
            priority_label = "HIGH"
        
        elif priority >= 130:
            priority_label = "MEDIUM"
        
        else:
            priority_label = "LOW"
            
        rotation_rows.append({
            "Ticker": ticker,
            "Health Score": health_score,
            "Health Status": health_status,
            "Current Value": current_value,
            "Portfolio Weight %": weight,
            "P/L %": pl_pct,
            "Position Risk": position_risk,
            "Action": action,
            "Priority": priority,
            "Priority Label": priority_label,
            "Replacement": replacement,
            "Replacement Score": replacement_score,
            "Replacement Edge": replacement_edge,
            "Switch Score": switch_score,
            "Capital Freed": round(capital_freed, 2),
            "Comments": comments,
        })
        
    rotation_rows.sort(
        key=lambda x: x["Priority"],
        reverse=True,
    )
            
    rotate_count = 0

    for row in rotation_rows:
    
        if row["Action"] == "ROTATE NOW":
    
            rotate_count += 1
    
            if rotate_count > 5:
                row["Action"] = "MONITOR"
    
    return rotation_rows
