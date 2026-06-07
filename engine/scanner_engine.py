import pandas as pd

from signals import (
    calculate_atr,
    add_volume_and_breakout,
    apply_risk_engine
)

from engine.risk_engine import (
    calculate_position_size,
    calculate_edge_score,
    calculate_edge_rating,
    get_trade_action
)

def run_scanner(
    results_map,
    open_tickers,
    regime,
    nifty_return,
    CAPITAL,
    RISK_PER_TRADE,
    DEBUG_LOGS,
    failed_logs,
    safe_generate_signal,
    log_scan,
    log_signal
):
    
def analyze_ticker(
    ticker,
    df,
    regime,
    nifty_return,
    capital,
    risk_per_trade,
    safe_generate_signal
):

# ----------------------------
# ANALYSIS
# ----------------------------
results = []
results_sorted = []
buy_candidates = []
watch_candidates = []

for ticker, df, error in results_map:
    error_reason = None
    
    try:
        
        # ----------------------------
        # EXISTING POSITIONS FILTER (PORTFOLIO SAFETY)
        # ----------------------------
        if ticker.upper() in open_tickers:
            if DEBUG_LOGS:
                print(f"SKIP: {ticker} already in OPEN portfolio")
            continue
            
        #df, error = safe_download(ticker)
    
        # =========================
        # HARD DATAFRAME NORMALIZATION FIX
        # =========================
        
        if error:
            failed_logs.append([ticker, "DOWNLOAD_FAILED", str(error)])
            continue
        
        if df is None:
            failed_logs.append([ticker, "EMPTY_DATA", "No data returned"])
            continue
        
        # 1. Flatten MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 2. Remove duplicate columns
        df = df.loc[:, ~df.columns.duplicated()]
        
        # 3. Keep only OHLCV columns
        required_cols = ["Open", "High", "Low", "Close", "Volume"]
        
        df = df[[col for col in required_cols if col in df.columns]]
        df = df.dropna(subset=["Close"])
        
        # 4. Convert all columns to numeric
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # 5. Drop bad rows
        df = df.dropna()
        
        if len(df) < 60:
            print(f"SKIP: {ticker} REASON: INSUFFICIENT_DATA {len(df)}")

            failed_logs.append([
                ticker,
                "INSUFFICIENT_DATA",
                str(len(df))
            ])
        
            continue
            
        # 6. Final safety check
        if df.empty:
            failed_logs.append([
                ticker,
                "EMPTY_AFTER_NORMALIZATION",
                "DataFrame empty after cleanup"
            ])
            continue
        
        # ----------------------------
        # ATR CALCULATION AND VOLUME/BREAKOUT
        # ----------------------------
        
        df = calculate_atr(df)
        df = add_volume_and_breakout(df)
        
        row = df.iloc[-1]
        
        avg_volume = row.get("Avg Volume", 0)
        volume_spike = row.get("Volume Spike", 0)
        breakout = row.get("Breakout", 0)

        raw_volume = row.get("Volume", 0)
        atr_indicator = row.get("ATR", 0)

        # ---------------------------
        # FILTERS (EARLY EXIT CONDITIONS)
        # ---------------------------
        
        # Safety conversions (important because yfinance + pandas can return NaN/Series)
        current_volume = float(raw_volume) if pd.notna(raw_volume) else 0
        atr_indicator = float(atr_indicator) if pd.notna(atr_indicator) else 0
        
        # B) Liquidity filter
        if current_volume <= 0:
            print(f"SKIP: {ticker} REASON: INVALID_VOLUME {current_volume}")
            continue

        if current_volume < avg_volume * 0.5:   # relaxed threshold
            log_scan(f"{ticker} skipped - LOW_VOLUME {current_volume}")
            
            failed_logs.append([
                ticker,
                "LOW_VOLUME",
                str(current_volume)
            ])
        
            continue
    
        # C) ATR filter
        if atr_indicator <= 0:
            print(f"SKIP: {ticker} REASON: BAD_ATR {atr_indicator}")
            continue
        
        # =========================
        # FINAL DATA NORMALIZATION FIX
        # =========================
        
        stock_close = df["Close"].dropna()

        if len(stock_close) < 2:
            continue
    
        # ----------------------------
        # BASIC RETURNS (RS LOGIC)
        # ----------------------------
        
        stock_return = float((stock_close.iloc[-1] / stock_close.iloc[0]) - 1)

        rs_score = (stock_return - nifty_return)
        rs_score = rs_score * 100
        rs_score = max(min(rs_score, 100), -100)
            
        if rs_score >= 50:
            rs_rank = "ELITE"
        elif rs_score >= 25:
            rs_rank = "STRONG"
        elif rs_score >= 10:
            rs_rank = "AVERAGE"
        else:
            rs_rank = "WEAK"
    
        # ----------------------------
        # SIGNAL ENGINE
        # ----------------------------
        
        try:
            signal_data = safe_generate_signal(df, regime, rs_score, ticker)

            if signal_data is None:
                failed_logs.append([ticker, "SIGNAL_FAILED", "generate_signal returned None"])
                continue
        
        except Exception as e:
            failed_logs.append([ticker, "SIGNAL_EXCEPTION", str(e)])
            continue

        if signal_data is None:
            continue

        (
            cmp,
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

        if DEBUG_LOGS:
            log_signal(f"{ticker} signal generated successfully")
    
        rsi = float(rsi) if pd.notna(rsi) else 0
        ema20 = float(ema20) if pd.notna(ema20) else 0
        ema50 = float(ema50) if pd.notna(ema50) else 0
        
        # ----------------------------
        # ATR RISK ENGINE
        # ----------------------------

        last_row = df.iloc[-1]

        risk_values = apply_risk_engine(last_row, df=df)
        
        atr_risk = round(float(risk_values.iloc[0]), 2)
        stop_loss = round(float(risk_values.iloc[1]), 2)
        target = round(float(risk_values.iloc[2]), 2)        
        risk_reward = float(risk_values.iloc[3]) if pd.notna(risk_values.iloc[3]) else 0

        position_size = calculate_position_size(CAPITAL, atr_risk, RISK_PER_TRADE)
        
        #if risk_reward < 1.5:
            #print(f"SKIP: {ticker} REASON: LOW_RR {risk_reward}")
            #continue

        if pd.isna(risk_reward):
            print(f"SKIP: {ticker} REASON: RR_NAN")
            continue

        if risk_reward < 1.0:   # relax temporarily
            print(f"SKIP: {ticker} REASON: LOW_RR {risk_reward}")

            failed_logs.append([
                ticker,
                "LOW_RR",
                str(risk_reward)
            ])
        
            continue
            
        # ----------------------------
        # DEBUG LOGGING
        # ----------------------------
        
        #print(
        #    ticker,
        #    "Score:", score,
        #    "RR:", risk_reward,
        #    "Signal:", signal
        #)
        

        # ----------------------------
        # FINAL ROW
        # ----------------------------
    
        edge_score = calculate_edge_score(
            score,
            risk_reward,
            rs_score,
            volume_spike,
            breakout,
            regime
        )

        edge_rating = int(calculate_edge_rating(edge_score))
        trade_action = get_trade_action(edge_rating)

        # ----------------------------
        # STREAM ROUTING (FIXED LOGIC)
        # ----------------------------

        if trade_action == "WATCH":
            print(f"👀 WATCH CANDIDATE: {ticker} Edge: {edge_rating}")
            # later we can send to Telegram / WhatsApp / email
        
        else:
            pass
            
        print(
            ticker,
            "Score:", score,
            "Edge:", edge_score,
            "RR:", risk_reward,
            "Signal:", signal
        )
        
        print(
            f"ADDING RESULT: {ticker} | "
            f"Score={score} | "
            f"RR={risk_reward} | "
            f"Edge={edge_score}"
        )
        
        results.append({
            "ticker": ticker,
            "cmp": cmp,
            "rsi": rsi,
            "ema20": ema20,
            "ema50": ema50,
            "trend": trend,
            "score": score,
            "edge_score": edge_score,
            "edge_rating": edge_rating,
            "trade_action": trade_action,
            "position_size": position_size,
            "signal": signal,
            "atr_risk": atr_risk,
            "stop_loss": stop_loss,
            "target": target,
            "risk_reward": risk_reward,
            "rs_score": rs_score,
            "rs_rank": rs_rank,
            "avg_volume": avg_volume,
            "current_volume": current_volume,
            "volume_spike": volume_spike,
            "breakout": breakout
        })
        print("RESULTS SIZE:", len(results))

    except Exception as e:
        error_reason = str(e)
    
        print(
            f"ERROR: {ticker} | "
            f"{type(e).__name__} | "
            f"{error_reason}"
        )
    
        failed_logs.append([
            ticker,
            "PIPELINE_ERROR",
            error_reason
        ])
    
        continue
