from signals import generate_signal

class SignalEngine:

    def get_signal(self, df, regime, rs_score):
        return generate_signal(df, regime, rs_score)
