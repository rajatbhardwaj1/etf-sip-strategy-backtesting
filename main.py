from src.utils import fetch_multiple_ohlc
from src.strategy import MovingAverageStrategy
from src.backtester import Backtester
from src.etfs import ETFS

if __name__ == "__main__":
    start_date = "2023-01-01"
    end_date = "2023-01-10"

    # Fetch all ETFs
    data = fetch_multiple_ohlc(ETFS, start=start_date, end=end_date)

    # Run backtester on first ETF that has data
    for symbol, df in data.items():
        print(f"Running backtest for {symbol}")
        strategy = MovingAverageStrategy()
        backtester = Backtester(symbol, start_date, end_date, strategy)
        result = backtester.run()
        if result:
            print(result["data"].head())
        break  # demo on first ETF
