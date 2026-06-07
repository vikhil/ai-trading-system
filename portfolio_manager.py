import yfinance as yf
import pandas as pd

from signals import (
    generate_signal,
    calculate_atr,
    apply_risk_engine
)

def calculate_health_score(trend, rs_score, rsi, score):

    # -------------------------
    # 1. Trend Score (30)
    # -------------------------
    trend_points = 0

    if str(trend).lower() in ["bullish", "uptrend", "strong"]:
        trend_points = 30
    elif str(trend).lower() in ["neutral", "sideways"]:
        trend_points = 15
    else:
        trend_points = 0

    # -------------------------
    # 2. Relative Strength (30)
    # -------------------------
    rs_score = float(rs_score) if rs_score is not None else 0

    if rs_score >= 50:
        rs_points = 30
    elif rs_score >= 25:
        rs_points = 20
    elif rs_score >= 10:
        rs_points = 10
    else:
        rs_points = 0

    # -------------------------
    # 3. RSI Quality (20)
    # -------------------------
    rsi = float(rsi) if rsi is not None else 0

    if 55 <= rsi <= 75:
        rsi_points = 20
    elif 50 <= rsi < 55:
        rsi_points = 15
    elif 40 <= rsi < 50:
        rsi_points = 10
    else:
        rsi_points = 0

    # -------------------------
    # 4. Signal Score (20)
    # -------------------------
    score = float(score) if score is not None else 0

    if score >= 80:
        score_points = 20
    elif score >= 70:
        score_points = 15
    elif score >= 60:
        score_points = 10
    else:
        score_points = 0

    # -------------------------
    # FINAL SCORE
    # -------------------------
    health_score = trend_points + rs_points + rsi_points + score_points

    # -------------------------
    # STATUS
    # -------------------------
    if health_score >= 80:
        health_status = "STRONG"
    elif health_score >= 60:
        health_status = "HEALTHY"
    elif health_score >= 40:
        health_status = "WEAK"
    else:
        health_status = "EXIT_CANDIDATE"

    return health_score, health_status
    
def enrich_portfolio(portfolio_data):

    enriched = []

    for row in portfolio_data:

        ticker = str(
            row.get("Ticker", "")
        ).strip()

        if not ticker:
            continue

        try:

            df = yf.download(
                ticker,
                period="6mo",
                interval="1d",
                auto_adjust=True,
                progress=False
            )

            if df.empty:
                continue
            
            df = calculate_atr(df)

            signal_data = generate_signal(
                df,
                "BULL",
                0
            )

            (
                ltp,
                rsi,
                ema20,
                ema50,
                trend,
                score,
                signal,
                avg_volume,
                current_volume,
                volume_spike,
                breakout
            ) = signal_data

            health_score, health_status = calculate_health_score(
                trend,
                row.get("RS Score", 0),
                rsi,
                score
            )

            row["Health Score"] = health_score
            row["Health Status"] = health_status
            
            buy_price = float(
                row.get("Buy Price", 0)
            )

            qty = float(
                row.get("Quantity", 0)
            )

            pl_pct = 0

            if buy_price > 0:
                pl_pct = ((ltp - buy_price)/ buy_price) * 100
            
            enriched.append({
                **row,
                "LTP": round(ltp,2),
                "P/L %": round(pl_pct,2),
                "RSI": round(rsi,2),
                "Trend": trend,
                "Score": score,
                "Health Score": health_score,
                "Health Status": health_status
            })

        except Exception:
            enriched.append(row)

    return enriched
