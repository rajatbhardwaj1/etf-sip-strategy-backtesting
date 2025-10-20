from backtester import Backtester
from strategy import MovingAverageStrategy


def test_backtester_runs():
    strategy = MovingAverageStrategy(short_window=2, long_window=3)
    backtester = Backtester("AAPL", "2023-01-01", "2023-01-10", strategy)
    results = backtester.run()

    assert "portfolio" in results
    assert len(results["portfolio"]) > 0
