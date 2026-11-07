"""
Parameter sweep for the SIP strategy, evaluated on two windows so a result has
to hold in more than one regime before it counts as an improvement.

One parameter varies at a time from the live configuration. Anything that only
wins on a single window is noise, not a finding.

    python param_sweep.py
"""
import os
import sys
from datetime import date, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_windows import load_universe, benchmark_sip, max_drawdown, xirr, live_universe
from src.sip_strategy import SIPStrategy

SIP_AMOUNT = 30_000
LIVE = dict(dma_window=10, profit_threshold=6.5, trailing_stop=0.5,
            max_daily_buys=1, avg_down_threshold=4.0, buy_divisor=40)

VARIANTS = [
    ("live config", {}),
    # Cash deployment — the live config leaves 25-57% of net worth idle.
    ("buy_divisor 20", {"buy_divisor": 20}),
    ("buy_divisor 10", {"buy_divisor": 10}),
    ("buy_divisor 60", {"buy_divisor": 60}),
    ("max_daily_buys 2", {"max_daily_buys": 2}),
    ("max_daily_buys 3", {"max_daily_buys": 3}),
    ("divisor 20 + 2 buys", {"buy_divisor": 20, "max_daily_buys": 2}),
    ("divisor 10 + 3 buys", {"buy_divisor": 10, "max_daily_buys": 3}),
    # Signal
    ("dma_window 20", {"dma_window": 20}),
    ("dma_window 5", {"dma_window": 5}),
    ("dma_window 50", {"dma_window": 50}),
    # Exit
    ("profit_threshold 4", {"profit_threshold": 4.0}),
    ("profit_threshold 10", {"profit_threshold": 10.0}),
    ("profit_threshold 15", {"profit_threshold": 15.0}),
    ("trailing_stop 1.0", {"trailing_stop": 1.0}),
    ("trailing_stop 2.0", {"trailing_stop": 2.0}),
    # Averaging down
    ("avg_down 2%", {"avg_down_threshold": 2.0}),
    ("avg_down 8%", {"avg_down_threshold": 8.0}),
]


def run(window_label, start, end, symbols, overrides):
    data, _ = load_universe(symbols, start, end)
    if not data:
        return None
    all_dates = sorted({d for df in data.values() for d in pd.to_datetime(df["Date"])})
    sip_dates = {}
    for when in all_dates:
        key = when.strftime("%Y-%m")
        sip_dates.setdefault(key, when.date())

    params = {**LIVE, **overrides}
    result = SIPStrategy(**params).generate_signals(data, capital=0, sip_amount=SIP_AMOUNT)

    monthly = result["monthly_invested_cash"]
    invested = sum(monthly.values())
    final = float(result["net_worth"]["NetWorth"].iloc[-1])
    flows = [(sip_dates[m], -a) for m, a in sorted(monthly.items()) if m in sip_dates]
    flows.append((all_dates[-1].date(), final))

    cash_df = pd.DataFrame(result["cash_history"])
    merged = result["net_worth"].merge(cash_df, on="Date", how="left")
    drag = float((merged["Cash"] / merged["NetWorth"].replace(0, pd.NA)).mean())

    return {
        "xirr": xirr(flows),
        "final": round(final),
        "invested": round(invested),
        "max_dd": max_drawdown(result["net_worth"]),
        "trades": len(result["trades"]),
        "cash_pct": round(drag, 3),
        "open": len(result.get("portfolio", {})),
    }


def main():
    today = date.today()
    symbols = live_universe()
    windows = [
        ("2016→ (10.9y)", "2016-01-01", today.isoformat()),
        ("last 5y", (today - timedelta(days=5 * 365)).isoformat(), today.isoformat()),
    ]

    # Benchmarks for reference, cashflow-matched per window inside run().
    rows = []
    for label, overrides in VARIANTS:
        row = {"variant": label}
        for wlabel, start, end in windows:
            res = run(wlabel, start, end, symbols, overrides)
            if res:
                row[f"{wlabel} xirr"] = res["xirr"]
                row[f"{wlabel} dd"] = res["max_dd"]
                row[f"{wlabel} cash%"] = res["cash_pct"]
                row[f"{wlabel} trades"] = res["trades"]
        rows.append(row)
        print(f"  {label:22} "
              + "  ".join(f"{row.get(f'{w[0]} xirr', float('nan')):+.2%}" for w in windows),
              flush=True)

    out = pd.DataFrame(rows)
    os.makedirs("reports", exist_ok=True)
    out.to_csv("reports/param_sweep.csv", index=False)
    print("\nWrote reports/param_sweep.csv\n")
    pd.set_option("display.width", 200)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
