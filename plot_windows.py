"""
Interactive per-window charts: strategy net worth, idle cash, cumulative SIP
and a cashflow-matched Nifty 50 SIP, on one time axis per regime.

Produces a single self-contained HTML (plotly.js inlined once, no CDN).

    python plot_windows.py                 # -> docs/index.html, for GitHub Pages
    python plot_windows.py --config L --out reports/windows_L.html
"""
import argparse
import os
import sys
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from plotly.io import to_html
from plotly.offline import get_plotlyjs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest_windows import (live_universe, load_universe, max_drawdown,
                              windows, xirr)
from src.sip_strategy import SIPStrategy
from src.utils import fetch_ohlc, filter_outliers, sanitize_price_series

SIP_AMOUNT = 30_000
CONFIGS = {
    "live": {},
    # Research variant: averaging driven by drawdown from average cost, with a
    # daily slot reserved for it. max_daily_buys stays at the live value of 1.
    "L": {"avg_down_scan_all": True, "avg_down_priority": True,
          "avg_down_extra_slots": 1},
}

# One palette for the whole page so a colour means the same thing everywhere.
C_NET = "#2563eb"      # strategy net worth
C_CASH = "#f59e0b"     # idle cash
C_INV = "#94a3b8"      # cumulative SIP (the money put in)
C_BENCH = "#db2777"    # Nifty 50 SIP


def benchmark_series(ticker, monthly_cash, sip_dates, start, end):
    """Daily value of a Nifty SIP receiving the strategy's own cashflows."""
    df = fetch_ohlc(ticker, start=start, end=end)
    if df.empty:
        return None
    df = sanitize_price_series(filter_outliers(df, column="Close", max_change_pct=20))
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)

    buys = {}
    for month, amount in monthly_cash.items():
        when = sip_dates.get(month)
        if when is not None:
            buys[pd.Timestamp(when)] = amount

    units, values = 0.0, []
    for _, row in df.iterrows():
        for when, amount in list(buys.items()):
            if row["Date"] >= when:
                units += amount / float(row["Close"])
                del buys[when]
        values.append(units * float(row["Close"]))
    return pd.DataFrame({"Date": df["Date"], "Benchmark": values})


def build_window(label, start, end, symbols, overrides):
    data, _ = load_universe(symbols, start, end)
    if not data:
        return None
    all_dates = sorted({d for df in data.values() for d in pd.to_datetime(df["Date"])})
    sip_dates = {}
    for when in all_dates:
        sip_dates.setdefault(when.strftime("%Y-%m"), when.date())

    result = SIPStrategy(**overrides).generate_signals(
        data, capital=0, sip_amount=SIP_AMOUNT)

    net = result["net_worth"].copy()
    net["Date"] = pd.to_datetime(net["Date"])
    cash = pd.DataFrame(result["cash_history"])
    cash["Date"] = pd.to_datetime(cash["Date"])
    series = net.merge(cash, on="Date", how="left")

    # Cumulative SIP paid in, stepped on each SIP date.
    monthly = result["monthly_invested_cash"]
    paid = pd.Series(0.0, index=series.index)
    running = 0.0
    sip_by_date = {pd.Timestamp(d): monthly[m] for m, d in sip_dates.items() if m in monthly}
    for i, when in enumerate(series["Date"]):
        running += sip_by_date.get(when, 0.0)
        paid.iloc[i] = running
    series["Invested"] = paid

    bench = benchmark_series("^NSEI", monthly, sip_dates, start, end)
    if bench is not None:
        series = series.merge(bench, on="Date", how="left")
        series["Benchmark"] = series["Benchmark"].ffill()

    invested_total = sum(monthly.values())
    final = float(series["NetWorth"].iloc[-1])
    flows = [(sip_dates[m], -a) for m, a in sorted(monthly.items()) if m in sip_dates]
    flows.append((all_dates[-1].date(), final))
    bench_final = float(series["Benchmark"].iloc[-1]) if "Benchmark" in series else None
    bench_flows = flows[:-1] + [(all_dates[-1].date(), bench_final)] if bench_final else None

    return {
        "label": label,
        "series": series,
        "stats": {
            "xirr": xirr(flows),
            "bench_xirr": xirr(bench_flows) if bench_flows else None,
            "invested": invested_total,
            "final": final,
            "bench_final": bench_final,
            "max_dd": max_drawdown(net),
            "avg_cash": float((series["Cash"] / series["NetWorth"].replace(0, pd.NA)).mean()),
            "etfs": len(data),
            "from": str(all_dates[0].date()),
            "to": str(all_dates[-1].date()),
        },
    }


