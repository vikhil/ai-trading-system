import pandas as pd

def calculate_position_size(capital, atr_risk, risk_per_trade=0.01):
    if atr_risk <= 0 or pd.isna(atr_risk):
        return 0

    risk_amount = capital * risk_per_trade
    qty = risk_amount / atr_risk

    return max(0, round(qty, 2))


def calculate_edge_score(score, risk_reward, rs_score, volume_spike, breakout, regime):

    if pd.isna(score) or score < 60:
        return 0

    edge = 0

    score = float(score)
    risk_reward = float(risk_reward) if pd.notna(risk_reward) else 0
    rs_score = float(rs_score) if pd.notna(rs_score) else 0
    volume_spike = float(volume_spike) if pd.notna(volume_spike) else 0

    # 1. Signal strength
    if score >= 80:
        edge += 5
    elif score >= 75:
        edge += 4
    elif score >= 70:
        edge += 3
    elif score >= 65:
        edge += 2
    elif score >= 60:
        edge += 1

    # 2. Risk-reward quality
    if risk_reward >= 3:
        edge += 2
    elif risk_reward >= 2:
        edge += 1

    # 3. Relative strength
    if rs_score >= 50:
        edge += 2
    elif rs_score >= 25:
        edge += 1

    # 4. Volume + breakout
    if volume_spike >= 1.5 and str(breakout).upper() == "YES":
        edge += 2
    elif volume_spike >= 1.2:
        edge += 1

    base_score = edge * 10

    return min(base_score, 100)


def calculate_edge_rating(edge_score):
    edge_score = float(edge_score) if pd.notna(edge_score) else 0

    if edge_score >= 90:
        return 9
    elif edge_score >= 80:
        return 8
    elif edge_score >= 70:
        return 7
    elif edge_score >= 60:
        return 6
    elif edge_score >= 50:
        return 5
    elif edge_score >= 40:
        return 4
    elif edge_score >= 30:
        return 3
    elif edge_score >= 20:
        return 2
    elif edge_score >= 10:
        return 1
    else:
        return 0


def get_trade_action(edge_rating):
    if edge_rating >= 8:
        return "STRONG_BUY"
    elif edge_rating == 7:
        return "BUY"
    elif edge_rating >= 5:
        return "WATCH"
    else:
        return "IGNORE"
