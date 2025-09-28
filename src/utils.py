from typing import List, Optional

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

import matplotlib.dates as mdates

import os
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

DATA_DIR = "data"

# Ensure the data directory exists
os.makedirs(DATA_DIR, exist_ok=True)
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
DATA_DIR = os.path.join(BASE_DIR, "data")

# Ensure the data directory exists
os.makedirs(DATA_DIR, exist_ok=True)


def fetch_ohlc(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch daily OHLCV data for a single stock/ETF from local CSV file.
    Filters data between start and end dates.
    """
    import pandas as pd
    import os

    file_path = os.path.join(DATA_DIR, f"{symbol}.csv")
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path, parse_dates=["Date"], dayfirst=False)
    # Drop rows where Date is NaT (invalid)
    df = df.dropna(subset=["Date"])

    # Filter by start and end date
    df = df[(df["Date"] >= pd.to_datetime(start)) & (df["Date"] <= pd.to_datetime(end))]

    if df.empty:
        print(f"No data for {symbol} in the given date range")
    return df.reset_index(drop=True)


def fetch_multiple_ohlc(symbols: list, start: str, end: str) -> dict:
    """
    Fetch OHLCV data for multiple ETFs from local CSV files.
    Returns a dict: {symbol: dataframe}
    """
    data = {}
    for symbol in symbols:
        df = fetch_ohlc(symbol, start, end)
        if not df.empty:
            data[symbol] = df
    return data


def load_etf_data(symbol: str) -> pd.DataFrame:
    """
    Load ETF data from local CSV file.
    """
    file_path = os.path.join(DATA_DIR, f"{symbol}.csv")
    print(f"file path = , {file_path}")
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, parse_dates=["Date"])
        return df
    else:
        print(f"No local data found for {symbol}")
        return pd.DataFrame()


def plot_opening_prices(
        symbols: List[str],
        start_date: str,
        end_date: Optional[str] = None,
        sample_every: int = 10,
        save_dir: str = "plots"
):
    """
    Plots opening prices of each symbol fetched, ignoring invalid or missing data.
    Saves each plot individually in the save_dir with the symbol as filename.

    Args:
        symbols (list): List of ETF symbols to plot.
        start_date (str): Start date for data fetching.
        end_date (str, optional): End date. Defaults to today.
        sample_every (int): Plots every N-th row to reduce clutter (X-axis sampling).
        save_dir (str): Directory to save the plots.
    """
    if end_date is None:
        end_date = pd.Timestamp.today().strftime("%Y-%m-%d")

    if not symbols:
        print("No symbols provided to plot.")
        return

    os.makedirs(save_dir, exist_ok=True)

    for symbol in symbols:
        df = fetch_ohlc(symbol, start=start_date, end=end_date)

        if df is None or df.empty:
            print(f"No data to plot for {symbol}")
            continue

        # --- Data Cleaning ---
        df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
        df["Open"] = pd.to_numeric(df["Open"], errors='coerce')
        df = df.dropna(subset=["Date", "Open"])
        df = df.sort_values("Date")

        if df.empty:
            print(f"No valid data to plot for {symbol}")
            continue

        # Sample every N-th row to reduce clutter
        df_sampled = df.iloc[::sample_every, :]

        # --- Plotting ---
        plt.style.use('seaborn-v0_8-whitegrid')
        plt.figure(figsize=(16, 7))

        plt.plot(df_sampled["Date"], df_sampled["Open"],
                 label=f"{symbol} Opening Price",
                 linewidth=2.5,
                 color="#2980b9")

        # Title and labels
        plt.title(f"Opening Prices of {symbol} ({df_sampled['Date'].iloc[0].date()} - {df_sampled['Date'].iloc[-1].date()})",
                  fontsize=20,
                  fontweight='bold',
                  pad=20)
        plt.xlabel("Date", fontsize=14, labelpad=15)
        plt.ylabel("Opening Price", fontsize=14, labelpad=15)

        # Limit Y-axis ticks
        ax = plt.gca()
        ax.yaxis.set_major_locator(ticker.MaxNLocator(nbins=10))
        ax.yaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.2f}'))

        # X-axis tick formatting
        plt.xticks(rotation=45, ha='right', fontsize=12)
        plt.yticks(fontsize=12)
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.tight_layout()

        # Save plot
        save_path = os.path.join(save_dir, f"{symbol}.png")
        plt.savefig(save_path, dpi=300)
        plt.close()
        print(f"Plot saved to {save_path}")


def save_etf_data(symbols: list, start: str = "2015-01-01"):
    """
    Download data for all ETFs and save as CSV in the data folder.
    """
    for symbol in symbols:
        try:
            print(f"Downloading {symbol}...")
            df = fetch_ohlc(symbol, start=start, end=pd.Timestamp.today().strftime("%Y-%m-%d"))
            if not df.empty:
                file_path = os.path.join(DATA_DIR, f"{symbol}.csv")
                df.to_csv(file_path, index=False)
                print(f"Saved {symbol} to {file_path}")
            else:
                print(f"No data for {symbol}")
        except Exception as e:
            print(f"Error downloading {symbol}: {e}")


def check_opening_price_discrepancies(df: pd.DataFrame, threshold: float = 2.0) -> pd.DataFrame:
    """
    Check for discrepancies in the opening price.
    Flags rows where the opening price changes more than `threshold` times from the previous day.

    Args:
        df (pd.DataFrame): OHLCV DataFrame with columns ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        threshold (float): Factor change to flag (e.g., 2.0 means >2x rise or <0.5x drop)

    Returns:
        pd.DataFrame: Subset of df with the discrepancies
    """
    df = df.copy()
    df["Open"] = pd.to_numeric(df["Open"], errors='coerce')
    df = df.dropna(subset=["Open"])
    df = df.sort_values("Date").reset_index(drop=True)

    # Previous day Open
    df["Prev_Open"] = df["Open"].shift(1)

    # Calculate ratio
    df["Open_Ratio"] = df["Open"] / df["Prev_Open"]

    # Flag rows where ratio > threshold or < 1/threshold
    discrepancies = df[(df["Open_Ratio"] > threshold) | (df["Open_Ratio"] < 1/threshold)]

    return discrepancies