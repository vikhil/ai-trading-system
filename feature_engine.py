from signals import calculate_atr, add_volume_and_breakout

class FeatureEngine:

    def enrich(self, df):
        if df is None or df.empty:
            return None

        df = calculate_atr(df)
        df = add_volume_and_breakout(df)
        return df
