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
    
    if rsi >= 60:
        rsi_points = 20
    elif rsi >= 50:
        rsi_points = 15
    elif rsi >= 40:
        rsi_points = 10
    elif rsi >= 30:
        rsi_points = 5
    else:
        rsi_points = 0

    # -------------------------
    # 4. Signal Score (20)
    # -------------------------
    score = float(score) if score is not None else 0
    
    if score >= 80:
        score_points = 20
    elif score >= 60:
        score_points = 15
    elif score >= 40:
        score_points = 10
    elif score >= 20:
        score_points = 5
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

            # Fix Yahoo MultiIndex issue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
    
            print(f"{ticker} Columns = {df.columns}")
            
            if df.empty:
                print(f"{ticker}: No data")
                continue

            required_cols = ["High", "Low", "Close"]

            if not all(col in df.columns for col in required_cols):
                print(f"{ticker}: Missing OHLC columns")
                continue
    
            df = calculate_atr(df)

            print(df.tail(3)[["High","Low","Close","ATR"]])

            print(
                ticker,
                "Latest ATR =",
                df["ATR"].iloc[-1]
            )

            risk_values = apply_risk_engine(
                df.iloc[-1],
                df=df
            )

            print(
                f"{ticker} Risk Values = {risk_values}"
            )

            if risk_values is None or len(risk_values) < 4:
                raise Exception("Invalid risk values")
            
            atr_risk = safe_number(risk_values.iloc[0])
            stop_loss = safe_number(risk_values.iloc[1])
            target = safe_number(risk_values.iloc[2])
            risk_reward = safe_number(risk_values.iloc[3])

            signal_data = generate_signal(df, "BULL", 0)

            if (
                signal_data is None
                or not isinstance(signal_data, (list, tuple))
                or len(signal_data) < 11
            ):
                raise Exception("Invalid signal data")
                
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

            #rs_score = safe_number(
            #    row.get("RS Score", 0)
            #)

            # ---------------------------------
            # TEMP RS SCORE DERIVED FROM SCORE
            # ---------------------------------
            
            rs_score = safe_number(score)

            health_score, health_status = calculate_health_score(
                trend,
                rs_score,
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

            print(
                f"{ticker} | Qty={qty} | Buy={buy_price} | "
                f"LTP={ltp} | Invested={qty*buy_price} | "
                f"Current={qty*ltp}"
            )
            
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

                "RS Score": round(rs_score, 2),
                
                "Trend": trend,
            
                "Score": score,
                
                "Health Score": health_score,
            
                "Health Status": health_status
            })

        except Exception as e:

            print(f"Portfolio Enrich Error for {ticker}: {e}")
        
            enriched.append({
                **row,
                "LTP": 0,
                "Invested": 0,
                "Current Value": 0,
                "P/L ₹": 0,
                "P/L %": 0,
                "ATR Risk": 0,
                "Position Risk": 0,
                "Stop Loss": 0,
                "Target": 0,
                "Risk Reward": 0,
                "RSI": 0,
                "RS Score": 0,
                "Trend": "ERROR",
                "Score": 0,
                "Health Score": 0,
                "Health Status": "ERROR"
            })

    return enriched
