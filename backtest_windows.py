"""
Runs the SIP strategy across several market regimes and compares each one
against a Nifty 50 (and Nifty 500) SIP receiving *identical* cashflows.

Two things make the comparison honest:

  * The benchmark is fed the strategy's own `monthly_invested_cash`, so both
    sides receive the same rupees on the same dates. Comparing against a
    benchmark with its own SIP schedule would measure the schedule as much as
    the strategy.
  * XIRR is computed from actual dates. `src.utils.xirr_calculator` uses
    npf.irr on assumed-equal monthly spacing, which is fine for a rough figure
    but drifts when a window ends mid-month. Both sides get the dated version.

    python backtest_windows.py              # all windows
    python backtest_windows.py --window 2022
"""
import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.sip_strategy import SIPStrategy
from src.utils import fetch_ohlc, filter_outliers, sanitize_price_series

LIVE_UNIVERSE_SRC = (
    "/Users/rajatbhardwaj.rajat/Documents/personal/strategy-automation/src/etf.py"
)
SIP_AMOUNT = 30_000
BENCHMARKS = {"Nifty 50": "^NSEI", "Nifty 500": "^CRSLDX"}
DAYS_PER_YEAR = 365.0


def live_universe():
    """
    The ETFs the deployed strategy actually trades, read from its own source so
    this cannot drift from production.
    """
    if os.path.exists(LIVE_UNIVERSE_SRC):
        syms = re.findall(r'"([A-Z0-9]+)"', open(LIVE_UNIVERSE_SRC).read())
        return [f"{s}.NS" for s in syms]
    from src.etfs import ETFS
    return ETFS


# ---------------------------------------------------------------- XIRR
def xirr(flows, lo=-0.9999, hi=10.0):
    """Dated money-weighted annual return. Bisection: cannot diverge."""
    flows = [(d, float(a)) for d, a in flows if a]
    if len(flows) < 2:
        return None
    if not (any(a < 0 for _, a in flows) and any(a > 0 for _, a in flows)):
        return None
    flows.sort(key=lambda f: f[0])
    t0 = flows[0][0]

    def npv(rate):
        return sum(a / ((1 + rate) ** ((d - t0).days / DAYS_PER_YEAR)) for d, a in flows)

    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


# ---------------------------------------------------------------- data
def load_universe(symbols, start, end):
    """Load each ETF for the window, dropping ones with too little history."""
    data, skipped = {}, []
    for symbol in symbols:
        df = fetch_ohlc(symbol, start=start, end=end)
        if df.empty or len(df) < 30:
            skipped.append(symbol)
            continue
        # filter_outliers alone cannot catch a multi-day corrupt plateau -
        # five Nippon BeES ETFs carry one on 2019-12-19/20 - so the
        # neighbourhood check runs after it.
        df = filter_outliers(df, column="Close", max_change_pct=20)
        data[symbol] = sanitize_price_series(df, column="Close")
    return data, skipped


def benchmark_sip(ticker, monthly_cash, sip_dates, start, end):
    """
    SIP the strategy's exact monthly amounts into one index.

    Units are bought at the close of the same trading day the strategy received
    its SIP, so neither side gets a timing edge.
    """
    df = fetch_ohlc(ticker, start=start, end=end)
    if df.empty:
        return None
    df = filter_outliers(df, column="Close", max_change_pct=20)
    df = sanitize_price_series(df, column="Close")
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)
    if df.empty:
        return None

    units, invested, flows = 0.0, 0.0, []
    for month, amount in sorted(monthly_cash.items()):
        when = sip_dates.get(month)
        if when is None:
            continue
        on_or_after = df[df["Date"] >= pd.Timestamp(when)]
        if on_or_after.empty:
            continue
        price = float(on_or_after.iloc[0]["Close"])
        if price <= 0:
            continue
        units += amount / price
        invested += amount
        flows.append((pd.Timestamp(when).date(), -amount))

    final_price = float(df.iloc[-1]["Close"])
    final_value = units * final_price
    end_date = df.iloc[-1]["Date"].date()
    flows.append((end_date, final_value))
    return {
        "final_value": final_value,
        "invested": invested,
        "xirr": xirr(flows),
    }


def max_drawdown(net_worth_df):
    """
    Peak-to-trough on the net-worth curve.

    Understates real pain: fresh SIP money keeps lifting the curve, so a true
    drawdown is partly masked by inflows. Reported as a relative figure between
    windows rather than an absolute risk measure.
    """
    series = pd.to_numeric(net_worth_df["NetWorth"], errors="coerce").dropna()
    if series.empty:
        return None
    running_peak = series.cummax()
    return float(((series - running_peak) / running_peak).min())


