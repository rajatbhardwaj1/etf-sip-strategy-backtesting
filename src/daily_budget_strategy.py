import pandas as pd
from typing import Dict, List, Optional


class DailyAdaptiveMonthlyBudget:
    """
    Per-fund, single-fund strategy: you commit a fixed monthly budget to a
    fund (e.g. Nifty50 = 10k/month). Each trading day the algorithm decides
    how much of the REMAINING monthly budget to deploy today, based on the
    fund's own NAV relative to its recent moving average:

    - NAV below its MA (relatively cheap vs its own recent trend) -> deploy
      more than the flat daily share.
    - NAV above its MA (relatively expensive) -> deploy less.
    - Always converges to depositing exactly 100% of the monthly budget by
      the last trading day of the month (algorithm only controls WHEN within
      the month the money goes in, never whether the full budget is used).

    This is causal: on day t it only uses NAV/MA data available up to and
    including day t, and the remaining budget / remaining trading-day count
    for the current month (no lookahead into future days' prices).
    """

    def __init__(
        self,
        ma_window: int = 20,
        sensitivity: float = 8.0,
        min_multiplier: float = 0.3,
        max_multiplier: float = 2.5,
    ):
        self.ma_window = ma_window
        self.sensitivity = sensitivity
        self.min_multiplier = min_multiplier
        self.max_multiplier = max_multiplier

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

        # Trading days per month, known in advance from the data (calendar
        # is known; we are not looking at future PRICES, just counting days).
        df["month_str"] = df["Date"].dt.strftime("%Y-%m")
        days_in_month = df.groupby("month_str")["Date"].transform("count")
        df["days_in_month"] = days_in_month
        df["day_index_in_month"] = df.groupby("month_str").cumcount()

        units = 0.0
        monthly_invested = {}
        trades = []
        net_worth_history = []

        remaining_budget = 0.0
        remaining_days = 0
        current_month = None

        for _, row in df.iterrows():
            month_str = row["month_str"]
            if month_str != current_month:
                current_month = month_str
                remaining_budget = monthly_budget
                remaining_days = int(row["days_in_month"] - row["day_index_in_month"])
                monthly_invested[month_str] = 0.0

            base = remaining_budget / remaining_days if remaining_days > 0 else 0.0

            pct_dev = row["pct_dev"]
            if pd.notna(pct_dev):
                multiplier = 1 - (self.sensitivity / 100.0) * pct_dev
                multiplier = max(self.min_multiplier, min(self.max_multiplier, multiplier))
            else:
                multiplier = 1.0

            invest_today = base * multiplier
            invest_today = min(invest_today, remaining_budget)

            if remaining_days == 1:
                invest_today = remaining_budget

            nav = row["NAV"]
            bought_units = invest_today / nav if nav > 0 and invest_today > 0 else 0.0
            units += bought_units
            remaining_budget -= invest_today
            remaining_days -= 1

            monthly_invested[month_str] += invest_today
            trades.append({
                "date": row["Date"],
                "nav": nav,
                "pct_dev": pct_dev,
                "amount": invest_today,
                "units": bought_units,
            })
            net_worth_history.append({"Date": row["Date"], "NetWorth": units * nav})

        return {
            "trades": trades,
            "net_worth": pd.DataFrame(net_worth_history),
            "monthly_invested": monthly_invested,
            "units": units,
            "final_nav": df["NAV"].iloc[-1] if not df.empty else None,
        }


class LumpSumMonthlyBudget:
    """Baseline: deploy the full monthly budget on the first trading day of each month."""

    def generate_signals(
        self,
        nav_df: pd.DataFrame,
        monthly_budget: float,
        start_date: str = None,
        end_date: str = None,
    ) -> Dict:
        df = nav_df.copy().sort_values("Date").reset_index(drop=True)
        if start_date:
            df = df[df["Date"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["Date"] <= pd.to_datetime(end_date)]
        df = df.reset_index(drop=True)
        df["month_str"] = df["Date"].dt.strftime("%Y-%m")

        units = 0.0
        monthly_invested = {}
        net_worth_history = []
        current_month = None

        for _, row in df.iterrows():
            month_str = row["month_str"]
            if month_str != current_month:
                current_month = month_str
                nav = row["NAV"]
                units += monthly_budget / nav
                monthly_invested[month_str] = monthly_budget
            net_worth_history.append({"Date": row["Date"], "NetWorth": units * row["NAV"]})

        return {
            "net_worth": pd.DataFrame(net_worth_history),
            "monthly_invested": monthly_invested,
            "units": units,
        }


class FlatDailyMonthlyBudget:
    """Baseline: spread the monthly budget evenly across every trading day of the month."""

    def generate_signals(
        self,
        nav_df: pd.DataFrame,
        monthly_budget: float,
        start_date: str = None,
        end_date: str = None,
    ) -> Dict:
        df = nav_df.copy().sort_values("Date").reset_index(drop=True)
        if start_date:
            df = df[df["Date"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["Date"] <= pd.to_datetime(end_date)]
        df = df.reset_index(drop=True)
        df["month_str"] = df["Date"].dt.strftime("%Y-%m")
        days_in_month = df.groupby("month_str")["Date"].transform("count")
        df["days_in_month"] = days_in_month

        units = 0.0
        monthly_invested = {}
        net_worth_history = []

        for _, row in df.iterrows():
            month_str = row["month_str"]
            per_day = monthly_budget / row["days_in_month"]
            nav = row["NAV"]
            units += per_day / nav
            monthly_invested[month_str] = monthly_invested.get(month_str, 0.0) + per_day
            net_worth_history.append({"Date": row["Date"], "NetWorth": units * nav})

        return {
            "net_worth": pd.DataFrame(net_worth_history),
            "monthly_invested": monthly_invested,
            "units": units,
        }
