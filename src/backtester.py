import pandas as pd
from src.utils import fetch_data

class Backtester:
    def __init__(self, symbol: str, start: str, end: str, strategy):
        self.symbol = symbol
        self.start = start
        self.end = end
        self.strategy = strategy

    def run(self):
        # Fetch data
        data = fetch_data(self.symbol, self.start, self.end)

        # Generate signals
        signals = self.strategy.generate_signals(data)

        # Backtest portfolio
        initial_capital = 10000.0
        shares = 0
        cash = initial_capital
        portfolio_values = []
        trades = 0

        for date, row in signals.iterrows():
            price = row["Close"]

            # Buy signal
            if row["position"] == 1 and cash >= price:
                shares = cash // price
                cash -= shares * price
                trades += 1

            # Sell signal
            elif row["position"] == -1 and shares > 0:
                cash += shares * price
                shares = 0
                trades += 1

            # Portfolio value = cash + shares*price
            portfolio_values.append(cash + shares * price)

        signals["portfolio"] = portfolio_values

        return {
            "data": signals,
            "portfolio": portfolio_values,
            "trades": trades,
        }
