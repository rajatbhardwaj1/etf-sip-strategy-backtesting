import pandas as pd
from typing import Dict, List
from src.utils import xirr_calculator


def load_mf_nav(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["Date"])
    df["NAV"] = pd.to_numeric(df["NAV"], errors="coerce")
    df = df.dropna(subset=["Date", "NAV"]).sort_values("Date").reset_index(drop=True)
    return df


def align_nav_data(nav_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Restrict all funds to the common set of dates (inner join on Date),
    so every fund has a NAV on every date used by the strategy.
    """
    common_dates = None
    for df in nav_data.values():
        dates = set(df["Date"])
        common_dates = dates if common_dates is None else (common_dates & dates)

    aligned = {}
    for symbol, df in nav_data.items():
        aligned[symbol] = df[df["Date"].isin(common_dates)].sort_values("Date").reset_index(drop=True)
    return aligned


class MFValueTiltSIP:
    """
    Buy-only, allocation-timing strategy for a fixed basket of mutual funds.

    Each month, a fixed SIP quota is split across the funds. The split is
    tilted toward funds trading below their own trailing moving average
    (relatively 'cheap' vs their own trend) and away from funds trading
    well above it, subject to min/max weight bounds so no fund is ever
    fully dropped or over-concentrated.

    If every fund is simultaneously overextended above its MA, only a
    floor fraction of the quota is deployed and the rest is banked as
    'dry powder' (capped) to be deployed on the next real dip.

    No selling — pure accumulation, matching a long-term mutual fund SIP.
    """

    def __init__(
        self,
        ma_window: int = 50,
        min_weight: float = 0.15,
        max_weight: float = 0.50,
        tilt_strength: float = 3.0,
        overextended_threshold: float = 2.0,
        floor_fraction: float = 0.6,
        dip_threshold: float = -3.0,
        max_dry_powder_months: float = 2.0,
    ):
        self.ma_window = ma_window
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.tilt_strength = tilt_strength
        self.overextended_threshold = overextended_threshold
        self.floor_fraction = floor_fraction
        self.dip_threshold = dip_threshold
        self.max_dry_powder_months = max_dry_powder_months

    def _prepare(self, nav_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        prepared = {}
        for symbol, df in nav_data.items():
            df = df.copy()
            df["MA"] = df["NAV"].rolling(window=self.ma_window, min_periods=self.ma_window).mean()
            df["pct_dev"] = (df["NAV"] - df["MA"]) / df["MA"] * 100
            prepared[symbol] = df
        return prepared

    def _weights_for_date(self, devs: Dict[str, float]) -> Dict[str, float]:
        symbols = list(devs.keys())
        n = len(symbols)
        base = 1.0 / n
        mean_dev = sum(devs.values()) / n

        raw = {}
        for s in symbols:
            centered = devs[s] - mean_dev
            w = base - (self.tilt_strength / 100.0) * centered
            raw[s] = max(self.min_weight, min(self.max_weight, w))

        total = sum(raw.values())
        return {s: w / total for s, w in raw.items()}

    def generate_signals(
        self,
        nav_data: Dict[str, pd.DataFrame],
        sip_amount: float = 30000,
        annual_increment_pct: float = 0.0,
        start_date: str = None,
        end_date: str = None,
    ) -> Dict:
        nav_data = align_nav_data(nav_data)
        prepared = self._prepare(nav_data)

        symbols = list(prepared.keys())
        ref = prepared[symbols[0]]
        all_dates = sorted(ref["Date"])
        if start_date:
            all_dates = [d for d in all_dates if d >= pd.to_datetime(start_date)]
        if end_date:
            all_dates = [d for d in all_dates if d <= pd.to_datetime(end_date)]

        nav_lookup = {s: prepared[s].set_index("Date") for s in symbols}

        units = {s: 0.0 for s in symbols}
        monthly_invested_cash = {}
        trades = []
        net_worth_history = []
        dry_powder = 0.0
        current_sip = sip_amount

        last_month = None
        last_year = None
        first_year = True

        for date in all_dates:
            row_by_symbol = {}
            valid = True
            for s in symbols:
                if date not in nav_lookup[s].index:
                    valid = False
                    break
                row_by_symbol[s] = nav_lookup[s].loc[date]
            if not valid:
                continue

            if last_year != date.year:
                if not first_year and annual_increment_pct:
                    current_sip *= (1 + annual_increment_pct / 100)
                last_year = date.year
                first_year = False

            month_str = date.strftime("%Y-%m")
            if date.month != last_month:
                last_month = date.month

                devs = {s: row_by_symbol[s]["pct_dev"] for s in symbols}
                have_ma = all(pd.notna(v) for v in devs.values())

                quota = current_sip
                deploy_amount = quota
                note = "NORMAL"

                if have_ma:
                    all_overextended = all(v > self.overextended_threshold for v in devs.values())
                    any_dip = any(v < self.dip_threshold for v in devs.values())

                    if all_overextended:
                        deploy_amount = quota * self.floor_fraction
                        dry_powder = min(
                            dry_powder + (quota - deploy_amount),
                            self.max_dry_powder_months * quota,
                        )
                        note = "OVEREXTENDED_BANK"
                    elif any_dip and dry_powder > 0:
                        deploy_amount = quota + dry_powder
                        dry_powder = 0.0
                        note = "DIP_DEPLOY"

                    weights = self._weights_for_date(devs)
                else:
                    weights = {s: 1.0 / len(symbols) for s in symbols}

                monthly_invested_cash[month_str] = deploy_amount

                for s in symbols:
                    amount = deploy_amount * weights[s]
                    nav = row_by_symbol[s]["NAV"]
                    bought_units = amount / nav
                    units[s] += bought_units
                    trades.append({
                        "date": date,
                        "symbol": s,
                        "action": "BUY",
                        "nav": nav,
                        "amount": amount,
                        "units": bought_units,
                        "weight": weights[s],
                        "note": note,
                    })

            net_worth = sum(units[s] * row_by_symbol[s]["NAV"] for s in symbols)
            net_worth_history.append({"Date": date, "NetWorth": net_worth})

        xirr = xirr_calculator(monthly_invested_cash, net_worth_history)
        return {
            "trades": trades,
            "net_worth": pd.DataFrame(net_worth_history),
            "monthly_invested_cash": monthly_invested_cash,
            "units": units,
            "dry_powder_remaining": dry_powder,
            "xirr": xirr,
        }


class MFFlatSIP:
    """Baseline: fixed equal-split monthly SIP across the funds, no tilting."""

    def generate_signals(
        self,
        nav_data: Dict[str, pd.DataFrame],
        sip_amount: float = 30000,
        annual_increment_pct: float = 0.0,
        start_date: str = None,
        end_date: str = None,
    ) -> Dict:
        nav_data = align_nav_data(nav_data)
        symbols = list(nav_data.keys())
        n = len(symbols)
        nav_lookup = {s: nav_data[s].set_index("Date") for s in symbols}

        ref = nav_data[symbols[0]]
        all_dates = sorted(ref["Date"])
        if start_date:
            all_dates = [d for d in all_dates if d >= pd.to_datetime(start_date)]
        if end_date:
            all_dates = [d for d in all_dates if d <= pd.to_datetime(end_date)]

        units = {s: 0.0 for s in symbols}
        monthly_invested_cash = {}
        net_worth_history = []
        current_sip = sip_amount
        last_month = None
        last_year = None
        first_year = True

        for date in all_dates:
            row_by_symbol = {}
            valid = True
            for s in symbols:
                if date not in nav_lookup[s].index:
                    valid = False
                    break
                row_by_symbol[s] = nav_lookup[s].loc[date]
            if not valid:
                continue

            if last_year != date.year:
                if not first_year and annual_increment_pct:
                    current_sip *= (1 + annual_increment_pct / 100)
                last_year = date.year
                first_year = False

            month_str = date.strftime("%Y-%m")
            if date.month != last_month:
                last_month = date.month
                monthly_invested_cash[month_str] = current_sip
                for s in symbols:
                    amount = current_sip / n
                    nav = row_by_symbol[s]["NAV"]
                    units[s] += amount / nav

            net_worth = sum(units[s] * row_by_symbol[s]["NAV"] for s in symbols)
            net_worth_history.append({"Date": date, "NetWorth": net_worth})

        xirr = xirr_calculator(monthly_invested_cash, net_worth_history)
        return {
            "net_worth": pd.DataFrame(net_worth_history),
            "monthly_invested_cash": monthly_invested_cash,
            "units": units,
            "xirr": xirr,
        }
