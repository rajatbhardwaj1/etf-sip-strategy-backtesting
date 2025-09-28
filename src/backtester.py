from src.utils import fetch_ohlc

class Backtester:
    """
    Backtester for a single symbol and strategy.
    """
    def __init__(self, symbol: str, start: str, end: str, strategy):
        self.symbol = symbol
        self.start = start
        self.end = end
        self.strategy = strategy

    def run(self):
        # Fetch data
        data = fetch_ohlc(self.symbol, self.start, self.end)
        if data.empty:
            print(f"No data for {self.symbol}")
            return None

        # Generate signals
        signals = self.strategy.generate_signals(data)

        # Portfolio backtesting
        initial_capital = 10000.0
        shares = 0
        cash = initial_capital
        portfolio_values = []
        trades = 0

        for _, row in signals.iterrows():
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

            portfolio_values.append(cash + shares * price)

        signals["portfolio"] = portfolio_values
        return {
            "data": signals,
            "portfolio": portfolio_values,
            "trades": trades,
        }
