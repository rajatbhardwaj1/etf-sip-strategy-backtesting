"""
Interactive HTML backtest report.

Produces a single self contained file (plotly.js is inlined) with zoomable,
hoverable, clickable charts: click a point on the equity curve to inspect that
day, click a symbol bar or a trade marker to filter the trade log, and use the
range selector / range slider to drill into any period.

All monetary axes are rendered in INR using Indian digit grouping (₹1,23,456).
"""
import json
import os
import webbrowser
from typing import Dict, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs
from plotly.subplots import make_subplots

from src.analytics import (
    build_benchmark_frame,
    friction_analysis,
    mark_to_market_stats,
    build_equity_frame,
    max_drawdown_window,
    monthly_return_table,
    prepare_trades,
    rolling_metrics,
    summary_metrics,
    symbol_pnl,
    trade_stats,
    yearly_returns,
)

# ---------------------------------------------------------------- formatting

MONEY_TICK = "$,.0f"          # with the en-IN locale below this renders ₹1,23,456
MONEY_HOVER = "%{y:$,.0f}"

COLORS = {
    "strategy": "#4dd4ac",
    "benchmark": "#f5a623",
    "invested": "#8b93a7",
    "cash": "#5b8def",
    "buy": "#4dd4ac",
    "avg": "#2f9e8f",
    "sell": "#ff6b6b",
    "profit": "#4dd4ac",
    "loss": "#ff6b6b",
}


def fmt_inr(value: Optional[float], decimals: int = 0) -> str:
    """Format a number with Indian digit grouping and a rupee sign."""
    if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
        return "—"
    neg = value < 0
    value = abs(float(value))
    whole = int(value)
    frac = f"{value - whole:.{decimals}f}"[2:] if decimals else ""
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    out = f"₹{s}" + (f".{frac}" if decimals else "")
    return f"-{out}" if neg else out


def fmt_pct(value: Optional[float], decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
        return "—"
    return f"{value:.{decimals}f}%"


def fmt_num(value: Optional[float], decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    if isinstance(value, float) and np.isinf(value):
        return "∞" if value > 0 else "-∞"
    return f"{value:.{decimals}f}"


# ---------------------------------------------------------------- plot theme

pio.templates["backtest"] = go.layout.Template(
    layout=dict(
        paper_bgcolor="#12151c",
        plot_bgcolor="#12151c",
        font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", color="#c9d1d9", size=12),
        xaxis=dict(gridcolor="#232833", zerolinecolor="#2c3240", showspikes=True,
                   spikemode="across", spikethickness=1, spikedash="dot", spikecolor="#6b7280"),
        yaxis=dict(gridcolor="#232833", zerolinecolor="#2c3240"),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", yanchor="bottom", y=1.02, x=0),
        hoverlabel=dict(bgcolor="#1b2029", bordercolor="#2c3240", font_size=12),
        margin=dict(l=70, r=30, t=50, b=40),
        dragmode="pan",          # drag pans instead of firing off accidental zoom boxes
        hoverdistance=12,        # only react when the cursor is genuinely near a point
        spikedistance=-1,
        clickmode="event",
        colorway=[COLORS["strategy"], COLORS["benchmark"], COLORS["cash"], COLORS["invested"]],
    )
)

PLOT_CONFIG = {
    "locale": "en-IN",
    "displaylogo": False,
    "scrollZoom": False,          # wheel scrolls the page, it never zooms the chart by accident
    "doubleClick": "reset",       # double click always returns to the full range
    "responsive": True,
    "displayModeBar": True,
    "modeBarButtonsToAdd": ["zoom2d", "select2d", "toggleSpikelines"],
    "modeBarButtonsToRemove": ["lasso2d", "autoScale2d"],
    "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "backtest"},
}

RANGE_SELECTOR = dict(
    buttons=[
        dict(count=1, label="1M", step="month", stepmode="backward"),
        dict(count=3, label="3M", step="month", stepmode="backward"),
        dict(count=6, label="6M", step="month", stepmode="backward"),
        dict(count=1, label="YTD", step="year", stepmode="todate"),
        dict(count=1, label="1Y", step="year", stepmode="backward"),
        dict(count=3, label="3Y", step="year", stepmode="backward"),
        dict(step="all", label="All"),
    ],
    bgcolor="#1b2029", activecolor="#2f9e8f", font=dict(color="#c9d1d9"),
    x=0, y=1.02, xanchor="left", yanchor="bottom",
)


def _div(fig: go.Figure, div_id: str, height: int = 520) -> str:
    fig.update_layout(template="backtest", height=height)
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id=div_id, config=PLOT_CONFIG)


# ---------------------------------------------------------------- figures


def equity_figure(equity: pd.DataFrame, bench: pd.DataFrame, trades: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[0.56, 0.22, 0.22],
        subplot_titles=("", "Drawdown (flow adjusted)", "Profit over invested capital"),
    )

    fig.add_trace(go.Scatter(
        x=equity["Date"], y=equity["NetWorth"], name="Strategy net worth",
        line=dict(color=COLORS["strategy"], width=2),
        hovertemplate="Strategy: %{y:$,.0f}<extra></extra>"), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=bench["Date"], y=bench["NetWorth"], name="Nifty 50 SIP",
        line=dict(color=COLORS["benchmark"], width=1.6, dash="dash"),
        hovertemplate="Nifty SIP: %{y:$,.0f}<extra></extra>"), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=equity["Date"], y=equity["Invested"], name="Capital invested",
        line=dict(color=COLORS["invested"], width=1.4, shape="hv"),
        hovertemplate="Invested: %{y:$,.0f}<extra></extra>"), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=equity["Date"], y=equity["Cash"], name="Idle cash",
        line=dict(color=COLORS["cash"], width=1, dash="dot"), visible="legendonly",
        hovertemplate="Cash: %{y:$,.0f}<extra></extra>"), row=1, col=1)

    # --- trade markers, clickable ---
    if not trades.empty:
        merged = trades.merge(equity[["Date", "NetWorth"]], left_on="date", right_on="Date", how="left")
        merged["NetWorth"] = merged["NetWorth"].ffill()
        groups = [
            ("BUY", merged[merged["action"] == "BUY"], COLORS["buy"], "triangle-up"),
            ("Average down", merged[merged["action"] == "BUY_AVERAGE_DOWN"], COLORS["avg"], "triangle-down"),
            ("SELL", merged[merged["side"] == "SELL"], COLORS["sell"], "x"),
        ]
        for name, sub, color, symbol in groups:
            if sub.empty:
                continue
            custom = np.stack([
                sub["symbol"].to_numpy(),
                sub["action"].to_numpy(),
                sub["price"].to_numpy(),
                sub["shares"].to_numpy(),
                sub["value"].to_numpy(),
                sub["profit"].to_numpy(),
                sub["hold_days"].fillna(0).to_numpy(),
            ], axis=-1)
            fig.add_trace(go.Scatter(
                x=sub["date"], y=sub["NetWorth"], mode="markers", name=f"{name} ({len(sub)})",
                marker=dict(color=color, size=8, symbol=symbol, line=dict(width=0.5, color="#0d1117")),
                customdata=custom, visible=True if name == "SELL" else "legendonly",
                hovertemplate=(
                    "<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
                    "%{x|%d %b %Y}<br>Price %{customdata[2]:$,.2f} × %{customdata[3]:,.0f}"
                    "<br>Value %{customdata[4]:$,.0f}<br>Profit %{customdata[5]:$,.0f}"
                    "<br>Held %{customdata[6]:,.0f} d<extra></extra>"
                )), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=equity["Date"], y=equity["Drawdown"], name="Strategy DD", fill="tozeroy",
        line=dict(color=COLORS["loss"], width=1), fillcolor="rgba(255,107,107,0.2)",
        hovertemplate="Strategy DD: %{y:.2f}%<extra></extra>"), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=bench["Date"], y=bench["Drawdown"], name="Nifty DD",
        line=dict(color=COLORS["benchmark"], width=1, dash="dot"), visible="legendonly",
        hovertemplate="Nifty DD: %{y:.2f}%<extra></extra>"), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=equity["Date"], y=equity["Profit"], name="Strategy profit", fill="tozeroy",
        line=dict(color=COLORS["strategy"], width=1.4), fillcolor="rgba(77,212,172,0.15)",
        hovertemplate="Profit: %{y:$,.0f}<extra></extra>"), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=bench["Date"], y=bench["Profit"], name="Nifty SIP profit",
        line=dict(color=COLORS["benchmark"], width=1.2, dash="dash"),
        hovertemplate="Nifty profit: %{y:$,.0f}<extra></extra>"), row=3, col=1)

    fig.update_yaxes(title_text="INR", tickformat=MONEY_TICK, fixedrange=True, row=1, col=1)
    fig.update_yaxes(title_text="%", ticksuffix="%", fixedrange=True, row=2, col=1)
    fig.update_yaxes(title_text="INR", tickformat=MONEY_TICK, fixedrange=True, row=3, col=1)
    fig.update_xaxes(rangeselector=RANGE_SELECTOR, row=1, col=1)
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.05, bgcolor="#1b2029"), row=3, col=1)
    fig.update_layout(hovermode="x unified", legend=dict(y=1.10, yanchor="bottom"),
                      margin=dict(t=120))
    return fig


