from typing import List, Optional, Dict, Tuple

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import yfinance as yf
import matplotlib.dates as mdates

import os
import warnings
import datetime
import numpy_financial as npf

warnings.simplefilter(action='ignore', category=FutureWarning)

DATA_DIR = "backtesting/data"

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

    # Round numeric columns to 2 decimals
    numeric_cols = df.select_dtypes(include=["float", "int"]).columns
    df[numeric_cols] = df[numeric_cols].round(2)

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




def save_etf_data_yf(symbols: list, start: str = "2015-01-01"):
    """
    Download data for all ETFs using yfinance and save as CSV in the data folder.

    Args:
        symbols: List of ETF symbols.
        start: Start date (YYYY-MM-DD)
    """
    end = pd.Timestamp.today().strftime("%Y-%m-%d")

    for symbol in symbols:
        try:
            print(f"Downloading {symbol} from Yahoo Finance...")
            df = yf.download(symbol, start=start, end=end)
            if not df.empty:
                df.reset_index(inplace=True)  # Make sure 'Date' is a column
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


def calculate_dma(df: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """
    Calculate the simple moving average (DMA) for the given OHLC DataFrame.

    Args:
        df (pd.DataFrame): OHLC data with 'Close' column.
        window (int): Number of days for moving average.

    Returns:
        pd.DataFrame: Original DataFrame with additional 'DMA' column.
    """
    df = df.copy()
    df["DMA"] = df["Close"].rolling(window=window).mean()
    return df


def calculate_pct_change_vs_dma(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate percentage change of current Close vs DMA.

    Args:
        df (pd.DataFrame): OHLC data with 'Close' and 'DMA' columns.

    Returns:
        pd.DataFrame: DataFrame with additional 'pct_change' column.
    """
    df = df.copy()
    df["pct_change"] = (df["Close"] - df["DMA"]) / df["Close"] * 100
    return df


def clean_ohlc_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean OHLC data:
    - Ensure 'Date' is datetime
    - Ensure numeric values for 'Open', 'Close', 'High', 'Low'
    - Drop rows with missing data in 'Date' or 'Open'/'Close'

    Args:
        df (pd.DataFrame): Raw OHLC DataFrame

    Returns:
        pd.DataFrame: Cleaned OHLC DataFrame
    """
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
    for col in ["Open", "Close", "High", "Low"]:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=["Date", "Open", "Close"])
    df = df.sort_values("Date")
    return df


def get_most_fallen_etfs(
        etf_data: Dict[str, pd.DataFrame],
        date: pd.Timestamp,
        top_n: int = 3
) -> List[Tuple[str, float, float]]:
    """
    For a given date, return top N most fallen ETFs by pct_change.

    Args:
        etf_data (dict): {symbol: pd.DataFrame with 'Date', 'pct_change', 'Close'}
        date (pd.Timestamp): Specific date to check
        top_n (int): Number of top fallen ETFs to return

    Returns:
        List[Tuple[symbol, pct_change, close_price]]
    """
    daily_list = []
    for symbol, df in etf_data.items():
        day_row = df[df["Date"] == date]
        if not day_row.empty:
            pct = day_row["pct_change"].values[0]
            close = day_row["Close"].values[0]
            daily_list.append((symbol, pct, close))
    # Sort ascending → most negative first
    daily_list.sort(key=lambda x: x[1])
    return daily_list[:top_n]
def update_portfolio_for_buy(
        portfolio: Dict[str, Dict],
        symbol: str,
        price: float,
        capital_per_trade: float
) -> int:
    """
    Update portfolio when buying an ETF for the first time.
    """
    shares = capital_per_trade // price
    if shares > 0:
        portfolio[symbol] = {"buy_price": price, "shares": shares, "peak": price}
    return int(shares)


def update_portfolio_for_avg_down(
        portfolio: Dict[str, Dict],
        symbol: str,
        price: float,
        capital_per_trade: float
) -> int:
    """
    Average down position for an existing ETF in the portfolio.
    If the symbol does not exist, behaves like update_portfolio_for_buy.
    """
    shares = capital_per_trade // price
    if shares > 0:
        if symbol not in portfolio:
            # Treat as a fresh buy
            portfolio[symbol] = {"buy_price": price, "shares": shares, "peak": price}
        else:
            current = portfolio[symbol]
            total_shares = current["shares"] + shares
            avg_price = (current["buy_price"] * current["shares"] + price * shares) / total_shares
            portfolio[symbol]["buy_price"] = avg_price
            portfolio[symbol]["shares"] = total_shares
            portfolio[symbol]["peak"] = max(current["peak"], price)
    return int(shares)


def filter_outliers(df, column="Close", max_change_pct=50):
    """
    Remove rows where the daily percentage change exceeds max_change_pct.

    Args:
        df: pd.DataFrame with OHLC data.
        column: Column to check for daily % change.
        max_change_pct: Maximum allowed percentage change per day.

    Returns:
        Cleaned DataFrame.
    """
    df = df.sort_values("Date").copy()

    # Ensure numeric values
    df[column] = pd.to_numeric(df[column], errors="coerce")

    # Shift previous day's value
    df["prev"] = df[column].shift(1)

    # Compute absolute daily pct change safely
    df["pct_change"] = abs((df[column] - df["prev"]) / df["prev"]) * 100

    # Filter out rows exceeding threshold
    df_filtered = df[(df["pct_change"] <= max_change_pct) | (df["pct_change"].isna())].drop(
        columns=["prev", "pct_change"]
    )
    return df_filtered



def calculate_cagr(df: pd.DataFrame, value_column: str = "NetWorth") -> dict:
    """
    Calculate overall CAGR and yearly CAGR for a portfolio or index.

    Args:
        df (pd.DataFrame): DataFrame with 'Date' and value column (NetWorth / InvestedValue)
        value_column (str): Column to use for CAGR calculation

    Returns:
        dict: {
            "overall_cagr": float,
            "yearly_cagr": dict {year: cagr}
        }
    """
    df = df.sort_values("Date").copy()
    df["Year"] = df["Date"].dt.year

    # --- Overall CAGR ---
    start_value = df[value_column].iloc[0]
    end_value = df[value_column].iloc[-1]
    total_days = (df["Date"].iloc[-1] - df["Date"].iloc[0]).days
    total_years = total_days / 365.25
    if start_value == 0:
        overall_cagr = 0
    else:
        overall_cagr = (end_value / start_value) ** (1 / total_years) - 1

    # --- Yearly CAGR ---
    yearly_cagr = {}
    for year, group in df.groupby("Year"):
        start_val = group[value_column].iloc[0]
        end_val = group[value_column].iloc[-1]
        days = (group["Date"].iloc[-1] - group["Date"].iloc[0]).days
        years = days / 365.25
        if start_val == 0:
            yearly_cagr[year] = 0
        else:
            yearly_cagr[year] = (end_val / start_val) ** (1 / years) - 1

    return {"overall_cagr": overall_cagr, "yearly_cagr": yearly_cagr}

import numpy as np

def calculate_cagr(df: pd.DataFrame, value_column: str = "NetWorth", invested_column: str = None) -> dict:
    """
    Calculate overall CAGR and yearly CAGR for a portfolio using invested cash vs net worth.

    Args:
        df (pd.DataFrame): DataFrame with 'Date', value_column (NetWorth), and optionally invested_column
        value_column (str): Portfolio NetWorth column
        invested_column (str): Optional column for cumulative invested cash (SIP + extra cash)

    Returns:
        dict: {"overall_cagr": float, "yearly_cagr": dict}
    """
    df = df.sort_values("Date").copy()
    df["Year"] = df["Date"].dt.year

    # --- Calculate Overall CAGR using XIRR approach ---
    # Cash flows: negative for investments, positive for current net worth at last date
    cash_flows = []
    dates = []

    if invested_column is not None:
        for i, row in df.iterrows():
            # Treat monthly invested cash as negative cash flow
            invested = row[invested_column]
            cash_flows.append(-invested)
            dates.append(row["Date"])
        # Add final net worth as positive cash flow at last date
        cash_flows[-1] += df[value_column].iloc[-1]
    else:
        # If no invested_column provided, treat first net worth as starting investment
        cash_flows = [-df[value_column].iloc[0], df[value_column].iloc[-1]]
        dates = [df["Date"].iloc[0], df["Date"].iloc[-1]]

    # Convert to years fraction for XIRR
    days = np.array([(d - dates[0]).days for d in dates])
    years = days / 365.25

    # Solve IRR iteratively using numpy's root finding
    try:
        # Define function for NPV = 0
        f = lambda r: np.sum([cf / ((1 + r) ** t) for cf, t in zip(cash_flows, years)])
        # Simple grid search for approximate IRR
        guess = 0.1
        overall_cagr = np.irr(cash_flows)  # numpy's IRR approximates XIRR
        if overall_cagr is None:
            overall_cagr = 0
    except:
        overall_cagr = 0

    # --- Yearly CAGR ---
    yearly_cagr = {}
    for year, group in df.groupby("Year"):
        start_val = group[value_column].iloc[0]
        end_val = group[value_column].iloc[-1]
        days = (group["Date"].iloc[-1] - group["Date"].iloc[0]).days
        years = days / 365.25
        if start_val == 0 or years == 0:
            yearly_cagr[year] = 0
        else:
            yearly_cagr[year] = (end_val / start_val) ** (1 / years) - 1

    return {"overall_cagr": overall_cagr, "yearly_cagr": yearly_cagr}

def sell_most_profitable_stock(portfolio: Dict[str, Dict], trades: list, date, cash: float, min_profit: float = 2.0) -> float:
    """
    Sell the most profitable stock in the portfolio if its profit exceeds `min_profit`.

    Args:
        portfolio (dict): Current portfolio
        trades (list): List to append trade actions
        date (datetime/date): Current trading date
        cash (float): Available cash
        min_profit (float): Minimum % profit required to sell

    Returns:
        float: Updated cash after selling (if sell happens)
    """
    if not portfolio:
        return cash

    # Find most profitable stock
    best_symbol = max(
        portfolio.keys(),
        key=lambda s: (portfolio[s]["current_close"] - portfolio[s]["buy_price"]) / portfolio[s]["buy_price"]
    )

    buy_price = portfolio[best_symbol]["buy_price"]
    current_price = portfolio[best_symbol]["current_close"]
    profit_pct = (current_price - buy_price) / buy_price * 100

    # Only sell if profit > min_profit
    if profit_pct > min_profit:
        trades.append({
            "date": date,
            "symbol": best_symbol,
            "action": "SELL_FOR_CASH",
            "price": current_price,
            "shares": portfolio[best_symbol]["shares"]
        })
        cash += portfolio[best_symbol]["shares"] * current_price
        del portfolio[best_symbol]

    return cash



def plot_strategy_vs_index(
    net_worth_df,
    nifty_df,
    big_drops,
    cash_history,
    title="Portfolio Net Worth vs Nifty 50 Buy & Hold"
):
    """
    Plot ETF Strategy vs Nifty 50 Buy & Hold with >10% drop markers.
    """
    plt.figure(figsize=(14, 7))

    # Thin lines for clarity
    plt.plot(net_worth_df["Date"], net_worth_df["NetWorth"], linewidth=1, label="ETF Strategy")
    plt.plot(nifty_df["Date"], nifty_df["InvestedValue"], linewidth=1, linestyle='--', label="Nifty 50 Buy & Hold")
    plt.plot(cash_history["Date"], cash_history["Cash"] , linewidth=1, linestyle='--', label="Cash")

    # Mark drops
    if not big_drops.empty:
        plt.scatter(big_drops["Date"], big_drops["NetWorth"], color='red', s=80, marker='v', label=">10% Drop")

    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value (INR)")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

def plot_strategy_vs_index_without_cash(
        net_worth_df,
        nifty_df,
        big_drops,
        title="Portfolio Net Worth vs Nifty 50 Buy & Hold"
):
    """
    Plot ETF Strategy vs Nifty 50 Buy & Hold with >10% drop markers.
    """
    plt.figure(figsize=(14, 7))

    # Thin lines for clarity
    plt.plot(net_worth_df["Date"], net_worth_df["NetWorth"], linewidth=1, label="ETF Strategy")
    plt.plot(nifty_df["Date"], nifty_df["InvestedValue"], linewidth=1, linestyle='--', label="Nifty 50 Buy & Hold")

    # Mark drops
    if not big_drops.empty:
        plt.scatter(big_drops["Date"], big_drops["NetWorth"], color='red', s=80, marker='v', label=">10% Drop")

    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value (INR)")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

def xirr_calculator(monthly_invested_cash, net_worth_history):
    """
    Calculate the IRR (approx CAGR) for a SIP strategy
    assuming equal monthly intervals.
    """
    cashflows = []

    # Monthly SIPs (outflows)
    for _, amount in monthly_invested_cash.items():
        cashflows.append(-amount)

    # Final redemption (inflow)
    if net_worth_history:
        final_value = net_worth_history[-1]["NetWorth"]
        cashflows.append(final_value)

    print("Cashflows:", cashflows)

    try:
        irr_monthly = npf.irr(cashflows)
        irr_annual = (1 + irr_monthly)**12 - 1 if irr_monthly is not None else None
    except Exception as e:
        print("IRR calculation failed:", e)
        irr_annual = None

    return irr_annual
