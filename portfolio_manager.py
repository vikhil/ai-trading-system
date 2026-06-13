import yfinance as yf
import pandas as pd

from signals import (
    generate_signal,
    calculate_atr,
    apply_risk_engine
)

import math

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

def safe_number(value, default=0):

    try:
        value = float(value)

        if math.isnan(value):
            return default

        if math.isinf(value):
            return default

        return value

    except:
        return default
        
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

            risk_values = apply_risk_engine(
                df.iloc[-1],
                df=df
            )
            
            atr_risk = safe_number(risk_values.iloc[0])
            stop_loss = safe_number(risk_values.iloc[1])
            target = safe_number(risk_values.iloc[2])
            risk_reward = safe_number(risk_values.iloc[3])

            signal_data = generate_signal(df, "BULL", 0)

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
            
            ltp = safe_number(ltp)
            rsi = safe_number(rsi)
            
            ema20 = safe_number(ema20)
            ema50 = safe_number(ema50)
            
            score = safe_number(score)
            
            avg_volume = safe_number(avg_volume)
            current_volume = safe_number(current_volume)
            
            volume_spike = safe_number(volume_spike)
            breakout = str(breakout)
            
            if ltp <= 0:
                continue
    
            health_score, health_status = calculate_health_score(
                trend,
                row.get("RS Score", 0),
                rsi,
                score
            )
            
            buy_price = pd.to_numeric(
                row.get("Buy Price", 0),
                errors="coerce"
            )
            
            qty = pd.to_numeric(
                row.get("Quantity", 0),
                errors="coerce"
            )
            
            buy_price = 0 if pd.isna(buy_price) else float(buy_price)
            qty = 0 if pd.isna(qty) else float(qty)
            atr_risk = 0 if pd.isna(atr_risk) else float(atr_risk)

            position_risk = atr_risk * qty
            
            invested = qty * buy_price

            current_value = qty * ltp
            
            pl_rupees = current_value - invested

            pl_pct = 0

            if buy_price > 0:
                pl_pct = ((ltp - buy_price) / buy_price) * 100

            invested = safe_number(invested)
            current_value = safe_number(current_value)
            
            pl_rupees = safe_number(pl_rupees)
            pl_pct = safe_number(pl_pct)
            
            position_risk = safe_number(position_risk)
            
            health_score = int(safe_number(health_score))

            if any([
                math.isnan(x) if isinstance(x, float) else False
                for x in [
                    ltp,
                    invested,
                    current_value,
                    pl_rupees,
                    pl_pct,
                    atr_risk,
                    position_risk
                ]
            ]):
                print(f"BAD VALUE FOUND: {ticker}")

            stop_loss = safe_number(stop_loss)
            target = safe_number(target)
            risk_reward = safe_number(risk_reward)

            enriched.append({
                **row,
            
                "LTP": round(ltp, 2),
            
                "Invested": round(invested, 2),
            
                "Current Value": round(current_value, 2),
            
                "P/L ₹": round(pl_rupees, 2),
            
                "P/L %": round(pl_pct, 2),

                "ATR Risk": round(atr_risk, 2),
            
                "Position Risk": round(position_risk, 2),

                "Stop Loss": round(stop_loss, 2),

                "Target": round(target, 2),
            
                "Risk Reward": round(risk_reward, 2),
                
                "RSI": round(rsi, 2),
            
                "Trend": trend,
            
                "Score": score,
            
                "Health Score": health_score,
            
                "Health Status": health_status
            })

        except Exception as e:
            print(f"Portfolio Enrich Error for {ticker}: {e}")
            enriched.append(row)

    return enriched