def relative_figure(equity: pd.DataFrame, bench: pd.DataFrame) -> go.Figure:
    merged = equity[["Date", "TWR", "NetWorth", "Invested"]].merge(
        bench[["Date", "TWR", "NetWorth"]], on="Date", how="inner", suffixes=("", "_b"))
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        row_heights=[0.6, 0.4],
                        subplot_titles=("", "Strategy net worth minus Nifty SIP net worth"))
    fig.add_trace(go.Scatter(x=merged["Date"], y=merged["TWR"], name="Strategy",
                             line=dict(color=COLORS["strategy"], width=2),
                             hovertemplate="Strategy: %{y:$,.1f}<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=merged["Date"], y=merged["TWR_b"], name="Nifty 50",
                             line=dict(color=COLORS["benchmark"], width=1.6, dash="dash"),
                             hovertemplate="Nifty: %{y:$,.1f}<extra></extra>"), row=1, col=1)
    diff = merged["NetWorth"] - merged["NetWorth_b"]
    fig.add_trace(go.Scatter(x=merged["Date"], y=diff, name="Excess value", fill="tozeroy",
                             line=dict(color=COLORS["cash"], width=1.2), fillcolor="rgba(91,141,239,0.18)",
                             hovertemplate="Excess: %{y:$,.0f}<extra></extra>"), row=2, col=1)
    fig.update_yaxes(tickformat=MONEY_TICK, fixedrange=True, row=1, col=1)
    fig.update_yaxes(title_text="INR", tickformat=MONEY_TICK, fixedrange=True, row=2, col=1)
    fig.update_xaxes(rangeselector=RANGE_SELECTOR, row=1, col=1)
    fig.update_layout(hovermode="x unified", legend=dict(y=1.10, yanchor="bottom"),
                      margin=dict(t=120))
    return fig


def monthly_heatmap(equity: pd.DataFrame) -> go.Figure:
    table = monthly_return_table(equity)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    z = table.reindex(columns=range(1, 13)).to_numpy(dtype=float)
    text = [[("" if np.isnan(v) else f"{v:.1f}%") for v in row] for row in z]
    lim = np.nanmax(np.abs(z)) if np.isfinite(z).any() else 1
    fig = go.Figure(go.Heatmap(
        z=z, x=months, y=[str(y) for y in table.index], text=text, texttemplate="%{text}",
        colorscale="RdYlGn", zmid=0, zmin=-lim, zmax=lim, xgap=2, ygap=2,
        colorbar=dict(title="%", ticksuffix="%"),
        hovertemplate="%{y} %{x}: %{z:.2f}%<extra></extra>"))
    fig.update_layout(margin=dict(l=60, t=40), dragmode=False,
                      xaxis=dict(fixedrange=True), yaxis=dict(fixedrange=True))
    return fig


def yearly_figure(equity: pd.DataFrame, bench: pd.DataFrame) -> go.Figure:
    ey, by = yearly_returns(equity), yearly_returns(bench)
    merged = ey.merge(by, on="Year", how="outer", suffixes=("_s", "_b")).sort_values("Year")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=merged["Year"], y=merged["Return_s"], name="Strategy",
                         marker_color=COLORS["strategy"],
                         hovertemplate="%{x}: %{y:.2f}%<extra>Strategy</extra>"))
    fig.add_trace(go.Bar(x=merged["Year"], y=merged["Return_b"], name="Nifty 50",
                         marker_color=COLORS["benchmark"],
                         hovertemplate="%{x}: %{y:.2f}%<extra>Nifty</extra>"))
    fig.update_layout(barmode="group", margin=dict(t=60), dragmode=False,
                      yaxis=dict(ticksuffix="%", title="Return", fixedrange=True),
                      xaxis=dict(type="category", fixedrange=True))
    return fig


def rolling_figure(equity: pd.DataFrame) -> go.Figure:
    roll = rolling_metrics(equity)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        subplot_titles=("", "Rolling 1 year volatility and Sharpe"))
    fig.add_trace(go.Scatter(x=roll["Date"], y=roll["RollingReturn"], name="1Y return",
                             line=dict(color=COLORS["strategy"], width=1.6),
                             hovertemplate="%{y:.2f}%<extra>1Y return</extra>"), row=1, col=1)
    fig.add_hline(y=0, line=dict(color="#6b7280", width=1, dash="dot"), row=1, col=1)
    fig.add_trace(go.Scatter(x=roll["Date"], y=roll["RollingVol"], name="1Y volatility",
                             line=dict(color=COLORS["benchmark"], width=1.4),
                             hovertemplate="%{y:.2f}%<extra>Volatility</extra>"), row=2, col=1)
    fig.add_trace(go.Scatter(x=roll["Date"], y=roll["RollingSharpe"], name="1Y Sharpe", yaxis="y3",
                             line=dict(color=COLORS["cash"], width=1.4),
                             hovertemplate="%{y:.2f}<extra>Sharpe</extra>"), row=2, col=1)
    fig.update_yaxes(ticksuffix="%", fixedrange=True, row=1, col=1)
    fig.update_yaxes(ticksuffix="%", fixedrange=True, row=2, col=1)
    fig.update_xaxes(rangeselector=RANGE_SELECTOR, row=1, col=1)
    fig.update_layout(hovermode="x unified", legend=dict(y=1.10, yanchor="bottom"),
                      margin=dict(t=120))
    return fig