def figure_for(window):
    s, st = window["series"], window["stats"]
    fig = go.Figure()

    # Cash drawn first and filled: it is a component of net worth, so showing
    # it as the shaded floor makes the idle-capital share readable at a glance
    # rather than needing a second axis.
    fig.add_trace(go.Scatter(
        x=s["Date"], y=s["Cash"], name="Idle cash", mode="lines",
        line=dict(color=C_CASH, width=1.2), fill="tozeroy",
        fillcolor="rgba(245,158,11,0.16)",
        hovertemplate="Idle cash  ₹%{y:,.0f}<extra></extra>"))

    fig.add_trace(go.Scatter(
        x=s["Date"], y=s["Invested"], name="Cumulative SIP paid in",
        mode="lines", line=dict(color=C_INV, width=1.6, dash="dot"),
        hovertemplate="Paid in  ₹%{y:,.0f}<extra></extra>"))

    if "Benchmark" in s:
        fig.add_trace(go.Scatter(
            x=s["Date"], y=s["Benchmark"], name="Nifty 50 SIP (same cashflows)",
            mode="lines", line=dict(color=C_BENCH, width=1.8),
            hovertemplate="Nifty 50 SIP  ₹%{y:,.0f}<extra></extra>"))

    fig.add_trace(go.Scatter(
        x=s["Date"], y=s["NetWorth"], name="Strategy net worth (cash + portfolio)",
        mode="lines", line=dict(color=C_NET, width=2.6),
        hovertemplate="<b>Strategy  ₹%{y:,.0f}</b><extra></extra>"))

    fig.update_layout(
        height=460,
        margin=dict(l=70, r=30, t=20, b=50),
        hovermode="x unified",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, rangeslider=dict(visible=False)),
        yaxis=dict(title="₹", gridcolor="rgba(148,163,184,0.25)",
                   zeroline=False, tickformat=",.0f"),
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                  size=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def pct(v):
    return "—" if v is None or pd.isna(v) else f"{v * 100:+.1f}%"


def money(v):
    return "—" if v is None or pd.isna(v) else f"₹{v:,.0f}"


