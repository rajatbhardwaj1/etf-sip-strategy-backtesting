from src.utils import fetch_multiple_ohlc, filter_outliers, fetch_ohlc, calculate_cagr, plot_strategy_vs_index
from src.sip_strategy import SIPStrategy
from src.etfs import ETFS
import matplotlib.pyplot as plt
import pandas as pd
import json

if __name__ == "__main__":
    start_date = "2020-01-01"
    end_date = "2025-10-01"
    initial_capital = 0
    sip_amount = 50000

    # --- Fetch ETFs ---
    etf_data = fetch_multiple_ohlc(ETFS, start=start_date, end=end_date)
    for symbol, df in etf_data.items():
        etf_data[symbol] = filter_outliers(df, column="Close", max_change_pct=20)

    # --- Run SIP strategy ---
    strategy = SIPStrategy()
    result = strategy.generate_signals(etf_data, capital=initial_capital, sip_amount=sip_amount )

    trades = result["trades"]
    net_worth_df = result["net_worth"].copy()
    extra_cash_needed = result.get("extra_cash_needed", {})
    monthly_invested_cash = result.get("monthly_invested_cash", {})
    cash_history = result.get("cash_history", {})
    portfolio = result.get("portfolio" , {})

    # --- Print CAGR ---
    cagr_result = calculate_cagr(net_worth_df, value_column="NetWorth", invested_column=None)
    print(f"SIP Strategy Overall CAGR: {cagr_result['overall_cagr'] * 100:.2f}%")
    print(f"SIP Strategy Final Net Worth: {net_worth_df['NetWorth'].iloc[-1]:.2f}")
    print(f"SIP Strategy Overall CAGR: {cagr_result['overall_cagr']*100:.2f}%")
    print("SIP Strategy Yearly CAGR:")
    for year, c in cagr_result["yearly_cagr"].items():
        print(f"  {year}: {c*100:.2f}%")

    # --- Extra cash per month ---
    if extra_cash_needed is not None:
        print("\nExtra Cash Needed (capped at 50k) per month:")
        for month, (amt, net_worth) in sorted(extra_cash_needed.items()):
            print(f"  {month}: Extra Cash = {amt:.2f}, Net Worth = {net_worth:.2f}")
    # --- Monthly invested cash and net worth ---
    if monthly_invested_cash:
        print("\n Total Monthly Invested Cash vs Net Worth at Month End:")

        # Convert net worth dates to month string
        net_worth_df["Month"] = net_worth_df["Date"].dt.strftime("%Y-%m")
        monthly_net_worth = net_worth_df.groupby("Month")["NetWorth"].last()

        for month, invested in sorted(monthly_invested_cash.items()):
            net_worth = monthly_net_worth.get(month, 0)
            print(f"  {month}: Invested = {invested:.2f}, Month-End Net Worth = {net_worth:.2f}")


    # --- Nifty SIP comparison ---
    nifty_ticker = "^NSEI"
    nifty_df = fetch_ohlc(nifty_ticker, start=start_date, end=end_date)
    nifty_df.reset_index(inplace=True)
    nifty_df = nifty_df.sort_values("Date")
    nifty_df = filter_outliers(nifty_df, column="Close", max_change_pct=20)

    # --- Nifty SIP comparison with annual increment ---
    nifty_units = 0
    nifty_cash_invested = 0
    nifty_sip = sip_amount
    nifty_df["Units"] = 0
    nifty_df["InvestedValue"] = 0
    total_invested = 0

    last_month = None
    for i, row in nifty_df.iterrows():
        date = row["Date"]
        price = row["Close"]
        month_str = date.strftime("%Y-%m")

        # SIP on first trading day of the month
        if month_str != last_month:
            # Annual increment in January
            if date.month == 1 and last_month is not None:
                nifty_sip *= 1.15

            nifty_units += nifty_sip / price
            nifty_cash_invested += nifty_sip
            total_invested += nifty_sip
            last_month = month_str

        nifty_df.loc[i, "Units"] = nifty_units
        nifty_df.loc[i, "InvestedValue"] = nifty_units * price

    nifty_cagr_result = calculate_cagr(nifty_df, value_column="InvestedValue")
    print(f"\nNifty 50 Final Value (with SIP): {nifty_df['InvestedValue'].iloc[-1]:.2f}")
    print(f"\nTotal invested sum : {total_invested:.2f}")
    print(f"Nifty 50 Overall CAGR: {nifty_cagr_result['overall_cagr'] * 100:.2f}%")

    # --- Plot net worth vs index ---
    net_worth_df["PrevNetWorth"] = net_worth_df["NetWorth"].shift(1)
    net_worth_df["DailyChangePct"] = ((net_worth_df["NetWorth"] - net_worth_df["PrevNetWorth"])
                                      / net_worth_df["PrevNetWorth"] * 100)
    big_drops = net_worth_df[net_worth_df["DailyChangePct"] <= -10]
    cash_history_df = pd.DataFrame(result["cash_history"])
    # --- Save trades to CSV ---
    trades_df = pd.DataFrame(trades)
    trades_df.to_csv(f"sip_strategy_trades_{date.strftime('%Y-%m')}.csv", index=False)
    print("\nTrades saved to sip_strategy_trades.csv")

    print("total profit = " , trades_df["profit"].sum() )
    total_gain = sum(
        (info["current_close"] - info["buy_price"]) * info["shares"]
        for info in portfolio.values()
    )
    print("Portfolio gain =", total_gain)

    # print(json.dumps(portfolio, indent=4, default=str))
    print("cash = " , result.get("cash"))
    trades = result["trades"]
    portfolio = result.get("portfolio", {})
    final_cash = result.get("cash", None)
    net_worth_df = result["net_worth"]

    trades_df = pd.DataFrame(trades)
    # Ensure action column is string to use str.contains safely
    if "action" in trades_df.columns:
        trades_df["action"] = trades_df["action"].astype(str)

    # Compute totals
    total_sip = sum(result.get("monthly_invested_cash", {}).values())  # I
    initial_capital = 0  # set to whatever you passed in
    total_buy_spend = 0.0
    total_sell_proceeds = 0.0
    total_realized_profit = 0.0
    total_fees = 0.0
    if not trades_df.empty:
        buy_mask = trades_df["action"].str.contains("BUY", na=False)
        sell_mask = trades_df["action"].str.contains("SELL", na=False)
        total_buy_spend = (trades_df.loc[buy_mask, "price"] * trades_df.loc[buy_mask, "shares"]).sum()
        total_sell_proceeds = (trades_df.loc[sell_mask, "price"] * trades_df.loc[sell_mask, "shares"]).sum()
        if "profit" in trades_df.columns:
            total_realized_profit = trades_df.loc[sell_mask, "profit"].sum()
        # If you tracked fees per trade add it here; otherwise estimate from count of sells
        sell_count = sell_mask.sum()
        # if you used flat 20 per sell:
        estimated_fees = sell_count * 20
        # if you tracked it per trade:
        if "fee" in trades_df.columns:
            total_fees = trades_df["fee"].sum()
        else:
            total_fees = estimated_fees

    # Market value of current holdings (use current_close if available else buy_price)
    market_value = sum(
        info["shares"] * info.get("current_close", info["buy_price"])
        for info in portfolio.values()
    )

    # Final cash reported
    if final_cash is None:
        # try last cash_history entry
        ch = result.get("cash_history", [])
        if ch:
            final_cash = pd.DataFrame(ch)["Cash"].iloc[-1]
        else:
            final_cash = 0

    computed_net_worth = final_cash + market_value
    reported_net_worth = net_worth_df["NetWorth"].iloc[-1]

    # PnL_total = S + market_value - B
    pnl_total = total_sell_proceeds + market_value - total_buy_spend

    expected_net_worth = initial_capital + total_sip - total_fees + pnl_total

    print("=== Reconciliation ===")
    print("Total SIP (sum monthly_invested_cash):", total_sip)
    print("Total buy spend (sum of BUY price*shares):", total_buy_spend)
    print("Total sell proceeds (sum price*shares for SELL):", total_sell_proceeds)
    print("Total realized profit (sum trade profit for SELL):", total_realized_profit)
    print("Total fees (estimated or recorded):", total_fees, "(sell_count:", sell_count, ")")
    print("Market value (current holdings):", market_value)
    print("Final cash:", final_cash)
    print("Computed net worth = cash + market_value:", computed_net_worth)
    print("Reported net worth (from net_worth_df):", reported_net_worth)
    print("PnL_total (S + market_value - B):", pnl_total)
    print("Expected net worth (initial + SIP - fees + PnL_total):", expected_net_worth)
    print("Gap (reported_net_worth - expected_net_worth):", reported_net_worth - expected_net_worth)
    plot_strategy_vs_index(net_worth_df, nifty_df,big_drops,  cash_history_df)
