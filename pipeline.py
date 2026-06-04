from signals import apply_risk_engine

class Pipeline:

    def __init__(self, data_engine, feature_engine, signal_engine, scoring_engine):
        self.data = data_engine
        self.features = feature_engine
        self.signals = signal_engine
        self.scoring = scoring_engine

    def run(self, tickers, regime, nifty_return):

        results = []

        self.data.load_batch(tickers)

        for t in tickers:

            df = self.data.get(t)

            if df is None:
                continue

            df = self.features.enrich(df)

            if df is None or len(df) < 60:
                continue

            stock_return = df["Close"].iloc[-1] / df["Close"].iloc[0] - 1
            rs_score = (stock_return - nifty_return) * 100

            signal = self.signals.get_signal(df, regime, rs_score)
            if signal is None:
                continue

            cmp, rsi, ema20, ema50, trend, score, sig, avg_vol, curr_vol, vol_spike, breakout = signal

            risk = apply_risk_engine(df.iloc[-1], df)

            rr = float(risk.iloc[3])

            edge = self.scoring.edge_score(score, rr, rs_score, vol_spike, breakout, regime)
            rating = self.scoring.rating(edge)
            action = self.scoring.action(rating)

            results.append({
                "ticker": t,
                "cmp": cmp,
                "score": score,
                "edge": edge,
                "rating": rating,
                "action": action
            })

        return results
