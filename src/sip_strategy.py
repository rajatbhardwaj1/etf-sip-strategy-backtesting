import datetime
import pandas as pd
from typing import Dict

from src.utils import xirr_calculator
from src.utils import (
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
        increment: float = 15,
        buy_divisor: int = 40,
        hydration: float = 0,
        hydration_increment: float = 0,
        sell_fee: float = 20,
        avg_down_priority: bool = False,
        avg_down_extra_slots: int = 0,
        avg_down_scan_all: bool = False,
        max_positions: int = 0,
        hydration_mode: str = "overdraft",
    ):
        self.dma_window = dma_window
        self.profit_threshold = profit_threshold
        self.trailing_stop = trailing_stop
        self.max_daily_buys = max_daily_buys
        self.avg_down_threshold = avg_down_threshold
        self.increment = increment
        # Each buy is net_worth/buy_divisor, so this sets how fast the SIP is
        # deployed. Previously hardcoded at 40 inside generate_signals, which
        # made it the one parameter that could not be tuned or swept.
        self.buy_divisor = buy_divisor
        self.hydration = hydration
        self.hydration_increment = hydration_increment
        self.sell_fee = sell_fee

        # --- Averaging-down behaviour -------------------------------------
        # By default averaging down is opportunistic: a held position is only
        # topped up if it happens to rank in the day's top-3 most-fallen vs
        # DMA *and* wins the single daily buy slot. A position sitting quietly
        # below cost never ranks in a short-term momentum screen, so it is
        # never averaged and its break-even bar never comes down - which is
        # the opposite of what a no-stop-loss, keep-averaging thesis needs.
        #
        # avg_down_priority   : consider held losers before opening anything new.
        # avg_down_extra_slots: daily buys reserved for averaging, on top of
        #                       max_daily_buys, so averaging never starves.
        # avg_down_scan_all   : trigger on drawdown from average cost across
        #                       the whole book, ignoring the DMA ranking.
        # max_positions       : stop opening new names past this count, so
        #                       capital concentrates on existing ones.
        self.avg_down_priority = avg_down_priority
        self.avg_down_extra_slots = avg_down_extra_slots
        self.avg_down_scan_all = avg_down_scan_all
        self.max_positions = max_positions

        # The deployed bot and this backtester historically meant opposite
        # things by "hydration", which only matters once it is non-zero:
        #
        #   "overdraft" (this file's original behaviour) - hydration lifts the
        #       spending cap above available cash, so cash may go negative. The
        #       borrowed money is never counted as capital, and no interest is
        #       charged, which makes it free leverage.
        #   "live" (src/strategy.py in strategy-automation) - hydration is a
        #       loan that is ALREADY sitting in the broker cash balance. The
        #       full cash is spendable, and the loan is subtracted from the
        #       sizing base so positions are not sized as though the loan were
        #       the account's own capital.
        #
        # Use "live" to backtest what is actually deployed. The caller must
        # also seed capital=hydration and repay it from the final net worth,
        # or borrowed money is reported as profit.
        self.hydration_mode = hydration_mode

    def generate_signals(
        self,
        etf_data: Dict[str, pd.DataFrame],
        capital: float = 0,
        sip_amount: float = 30000
    ) -> Dict[str, pd.DataFrame]:

        portfolio = {}
        monthly_invested_cash = {}
        trades = []
        net_worth_history = []
        cash_history = []
        cash = capital
        hydration = self.hydration
        buy_divisor = self.buy_divisor
        hydration_increment = self.hydration_increment
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
            # Candidate list: by default the day's most-fallen ETFs, in that
            # order, exactly as before. The options below reorder it or widen
            # it so averaging down is driven by distance from cost rather than
            # by momentum ranking.
            candidates = list(daily_etfs)

            if self.avg_down_scan_all:
                # Every held position far enough below its average cost is a
                # candidate, whether or not it ranks today - this is what makes
                # the break-even bar actually come down.
                ranked = {sym for sym, _, _ in candidates}
                extra = []
                for sym in portfolio:
                    if sym in ranked:
                        continue
                    df_sym = percent_changes[sym]
                    row_sym = df_sym[df_sym["Date"] == date]
                    if row_sym.empty:
                        continue
                    close_sym = row_sym["Close"].values[0]
                    buy_price = portfolio[sym]["buy_price"]
                    loss_pct = (buy_price - close_sym) / buy_price * 100
                    if loss_pct > self.avg_down_threshold:
                        extra.append((sym, -loss_pct, close_sym))
                # Deepest drawdown from cost first.
                candidates += sorted(extra, key=lambda c: c[1])

            if self.avg_down_priority:
                # Held losers ahead of brand-new names.
                candidates.sort(key=lambda c: 0 if c[0] in portfolio else 1)

            avg_down_budget = self.avg_down_extra_slots
            for symbol, pct, close in candidates:
                is_held = symbol in portfolio
                # A held candidate may draw on the reserved averaging budget;
                # a new name only ever uses a normal daily slot.
                if is_held and avg_down_budget > 0:
                    pass
                elif buys_today >= self.max_daily_buys:
                    if not (is_held and avg_down_budget > 0):
                        continue
                # Only buy weakness. A scan_all candidate carries -loss_pct, so
                # it is negative by construction and passes this too.
                if pct > 0:
                    continue
                if not is_held and self.max_positions and len(portfolio) >= self.max_positions:
                    continue

                net_worth = cash + sum(info["shares"] * info.get("current_close", info["buy_price"])
                                       for info in portfolio.values())
                if self.hydration_mode == "live":
                    # Loan already inside cash: exclude it from the sizing base,
                    # and treat cash alone as the ceiling.
                    buy_amount = max(net_worth - hydration, 0) / buy_divisor
                    max_allowance = cash
                else:
                    buy_amount = net_worth / buy_divisor
                    max_allowance = cash + hydration
                buy_amount = min(buy_amount , max_allowance)

                if not is_held:
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
                    if action == "BUY_AVERAGE_DOWN" and avg_down_budget > 0:
                        avg_down_budget -= 1
                    else:
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
                        cash -= self.sell_fee
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
