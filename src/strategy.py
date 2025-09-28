import pandas as pd

class MovingAverageStrategy:
    """
    Simple SMA crossover strategy.
    """
    def __init__(self, short_window: int = 20, long_window: int = 50):
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["SMA_short"] = df["Close"].rolling(window=self.short_window).mean()
        df["SMA_long"] = df["Close"].rolling(window=self.long_window).mean()

        # Buy signal: 1 if short SMA > long SMA, 0 otherwise
        df["signal"] = 0
        df.loc[df.index[self.short_window:], "signal"] = \
            (df["SMA_short"][self.short_window:] > df["SMA_long"][self.short_window:]).astype(int)

        # Position: diff of signal
        df["position"] = df["signal"].diff().fillna(0)
        return df
