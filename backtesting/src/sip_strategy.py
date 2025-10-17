import datetime
import pandas as pd
from typing import Dict

from utils import xirr_calculator
from .utils import (
    clean_ohlc_data,
    calculate_dma,
    calculate_pct_change_vs_dma,
    get_most_fallen_etfs,
    update_portfolio_for_buy,
    update_portfolio_for_avg_down,
)

class SIPStrategy:
    def __init__(
        self,
        dma_window: int = 10,
        profit_threshold: float = 6.5,
        trailing_stop: float = 0.5,
        max_daily_buys: int = 1,
        avg_down_threshold: float = 4.0,
        increment: float = 15
    ):
        self.dma_window = dma_window
        self.profit_threshold = profit_threshold
        self.trailing_stop = trailing_stop
        self.max_daily_buys = max_daily_buys
        self.avg_down_threshold = avg_down_threshold
        self.increment = increment

    def generate_signals(
        self,
        etf_data: Dict[str, pd.DataFrame],
        capital: float = 0,
        sip_amount: float = 40000
    ) -> Dict[str, pd.DataFrame]:

        portfolio = {}
        monthly_invested_cash = {}
        trades = []
        net_worth_history = []
        cash_history = []
        cash = capital
        hydration = 0
        buy_divisor = 40
        hydration_increment = 100000
        # Prepare percent changes
        percent_changes = {}
        for symbol, df in etf_data.items():
            df_clean = clean_ohlc_data(df)
            df_dma = calculate_dma(df_clean, self.dma_window)
            df_pct = calculate_pct_change_vs_dma(df_dma)
            percent_changes[symbol] = df_pct

        all_dates = sorted(set(date for df in percent_changes.values() for date in df["Date"]))
        first_year = True
        last_month = None
        last_year = None
        for date in all_dates:
            if last_year != date.year:
                last_year = date.year
                if not first_year :
                    hydration += hydration_increment
                    sip_amount = sip_amount  + (self.increment/100)*sip_amount
                first_year = False
            for sym in portfolio:
                if "hold_days" not in portfolio[sym]:
                    portfolio[sym]["hold_days"] = 1  # first day holding
                else:
                    portfolio[sym]["hold_days"] += 1

            daily_etfs = get_most_fallen_etfs(percent_changes, date, top_n=3)
            buys_today = 0
            month_str = date.strftime("%Y-%m")

            # --- Add SIP on 1st of the month ---
            if date.month != last_month:
                last_month = date.month
                cash += sip_amount
                invested_this_month = sip_amount
                monthly_invested_cash[month_str] = invested_this_month

            # --- Buy / Avg Down ---
            for symbol, pct, close in daily_etfs:
                if buys_today >= self.max_daily_buys:
                    break

                net_worth = cash + sum(info["shares"] * info.get("current_close", info["buy_price"])
                                       for info in portfolio.values())
                buy_amount = net_worth / buy_divisor

                max_allowance =  cash + hydration
                buy_amount = min(buy_amount , max_allowance)

                if symbol not in portfolio:
                    shares = update_portfolio_for_buy(portfolio, symbol, close, buy_amount)
                    action = "BUY"
                else:
                    buy_price = portfolio[symbol]["buy_price"]
                    loss_pct = (buy_price - close) / buy_price * 100
                    if loss_pct > self.avg_down_threshold:
                        shares = update_portfolio_for_avg_down(portfolio, symbol, close, buy_amount)
                        action = "BUY_AVERAGE_DOWN"
                    else:
                        continue
                if shares > 0:
                    trades.append({
                        "date": date,
                        "symbol": symbol,
                        "action": action,
                        "price": close,
                        "shares": shares,
                        "profit": 0,
                        "hold_days": portfolio.get(symbol, {}).get("hold_days", 0)
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
                        profit = (open_price - buy_price) * portfolio[symbol]["shares"]
                        trades.append({"date": date, "symbol": symbol, "action": "SELL_TRAILING",
                                       "price": open_price, "shares": portfolio[symbol]["shares"] , "profit": profit, "hold_days" : portfolio[symbol]["hold_days"]})
                        cash += portfolio[symbol]["shares"] * open_price
                        # cash -= 20
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
            cash_history.append({"Date": date, "Cash": cash})

        xirr = xirr_calculator(monthly_invested_cash, net_worth_history)
        return {
            "trades": trades,
            "net_worth": pd.DataFrame(net_worth_history),
            "monthly_invested_cash": monthly_invested_cash,
            "cash_history": cash_history,
            "portfolio": portfolio,
            "cash" : cash,
            "xirr" : xirr
        }