def distribution_figure(equity: pd.DataFrame, bench: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=equity["Ret"] * 100, name="Strategy", nbinsx=90,
                               marker_color=COLORS["strategy"], opacity=0.75,
                               hovertemplate="%{x:.2f}%: %{y} days<extra>Strategy</extra>"))
    fig.add_trace(go.Histogram(x=bench["Ret"] * 100, name="Nifty 50", nbinsx=90,
                               marker_color=COLORS["benchmark"], opacity=0.55,
                               hovertemplate="%{x:.2f}%: %{y} days<extra>Nifty</extra>"))
    fig.update_layout(barmode="overlay", margin=dict(t=60), dragmode=False,
                      xaxis=dict(title="Daily return", ticksuffix="%", fixedrange=True),
                      yaxis=dict(title="Days", fixedrange=True))
    return fig


def underwater_figure(equity: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity["Date"], y=equity["Drawdown"], fill="tozeroy", name="Drawdown",
                             line=dict(color=COLORS["loss"], width=1), fillcolor="rgba(255,107,107,0.25)",
                             hovertemplate="%{x|%d %b %Y}: %{y:.2f}%<extra></extra>"))
    trough, depth, peak, recovery = max_drawdown_window(equity)
    if trough is not None:
        fig.add_vrect(x0=peak, x1=recovery if recovery is not None else equity["Date"].iloc[-1],
                      fillcolor="rgba(255,107,107,0.08)", line_width=0,
                      annotation_text=f"max DD {depth:.1f}%", annotation_position="top left")
    fig.update_layout(yaxis=dict(ticksuffix="%", fixedrange=True),
                      xaxis=dict(rangeselector=RANGE_SELECTOR), margin=dict(t=110))
    return fig


def symbol_figure(pnl: pd.DataFrame) -> go.Figure:
    top = pnl.sort_values("total")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=top["symbol"], x=top["realized"], name="Realized", orientation="h",
        marker_color=[COLORS["profit"] if v >= 0 else COLORS["loss"] for v in top["realized"]],
        customdata=np.stack([top["trades"], top["buys"], top["sells"], top["invested"]], axis=-1),
        hovertemplate=("<b>%{y}</b><br>Realized %{x:$,.0f}<br>%{customdata[0]} trades "
                       "(%{customdata[1]} buys / %{customdata[2]} sells)"
                       "<br>Bought %{customdata[3]:$,.0f}<extra></extra>")))
    fig.add_trace(go.Bar(
        y=top["symbol"], x=top["open_pnl"], name="Open (unrealized)", orientation="h",
        marker_color=COLORS["cash"], opacity=0.8,
        hovertemplate="<b>%{y}</b><br>Open PnL %{x:$,.0f}<extra></extra>"))
    fig.update_layout(barmode="relative", dragmode=False,
                      xaxis=dict(title="INR", tickformat=MONEY_TICK, fixedrange=True),
                      yaxis=dict(fixedrange=True),
                      margin=dict(l=130, t=60), height=max(420, 22 * len(top)))
    return fig


def trade_scatter_figure(trades: pd.DataFrame) -> go.Figure:
    sells = trades[trades["side"] == "SELL"]
    fig = go.Figure()
    if not sells.empty:
        size = sells["value"].to_numpy(dtype=float)
        size = 6 + 18 * (size - size.min()) / (np.ptp(size) or 1)
        fig.add_trace(go.Scatter(
            x=sells["date"], y=sells["profit_pct"], mode="markers", name="Closed trades",
            marker=dict(size=size, color=sells["profit"], colorscale="RdYlGn", cmid=0,
                        line=dict(width=0.5, color="#0d1117"),
                        colorbar=dict(title="₹ profit", tickformat=MONEY_TICK)),
            customdata=np.stack([sells["symbol"], sells["profit"], sells["value"],
                                 sells["hold_days"].fillna(0), sells["shares"]], axis=-1),
            hovertemplate=("<b>%{customdata[0]}</b><br>%{x|%d %b %Y}<br>Return %{y:.2f}%"
                           "<br>Profit %{customdata[1]:$,.0f}<br>Size %{customdata[2]:$,.0f}"
                           "<br>Held %{customdata[3]:,.0f} d<extra></extra>")))
        fig.add_hline(y=0, line=dict(color="#6b7280", width=1, dash="dot"))
    fig.update_layout(yaxis=dict(title="Trade return", ticksuffix="%"),
                      xaxis=dict(rangeselector=RANGE_SELECTOR), margin=dict(t=110))
    return fig


def hold_figure(trades: pd.DataFrame) -> go.Figure:
    sells = trades[trades["side"] == "SELL"]
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Holding period of closed trades", "Profit per trade"))
    if not sells.empty:
        fig.add_trace(go.Histogram(x=sells["hold_days"], nbinsx=40, marker_color=COLORS["cash"],
                                   name="Hold days",
                                   hovertemplate="%{x} days: %{y} trades<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Histogram(x=sells["profit"], nbinsx=40, marker_color=COLORS["strategy"],
                                   name="Profit",
                                   hovertemplate="%{x:$,.0f}: %{y} trades<extra></extra>"), row=1, col=2)
    fig.update_xaxes(title_text="Days", row=1, col=1)
    fig.update_xaxes(title_text="INR", tickformat=MONEY_TICK, row=1, col=2)
    fig.update_layout(showlegend=False, dragmode=False)
    return fig


def activity_figure(trades: pd.DataFrame, equity: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=("Trades per month", "Cash deployed vs idle cash"))
    if not trades.empty:
        monthly = trades.copy()
        monthly["Month"] = monthly["date"].dt.to_period("M").dt.to_timestamp()
        counts = monthly.groupby(["Month", "side"]).size().unstack(fill_value=0)
        for side, color in (("BUY", COLORS["buy"]), ("SELL", COLORS["sell"])):
            if side in counts.columns:
                fig.add_trace(go.Bar(x=counts.index, y=counts[side], name=side, marker_color=color,
                                     hovertemplate="%{x|%b %Y}: %{y} " + side + "<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=equity["Date"], y=equity["Holdings"], name="Deployed in ETFs",
                             stackgroup="one", line=dict(width=0.5, color=COLORS["strategy"]),
                             hovertemplate="Deployed: %{y:$,.0f}<extra></extra>"), row=2, col=1)
    fig.add_trace(go.Scatter(x=equity["Date"], y=equity["Cash"], name="Idle cash",
                             stackgroup="one", line=dict(width=0.5, color=COLORS["cash"]),
                             hovertemplate="Cash: %{y:$,.0f}<extra></extra>"), row=2, col=1)
    fig.update_layout(barmode="stack", hovermode="x unified")
    fig.update_yaxes(title_text="Trades", row=1, col=1)
    fig.update_yaxes(title_text="INR", tickformat=MONEY_TICK, row=2, col=1)
    return fig


