import yfinance as yf
import pandas as pd

def get_market_regime():

    nifty = yf.download(
        "^NSEI",
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False
    )

    if nifty.empty:
        return "SIDEWAYS", 0, 0, 0, 0.0

    close = nifty["Close"]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close = close.dropna()

    ema50 = close.ewm(span=50).mean()
    ema200 = close.ewm(span=200).mean()

    last_close = float(close.iloc[-1])
    last_ema50 = float(ema50.iloc[-1])
    last_ema200 = float(ema200.iloc[-1])

    nifty_return = float((close.iloc[-1] / close.iloc[0]) - 1)

    if last_close > last_ema50 and last_ema50 > last_ema200:
        regime = "BULL"
    elif last_close < last_ema50 and last_ema50 < last_ema200:
        regime = "BEAR"
    else:
        regime = "SIDEWAYS"

    return (
        regime,
        last_close,
        last_ema50,
        last_ema200,
        nifty_return
    )
