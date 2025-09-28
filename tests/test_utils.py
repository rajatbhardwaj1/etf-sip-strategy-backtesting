import unittest
import warnings
from src.utils import fetch_ohlc, check_opening_price_discrepancies
from src.utils import plot_opening_prices
from src.etfs import ETFS
import pandas as pd
import os
# Suppress FutureWarnings from yfinance
warnings.simplefilter(action='ignore', category=FutureWarning)

class TestUtils(unittest.TestCase):

    def test_fetch_ohlc(self):
        symbol = "ALPL30IETF.NS"
        start_date = "2023-01-03"
        end_date = "2023-01-10"

        df = fetch_ohlc(symbol, start_date, end_date)

        # DataFrame should not be empty
        self.assertFalse(df.empty, "DataFrame should not be empty")
        print(df)


    def test_plot_opening_prices(self):
        """
        Plot all ETFs and save each individually in tests/plots folder.
        """
        plots_dir = os.path.join(os.path.dirname(__file__), "plots")
        try:
            plot_opening_prices(ETFS, start_date="2015-03-12", end_date="2025-09-26",
                                sample_every=10, save_dir=plots_dir)
        except Exception as e:
            self.fail(f"plot_opening_prices raised an exception: {e}")

        # Check that at least one plot file was created
        files = os.listdir(plots_dir) if os.path.exists(plots_dir) else []
        self.assertTrue(len(files) > 0, "No plot files were created in the plots folder.")

    def test_opening_price_discrepancies_dummy(self):
        """
        Test the check_opening_price_discrepancies function with dummy data.
        """
        data = {
            "Date": pd.date_range(start="2025-01-01", periods=5, freq="D"),
            "Open": [100, 102, 250, 248, 120],  # 250 (>2x) and 120 (<1/2) should be flagged
            "High": [0] * 5,
            "Low": [0] * 5,
            "Close": [0] * 5,
            "Volume": [0] * 5
        }
        df = pd.DataFrame(data)

        discrepancies = check_opening_price_discrepancies(df, threshold=2.0)

        # Expect 2 rows to be flagged
        self.assertEqual(len(discrepancies), 2)
        self.assertIn(250, discrepancies["Open"].values)
        self.assertIn(120, discrepancies["Open"].values)

    def test_opening_price_discrepancies_all_etfs(self):
        """
        Check discrepancies in all ETFs using local data.
        """
        for symbol in ETFS:
            df = fetch_ohlc(symbol, "2015-01-01", "2025-09-27")
            if df.empty:
                continue
            discrepancies = check_opening_price_discrepancies(df, threshold=2.0)
            if not discrepancies.empty:
                print(f"\nDiscrepancies for {symbol}:")
                print(discrepancies[["Date", "Open", "Prev_Open", "Open_Ratio"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
