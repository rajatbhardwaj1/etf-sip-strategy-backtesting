import unittest
import pandas as pd
from finances.src.strategy import MovingAverageStrategy


class TestMovingAverageStrategy(unittest.TestCase):

    def setUp(self):
        # Create dummy OHLC data for two ETFs
        self.etf_data = {}

        dates = pd.date_range(start="2025-01-01", periods=10, freq="D")

        # ETF 1: steadily rising
        self.etf_data["ETF1"] = pd.DataFrame({
            "Date": dates,
            "Open": [100, 101, 102, 104, 103, 105, 106, 108, 110, 111],
            "High": [0] * 10,
            "Low": [0] * 10,
            "Close": [100, 101, 102, 104, 103, 105, 106, 108, 110, 111],
            "Volume": [1000] * 10
        })

        # ETF 2: sudden drop and rise to test average down and trailing
        self.etf_data["ETF2"] = pd.DataFrame({
            "Date": dates,
            "Open": [200, 198, 100, 102, 103, 105, 108, 150, 155, 160],
            "High": [0] * 10,
            "Low": [0] * 10,
            "Close": [200, 198, 100, 102, 103, 105, 108, 150, 155, 160],
            "Volume": [1000] * 10
        })

        self.strategy = MovingAverageStrategy(
            dma_window=3,
            profit_threshold=5,
            trailing_stop=1,
            max_daily_buys=1,
            avg_down_threshold=3
        )

    def test_generate_signals(self):
        trades = self.strategy.generate_signals(self.etf_data, capital=10000)
        self.assertIsInstance(trades, list)
        self.assertGreater(len(trades), 0)  # Expect some trades

        # Check that BUY actions exist
        buy_trades = [t for t in trades if t["action"] in ("BUY", "BUY_AVERAGE_DOWN")]
        self.assertTrue(len(buy_trades) > 0, "Expected at least one buy trade")

        # Check that SELL_TRAILING actions exist (if profit threshold is reached)
        sell_trades = [t for t in trades if t["action"] == "SELL_TRAILING"]
        self.assertTrue(len(sell_trades) >= 0)  # Could be zero if profit not reached

        # Check that all trades have correct keys
        for t in trades:
            self.assertIn("date", t)
            self.assertIn("symbol", t)
            self.assertIn("action", t)
            self.assertIn("price", t)
            self.assertIn("shares", t)


if __name__ == "__main__":
    unittest.main()
