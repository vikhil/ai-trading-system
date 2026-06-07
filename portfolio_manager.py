import yfinance as yf
import pandas as pd

from signals import (
    generate_signal,
    calculate_atr,
    apply_risk_engine
)

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
                "Score": score
            })

        except Exception:
            enriched.append(row)

    return enriched
