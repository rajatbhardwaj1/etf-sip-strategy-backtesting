These are mainly for testing the SIP strategy, although test of lump-sum strategy is also there. User can run the funciton 
in the `main.py` and `main_non_SIP.py`.

Lets discuss the SIP strat, mainly the results, what is the best parameter to use this strat, how much returns one can expect,
does it beat nifty? below are the results. 

What I considered best parameters are as follows --

1. DMA = 10 , very important, for 20 its not giving as good results, at DMA = 10 , it beats nifty for 6y run easily. 
2. profit_thres = 6.5
3. trailing stoploss = 0.5
4. max buys = 1 
5. avg_down_thres = 0.4

I have assumed increment of 15% annually in the SIP.

I have compared the result of this strat with Nifty 50, i.e. at month end both strategy gets that lump sum , there are some
interesting observation, and tricks that lead to much better results ....... lets see 

 We are using a SIP of 30,000 INR. End date is fixed at 1 Oct 2025. XIRR values for ETF strategy and Nifty are shown. We are using hydration constant of 1,00,000

| Start Date | End Date    | ETF SIP Strategy XIRR | Nifty SIP XIRR |
|------------|------------|-----------------------|----------------|
| 2020-01-01 | 2025-10-01 | 21.8%                 | 12.63%         |
| 2021-01-01 | 2025-10-01 | 21.26%                | 10.55%         |
| 2022-01-01 | 2025-10-01 | 18.66%                | 10.24%         |
| 2023-01-01 | 2025-10-01 | 15.4%                 | 9.3%           |
| 2024-01-01 | 2025-10-01 | 13.41%                | 4.39%          |
| 2025-01-01 | 2025-10-01 | 9.60%                 | 6.70%          |
| 2025-04-01 | 2025-10-01 | 3.16%                 | 2.57%          |
| 2025-06-01 | 2025-10-01 | -0.62%                | -3.83%         |
| 2025-08-01 | 2025-10-01 | 1.54%                 | 1.95%          |



## Refreshing the price data

`data/*.csv` holds the daily OHLCV history used by every strategy. To pull in
whatever has been published since the last stored date:

```bash
python update_data.py            # every symbol in data/
python update_data.py GOLDBEES.NS ^NSEI   # just these
```

New rows are appended in place, so nothing already downloaded is re-fetched or
overwritten.

## Interactive report

`python main.py` runs the SIP strategy and writes
`reports/backtest_report.html` — a single self contained file (no internet
needed) that opens in the browser automatically. All amounts are in INR with
Indian digit grouping.

What you can do in it:

- **Overview** — net worth vs the Nifty 50 SIP, capital invested, idle cash,
  drawdown and profit on shared, zoomable axes. Drag to zoom, use the
  1M/3M/6M/YTD/1Y/3Y/All buttons or the range slider, double click to reset.
  **Click any point to inspect that day**: net worth, invested, profit, cash,
  deployed capital, drawdown, the day's move and the trades booked, with a
  button to jump straight to those trades in the log. Buy and average-down
  markers can be switched on from the legend.
- **Risk** — underwater plot with the worst drawdown window shaded, rolling
  1 year return / volatility / Sharpe, and the daily return distribution
  against the index.
- **Returns** — monthly return heatmap, calendar year returns vs the index,
  trades per month and the cash deployed vs idle split.
- **Trades** — profit by symbol (click a bar to filter), a bubble chart of
  every closed trade (click a bubble to filter), holding period and profit
  histograms, plus a searchable, sortable trade log with side/symbol/date/min
  profit filters and CSV export of exactly what is on screen.
- **Holdings** — treemap and table of the open positions with average cost,
  last close, market value and open P/L.
- **All metrics** — XIRR, time weighted CAGR, volatility, Sharpe, Sortino,
  Calmar, max drawdown, win rate, expectancy and more, side by side with the
  Nifty 50 SIP benchmark, plus a **reality check** table: marked to market
  profit factor and win rate (the closed trade profit factor is undefined
  because the exit rule cannot book a loss), concentration, idle cash, turnover
  and the cost/tax that the backtest does not charge.

Chart handling is deliberately calm: dragging **pans** (it never fires off an
accidental zoom box), the mouse wheel scrolls the page rather than the chart,
the y axis is locked and refits itself to whatever window you pan or zoom to,
double click resets, and a drag is never mistaken for a click.

Returns used for the risk metrics are flow adjusted, so the monthly SIP inflow
is not counted as performance.

---

# Multi-window backtest (Nov 2026)

**📄 [Full write-up: docs/RESULTS.md](docs/RESULTS.md)** — methodology, regime
results, limitations and a Yahoo data bug that was inflating every earlier
number.

