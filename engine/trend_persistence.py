def calculate_trend_persistence(df):

    if len(df) < 30:
        return 0

    score = 0

    recent = df.tail(20)

    bullish_days = 0

    for _, row in recent.iterrows():

        close = float(row["Close"])
        ema20 = float(row["EMA20"])
        ema50 = float(row["EMA50"])

        if close > ema20 > ema50:
            bullish_days += 1

    # -------------------------
    # Score based on consistency
    # -------------------------

    if bullish_days >= 18:
        score = 100

    elif bullish_days >= 15:
        score = 85

    elif bullish_days >= 12:
        score = 70

    elif bullish_days >= 8:
        score = 50

    elif bullish_days >= 5:
        score = 30

    else:
        score = 10

    return score
