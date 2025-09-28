import yfinance as yf
import pandas as pd

def fetch_data(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch OHLCV data from Yahoo Finance."""
    df = yf.download(symbol, start=start, end=end)
    df = df.dropna()
    return df
