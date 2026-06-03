import yfinance as yf
import pandas as pd

class DataEngine:

    def __init__(self):
        self.cache = {}
        self.nifty_cache = None

    def load_batch(self, tickers, period="6mo"):
        data = yf.download(
            tickers=tickers,
            period=period,
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False
        )

        for t in tickers:
            try:
                df = data[t].dropna()
                self.cache[t] = df
            except Exception:
                self.cache[t] = None

        return self.cache

    def get(self, ticker):
        return self.cache.get(ticker)
