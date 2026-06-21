import yfinance as yf
import pandas as pd

from signals import (
    generate_signal,
    calculate_atr,
    apply_risk_engine
)

import math
from engine.sector_health import calculate_sector_health

def calculate_health_score(
    trend,
    rs_score,
    score,
    risk_reward,
    breakout,
    volume_spike,
    pl_pct,
    position_risk
):

    health = 0

    # -------------------------
    # Trend (20)
    # -------------------------

    trend = str(trend).lower()

    if trend in ["bullish", "uptrend", "strong"]:
        health += 20

    elif trend in ["neutral", "sideways"]:
        health += 10

    # -------------------------
    # Relative Strength (20)
    # -------------------------

    rs_score = safe_number(rs_score)

    if rs_score >= 30:
        health += 20

    elif rs_score >= 20:
        health += 15

    elif rs_score >= 10:
        health += 10

    # -------------------------
    # Scanner Score (20)
    # -------------------------

    score = safe_number(score)

    if score >= 80:
        health += 20

    elif score >= 60:
        health += 15

    elif score >= 40:
        health += 10

    # -------------------------
    # P/L Contribution (10)
    # -------------------------

    pl_pct = safe_number(pl_pct)

    if pl_pct >= 20:
        health += 10

    elif pl_pct >= 10:
        health += 8

    elif pl_pct >= 0:
        health += 5

    elif pl_pct >= -10:
        health += 3

    # -------------------------
    # Position Risk (10)
    # -------------------------

    position_risk = safe_number(position_risk)

    if position_risk <= 500:
        health += 10

    elif position_risk <= 1000:
        health += 7

    elif position_risk <= 2000:
        health += 4

    # -------------------------
    # Volume + Breakout (20)
    # -------------------------

    if str(breakout).upper() == "YES":
        health += 10

    volume_spike = safe_number(volume_spike)

    if volume_spike >= 2:
        health += 10

    elif volume_spike >= 1.5:
        health += 6

    elif volume_spike >= 1.2:
        health += 3

    health = round(health)

    if health >= 85:
        status = "ELITE"

    elif health >= 70:
        status = "STRONG"

    elif health >= 55:
        status = "HEALTHY"

    elif health >= 40:
        status = "WEAK"

    elif health >= 25:
        status = "EXIT_CANDIDATE"

    else:
        status = "URGENT_EXIT"

    return health, status

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
            print(f"START DOWNLOAD -> {ticker}")
            
            df = yf.download(
                ticker,
                period="6mo",
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=False
            )
            print(f"END DOWNLOAD -> {ticker}")
            
            if df is None or df.empty:
                print(f"{ticker}: Download returned empty")
                continue
    
            # Fix Yahoo MultiIndex issue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # REMOVE Yahoo rows containing NaN prices
            df = df.dropna(
                subset=["High", "Low", "Close"]
            )
            
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

            last_valid_row = (
                df.dropna(
                    subset=["High", "Low", "Close", "ATR"]
                ).iloc[-1]
            )
            
            risk_values = apply_risk_engine(
                last_valid_row,
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

            print(
                f"{ticker} AFTER EXTRACTION -> "
                f"ATR={atr_risk}, "
                f"SL={stop_loss}, "
                f"TARGET={target}, "
                f"RR={risk_reward}"
            )
            
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
                breakout,
                trend_persistence,
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
            
            print(
                f"{ticker} AFTER EXTRACTION -> "
                f"ATR={atr_risk}, "
                f"SL={stop_loss}, "
                f"TARGET={target}, "
                f"RR={risk_reward}"
            )
            
            atr_risk = 0 if pd.isna(atr_risk) else float(atr_risk)

            position_risk = atr_risk * qty

            print(
                f"{ticker} AFTER POSITION RISK -> "
                f"ATR={atr_risk}, "
                f"POS={position_risk}"
            )
            
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

            health_score, health_status = calculate_health_score(
                trend=trend,
                rs_score=rs_score,
                score=score,
                risk_reward=risk_reward,
                breakout=breakout,
                volume_spike=volume_spike,
                pl_pct=pl_pct,
                position_risk=position_risk
            )
            
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

            print(
                f"{ticker} FINAL VALUES -> "
                f"ATR={atr_risk}, "
                f"PosRisk={position_risk}, "
                f"SL={stop_loss}, "
                f"Target={target}, "
                f"RR={risk_reward}"
            )

            print(f"{ticker} APPENDING SUCCESS ROW")
            
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

                "Trend Persistence": trend_persistence,
            
                "Score": score,
                
                "Health Score": health_score,
            
                "Health Status": health_status,

                "Sector Health Bonus": 0
            })

        except Exception as e:
            print(f"{ticker} APPENDING ERROR ROW")
            print(f"Portfolio Enrich Error for {ticker}: {e}")

            print(
                f"{ticker} FINAL APPEND -> "
                f"ATR={atr_risk}, "
                f"POS={position_risk}, "
                f"SL={stop_loss}, "
                f"TARGET={target}, "
                f"RR={risk_reward}"
            )
            
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
                "Health Status": "ERROR",
                "Sector Health Bonus": 0
            })
    # --------------------------------
    # APPLY SECTOR HEALTH
    # --------------------------------
    
    sector_health = calculate_sector_health(enriched)

    print("\nSector Health Summary")

    for sector, values in sector_health.items():
        print(
            sector,
            values["Average Health"],
            values["Bonus"]
        )
    
    for row in enriched:
    
        sector = row.get("Sector","UNKNOWN")
    
        bonus = sector_health.get(
            sector,
            {}
        ).get(
            "Bonus",
            0
        )
    
        new_health = min(
            100,
            max(
                0,
                row["Health Score"] + bonus
            )
        )
    
        row["Health Score"] = round(new_health)

        row["Sector Health Bonus"] = bonus
    
        if new_health >= 85:
            row["Health Status"] = "ELITE"
    
        elif new_health >= 70:
            row["Health Status"] = "STRONG"
    
        elif new_health >= 55:
            row["Health Status"] = "HEALTHY"
    
        elif new_health >= 40:
            row["Health Status"] = "WEAK"
    
        elif new_health >= 25:
            row["Health Status"] = "EXIT_CANDIDATE"
    
        else:
            row["Health Status"] = "URGENT_EXIT"
        
    return enriched