def holdings_figure(portfolio: Dict[str, Dict]) -> go.Figure:
    rows = []
    for sym, info in (portfolio or {}).items():
        close = float(info.get("current_close", info.get("buy_price", 0.0)))
        shares = float(info.get("shares", 0))
        buy = float(info.get("buy_price", 0.0))
        rows.append({
            "symbol": sym, "value": close * shares, "shares": shares,
            "buy_price": buy, "close": close,
            "pnl": (close - buy) * shares,
            "pnl_pct": ((close - buy) / buy * 100) if buy else 0.0,
            "hold_days": info.get("hold_days", 0),
        })
    df = pd.DataFrame(rows)
    fig = go.Figure()
    if not df.empty:
        df = df.sort_values("value", ascending=False)
        fig.add_trace(go.Treemap(
            labels=df["symbol"], parents=[""] * len(df), values=df["value"],
            marker=dict(colors=df["pnl_pct"], colorscale="RdYlGn", cmid=0,
                        colorbar=dict(title="P/L %", ticksuffix="%")),
            customdata=np.stack([df["shares"], df["buy_price"], df["close"], df["pnl"], df["pnl_pct"],
                                 df["hold_days"]], axis=-1),
            texttemplate="<b>%{label}</b><br>%{value:$,.0f}<br>%{customdata[4]:.1f}%",
            hovertemplate=("<b>%{label}</b><br>Value %{value:$,.0f}<br>%{customdata[0]:,.0f} shares"
                           "<br>Avg cost %{customdata[1]:$,.2f} → %{customdata[2]:$,.2f}"
                           "<br>Open P/L %{customdata[3]:$,.0f} (%{customdata[4]:.2f}%)"
                           "<br>Held %{customdata[5]:,.0f} d<extra></extra>")))
    fig.update_layout(margin=dict(t=30, l=20, r=20))
    return fig, df


# ---------------------------------------------------------------- html shell

CSS = """
:root{--bg:#0d1117;--panel:#12151c;--panel2:#171b24;--line:#232833;--text:#c9d1d9;--muted:#8b93a7;
--green:#4dd4ac;--red:#ff6b6b;--blue:#5b8def;--amber:#f5a623;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{padding:22px 28px 0;display:flex;flex-wrap:wrap;gap:12px;align-items:baseline;justify-content:space-between}
h1{font-size:21px;margin:0;font-weight:650;letter-spacing:.2px}
.sub{color:var(--muted);font-size:13px}
.wrap{padding:0 28px 60px;max-width:1700px;margin:0 auto}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:12px;margin:20px 0}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px}
.kpi .k{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.7px}
.kpi .v{font-size:20px;font-weight:640;margin-top:5px;font-variant-numeric:tabular-nums}
.kpi .d{font-size:11px;color:var(--muted);margin-top:3px}
.pos{color:var(--green)}.neg{color:var(--red)}.neutral{color:var(--text)}
.tabs{display:flex;gap:6px;border-bottom:1px solid var(--line);margin:6px 0 16px;flex-wrap:wrap}
.tab{padding:9px 16px;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;font-weight:550;user-select:none}
.tab:hover{color:var(--text)}
.tab.active{color:var(--green);border-bottom-color:var(--green)}
.page{display:none}.page.active{display:block}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-bottom:18px}
.card h2{font-size:14px;margin:6px 4px 8px;font-weight:600;color:var(--text)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:18px}
.detail{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:16px;min-height:56px}
.detail .hint{color:var(--muted)}
.detail table{border-collapse:collapse;margin-top:8px;font-size:12.5px;width:100%}
.detail td,.detail th{padding:3px 10px 3px 0;text-align:left}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
input,select,button{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:7px;padding:7px 11px;font:inherit;font-size:13px}
button{cursor:pointer}button:hover{border-color:var(--green);color:var(--green)}
.tablewrap{max-height:640px;overflow:auto;border:1px solid var(--line);border-radius:10px}
table.log{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}
table.log th{position:sticky;top:0;background:var(--panel2);padding:9px 12px;text-align:right;cursor:pointer;white-space:nowrap;border-bottom:1px solid var(--line);z-index:2}
table.log th:first-child,table.log th:nth-child(2),table.log th:nth-child(3){text-align:left}
table.log th:hover{color:var(--green)}
table.log td{padding:6px 12px;text-align:right;border-bottom:1px solid #1a1e27;white-space:nowrap}
table.log td:first-child,table.log td:nth-child(2),table.log td:nth-child(3){text-align:left}
table.log tbody tr:hover{background:#181d26}
.pill{padding:1px 8px;border-radius:20px;font-size:11px;font-weight:600}
.pill.buy{background:rgba(77,212,172,.14);color:var(--green)}
.pill.sell{background:rgba(255,107,107,.14);color:var(--red)}
a.symlink{color:var(--text);text-decoration:none;border-bottom:1px dotted var(--muted)}
a.symlink:hover{color:var(--green);border-bottom-color:var(--green)}
.stats{color:var(--muted);font-size:12.5px;margin:8px 2px}
.metrics{border-collapse:collapse;width:100%;font-size:13px}
.metrics td,.metrics th{padding:7px 12px;border-bottom:1px solid var(--line);text-align:right;font-variant-numeric:tabular-nums}
.metrics td:first-child,.metrics th:first-child{text-align:left;color:var(--muted)}
.metrics td.note{text-align:left;color:var(--muted);font-size:12px}
.metrics th:last-child{text-align:left}
"""

LOCALE_JS = """
Plotly.register({moduleType:'locale',name:'en-IN',dictionary:{},
 format:{decimal:'.',thousands:',',grouping:[3,2,2],currency:['\\u20b9',''],year:'%Y'}});
"""


def _kpi(label: str, value: str, detail: str = "", cls: str = "neutral") -> str:
    return (f'<div class="kpi"><div class="k">{label}</div>'
            f'<div class="v {cls}">{value}</div><div class="d">{detail}</div></div>')


def _sign(value: Optional[float]) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "neutral"
    return "pos" if value >= 0 else "neg"