# ---------------------------------------------------------------- run
def run_window(label, start, end, symbols):
    data, skipped = load_universe(symbols, start, end)
    if not data:
        return None

    # The dates the strategy will actually iterate, so SIP dates can be
    # reconstructed for the dated XIRR and shared with the benchmark.
    all_dates = sorted({d for df in data.values() for d in pd.to_datetime(df["Date"])})
    sip_dates = {}
    for when in all_dates:
        key = when.strftime("%Y-%m")
        if key not in sip_dates:
            sip_dates[key] = when.date()

    result = SIPStrategy().generate_signals(data, capital=0, sip_amount=SIP_AMOUNT)

    net_worth_df = result["net_worth"]
    monthly_cash = result["monthly_invested_cash"]
    invested = sum(monthly_cash.values())
    final = float(net_worth_df["NetWorth"].iloc[-1])

    flows = [(sip_dates[m], -a) for m, a in sorted(monthly_cash.items()) if m in sip_dates]
    flows.append((all_dates[-1].date(), final))

    trades = pd.DataFrame(result["trades"])
    sells = trades[trades["action"].astype(str).str.contains("SELL")] if not trades.empty else trades
    buys = trades[trades["action"].astype(str).str.contains("BUY")] if not trades.empty else trades

    cash_df = pd.DataFrame(result["cash_history"])
    merged = net_worth_df.merge(cash_df, on="Date", how="left")
    cash_drag = float((merged["Cash"] / merged["NetWorth"].replace(0, pd.NA)).mean())

    # Open positions at the end: the strategy has no stop-loss, so a loser is
    # simply held forever. "win rate" on sells is therefore always 1.0 by
    # construction (it only sells above +profit_threshold) and says nothing -
    # the honest risk picture is in what is still being held underwater.
    portfolio = result.get("portfolio", {})
    open_positions = len(portfolio)
    underwater, unrealised = 0, 0.0
    worst_pct = 0.0
    for info in portfolio.values():
        current = info.get("current_close", info["buy_price"])
        pnl = (current - info["buy_price"]) * info["shares"]
        unrealised += pnl
        pct = (current - info["buy_price"]) / info["buy_price"] * 100
        if pct < 0:
            underwater += 1
            worst_pct = min(worst_pct, pct)

    row = {
        "window": label,
        "from": str(all_dates[0].date()),
        "to": str(all_dates[-1].date()),
        "years": round((all_dates[-1] - all_dates[0]).days / DAYS_PER_YEAR, 2),
        "etfs_used": len(data),
        "etfs_at_start": sum(
            1 for df in data.values()
            if pd.to_datetime(df["Date"]).min() <= all_dates[0] + pd.Timedelta(days=7)
        ),
        "invested": round(invested),
        "final_value": round(final),
        "multiple": round(final / invested, 3) if invested else None,
        "xirr": xirr(flows),
        "max_dd": max_drawdown(net_worth_df),
        "trades": len(trades),
        "buys": len(buys),
        "sells": len(sells),
        "win_rate": round(float((sells["profit"] > 0).mean()), 3) if len(sells) else None,
        "avg_hold_days": round(float(sells["hold_days"].mean()), 1) if len(sells) else None,
        "realised_profit": round(float(sells["profit"].sum())) if len(sells) else 0,
        "avg_cash_pct": round(cash_drag, 3) if pd.notna(cash_drag) else None,
        "open_positions": open_positions,
        "open_underwater": underwater,
        "underwater_pct": round(underwater / open_positions, 3) if open_positions else None,
        "worst_open_pct": round(worst_pct, 1),
        "unrealised": round(unrealised),
    }
    for name, ticker in BENCHMARKS.items():
        bench = benchmark_sip(ticker, monthly_cash, sip_dates, start, end)
        row[f"{name} xirr"] = bench["xirr"] if bench else None
        row[f"{name} final"] = round(bench["final_value"]) if bench else None
    return row


def windows(today):
    five = (today - timedelta(days=5 * 365)).isoformat()
    three = (today - timedelta(days=3 * 365)).isoformat()
    one = (today - timedelta(days=365)).isoformat()
    t = today.isoformat()
    return [
        ("Full history (2016→)", "2016-01-01", t),
        ("Pre-COVID (2016-2019)", "2016-01-01", "2019-12-31"),
        ("COVID crash+rally (2020-2021)", "2020-01-01", "2021-12-31"),
        ("Bear/sideways (2022)", "2022-01-01", "2022-12-31"),
        ("Recent regime (2023→)", "2023-01-01", t),
        ("Last 5 years", five, t),
        ("Last 3 years", three, t),
        ("Last 1 year", one, t),
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", help="substring filter on the window label")
    parser.add_argument("--out", default="reports/window_results.csv")
    args = parser.parse_args()

    today = date.today()
    symbols = live_universe()
    print(f"Live universe: {len(symbols)} ETFs\n")

    rows = []
    for label, start, end in windows(today):
        if args.window and args.window.lower() not in label.lower():
            continue
        print(f"--- {label}  [{start} → {end}]", flush=True)
        row = run_window(label, start, end, symbols)
        if row:
            rows.append(row)
            print(f"    strategy XIRR {row['xirr']:+.2%} | "
                  f"Nifty50 {row['Nifty 50 xirr']:+.2%} | "
                  f"{row['trades']} trades, {row['etfs_used']} ETFs\n", flush=True)

    out = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"\nWrote {args.out}")
    cols = ["window", "years", "etfs_used", "invested", "final_value", "multiple",
            "xirr", "Nifty 50 xirr", "Nifty 500 xirr", "max_dd", "trades",
            "avg_cash_pct", "open_positions", "underwater_pct", "worst_open_pct"]
    print(out[cols].to_string(index=False))


if __name__ == "__main__":
    main()
