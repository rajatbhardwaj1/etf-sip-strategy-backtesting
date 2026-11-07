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
    ("A live", {}),
    ("C more buys/day (3)", {"max_daily_buys": 3}),
    # Thesis: never stop out, keep averaging so the break-even bar comes down.
    ("I avg-down priority", {"avg_down_priority": True}),
    ("J avg-down own slot", {"avg_down_extra_slots": 1, "avg_down_priority": True}),
    ("K avg-down on cost drawdown", {"avg_down_scan_all": True, "avg_down_priority": True}),
    ("L K + own slot", {"avg_down_scan_all": True, "avg_down_priority": True,
                        "avg_down_extra_slots": 1}),
    ("M L + 3 buys/day", {"avg_down_scan_all": True, "avg_down_priority": True,
                          "avg_down_extra_slots": 1, "max_daily_buys": 3}),
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

    trades = pd.DataFrame(result["trades"])
    exits = len(trades[trades["action"].astype(str).str.contains("SELL")]) if len(trades) else 0
    opens = len(trades[trades["action"].astype(str) == "BUY"]) if len(trades) else 0
    avg_downs = len(trades[trades["action"].astype(str) == "BUY_AVERAGE_DOWN"]) if len(trades) else 0
    sells = trades[trades["action"].astype(str).str.contains("SELL")] if len(trades) else trades
    med_hold = float(sells["hold_days"].median()) if len(sells) else None
    pf = result.get("portfolio", {})
    under = sum(1 for i in pf.values()
                if i.get("current_close", i["buy_price"]) < i["buy_price"])

    bench = benchmark_sip("^NSEI", monthly, sip_dates, start, end)
    return {
        "xirr": xirr(flows),
        "exit_rate": round(exits / opens, 3) if opens else None,
        "avg_downs": avg_downs,
        "med_hold": med_hold,
        "open": len(pf),
        "underwater": under,
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
            row[f"{clabel} exit_rate"] = res["exit_rate"]
            row[f"{clabel} med_hold"] = res["med_hold"]
            row[f"{clabel} avg_downs"] = res["avg_downs"]
            row[f"{clabel} underwater"] = res["underwater"]
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
        print(f"  {c:30} beats live {beats_live}/{len(out)}  "
              f"beats Nifty {beats_bench}/{len(out)}  "
              f"mean XIRR {out[c].mean():+.2%}  "
              f"worst dd {out[f'{c} dd'].min():+.1%}  "
              f"med hold {out[f'{c} med_hold'].mean():.0f}d  "
              f"avg-downs {out[f'{c} avg_downs'].sum():.0f}  "
              f"underwater at end {out[f'{c} underwater'].sum():.0f}")


if __name__ == "__main__":
    main()