def _metrics_table(strat: Dict, bench: Dict, tstats: Dict) -> str:
    def row(name, s, b=""):
        return f"<tr><td>{name}</td><td>{s}</td><td>{b}</td></tr>"
    rows = [
        row("Capital invested", fmt_inr(strat["invested"]), fmt_inr(bench["invested"])),
        row("Final value", fmt_inr(strat["final_value"]), fmt_inr(bench["final_value"])),
        row("Absolute profit", fmt_inr(strat["profit"]), fmt_inr(bench["profit"])),
        row("Money multiple", f"{fmt_num(strat['multiple'])}x", f"{fmt_num(bench['multiple'])}x"),
        row("XIRR", fmt_pct((strat["xirr"] or 0) * 100), fmt_pct((bench["xirr"] or 0) * 100)),
        row("CAGR (time weighted)", fmt_pct(strat["cagr"] * 100), fmt_pct(bench["cagr"] * 100)),
        row("Total return (TWR)", fmt_pct(strat["total_return"] * 100), fmt_pct(bench["total_return"] * 100)),
        row("Volatility (ann.)", fmt_pct(strat["volatility"] * 100), fmt_pct(bench["volatility"] * 100)),
        row("Sharpe (rf=0)", fmt_num(strat["sharpe"]), fmt_num(bench["sharpe"])),
        row("Sortino", fmt_num(strat["sortino"]), fmt_num(bench["sortino"])),
        row("Max drawdown", fmt_pct(strat["max_drawdown"]), fmt_pct(bench["max_drawdown"])),
        row("Calmar", fmt_num(strat["calmar"]), fmt_num(bench["calmar"])),
        row("Best day", fmt_pct(strat["best_day"]), fmt_pct(bench["best_day"])),
        row("Worst day", fmt_pct(strat["worst_day"]), fmt_pct(bench["worst_day"])),
        row("Positive days", fmt_pct(strat["positive_days"], 1), fmt_pct(bench["positive_days"], 1)),
        row("Period", f"{strat['years']:.2f} years", f"{bench['years']:.2f} years"),
    ]
    if tstats:
        rows += [
            row("Total trades", f"{tstats['total_trades']:,}", "—"),
            row("Buys / Sells", f"{tstats['buys']:,} / {tstats['sells']:,}", "—"),
            row("Realized profit", fmt_inr(tstats["realized_profit"]), "—"),
            row("Win rate on closed trades", fmt_pct(tstats["win_rate"], 1), "—"),
            row("Losing exits", f"{tstats['losing_sells']}", "—"),
            row("Profit factor (closed trades)", _profit_factor_text(tstats), "—"),
            row("Average win / loss", f"{fmt_inr(tstats['avg_win'])} / {fmt_inr(tstats['avg_loss'])}", "—"),
            row("Expectancy per closed trade", fmt_inr(tstats["expectancy"]), "—"),
            row("Average holding period", f"{fmt_num(tstats['avg_hold_days'], 1)} days", "—"),
            row("Best / worst trade", f"{fmt_inr(tstats['best_trade'])} / {fmt_inr(tstats['worst_trade'])}", "—"),
            row("Symbols traded", f"{tstats['symbols_traded']}", "—"),
            row("Gross turnover", fmt_inr(tstats["turnover"]), "—"),
        ]
    return ("<table class='metrics'><tr><th>Metric</th><th>Strategy</th><th>Nifty 50 SIP</th></tr>"
            + "".join(rows) + "</table>")


