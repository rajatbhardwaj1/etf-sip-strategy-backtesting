import pandas as pd

class MovingAverageStrategy:
    def __init__(self, short_window: int = 20, long_window: int = 50):
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate buy/sell signals using SMA crossover."""
        df = data.copy()
        df["SMA_short"] = df["Close"].rolling(window=self.short_window).mean()
        df["SMA_long"] = df["Close"].rolling(window=self.long_window).mean()

        # Buy when short SMA crosses above long SMA, sell when opposite
        df["signal"] = 0
        df["signal"][self.short_window:] = \
            (df["SMA_short"][self.short_window:] > df["SMA_long"][self.short_window:]).astype(int)

        # Generate trading positions (1 = buy, 0 = sell/flat)
        df["position"] = df["signal"].diff()
        return df
