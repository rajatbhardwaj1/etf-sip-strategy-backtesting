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

Run `backtest_windows.py` for the regime table, `param_sweep.py` for
one-at-a-time sensitivity, `candidate_configs.py` to test a candidate across
every window. Universe is read live from `strategy-automation/src/etf.py`, so
it cannot drift from what is actually deployed. Benchmarks receive the
strategy's **own monthly cashflows**, so the comparison measures the strategy
and not the SIP schedule.

## First: a data bug that was inflating every pre-2020 result

Five Nippon India (BeES) ETFs carry corrupt prices on **2019-12-19 and
2019-12-20** — Yahoo applied a bogus split factor for two days (10x for
NIFTYBEES, BANKBEES, PSUBNKBEES, HNGSNGBEES; 100x for GOLDBEES, which shows
₹0.34 against a true ₹34).

`filter_outliers()` cannot catch this. It compares each row only to the
previous one, computed in a single pass, so the -99% entry and +9900% exit rows
are dropped while the corrupt **plateau between them survives**. The strategy
read that plateau as the largest "fallen" signal in its history, bought with
everything it had, and booked a fictional ₹5.7M profit — 99.7% of all profit in
the 2016-2019 window.

`sanitize_price_series()` compares each price to a centred 21-day rolling
median and drops anything outside a 3x band. A plateau cannot drag a median it
is a minority of. Now wired into `main.py` and the backtest harness.

Effect of the fix:

| Window | Before | After |
|---|---|---|
| Pre-COVID (2016-2019) | +92.1% | **+14.1%** |
| Full history (2016→) | +27.8% | **+15.2%** |

Any earlier result from this repo that spans Dec 2019 was overstated.

## Results — live configuration

DMA 10, profit threshold 6.5%, trailing stop 0.5%, 1 buy/day, avg-down 4%,
buy divisor 40. SIP ₹30,000/month, +15% a year.

| Window | Years | ETFs | Strategy XIRR | Nifty 50 | Nifty 500 | Max DD | Avg cash |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full history (2016→) | 10.9 | 37 | **+15.2%** | +10.3% | +11.9% | -33% | 28% |
| Pre-COVID (2016-19) | 4.0 | 13 | **+14.1%** | +10.9% | +8.2% | -13% | 45% |
| COVID crash+rally (2020-21) | 2.0 | 19 | +17.8% | **+32.1%** | +36.7% | -15% | 57% |
| Bear/sideways (2022) | 1.0 | 25 | **+26.4%** | +9.2% | +8.2% | -6% | 54% |
| Recent regime (2023→) | 3.9 | 37 | **+12.4%** | +5.7% | +7.3% | -9% | 28% |
| Last 5 years | 5.0 | 37 | **+13.3%** | +6.8% | +8.6% | -9% | 26% |
| Last 3 years | 3.0 | 37 | **+11.1%** | +3.7% | +4.3% | -11% | 25% |
| Last 1 year | 1.0 | 37 | **+13.5%** | +6.3% | +5.3% | -6% | 36% |

**It beats the index in 7 of 8 windows, by 5-17 points.** The one loss is the
2020-21 melt-up: +17.8% against +32.1%. That is the expected signature of a
dip-buying strategy holding half its book in cash — it cannot keep up with a
market that only goes up, and it dominates when the market chops.

### Two structural caveats

- **Universe availability, not survivorship.** Only 10 of the 37 ETFs existed
  in 2016; six listed in 2024. The 2016 window is really a 10-ETF strategy that
  grows into a 37-ETF one. Point-in-time correct, but the early years are not
  testing today's strategy.
- **Every window starts from zero.** Each buy is net_worth/40, so a fresh run
  deploys very slowly — which is why short windows show 36-57% average cash. A
  mature book (the live one) does not carry that drag, so short-window results
  understate the live setup.

## Can it be improved? Yes — one bottleneck dominates

Cash drag. The live config leaves **25-28% of net worth idle** in mature
windows and over half in young ones. Fixing deployment is worth more than
anything else tested.

| Config | Mean XIRR | Beats live | Beats Nifty | Worst DD |
|---|---:|---:|---:|---:|
| A — live (divisor 40, 1 buy/day) | +15.5% | — | 7/8 | -33.3% |
| **B — buy divisor 10** | **+17.5%** | 6/8 | **8/8** | -35.1% |
| **C — max 3 buys/day** | **+16.9%** | **7/8** | 7/8 | **-32.5%** |
| D — profit threshold 12 | +13.8% | 2/8 | 5/8 | -34.5% |
| G — B+C together | +16.3% | 4/8 | 8/8 | -34.7% |
| H — divisor 20, 3 buys/day | +14.6% | 2/8 | 6/8 | -35.1% |

- **B (divisor 10)** is the highest-returning and the only config that beats
  the index in all 8 windows. It closes the bull-market gap outright: +36.8%
  against Nifty's +32.1% in 2020-21, where live managed +17.8%. Costs ~2 points
  of extra drawdown, and it is the weakest config over the last year.
- **C (3 buys/day)** is the most consistent — it is the only change that beat
  live in 7 of 8 windows *and* reduced drawdown.
- **B and C are substitutes, not complements.** Both solve the same bottleneck;
  applying both (G) is worse than either alone, because it over-deploys.
- **D is a cautionary tale.** Raising the exit threshold looked good on the two
  windows the sweep tuned on, then beat live in only 2 of 8. Tune on a subset,
  validate on everything.

### Confirmed as already-correct

`dma_window = 10` is well chosen — 20 gives +13.2%, 5 gives +15.4%, 50 gives
+12.1%, against +15.2% for 10. The readme's original claim holds up.
`profit_threshold = 6.5` and `avg_down_threshold = 4%` also survive: 4, 10 and
15 are all worse on balance, as are 2% and 8% avg-down.

### Unaddressed risk: there is no stop-loss

A position is only ever sold above +profit_threshold, so "win rate on sells" is
100% by construction and means nothing. The real picture is in what is still
held: at the end of most windows **48-67% of open positions are underwater**,
the worst around -10%. Losers are held indefinitely and quietly consume the
book. Nothing tested here addresses that, and it is the most interesting
direction left — a time-based or drawdown-based exit for chronic losers.