APP_JS = """
const TRADES = __TRADES__;
const DAILY = __DAILY__;
const fmtINR = new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0});
const fmtINR2 = new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2});
const money = v => (v===null||v===undefined||isNaN(v)) ? '—' : fmtINR.format(v);
const money2 = v => (v===null||v===undefined||isNaN(v)) ? '—' : fmtINR2.format(v);
const pct = v => (v===null||v===undefined||isNaN(v)) ? '—' : v.toFixed(2)+'%';
const cls = v => v>=0 ? 'pos' : 'neg';

function showTab(name){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));
  document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id==='page-'+name));
  window.dispatchEvent(new Event('resize'));
}
document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>showTab(t.dataset.tab)));

/* ---------- trade log: search, filter, sort, export ---------- */
let sortKey='date', sortDir=-1;
const F = {text:'', side:'', symbol:'', date:'', minProfit:''};

function visibleTrades(){
  return TRADES.filter(t=>{
    if(F.side && t.side!==F.side) return false;
    if(F.symbol && t.symbol!==F.symbol) return false;
    if(F.date && t.date!==F.date) return false;
    if(F.minProfit!=='' && !(t.profit>=parseFloat(F.minProfit))) return false;
    if(F.text){
      const q=F.text.toLowerCase();
      if(!(t.symbol.toLowerCase().includes(q)||t.action.toLowerCase().includes(q)||t.date.includes(q))) return false;
    }
    return true;
  }).sort((a,b)=>{
    const x=a[sortKey], y=b[sortKey];
    if(x===y) return 0;
    return (x>y?1:-1)*sortDir;
  });
}

function renderTable(){
  const rows = visibleTrades();
  const body = rows.map(t=>`<tr>
    <td>${t.date}</td>
    <td><a href="#" class="symlink" data-sym="${t.symbol}">${t.symbol}</a></td>
    <td><span class="pill ${t.side==='SELL'?'sell':'buy'}">${t.action}</span></td>
    <td>${money2(t.price)}</td>
    <td>${t.shares.toLocaleString('en-IN')}</td>
    <td>${money(t.value)}</td>
    <td class="${t.side==='SELL'?cls(t.profit):''}">${t.side==='SELL'?money(t.profit):'—'}</td>
    <td class="${t.side==='SELL'?cls(t.profit):''}">${t.side==='SELL'?pct(t.profit_pct):'—'}</td>
    <td>${t.hold_days??'—'}</td></tr>`).join('');
  document.getElementById('logBody').innerHTML = body || '<tr><td colspan="9">No trades match these filters.</td></tr>';
  const sells = rows.filter(t=>t.side==='SELL');
  const profit = sells.reduce((s,t)=>s+t.profit,0);
  const wins = sells.filter(t=>t.profit>0).length;
  const turnover = rows.reduce((s,t)=>s+t.value,0);
  document.getElementById('logStats').innerHTML =
    `${rows.length} of ${TRADES.length} trades · ${sells.length} closed · realized `+
    `<span class="${cls(profit)}">${money(profit)}</span> · win rate `+
    `${sells.length?(100*wins/sells.length).toFixed(1):'0.0'}% · turnover ${money(turnover)}`;
  document.querySelectorAll('.symlink').forEach(a=>a.addEventListener('click',e=>{
    e.preventDefault(); setFilter({symbol:a.dataset.sym});
  }));
}

function setFilter(patch){
  Object.assign(F, patch);
  document.getElementById('fSymbol').value = F.symbol;
  document.getElementById('fSide').value = F.side;
  document.getElementById('fDate').value = F.date;
  document.getElementById('fText').value = F.text;
  document.getElementById('fProfit').value = F.minProfit;
  renderTable();
  showTab('trades');
  document.querySelector('#page-trades .controls').scrollIntoView({behavior:'smooth',block:'nearest'});
}

document.getElementById('fText').addEventListener('input',e=>{F.text=e.target.value;renderTable();});
document.getElementById('fSide').addEventListener('change',e=>{F.side=e.target.value;renderTable();});
document.getElementById('fSymbol').addEventListener('change',e=>{F.symbol=e.target.value;renderTable();});
document.getElementById('fDate').addEventListener('change',e=>{F.date=e.target.value;renderTable();});
document.getElementById('fProfit').addEventListener('input',e=>{F.minProfit=e.target.value;renderTable();});
document.getElementById('fClear').addEventListener('click',()=>{
  Object.assign(F,{text:'',side:'',symbol:'',date:'',minProfit:''});
  ['fText','fSide','fSymbol','fDate','fProfit'].forEach(id=>document.getElementById(id).value='');
  renderTable();
});
document.getElementById('fExport').addEventListener('click',()=>{
  const rows=visibleTrades();
  const head=['date','symbol','action','price','shares','value','profit','profit_pct','hold_days'];
  const csv=[head.join(',')].concat(rows.map(r=>head.map(h=>r[h]).join(','))).join('\\n');
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));
  a.download='filtered_trades.csv'; a.click();
});
document.querySelectorAll('table.log th').forEach(th=>th.addEventListener('click',()=>{
  const k=th.dataset.key; if(!k) return;
  sortDir = (k===sortKey) ? -sortDir : -1; sortKey=k; renderTable();
}));

/* ---------- interaction helpers: only real clicks count ---------- */
/* A drag on a chart used to register as a click, which made the report feel
   twitchy. Every handler below goes through onPlotClick, which ignores a
   pointer that moved more than a few pixels or lingered, and ignores clicks
   that land right after a pan/zoom. */
function onPlotClick(gd, handler){
  if(!gd || !gd.on) return;
  let down=null, movedAt=0;
  gd.addEventListener('pointerdown', e=>{ down={x:e.clientX, y:e.clientY, t:Date.now()}; }, true);
  gd.addEventListener('pointerup', e=>{
    if(!down) return;
    const dist=Math.hypot(e.clientX-down.x, e.clientY-down.y);
    gd._wasDrag = dist>5 || (Date.now()-down.t)>600;
    down=null;
  }, true);
  gd.on('plotly_relayouting', ()=>{ movedAt=Date.now(); });
  gd.on('plotly_relayout', ()=>{ movedAt=Date.now(); });
  gd.on('plotly_click', ev=>{
    if(gd._wasDrag || Date.now()-movedAt < 250) return;   // that was a pan, not a click
    if(!ev.points || !ev.points.length) return;
    handler(ev);
  });
}
const pointDate = p => (p.x instanceof Date) ? p.x.toISOString().slice(0,10) : String(p.x).slice(0,10);

/* Y axes are locked so a drag can only pan sideways; refit them to whatever
   window the user lands on, otherwise zooming into 2020 shows a flat line. */
function autofitY(gd){
  if(!gd || !gd._fullLayout || gd._fitting) return;
  const fl=gd._fullLayout, upd={};
  const xr = (fl.xaxis && fl.xaxis.range) ? fl.xaxis.range.map(v=>new Date(v).getTime()) : null;
  if(!xr) return;
  /* Read _fullData, not data: plotly ships numeric columns as base64 typed
     arrays and only the fully resolved traces have them decoded. */
  const traces = gd._fullData || gd.data || [];
  Object.keys(fl).filter(k=>/^yaxis\d*$/.test(k)).forEach(yk=>{
    const anchor = 'y' + (yk.replace('yaxis','') || '');
    let lo=Infinity, hi=-Infinity;
    traces.forEach(tr=>{
      if((tr.yaxis||'y')!==anchor || tr.visible===false || tr.visible==='legendonly') return;
      if(!tr.x || !tr.y || !tr.y.length) return;
      if(!tr._tms) tr._tms = Array.prototype.map.call(tr.x, v => new Date(v).getTime());
      const n=Math.min(tr._tms.length, tr.y.length);
      for(let i=0;i<n;i++){
        const t=tr._tms[i];
        if(t<xr[0]||t>xr[1]) continue;
        const v=tr.y[i];
        if(v===null||v===undefined||isNaN(v)) continue;
        if(v<lo) lo=v; if(v>hi) hi=v;
      }
    });
    if(lo===Infinity) return;
    const pad=(hi-lo||Math.abs(hi)||1)*0.06;
    upd[yk+'.range']=[lo-pad, hi+pad];
  });
  if(!Object.keys(upd).length) return;
  gd._fitting=true;
  Plotly.relayout(gd, upd).then(()=>{ gd._fitting=false; }).catch(()=>{ gd._fitting=false; });
}
function wireAutofit(id){
  const gd=document.getElementById(id);
  if(!gd||!gd.on) return gd;
  let timer=null;
  gd.on('plotly_relayout', ev=>{
    if(gd._fitting) return;
    const keys=Object.keys(ev||{});
    if(!keys.some(k=>k.startsWith('xaxis'))) return;
    clearTimeout(timer);
    timer=setTimeout(()=>autofitY(gd), 80);   // debounced, so panning stays smooth
  });
  gd.on('plotly_doubleclick', ()=>setTimeout(()=>{
    const upd={};
    Object.keys(gd._fullLayout).filter(k=>/^yaxis\d*$/.test(k)).forEach(k=>upd[k+'.autorange']=true);
    upd['xaxis.autorange']=true;
    gd._fitting=true; Plotly.relayout(gd,upd).then(()=>{gd._fitting=false;});
  },50));
  return gd;
}
['equityChart','relativeChart','rollingChart','underwaterChart','tradeScatter'].forEach(wireAutofit);

/* ---------- click on the equity chart to inspect a day ---------- */
const eq = document.getElementById('equityChart');
function showDay(dateStr){
  const d = DAILY[dateStr];
  const box = document.getElementById('dayDetail');
  if(!d){ box.innerHTML = '<span class="hint">No portfolio record for '+dateStr+'.</span>'; return; }
  const dayTrades = TRADES.filter(t=>t.date===dateStr);
  const tradeRows = dayTrades.map(t=>`<tr><td><span class="pill ${t.side==='SELL'?'sell':'buy'}">${t.action}</span></td>
      <td>${t.symbol}</td><td>${money2(t.price)} × ${t.shares}</td><td>${money(t.value)}</td>
      <td class="${t.side==='SELL'?cls(t.profit):''}">${t.side==='SELL'?money(t.profit):''}</td></tr>`).join('');
  box.innerHTML = `<b>${dateStr}</b> &nbsp;
    Net worth <b>${money(d.nw)}</b> &nbsp;·&nbsp; invested ${money(d.inv)} &nbsp;·&nbsp;
    profit <span class="${cls(d.pnl)}">${money(d.pnl)}</span> &nbsp;·&nbsp;
    cash ${money(d.cash)} &nbsp;·&nbsp; deployed ${money(d.hold)} &nbsp;·&nbsp;
    drawdown <span class="${cls(d.dd)}">${pct(d.dd)}</span> &nbsp;·&nbsp; day ${pct(d.ret)}
    &nbsp;·&nbsp; Nifty SIP ${money(d.bench)}
    ${dayTrades.length? `<table>${tradeRows}</table>
      <button style="margin-top:8px" onclick="setFilter({date:'${dateStr}',symbol:'',side:''})">Show these ${dayTrades.length} trades in the log</button>`
      : '<div class="hint" style="margin-top:6px">No trades on this day.</div>'}`;
  box.scrollIntoView({behavior:'smooth', block:'nearest'});
}
/* The equity chart never yanks you to another tab: it fills the day panel and
   leaves the jump to the log to the button inside it. */
onPlotClick(eq, ev => showDay(pointDate(ev.points[0])));

onPlotClick(document.getElementById('symbolChart'), ev => setFilter({symbol:String(ev.points[0].y), date:'', side:''}));
onPlotClick(document.getElementById('tradeScatter'), ev => {
  const p=ev.points[0];
  setFilter({date:pointDate(p), symbol:p.customdata?String(p.customdata[0]):'', side:'SELL'});
});
renderTable();
"""