def render(results, config_name):
    cards = []
    for i, w in enumerate(results):
        st = w["stats"]
        beat = st["xirr"] is not None and st["bench_xirr"] is not None \
            and st["xirr"] > st["bench_xirr"]
        verdict = "beat Nifty" if beat else "lost to Nifty"
        chart = to_html(figure_for(w), include_plotlyjs=False, full_html=False,
                        config={"displaylogo": False, "responsive": True,
                                "modeBarButtonsToRemove": ["lasso2d", "select2d"]})
        cards.append(f"""
<section class="card">
  <header>
    <div>
      <h2>{w['label']}</h2>
      <p class="sub">{st['from']} → {st['to']} · {st['etfs']} ETFs available</p>
    </div>
    <span class="badge {'win' if beat else 'loss'}">{verdict}</span>
  </header>
  <div class="stats">
    <div><span class="k">Strategy XIRR</span><span class="v hero">{pct(st['xirr'])}</span></div>
    <div><span class="k">Nifty 50 SIP</span><span class="v">{pct(st['bench_xirr'])}</span></div>
    <div><span class="k">Paid in</span><span class="v">{money(st['invested'])}</span></div>
    <div><span class="k">Ended at</span><span class="v">{money(st['final'])}</span></div>
    <div><span class="k">Nifty ended at</span><span class="v">{money(st['bench_final'])}</span></div>
    <div><span class="k">Max drawdown</span><span class="v">{pct(st['max_dd'])}</span></div>
    <div><span class="k">Avg idle cash</span><span class="v">{st['avg_cash'] * 100:.0f}%</span></div>
  </div>
  {chart}
</section>""")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ETF SIP strategy — backtest windows</title>
<script>{get_plotlyjs()}</script>
<style>
  :root {{
    --bg:#f6f7f9; --card:#fff; --ink:#0f172a; --muted:#64748b;
    --line:#e2e8f0; --win:#059669; --loss:#db2777;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#0b1220; --card:#121a2b; --ink:#e8eefc; --muted:#93a4c3;
             --line:#1f2b45; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font:14px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:40px 20px 64px; }}
  h1 {{ font-size:26px; margin:0 0 6px; letter-spacing:-.02em; }}
  .lede {{ color:var(--muted); margin:0 0 8px; max-width:70ch; }}
  .note {{ color:var(--muted); font-size:13px; max-width:78ch;
    border-left:3px solid var(--line); padding:8px 0 8px 14px; margin:18px 0 28px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px;
    padding:20px 22px 8px; margin:0 0 26px; }}
  .card header {{ display:flex; justify-content:space-between; align-items:flex-start;
    gap:16px; margin-bottom:14px; }}
  h2 {{ font-size:17px; margin:0; letter-spacing:-.01em; }}
  .sub {{ color:var(--muted); font-size:12.5px; margin:3px 0 0; }}
  .badge {{ font-size:12px; font-weight:600; padding:4px 10px; border-radius:999px;
    white-space:nowrap; }}
  .badge.win {{ color:#fff; background:var(--win); }}
  .badge.loss {{ color:#fff; background:var(--loss); }}
  .stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(118px,1fr));
    gap:12px; padding:14px 0 6px; border-top:1px solid var(--line); }}
  .stats div {{ display:flex; flex-direction:column; gap:2px; }}
  .k {{ color:var(--muted); font-size:11.5px; text-transform:uppercase;
    letter-spacing:.04em; }}
  .v {{ font-variant-numeric:tabular-nums; font-weight:600; font-size:15px; }}
  .v.hero {{ font-size:19px; color:var(--win); }}
  .js-plotly-plot {{ width:100% !important; }}
  footer {{ color:var(--muted); font-size:12.5px; margin-top:8px; }}
</style></head><body><div class="wrap">
<h1>ETF SIP strategy — backtest by market regime</h1>
<p class="lede">Monthly SIP of ₹{SIP_AMOUNT:,} stepped up 15% a year, run on the
{len(live_universe())}-ETF universe the live bot trades. Configuration:
<strong>{config_name}</strong>.</p>
<p class="note">The Nifty 50 line receives the <em>strategy's own</em> monthly
cashflows on the same dates, so the comparison measures the strategy rather
than the SIP schedule. Every window starts from zero capital, which is why
early cash is high — each buy is net&nbsp;worth ÷ divisor, so a young book
deploys slowly. Prices are sanitised against a rolling median first: five
Nippon BeES ETFs carry corrupt quotes on 2019-12-19/20 that would otherwise
fabricate profit.</p>
{''.join(cards)}
<footer>Generated {date.today().isoformat()} · data to 2026-11-06 ·
cash + portfolio = net worth · drawdown is peak-to-trough on net worth and is
softened by ongoing SIP inflows.</footer>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/index.html")
    ap.add_argument("--config", default="live", choices=list(CONFIGS))
    args = ap.parse_args()

    symbols = live_universe()
    results = []
    for label, start, end in windows(date.today()):
        print(f"  building {label}", flush=True)
        w = build_window(label, start, end, symbols, CONFIGS[args.config])
        if w:
            results.append(w)

    html = render(results, args.config)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fh:
        fh.write(html)
    print(f"\nWrote {args.out} ({len(html) / 1e6:.1f} MB, {len(results)} windows)")


if __name__ == "__main__":
    main()
