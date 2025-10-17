import datetime
import json

import pandas as pd
from typing import Dict
from .utils import (
    clean_ohlc_data,
    calculate_dma,
    calculate_pct_change_vs_dma,
    get_most_fallen_etfs,
    update_portfolio_for_buy,
    update_portfolio_for_avg_down,
    sell_most_profitable_stock
)

class MovingAverageStrategy:
    """
    Trading strategy for selected ETFs:
    - Buy the most fallen ETF relative to its DMA.
    - Average down if loss exceeds threshold.
    - Sell using trailing stop-loss after reaching target profit.
    - Prints ETF contributing most to portfolio drop if drop > 10% in a day.
    """

    def __init__(
        self,
        dma_window: int = 20,
        profit_threshold: float = 6.5,   # % gain to start trailing profit
        trailing_stop: float = 0.5,      # % trailing loss
        max_daily_buys: int = 1,
        avg_down_threshold: float = 4.0  # % loss to average down
    ):
        self.dma_window = dma_window
        self.profit_threshold = profit_threshold
        self.trailing_stop = trailing_stop
        self.max_daily_buys = max_daily_buys
        self.avg_down_threshold = avg_down_threshold

    def generate_signals(self, etf_data: Dict[str, pd.DataFrame], capital: float = 100000) -> Dict[str, pd.DataFrame]:
        portfolio = {}  # {symbol: {'buy_price': float, 'shares': int, 'peak': float, 'current_close': float}}
        trades = []
        net_worth_history = []

        # Clean and calculate DMA + % change for each ETF
        percent_changes = {}
        for symbol, df in etf_data.items():
            df_clean = clean_ohlc_data(df)
            df_dma = calculate_dma(df_clean, self.dma_window)
            df_pct = calculate_pct_change_vs_dma(df_dma)
            percent_changes[symbol] = df_pct

        all_dates = sorted(set(date for df in percent_changes.values() for date in df["Date"]))
        cash = capital

        for date in all_dates:
            daily_etfs = get_most_fallen_etfs(percent_changes, date, top_n=3)
            buys_today = 0

            # --- Buy / Avg Down ---
            for symbol, pct, close in daily_etfs:
                if buys_today >= self.max_daily_buys:
                    break

                if symbol not in portfolio:
                    net_worth = cash + sum(
                        info["shares"] * info.get("current_close", info["buy_price"]) for info in portfolio.values())
                    buy_amount = net_worth / 40

                    if buy_amount > cash and portfolio:  # Not enough cash → try selling most profitable
                        cash = sell_most_profitable_stock(portfolio, trades, date, cash, min_profit=3)

                    buy_amount = min(cash, net_worth / 40)
                    shares = update_portfolio_for_buy(portfolio, symbol, close, buy_amount)
                    if shares > 0:
                        trades.append(
                            {"date": date, "symbol": symbol, "action": "BUY", "price": close, "shares": shares}
                        )
                        cash -= shares * close
                        buys_today += 1

                else:
                    buy_price = portfolio[symbol]["buy_price"]
                    loss_pct = (buy_price - close) / buy_price * 100
                    if loss_pct > self.avg_down_threshold:
                        net_worth = cash + sum(
                            info["shares"] * info.get("current_close", info["buy_price"]) for info in portfolio.values()
                        )
                        buy_amount = net_worth / 40

                        if buy_amount > cash and portfolio:  # Not enough cash → sell most profitable
                            if buy_amount > cash and portfolio:  # Not enough cash → try selling most profitable
                                cash = sell_most_profitable_stock(portfolio, trades, date, cash, min_profit=3.0)

                        buy_amount = min(cash, net_worth / 40)
                        shares = update_portfolio_for_avg_down(portfolio, symbol, close, buy_amount)
                        if shares > 0:
                            trades.append({
                                "date": date,
                                "symbol": symbol,
                                "action": "BUY_AVERAGE_DOWN",
                                "price": close,
                                "shares": shares
                            })
                            cash -= shares * close
                            buys_today += 1

            # --- Trailing stop-loss sell ---
            for symbol in list(portfolio.keys()):
                df = percent_changes[symbol]
                row = df[df["Date"] == date]
                if row.empty:
                    continue
                open_price = row["Open"].values[0]
                peak = max(portfolio[symbol]["peak"], open_price)
                portfolio[symbol]["peak"] = peak
                buy_price = portfolio[symbol]["buy_price"]
                profit_pct = (open_price - buy_price) / buy_price * 100

                if profit_pct >= self.profit_threshold:
                    trailing_price = peak * (1 - self.trailing_stop / 100)
                    if open_price <= trailing_price:
                        trades.append({
                            "date": date,
                            "symbol": symbol,
                            "action": "SELL_TRAILING",
                            "price": open_price,
                            "shares": portfolio[symbol]["shares"]
                        })
                        cash += portfolio[symbol]["shares"] * open_price
                        cash -= 20
                        del portfolio[symbol]

            # --- Update current closing price for portfolio ---
            for sym in portfolio:
                df_sym = percent_changes[sym]
                row_today = df_sym[df_sym["Date"] == date]
                if not row_today.empty:
                    portfolio[sym]["current_close"] = round(row_today["Close"].values[0], 2)

            # --- Record net worth ---
            net_worth = cash + sum(info["shares"] * info["current_close"] for info in portfolio.values())
            net_worth_history.append({"Date": date, "NetWorth": net_worth})

        return {"trades": trades, "net_worth": pd.DataFrame(net_worth_history)}