def build_report(
    net_worth_df: pd.DataFrame,
    nifty_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    monthly_invested_cash: Dict[str, float],
    cash_history: Optional[pd.DataFrame] = None,
    portfolio: Optional[Dict[str, Dict]] = None,
    out_path: str = "reports/backtest_report.html",
    title: str = "ETF SIP strategy — interactive backtest report",
    open_browser: bool = True,
) -> str:
    """Build the interactive HTML report and return its path."""
    cash_df = pd.DataFrame(cash_history) if cash_history is not None else None
    equity = build_equity_frame(net_worth_df, monthly_invested_cash, cash_df)
    bench = build_benchmark_frame(nifty_df, monthly_invested_cash)
    trades = prepare_trades(trades_df)
    strat_m = summary_metrics(equity, "Strategy")
    bench_m = summary_metrics(bench, "Nifty 50 SIP")
    tstats = trade_stats(trades)
    mtm = mark_to_market_stats(trades, portfolio)
    fric = friction_analysis(trades, equity)
    pnl = symbol_pnl(trades, portfolio)

    # ---- figures
    holdings_fig, holdings_tbl = holdings_figure(portfolio or {})
    divs = {
        "equity": _div(equity_figure(equity, bench, trades), "equityChart", 820),
        "relative": _div(relative_figure(equity, bench), "relativeChart", 620),
        "underwater": _div(underwater_figure(equity), "underwaterChart", 420),
        "rolling": _div(rolling_figure(equity), "rollingChart", 620),
        "dist": _div(distribution_figure(equity, bench), "distChart", 420),
        "heatmap": _div(monthly_heatmap(equity), "heatmapChart", 420),
        "yearly": _div(yearly_figure(equity, bench), "yearlyChart", 420),
        "symbol": _div(symbol_figure(pnl), "symbolChart", max(420, 22 * len(pnl))),
        "scatter": _div(trade_scatter_figure(trades), "tradeScatter", 460),
        "hold": _div(hold_figure(trades), "holdChart", 400),
        "activity": _div(activity_figure(trades, equity), "activityChart", 560),
        "holdings": _div(holdings_fig, "holdingsChart", 520),
    }

    # ---- KPI cards
    excess = strat_m["final_value"] - bench_m["final_value"]
    trough, depth, peak, recovery = max_drawdown_window(equity)
    kpis = "".join([
        _kpi("Final net worth", fmt_inr(strat_m["final_value"]),
             f"invested {fmt_inr(strat_m['invested'])}"),
        _kpi("Profit", fmt_inr(strat_m["profit"]),
             f"{fmt_num(strat_m['multiple'])}x money", _sign(strat_m["profit"])),
        _kpi("XIRR", fmt_pct((strat_m["xirr"] or 0) * 100),
             f"Nifty SIP {fmt_pct((bench_m['xirr'] or 0) * 100)}", _sign(strat_m["xirr"])),
        _kpi("CAGR (TWR)", fmt_pct(strat_m["cagr"] * 100),
             f"Nifty {fmt_pct(bench_m['cagr'] * 100)}", _sign(strat_m["cagr"])),
        _kpi("Max drawdown", fmt_pct(strat_m["max_drawdown"]),
             f"trough {pd.Timestamp(trough).date() if trough is not None else '—'}", "neg"),
        _kpi("Volatility", fmt_pct(strat_m["volatility"] * 100), f"Sharpe {fmt_num(strat_m['sharpe'])}"),
        _kpi("Vs Nifty 50 SIP", fmt_inr(excess),
             f"Nifty ends at {fmt_inr(bench_m['final_value'])}", _sign(excess)),
        _kpi("Win rate", fmt_pct(tstats.get("win_rate"), 1) if tstats else "—",
             f"{tstats.get('sells', 0)} closed trades · {fmt_pct(mtm.get('mtm_win_rate'), 1)} incl. open"
             if tstats else ""),
        _kpi("Profit factor (marked to market)", _pf(mtm.get("mtm_profit_factor")),
             f"undefined on closed trades: {tstats.get('losing_sells', 0)} losing exits" if tstats else ""),
        _kpi("Open positions", f"{len(portfolio or {})}",
             f"value {fmt_inr(holdings_tbl['value'].sum() if not holdings_tbl.empty else 0)}"),
        _kpi("Idle cash", fmt_inr(equity['Cash'].iloc[-1]),
             f"{equity['Cash'].iloc[-1] / strat_m['final_value'] * 100:.1f}% of net worth"
             if strat_m["final_value"] else ""),
        _kpi("Period", f"{strat_m['years']:.1f} yrs",
             f"{pd.Timestamp(equity['Date'].iloc[0]).date()} → {pd.Timestamp(equity['Date'].iloc[-1]).date()}"),
    ])

    # ---- embedded data for the JS layer
    trade_records = trades.copy()
    trade_records["date"] = trade_records["date"].dt.strftime("%Y-%m-%d")
    trade_records = trade_records[
        ["date", "symbol", "action", "side", "price", "shares", "value", "profit", "profit_pct", "hold_days"]
    ].replace({np.nan: None})
    trades_json = json.dumps(trade_records.to_dict("records"), default=float)

    daily = equity.merge(bench[["Date", "NetWorth"]], on="Date", how="left", suffixes=("", "_b"))
    daily_map = {
        pd.Timestamp(r.Date).strftime("%Y-%m-%d"): {
            "nw": round(float(r.NetWorth), 2),
            "inv": round(float(r.Invested), 2),
            "pnl": round(float(r.Profit), 2),
            "cash": None if pd.isna(r.Cash) else round(float(r.Cash), 2),
            "hold": None if pd.isna(r.Holdings) else round(float(r.Holdings), 2),
            "dd": round(float(r.Drawdown), 3),
            "ret": round(float(r.Ret) * 100, 3),
            "bench": None if pd.isna(r.NetWorth_b) else round(float(r.NetWorth_b), 2),
        }
        for r in daily.itertuples()
    }
    app_js = (APP_JS
              .replace("__TRADES__", trades_json)
              .replace("__DAILY__", json.dumps(daily_map)))

    symbols = sorted(trades["symbol"].unique().tolist()) if not trades.empty else []
    symbol_options = "".join(f'<option value="{s}">{s}</option>' for s in symbols)

    period = f"{pd.Timestamp(equity['Date'].iloc[0]).date()} → {pd.Timestamp(equity['Date'].iloc[-1]).date()}"
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{CSS}</style>
<script>{get_plotlyjs()}</script><script>{LOCALE_JS}</script>
</head><body>
<header>
  <div><h1>{title}</h1>
  <div class="sub">{period} · all values in INR · generated {pd.Timestamp.today().strftime('%d %b %Y %H:%M')}</div></div>
