import pandas as pd
from typing import Dict


class DipWaitBudget:
    """
    Pure 'wait for the dip' strategy, exactly as specified:

    - Each month a fixed budget is added to an accumulating pool
      (unspent money from prior months carries forward indefinitely,
      it is never forfeited or forced out).
    - Each trading day, compute NAV deviation from its own N-day
      moving average: pct_dev = (NAV - MA) / MA * 100.
    - If pct_dev <= -deep_threshold (e.g. -1%): invest 100% of the
      *entire currently available pool* (this month's budget + all
      carried-over backlog) that day.
    - Elif pct_dev <= -shallow_threshold (e.g. -0.5%): invest 50% of
      the currently available pool that day.
    - Else: invest nothing; the pool keeps accumulating.

    This is causal (only uses NAV/MA known up to and including today)
    and never forces deployment — money can sit in cash indefinitely
    if the dip conditions are never met.
    """

    def __init__(
        self,
        ma_window: int = 10,
        shallow_threshold: float = 0.5,
        deep_threshold: float = 1.0,
        shallow_fraction: float = 0.5,
        deep_fraction: float = 1.0,
    ):
        self.ma_window = ma_window
        self.shallow_threshold = shallow_threshold
        self.deep_threshold = deep_threshold
        self.shallow_fraction = shallow_fraction
        self.deep_fraction = deep_fraction

    def generate_signals(
        self,
        nav_df: pd.DataFrame,
        monthly_budget: float,
        start_date: str = None,
        end_date: str = None,
    ) -> Dict:
        df = nav_df.copy().sort_values("Date").reset_index(drop=True)
        df["MA"] = df["NAV"].rolling(window=self.ma_window, min_periods=self.ma_window).mean()
        df["pct_dev"] = (df["NAV"] - df["MA"]) / df["MA"] * 100

        if start_date:
            df = df[df["Date"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["Date"] <= pd.to_datetime(end_date)]
        df = df.reset_index(drop=True)
        df["month_str"] = df["Date"].dt.strftime("%Y-%m")

        units = 0.0
        pool = 0.0
        monthly_invested = {}
        monthly_added = {}
        trades = []
        net_worth_history = []
        idle_days_run = 0
        idle_run_stats = []
        current_month = None

        for _, row in df.iterrows():
            month_str = row["month_str"]
            if month_str != current_month:
                current_month = month_str
                pool += monthly_budget
                monthly_added[month_str] = monthly_budget
                monthly_invested.setdefault(month_str, 0.0)

            pct_dev = row["pct_dev"]
            invest_today = 0.0
            if pd.notna(pct_dev):
                if pct_dev <= -self.deep_threshold:
                    invest_today = pool * self.deep_fraction
                elif pct_dev <= -self.shallow_threshold:
                    invest_today = pool * self.shallow_fraction

            nav = row["NAV"]
            if invest_today > 0 and nav > 0:
                bought_units = invest_today / nav
                units += bought_units
                pool -= invest_today
                monthly_invested[month_str] += invest_today
                idle_run_stats.append(idle_days_run)
                idle_days_run = 0
                trades.append({"date": row["Date"], "nav": nav, "pct_dev": pct_dev, "amount": invest_today, "units": bought_units})
            else:
                idle_days_run += 1

            net_worth_history.append({
                "Date": row["Date"],
                "NetWorth": units * nav + pool,
                "InvestedNetWorth": units * nav,
                "Pool": pool,
            })

        if idle_days_run > 0:
            idle_run_stats.append(idle_days_run)

        return {
            "trades": trades,
            "net_worth": pd.DataFrame(net_worth_history),
            "monthly_invested": monthly_invested,
            "monthly_added": monthly_added,
            "units": units,
            "final_pool": pool,
            "idle_run_stats": idle_run_stats,
            "max_idle_run_days": max(idle_run_stats) if idle_run_stats else 0,
        }
