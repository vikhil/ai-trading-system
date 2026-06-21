from engine.rotation_engine import (
    calculate_replacement_quality,
    calculate_switch_score,
    generate_comments,
)

from engine.portfolio_classifier import classify_bucket
from engine.sector_rotation import get_sector_strength

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
    top_picks,
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
        top_picks,
        key=calculate_replacement_quality,
        reverse=True,
    )

    current_holdings = {
        row.get("Ticker", "")
        for row in portfolio_data
    }
    
    for row in holdings_sorted:

        ticker = row.get("Ticker", "")

        health_score = safe_number(row.get("Health Score"))

        health_status = str(
            row.get("Health Status", "")
        )

        bucket = classify_bucket(row)
        
        current_value = safe_number(row.get("Current Value"))

        weight = safe_number(row.get("Portfolio Weight %"))
        
        pl_pct = safe_number(row.get("P/L %"))
        
        position_risk = safe_number(row.get("Position Risk"))

        action = "HOLD"

        priority = 0
        
        replacement = ""
        replacement_score = ""
        
        replacement_edge = ""
        
        switch_score = ""

        selected_candidate = None
        
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
            
        priority_score = (
            (100 - health_score)
            + max(0, -pl_pct)
            + (position_risk / 100)
            + (weight * 2)
        )

        priority = round(priority_score, 2)
        
        # ----------------------------
        # Assign replacement
        # ----------------------------

        if action in ["ROTATE NOW", "CONSIDER ROTATION"]:

            best_candidate = None
            best_switch_score = float("-inf")
        
            for candidate in top_sorted:

                if candidate.get("Ticker") in current_holdings:
                    continue

                candidate_bucket = classify_bucket(candidate)

                if candidate_bucket != bucket:
                    continue
    
                sector_strength = get_sector_strength(
                    candidate.get("Sector"),
                    sector_rankings
                )
                
                current_switch = (
                    calculate_switch_score(
                        row,
                        candidate,
                    )
                    + (sector_strength * 0.20)
                )
        
                if current_switch > best_switch_score:
                    best_switch_score = current_switch
                    best_candidate = candidate
        
            if best_candidate is not None and best_switch_score >= 40:
        
                selected_candidate = best_candidate
        
                replacement = selected_candidate.get("Ticker", "")
                
                if selected_candidate in top_sorted:
                    top_sorted.remove(selected_candidate)
                
                replacement_score = calculate_replacement_quality(selected_candidate)
                
                replacement_edge = safe_number(selected_candidate.get("Edge Rating"))
                switch_score = best_switch_score

        # ----------------------------
        # Concentration check
        # ----------------------------

        try:

            if selected_candidate:
        
                breakout = selected_candidate.get(
                    "Breakout",
                    "NO"
                )
        
                volume = float(
                    selected_candidate.get(
                        "Volume Spike",
                        0
                    )
                )
        
            else:
        
                breakout = "NO"
                volume = 0
        
            comments = generate_comments(
                weight,
                position_risk,
                breakout,
                volume,
                health_score
            )
        
        except Exception:
            comments = ""

        switch_score = safe_number(switch_score)
        
        if switch_score >= 45:
            priority_label = "HIGH"
        
        elif switch_score >= 30:
            priority_label = "MEDIUM"
        
        else:
            priority_label = "LOW"
        
        rotation_rows.append([
            ticker,
            health_score,
            health_status,
            current_value,
            weight,
            pl_pct,
            position_risk,
            action,
            priority,
            priority_label,
            replacement,
            replacement_score,
            replacement_edge,
            switch_score,
            round(capital_freed, 2),
            comments
        ])
        
    rotation_rows.sort(
        key=lambda x: x[8],
        reverse=True
    )
            
    rotate_count = 0
            
    for row in rotation_rows:
            
        if row[7] == "ROTATE NOW":
            
            rotate_count += 1
            
            if rotate_count > 5:
                row[7] = "MONITOR"
            
    return rotation_rows
