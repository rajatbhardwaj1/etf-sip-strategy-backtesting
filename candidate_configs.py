"""
Tests a handful of candidate configurations across every window.

The sweep in param_sweep.py tunes on two windows; anything found there has to
survive all eight before it is a real improvement rather than a fit to the
windows it was chosen on. The 2020-2021 melt-up matters most - that is where
the live config loses to the index by 14 points.

    python candidate_configs.py
"""
import os
import sys
from datetime import date, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_windows import (benchmark_sip, live_universe, load_universe,
                              max_drawdown, windows, xirr)
from src.sip_strategy import SIPStrategy

SIP_AMOUNT = 30_000
LIVE = dict(dma_window=10, profit_threshold=6.5, trailing_stop=0.5,
            max_daily_buys=1, avg_down_threshold=4.0, buy_divisor=40)

CANDIDATES = [
    ("A live (divisor 40, exit 6.5)", {}),
    ("B deploy faster (divisor 10)", {"buy_divisor": 10}),
    ("C more buys/day (3)", {"max_daily_buys": 3}),
    ("D let winners run (exit 12)", {"profit_threshold": 12.0}),
    ("G B+C (divisor 10, 3 buys)", {"buy_divisor": 10, "max_daily_buys": 3}),
    ("H divisor 20, 3 buys", {"buy_divisor": 20, "max_daily_buys": 3}),
]


def evaluate(symbols, start, end, overrides):
    data, _ = load_universe(symbols, start, end)
    if not data:
        return None
    all_dates = sorted({d for df in data.values() for d in pd.to_datetime(df["Date"])})
    sip_dates = {}
    for when in all_dates:
        sip_dates.setdefault(when.strftime("%Y-%m"), when.date())

    result = SIPStrategy(**{**LIVE, **overrides}).generate_signals(
        data, capital=0, sip_amount=SIP_AMOUNT)

    monthly = result["monthly_invested_cash"]
    final = float(result["net_worth"]["NetWorth"].iloc[-1])
    flows = [(sip_dates[m], -a) for m, a in sorted(monthly.items()) if m in sip_dates]
    flows.append((all_dates[-1].date(), final))

    cash_df = pd.DataFrame(result["cash_history"])
    merged = result["net_worth"].merge(cash_df, on="Date", how="left")

    bench = benchmark_sip("^NSEI", monthly, sip_dates, start, end)
    return {
        "xirr": xirr(flows),
        "bench": bench["xirr"] if bench else None,
        "dd": max_drawdown(result["net_worth"]),
        "cash": float((merged["Cash"] / merged["NetWorth"].replace(0, pd.NA)).mean()),
    }


def main():
    today = date.today()
    symbols = live_universe()
    rows = []
    for wlabel, start, end in windows(today):
        bench_shown = None
        row = {"window": wlabel}
        for clabel, overrides in CANDIDATES:
            res = evaluate(symbols, start, end, overrides)
            if not res:
                continue
            row[clabel] = res["xirr"]
            row[f"{clabel} dd"] = res["dd"]
            bench_shown = res["bench"]
        row["Nifty 50"] = bench_shown
        rows.append(row)
        print(f"{wlabel:32} " + "  ".join(
            f"{row.get(c, float('nan')):+.1%}" for c, _ in CANDIDATES)
            + f"   | bench {bench_shown:+.1%}", flush=True)

    out = pd.DataFrame(rows)
    os.makedirs("reports", exist_ok=True)
    out.to_csv("reports/candidate_configs.csv", index=False)

    print("\n=== XIRR by window ===")
    cols = ["window"] + [c for c, _ in CANDIDATES] + ["Nifty 50"]
    table = out[cols].copy()
    for c in cols[1:]:
        table[c] = table[c].map(lambda v: f"{v:+.2%}" if pd.notna(v) else "—")
    pd.set_option("display.width", 250)
    print(table.to_string(index=False))

    print("\n=== how often each beats the live config, and the index ===")
    live_col = CANDIDATES[0][0]
    for c, _ in CANDIDATES:
        beats_live = (out[c] > out[live_col]).sum()
        beats_bench = (out[c] > out["Nifty 50"]).sum()
        print(f"  {c:32} beats live {beats_live}/{len(out)}   "
              f"beats Nifty {beats_bench}/{len(out)}   "
              f"mean XIRR {out[c].mean():+.2%}   "
              f"worst dd {out[f'{c} dd'].min():+.1%}")


if __name__ == "__main__":
    main()
