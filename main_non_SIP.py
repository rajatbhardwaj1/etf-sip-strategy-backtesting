from src.utils import fetch_multiple_ohlc, filter_outliers, fetch_ohlc, calculate_cagr, plot_strategy_vs_index_without_cash
from src.strategy import MovingAverageStrategy
from src.etfs import ETFS
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
    ##ddate -- 2024-11-05
if __name__ == "__main__":
    start_date = "2020-01-01"
    end_date = "2025-08-10"
    initial_capital = 100000

    # --- Fetch all ETFs ---
    etf_data = fetch_multiple_ohlc(ETFS, start=start_date, end=end_date)
    for symbol, df in etf_data.items():
        etf_data[symbol] = filter_outliers(df, column="Close", max_change_pct=20)

    # --- Initialize strategy ---
    strategy = MovingAverageStrategy()

    # --- Run strategy on all ETFs ---
    result = strategy.generate_signals(etf_data, capital=initial_capital)
    trades = result["trades"]
    net_worth_df = result["net_worth"].copy()

    # --- Calculate CAGR for ETF strategy ---
    cagr_result = calculate_cagr(net_worth_df, value_column="NetWorth")
    print(f"ETF Strategy Final Net Worth: {net_worth_df['NetWorth'].iloc[-1]:.2f}")
    print(f"ETF Strategy Overall CAGR: {cagr_result['overall_cagr']*100:.2f}%")
    print("ETF Strategy Yearly CAGR:")
    for year, c in cagr_result["yearly_cagr"].items():
        print(f"  {year}: {c*100:.2f}%")




    # --- Fetch Nifty 50 data from Yahoo Finance ---
    nifty_ticker = "^NSEI"
    nifty_df = fetch_ohlc(nifty_ticker, start=start_date, end=end_date)
    nifty_df.reset_index(inplace=True)
    nifty_df = nifty_df.sort_values("Date")
    nifty_df = filter_outliers(nifty_df, column="Close", max_change_pct=20)
    nifty_df["InvestedValue"] = initial_capital / nifty_df["Close"].iloc[0] * nifty_df["Close"]

    # --- Calculate CAGR for Nifty ---
    nifty_cagr_result = calculate_cagr(nifty_df, value_column="InvestedValue")
    print(f"\nNifty 50 Final Value: {nifty_df['InvestedValue'].iloc[-1]:.2f}")
    print(f"Nifty 50 Overall CAGR: {nifty_cagr_result['overall_cagr']*100:.2f}%")
    print("Nifty 50 Yearly CAGR:")
    for year, c in nifty_cagr_result["yearly_cagr"].items():
        print(f"  {year}: {c*100:.2f}%")

    # --- Calculate daily % change and mark drops > 10% ---
    net_worth_df["PrevNetWorth"] = net_worth_df["NetWorth"].shift(1)
    net_worth_df["DailyChangePct"] = (net_worth_df["NetWorth"] - net_worth_df["PrevNetWorth"]) / net_worth_df["PrevNetWorth"] * 100
    big_drops = net_worth_df[net_worth_df["DailyChangePct"] <= -10]

    plot_strategy_vs_index_without_cash(net_worth_df, nifty_df, big_drops)