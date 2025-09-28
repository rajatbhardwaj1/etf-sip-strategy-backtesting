from src.backtester import Backtester
from src.strategy import MovingAverageStrategy

def main():
    symbol = "AAPL"
    start_date = "2020-01-01"
    end_date = "2023-01-01"

    # Define strategy
    strategy = MovingAverageStrategy(short_window=20, long_window=50)

    # Run backtest
    backtester = Backtester(symbol, start_date, end_date, strategy)
    results = backtester.run()

    print("\nFinal Portfolio Value:", results["portfolio"][-1])
    print("Number of Trades:", results["trades"])

if __name__ == "__main__":
    main()
