"""
Analytics helpers for the interactive backtest report.

Everything here is pure pandas/numpy so it can be unit tested without plotting.
All money values are INR.
"""
from typing import Dict, Optional

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def build_flow_series(dates: pd.Series, monthly_invested_cash: Dict[str, float]) -> pd.Series:
    """
    Map monthly SIP amounts onto the first available trading date of each month.

    Returns a Series indexed like `dates` holding the external cash inflow for
    that day (0 on days with no inflow).
    """
    dates = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    flows = pd.Series(0.0, index=dates.index)
    month_keys = dates.dt.strftime("%Y-%m")
    first_idx = month_keys.drop_duplicates(keep="first")
    for idx, month in first_idx.items():
        flows.iloc[idx] = float(monthly_invested_cash.get(month, 0.0))
    return flows


def build_equity_frame(
    net_worth_df: pd.DataFrame,
    monthly_invested_cash: Dict[str, float],
    cash_history_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Core per-day frame used by every chart.

    Columns: Date, NetWorth, Flow, Invested (cumulative capital put in),
             Cash, Holdings, Ret (flow adjusted daily return), TWR (index=100),
             Drawdown (on TWR, %), NetWorthDrawdown (%), Profit (NetWorth - Invested).
    """
    df = net_worth_df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    df["Flow"] = build_flow_series(df["Date"], monthly_invested_cash)
    df["Invested"] = df["Flow"].cumsum()

    if cash_history_df is not None and not cash_history_df.empty:
        cash = cash_history_df.copy()
        cash["Date"] = pd.to_datetime(cash["Date"])
        df = df.merge(cash[["Date", "Cash"]], on="Date", how="left")
    else:
        df["Cash"] = np.nan
    df["Holdings"] = df["NetWorth"] - df["Cash"]

    # Flow adjusted daily return: money added by the SIP is not performance.
    prev_nw = df["NetWorth"].shift(1)
    ret = (df["NetWorth"] - prev_nw - df["Flow"]) / prev_nw.replace(0, np.nan)
    df["Ret"] = ret.fillna(0.0).replace([np.inf, -np.inf], 0.0)
    df["TWR"] = 100.0 * (1.0 + df["Ret"]).cumprod()

    df["Drawdown"] = drawdown_pct(df["TWR"])
    df["NetWorthDrawdown"] = drawdown_pct(df["NetWorth"])
    df["Profit"] = df["NetWorth"] - df["Invested"]
    return df


def drawdown_pct(series: pd.Series) -> pd.Series:
    """Percentage drawdown from the running peak."""
    s = pd.Series(series).astype(float)
    peak = s.cummax().replace(0, np.nan)
    return ((s - peak) / peak * 100.0).fillna(0.0)


def max_drawdown_window(df: pd.DataFrame, col: str = "Drawdown"):
    """Return (trough_date, depth_pct, peak_date, recovery_date_or_None)."""
    if df.empty:
        return None, 0.0, None, None
    trough_i = int(df[col].idxmin())
    depth = float(df[col].iloc[trough_i])
    base_col = "TWR" if col == "Drawdown" else "NetWorth"
    before = df.iloc[: trough_i + 1]
    peak_i = int(before[base_col].idxmax()) if not before.empty else 0
    peak_val = float(df[base_col].iloc[peak_i])
    after = df.iloc[trough_i:]
    rec = after[after[base_col] >= peak_val]
    recovery = rec["Date"].iloc[0] if not rec.empty else None
    return df["Date"].iloc[trough_i], depth, df["Date"].iloc[peak_i], recovery


def xirr(cashflows: pd.Series) -> Optional[float]:
    """
    Annualised XIRR from a date indexed Series of cashflows
    (negative = money in, positive = money out/final value).
    Solved by bisection so it never depends on a good initial guess.
    """
    cf = cashflows.dropna()
    cf = cf[cf != 0]
    if len(cf) < 2 or not (cf < 0).any() or not (cf > 0).any():
        return None
    t0 = cf.index[0]
    years = np.array([(d - t0).days / 365.25 for d in cf.index])
    values = cf.to_numpy(dtype=float)

    def npv(rate: float) -> float:
        return float(np.sum(values / np.power(1.0 + rate, years)))

    lo, hi = -0.9999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if np.isnan(f_lo) or np.isnan(f_hi) or f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def portfolio_xirr(equity: pd.DataFrame) -> Optional[float]:
    """XIRR of the SIP schedule against the final net worth."""
    flows = equity.loc[equity["Flow"] > 0, ["Date", "Flow"]]
    cf = pd.Series(-flows["Flow"].to_numpy(), index=pd.to_datetime(flows["Date"]))
    final_date = pd.to_datetime(equity["Date"].iloc[-1])
    final_value = float(equity["NetWorth"].iloc[-1])
    cf = pd.concat([cf, pd.Series([final_value], index=[final_date])])
    cf = cf.groupby(level=0).sum().sort_index()
    return xirr(cf)


def summary_metrics(equity: pd.DataFrame, label: str = "Strategy") -> Dict[str, float]:
    """Headline risk/return numbers for one equity curve."""
    if equity.empty:
        return {}
    rets = equity["Ret"].to_numpy()
    days = (equity["Date"].iloc[-1] - equity["Date"].iloc[0]).days or 1
    years = days / 365.25

    total_twr = equity["TWR"].iloc[-1] / equity["TWR"].iloc[0] - 1.0
    cagr = (1.0 + total_twr) ** (1.0 / years) - 1.0 if total_twr > -1 else -1.0
    vol = float(np.std(rets, ddof=1)) * np.sqrt(TRADING_DAYS) if len(rets) > 2 else 0.0
    downside = rets[rets < 0]
    dvol = float(np.std(downside, ddof=1)) * np.sqrt(TRADING_DAYS) if len(downside) > 2 else 0.0
    _, max_dd, _, _ = max_drawdown_window(equity, "Drawdown")

    invested = float(equity["Invested"].iloc[-1])
    final = float(equity["NetWorth"].iloc[-1])
    return {
        "label": label,
        "invested": invested,
        "final_value": final,
        "profit": final - invested,
        "multiple": (final / invested) if invested else np.nan,
        "xirr": portfolio_xirr(equity),
        "cagr": cagr,
        "total_return": total_twr,
        "volatility": vol,
        "sharpe": (cagr / vol) if vol else np.nan,
        "sortino": (cagr / dvol) if dvol else np.nan,
        "max_drawdown": max_dd,
        "calmar": (cagr / abs(max_dd / 100.0)) if max_dd else np.nan,
        "best_day": float(np.max(rets) * 100) if len(rets) else 0.0,
        "worst_day": float(np.min(rets) * 100) if len(rets) else 0.0,
        "positive_days": float((rets > 0).mean() * 100) if len(rets) else 0.0,
        "days": days,
        "years": years,
    }


def monthly_return_table(equity: pd.DataFrame) -> pd.DataFrame:
    """Year x month table of flow adjusted returns in %."""
    df = equity[["Date", "TWR"]].copy()
    df = df.set_index("Date")
    monthly = df["TWR"].resample("ME").last().pct_change() * 100.0
    first = df["TWR"].resample("ME").last()
    if len(first) > 0:
        start = df["TWR"].iloc[0]
        monthly.iloc[0] = (first.iloc[0] / start - 1.0) * 100.0
    out = pd.DataFrame({
        "Year": monthly.index.year,
        "Month": monthly.index.month,
        "Return": monthly.to_numpy(),
    })
    return out.pivot(index="Year", columns="Month", values="Return").sort_index(ascending=False)


def yearly_returns(equity: pd.DataFrame) -> pd.DataFrame:
    """Calendar year flow adjusted returns in %."""
    df = equity[["Date", "TWR"]].set_index("Date")
    yearly = df["TWR"].resample("YE").last()
    prev = df["TWR"].resample("YE").last().shift(1)
    prev.iloc[0] = df["TWR"].iloc[0]
    pct = (yearly / prev - 1.0) * 100.0
    return pd.DataFrame({"Year": yearly.index.year, "Return": pct.to_numpy()})


def build_benchmark_frame(nifty_df: pd.DataFrame, monthly_invested_cash: Dict[str, float]) -> pd.DataFrame:
    """
    Equity frame for the Nifty SIP benchmark, shaped exactly like the strategy
    frame so the same metric code works on both.
    """
    df = nifty_df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    value_col = "InvestedValue" if "InvestedValue" in df.columns else "Close"
    out = pd.DataFrame({"Date": df["Date"], "NetWorth": df[value_col].astype(float)})
    out["Flow"] = build_flow_series(out["Date"], monthly_invested_cash)
    out["Invested"] = out["Flow"].cumsum()
    out["Cash"] = 0.0
    out["Holdings"] = out["NetWorth"]
    prev = out["NetWorth"].shift(1)
    out["Ret"] = ((out["NetWorth"] - prev - out["Flow"]) / prev.replace(0, np.nan)).fillna(0.0)
    out["Ret"] = out["Ret"].replace([np.inf, -np.inf], 0.0)
    out["TWR"] = 100.0 * (1.0 + out["Ret"]).cumprod()
    out["Drawdown"] = drawdown_pct(out["TWR"])
    out["NetWorthDrawdown"] = drawdown_pct(out["NetWorth"])
    out["Profit"] = out["NetWorth"] - out["Invested"]
    return out


def prepare_trades(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Normalise the trade log: types, value, side flags."""
    if trades_df is None or trades_df.empty:
        return pd.DataFrame(
            columns=["date", "symbol", "action", "price", "shares", "profit", "hold_days", "value", "side", "profit_pct"]
        )
    df = trades_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    for col in ("price", "shares", "profit", "hold_days"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = np.nan
    df["action"] = df["action"].astype(str)
    df["value"] = df["price"] * df["shares"]
    df["side"] = np.where(df["action"].str.contains("SELL"), "SELL", "BUY")
    cost = df["value"] - df["profit"]
    df["profit_pct"] = np.where(df["side"] == "SELL", df["profit"] / cost.replace(0, np.nan) * 100.0, np.nan)
    return df.sort_values("date").reset_index(drop=True)


def trade_stats(trades: pd.DataFrame) -> Dict[str, float]:
    """Win rate, profit factor, expectancy and friends over closed (SELL) trades."""
    if trades.empty:
        return {}
    sells = trades[trades["side"] == "SELL"]
    buys = trades[trades["side"] == "BUY"]
    wins = sells[sells["profit"] > 0]
    losses = sells[sells["profit"] <= 0]
    gross_win = float(wins["profit"].sum())
    gross_loss = float(abs(losses["profit"].sum()))
    # This strategy only exits on a trailing stop that arms above a profit
    # threshold, so a losing exit is impossible by construction: gross_loss is 0
    # and the ratio is undefined rather than infinite. Losses sit unrealized in
    # the open book, which is what mark_to_market_stats() measures.
    return {
        "total_trades": int(len(trades)),
        "buys": int(len(buys)),
        "sells": int(len(sells)),
        "losing_sells": int(len(losses)),
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "realized_profit": float(sells["profit"].sum()),
        "win_rate": float(len(wins) / len(sells) * 100) if len(sells) else np.nan,
        "avg_win": float(wins["profit"].mean()) if len(wins) else 0.0,
        "avg_loss": float(losses["profit"].mean()) if len(losses) else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss else None,
        "expectancy": float(sells["profit"].mean()) if len(sells) else 0.0,
        "avg_hold_days": float(sells["hold_days"].mean()) if len(sells) else np.nan,
        "best_trade": float(sells["profit"].max()) if len(sells) else 0.0,
        "worst_trade": float(sells["profit"].min()) if len(sells) else 0.0,
        "symbols_traded": int(trades["symbol"].nunique()),
        "turnover": float(trades["value"].sum()),
    }


def symbol_pnl(trades: pd.DataFrame, portfolio: Optional[Dict[str, Dict]] = None) -> pd.DataFrame:
    """Per symbol realized PnL, open PnL and trade counts."""
    if trades.empty:
        return pd.DataFrame(columns=["symbol", "realized", "open_pnl", "total", "trades", "buys", "sells", "invested"])
    grp = trades.groupby("symbol")
    out = pd.DataFrame({
        "realized": grp.apply(lambda g: g.loc[g["side"] == "SELL", "profit"].sum()),
        "trades": grp.size(),
        "buys": grp.apply(lambda g: int((g["side"] == "BUY").sum())),
        "sells": grp.apply(lambda g: int((g["side"] == "SELL").sum())),
        "invested": grp.apply(lambda g: g.loc[g["side"] == "BUY", "value"].sum()),
    }).reset_index()

    open_pnl, open_value = [], []
    portfolio = portfolio or {}
    for sym in out["symbol"]:
        info = portfolio.get(sym)
        if info:
            close = info.get("current_close", info.get("buy_price", 0.0))
            pnl = (close - info.get("buy_price", 0.0)) * info.get("shares", 0)
            open_pnl.append(float(pnl))
            open_value.append(float(close * info.get("shares", 0)))
        else:
            open_pnl.append(0.0)
            open_value.append(0.0)
    out["open_pnl"] = open_pnl
    out["open_value"] = open_value
    out["total"] = out["realized"] + out["open_pnl"]
    return out.sort_values("total", ascending=False).reset_index(drop=True)


def rolling_metrics(equity: pd.DataFrame, window: int = TRADING_DAYS) -> pd.DataFrame:
    """Rolling annualised return, volatility and Sharpe over `window` trading days."""
    df = equity[["Date", "Ret", "TWR"]].copy()
    df["RollingReturn"] = (df["TWR"] / df["TWR"].shift(window) - 1.0) * 100.0
    df["RollingVol"] = df["Ret"].rolling(window).std(ddof=1) * np.sqrt(TRADING_DAYS) * 100.0
    df["RollingSharpe"] = df["RollingReturn"] / df["RollingVol"].replace(0, np.nan)
    return df


def mark_to_market_stats(trades: pd.DataFrame, portfolio: Optional[Dict[str, Dict]] = None) -> Dict[str, float]:
    """
    Position level view that counts the open book, not just closed trades.

    A strategy that never exits at a loss has an undefined profit factor on
    realized trades alone. Adding the unrealized marks gives the honest number.
    """
    portfolio = portfolio or {}
    sells = trades[trades["side"] == "SELL"] if not trades.empty else trades
    realized_win = float(sells.loc[sells["profit"] > 0, "profit"].sum()) if len(sells) else 0.0
    realized_loss = float(abs(sells.loc[sells["profit"] <= 0, "profit"].sum())) if len(sells) else 0.0

    open_rows = []
    for sym, info in portfolio.items():
        buy = float(info.get("buy_price", 0.0))
        close = float(info.get("current_close", buy))
        shares = float(info.get("shares", 0))
        open_rows.append({
            "symbol": sym,
            "pnl": (close - buy) * shares,
            "pnl_pct": ((close - buy) / buy * 100) if buy else 0.0,
            "value": close * shares,
            "hold_days": info.get("hold_days", 0) or 0,
        })
    op = pd.DataFrame(open_rows)
    open_win = float(op.loc[op["pnl"] > 0, "pnl"].sum()) if not op.empty else 0.0
    open_loss = float(abs(op.loc[op["pnl"] <= 0, "pnl"].sum())) if not op.empty else 0.0
    total_win, total_loss = realized_win + open_win, realized_loss + open_loss

    total_positions = (len(sells) + len(op)) or 1
    winners = (len(sells[sells["profit"] > 0]) if len(sells) else 0) + (int((op["pnl"] > 0).sum()) if not op.empty else 0)
    value = float(op["value"].sum()) if not op.empty else 0.0
    return {
        "realized_win": realized_win,
        "realized_loss": realized_loss,
        "open_win": open_win,
        "open_loss": open_loss,
        "open_pnl": open_win - open_loss,
        "mtm_profit_factor": (total_win / total_loss) if total_loss else None,
        "mtm_win_rate": winners / total_positions * 100,
        "open_positions": len(op),
        "open_losers": int((op["pnl"] < 0).sum()) if not op.empty else 0,
        "open_value": value,
        "top3_concentration": float(op["value"].nlargest(3).sum() / value * 100) if value else 0.0,
        "largest_position_pct": float(op["value"].max() / value * 100) if value else 0.0,
        "largest_position": str(op.loc[op["value"].idxmax(), "symbol"]) if not op.empty else "—",
        "oldest_loser_days": float(op.loc[op["pnl"] < 0, "hold_days"].max()) if not op.empty and (op["pnl"] < 0).any() else 0.0,
        "avg_loser_age": float(op.loc[op["pnl"] < 0, "hold_days"].mean()) if not op.empty and (op["pnl"] < 0).any() else 0.0,
    }


def friction_analysis(
    trades: pd.DataFrame,
    equity: pd.DataFrame,
    stcg_rate: float = 0.20,
    ltcg_rate: float = 0.125,
    cost_bps: tuple = (5, 10, 20, 30),
) -> Dict:
    """
    What the backtest does not charge you for: spread/brokerage on turnover and
    tax on realized short term gains. Indian equity rates are the defaults.
    """
    if trades.empty or equity.empty:
        return {}
    turnover = float(trades["value"].sum())
    final_nw = float(equity["NetWorth"].iloc[-1])
    scenarios = [
        {"bps": b, "cost": turnover * b / 10000.0, "pct_of_nw": turnover * b / 10000.0 / final_nw * 100}
        for b in cost_bps
    ]
    sells = trades[trades["side"] == "SELL"]
    short = float(sells.loc[sells["hold_days"] < 365, "profit"].sum()) if len(sells) else 0.0
    long = float(sells.loc[sells["hold_days"] >= 365, "profit"].sum()) if len(sells) else 0.0
    cash_pct = (equity["Cash"] / equity["NetWorth"] * 100).dropna()
    return {
        "turnover": turnover,
        "turnover_x_capital": turnover / float(equity["Invested"].iloc[-1]) if float(equity["Invested"].iloc[-1]) else 0.0,
        "cost_scenarios": scenarios,
        "short_term_gains": short,
        "long_term_gains": long,
        "short_term_share": short / (short + long) * 100 if (short + long) else 0.0,
        "estimated_tax": short * stcg_rate + long * ltcg_rate,
        "mean_cash_pct": float(cash_pct.mean()) if len(cash_pct) else 0.0,
        "median_cash_pct": float(cash_pct.median()) if len(cash_pct) else 0.0,
        "trades_per_year": len(trades) / max((equity["Date"].iloc[-1] - equity["Date"].iloc[0]).days / 365.25, 1e-9),
    }