**📊 [Interactive charts](https://rajatbhardwaj1.github.io/etf-sip-strategy-backtesting/)**
— net worth, idle cash, cumulative SIP and a cashflow-matched Nifty 50 SIP, for
each of eight windows. (Enable GitHub Pages from `/docs` to serve this.)

## Headline

₹30,000/month SIP, +15% a year, on the 39-ETF universe the live bot trades.
Benchmarks receive the strategy's own cashflows, so the comparison measures the
strategy and not the SIP schedule.

| Window | Years | Strategy XIRR | Nifty 50 | Max DD | Avg idle cash |
|---|---:|---:|---:|---:|---:|
| Full history (2016→) | 10.9 | **+15.2%** | +10.3% | -33% | 28% |
| Pre-COVID (2016-19) | 4.0 | **+14.1%** | +10.9% | -13% | 45% |
| COVID crash+rally (2020-21) | 2.0 | +17.8% | **+32.1%** | -15% | 57% |
| Bear/sideways (2022) | 1.0 | **+26.4%** | +9.2% | -6% | 54% |
| Recent regime (2023→) | 3.9 | **+12.4%** | +5.7% | -9% | 28% |
| Last 5 years | 5.0 | **+13.3%** | +6.8% | -9% | 26% |
| Last 3 years | 3.0 | **+11.1%** | +3.7% | -11% | 25% |
| Last 1 year | 1.0 | **+13.5%** | +6.3% | -6% | 36% |

Beat the index in 7 of 8 windows. The single loss is the 2020-21 melt-up
(+17.8% against +32.1%), and the cause is throughput rather than a shortage of
signals: ETFs were below their 10-day DMA on 41.0% of days in 2020-21 against
44.5% in 2022. Position size of net worth/40 and one buy a day could not deploy
the SIP fast enough - average idle cash was 57.4% - while the +6.5% exit kept
harvesting slices of a market that rose 128% off its low. The same mechanics
return the favour in 2022 (+26.4% against +9.2%). Full reasoning in
[docs/RESULTS.md](docs/RESULTS.md).

## The data bug

Five Nippon BeES ETFs carry corrupt prices on **2019-12-19/20** - Yahoo applied
a bogus split factor for two days, 100x on GOLDBEES, which shows ₹0.34 against
a true ₹34. A previous-row outlier filter cannot catch it: the -99% entry and
+9900% exit rows are dropped while the corrupt plateau between them survives.
The strategy read that plateau as the largest "fallen" signal in its history
and booked a fictional ₹5.7M profit - 99.7% of all profit in the 2016-2019
window.

`sanitize_price_series()` compares each price to a centred 21-day rolling median
instead, and is wired into `main.py` and the backtest harness.

| Window | Before | After |
|---|---:|---:|
| Pre-COVID (2016-2019) | +92.1% | **+14.1%** |
| Full history (2016→) | +27.8% | **+15.2%** |

## Parameters hold up

`dma_window = 10` is genuinely optimal (5 → +15.4%, 20 → +13.2%, 50 → +12.1%,
against +15.2%), confirming the original note above. `profit_threshold = 6.5`,
`avg_down_threshold = 4%` and `trailing_stop = 0.5%` also survive testing: the
alternatives are worse on balance. Raising the profit threshold looked better on
the two windows the sweep tuned on and then beat live in only 2 of 8 - tune on a
subset, validate on everything.

## Research note

The no-stop-loss design works - 408 of 433 positions (94%) exited at +6.5%,
median hold 63 days - but the averaging that underpins it rarely fires. 66% of
exited positions were never averaged at all, and INFRABEES, LOWVOLIETF and
ALPL30IETF were each held 1.5-2.5 years with **zero** averaging despite being
eligible on 138, 232 and 43 days. Averaging is gated on ranking in the day's
top-3 most-fallen vs the 10-day DMA, which a position that drifted down over
months never does; and between -4% and +6.5% nothing can happen at all.

Triggering on drawdown from average cost with a reserved daily slot raises mean
XIRR across the eight windows from +15.5% to +17.2% and cuts end-of-window
underwater positions from 90 to 69. Opt-in via `avg_down_scan_all`,
`avg_down_priority` and `avg_down_extra_slots`; defaults are unchanged, and the
live deployment runs the original rules. Details in
[docs/RESULTS.md](docs/RESULTS.md).

## Scripts

```bash
./.venv/bin/python backtest_windows.py     # the regime table
./.venv/bin/python param_sweep.py          # one-at-a-time sensitivity
./.venv/bin/python candidate_configs.py    # validate a variant on every window
./.venv/bin/python plot_windows.py         # interactive charts into docs/
```