</header>
<div class="wrap">
  <div class="kpis">{kpis}</div>
  <div class="tabs">
    <div class="tab active" data-tab="overview">Overview</div>
    <div class="tab" data-tab="risk">Risk</div>
    <div class="tab" data-tab="returns">Returns</div>
    <div class="tab" data-tab="trades">Trades</div>
    <div class="tab" data-tab="holdings">Holdings</div>
    <div class="tab" data-tab="metrics">All metrics</div>
  </div>

  <div class="page active" id="page-overview">
    <div class="detail" id="dayDetail"><span class="hint">
      Click any point on the chart below to inspect that day (net worth, cash, drawdown and the trades booked).
      Drag to zoom, use the range buttons or the slider, double click to reset,
      and toggle the BUY / average down markers in the legend.</span></div>
    <div class="card"><h2>Net worth, invested capital and trades</h2>{divs['equity']}</div>
    <div class="card"><h2>Growth of ₹100 (flow adjusted) and value gained over the Nifty SIP</h2>{divs['relative']}</div>
  </div>

  <div class="page" id="page-risk">
    <div class="card"><h2>Underwater plot — time spent below the previous peak</h2>{divs['underwater']}</div>
    <div class="card"><h2>Rolling 1 year return, volatility and Sharpe</h2>{divs['rolling']}</div>
    <div class="card"><h2>Daily return distribution — strategy vs Nifty</h2>{divs['dist']}</div>
  </div>

  <div class="page" id="page-returns">
    <div class="grid2">
      <div class="card"><h2>Monthly returns</h2>{divs['heatmap']}</div>
      <div class="card"><h2>Calendar year returns</h2>{divs['yearly']}</div>
    </div>
    <div class="card"><h2>Trading activity and how the money is deployed</h2>{divs['activity']}</div>
  </div>

  <div class="page" id="page-trades">
    <div class="card"><h2>Profit by symbol — click a bar to filter the trade log</h2>{divs['symbol']}</div>
    <div class="card"><h2>Closed trades — return vs date (bubble size = position size). Click a bubble to filter the log.</h2>{divs['scatter']}</div>
    <div class="card"><h2>Trade distribution</h2>{divs['hold']}</div>
    <div class="card">
      <h2>Trade log</h2>
      <div class="controls">
        <input id="fText" placeholder="Search symbol / action / date">
        <select id="fSide"><option value="">All sides</option><option value="BUY">Buys</option><option value="SELL">Sells</option></select>
        <select id="fSymbol"><option value="">All symbols</option>{symbol_options}</select>
        <input id="fDate" type="date">
        <input id="fProfit" type="number" step="100" placeholder="Min profit ₹" style="width:150px">
        <button id="fClear">Clear filters</button>
        <button id="fExport">Export CSV</button>
      </div>
      <div class="stats" id="logStats"></div>
      <div class="tablewrap"><table class="log">
        <thead><tr>
          <th data-key="date">Date</th><th data-key="symbol">Symbol</th><th data-key="action">Action</th>
          <th data-key="price">Price</th><th data-key="shares">Shares</th><th data-key="value">Value</th>
          <th data-key="profit">Profit</th><th data-key="profit_pct">Return</th><th data-key="hold_days">Held</th>
        </tr></thead><tbody id="logBody"></tbody></table></div>
    </div>
  </div>

  <div class="page" id="page-holdings">
    <div class="card"><h2>Open positions by market value (colour = open P/L %)</h2>{divs['holdings']}</div>
    <div class="card"><h2>Open positions</h2>{_holdings_table(holdings_tbl)}</div>
  </div>

  <div class="page" id="page-metrics">
    <div class="card"><h2>Strategy vs benchmark</h2>{_metrics_table(strat_m, bench_m, tstats)}</div>
    <div class="card"><h2>Reality check — what the backtest does not charge you for</h2>
      <p class="stats">The exit rule only fires above a profit threshold, so no closed trade can be a
      loss and the classic profit factor has nothing to divide by. Losses live on in the open book,
      so the marked to market figures below are the ones to judge the strategy on.</p>
      {_reality_table(mtm, fric, strat_m)}</div>
  </div>
</div>
<script>{app_js}</script>
</body></html>"""

    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Interactive report written to {out_path}")
    if open_browser:
        webbrowser.open(f"file://{out_path}")
    return out_path


def _profit_factor_text(tstats: Dict) -> str:
    """Gross win / gross loss, or an explanation when there is no loss to divide by."""
    pf = tstats.get("profit_factor")
    if pf is None:
        return "undefined — no losing exit"
    return fmt_num(pf)


def _reality_table(mtm: Dict, fric: Dict, strat: Dict) -> str:
    def row(name, value, note=""):
        return f"<tr><td>{name}</td><td>{value}</td><td class='note'>{note}</td></tr>"
    cost_rows = "".join(
        row(f"Round trip cost at {c['bps']} bps per side",
            f"-{fmt_inr(c['cost'])}", f"{c['pct_of_nw']:.2f}% of final net worth")
        for c in fric.get("cost_scenarios", [])
    )
    rows = [
        row("Realized gains", fmt_inr(mtm["realized_win"]), "booked by trailing stop exits"),
        row("Realized losses", fmt_inr(-mtm["realized_loss"]), "the exit rule cannot produce one"),
        row("Unrealized gains in the open book", fmt_inr(mtm["open_win"]), ""),
        row("Unrealized losses in the open book", fmt_inr(-mtm["open_loss"]),
            f"{mtm['open_losers']} of {mtm['open_positions']} positions underwater"),
        row("Profit factor, marked to market", _pf(mtm["mtm_profit_factor"]),
            "gains ÷ losses including open positions — the comparable number"),
        row("Win rate, marked to market", fmt_pct(mtm["mtm_win_rate"], 1),
            "closed trades plus open positions"),
        row("Oldest underwater position", f"{mtm['oldest_loser_days']:,.0f} days",
            f"average underwater age {mtm['avg_loser_age']:,.0f} days"),
        row("Largest position", f"{mtm['largest_position']} · {mtm['largest_position_pct']:.1f}%",
            f"top 3 hold {mtm['top3_concentration']:.1f}% of the book"),
        row("Idle cash", f"{fric['mean_cash_pct']:.1f}% average",
            f"median {fric['median_cash_pct']:.1f}% — capital not earning the strategy return"),
        row("Gross turnover", fmt_inr(fric["turnover"]),
            f"{fric['turnover_x_capital']:.1f}x the capital invested, {fric['trades_per_year']:.0f} trades a year"),
    ]
    tax = [
        row("Short term realized gains", fmt_inr(fric["short_term_gains"]),
            f"{fric['short_term_share']:.1f}% of realized profit, held under 365 days"),
        row("Long term realized gains", fmt_inr(fric["long_term_gains"]), ""),
        row("Estimated tax (20% STCG / 12.5% LTCG)", f"-{fmt_inr(fric['estimated_tax'])}",
            f"{fric['estimated_tax'] / strat['profit'] * 100:.1f}% of the backtested profit"),
    ]
    return ("<table class='metrics'><tr><th>Item</th><th>Value</th><th>What it means</th></tr>"
            + "".join(rows) + "".join(cost_rows) + "".join(tax) + "</table>")


def _pf(value) -> str:
    return "undefined — no losses" if value is None else fmt_num(value)


def _holdings_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "<p class='stats'>No open positions at the end of the backtest.</p>"
    rows = []
    for r in df.sort_values("value", ascending=False).itertuples():
        cls = "pos" if r.pnl >= 0 else "neg"
        rows.append(
            f"<tr><td>{r.symbol}</td><td>{r.shares:,.0f}</td><td>{fmt_inr(r.buy_price, 2)}</td>"
            f"<td>{fmt_inr(r.close, 2)}</td><td>{fmt_inr(r.value)}</td>"
            f"<td class='{cls}'>{fmt_inr(r.pnl)}</td><td class='{cls}'>{r.pnl_pct:.2f}%</td>"
            f"<td>{int(r.hold_days) if r.hold_days else '—'}</td></tr>")
    return ("<table class='metrics'><tr><th>Symbol</th><th>Shares</th><th>Avg cost</th><th>Last close</th>"
            "<th>Market value</th><th>Open P/L</th><th>P/L %</th><th>Held (d)</th></tr>"
            + "".join(rows) + "</table>")
