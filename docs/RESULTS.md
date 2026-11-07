# An ETF SIP strategy, backtested across market regimes

A systematic monthly-SIP strategy that buys Indian sector and index ETFs when
they fall below their short moving average, averages down into weakness, and
exits on a trailing stop once a position is 6.5% in profit. **It never sells at
a loss.**

This document reports what it actually returned over ten years, how it was
tested, and — importantly — a data bug that was inflating every earlier result.

**[→ Interactive charts for all eight windows](https://rajatbhardwaj1.github.io/etf-sip-strategy-backtesting/)**

---

## The strategy

| Rule | Value |
|---|---|
| Universe | 39 NSE-listed sector and index ETFs |
| SIP | ₹30,000 a month, stepped up 15% each year |
| Signal | Each day, rank ETFs by % below their 10-day moving average |
| Buy | The most-fallen ETF, at most 1 purchase per day, only while below the DMA |
| Position size | Net worth ÷ 40, capped by available cash |
| Average down | If a held ETF is more than 4% below its average cost |
| Exit | Once a position is +6.5% up, trail by 0.5% off its peak |
| Stop-loss | **None.** A losing position is averaged, never cut |

The no-stop-loss design is deliberate, and it is the part most likely to look
reckless at first glance. These are diversified baskets, not single companies —
a sector ETF does not go to zero. Averaging down lowers the break-even bar, so
a position does not need to recover to where it was first bought; it only needs
to reach *average cost* + 6.5%.

The data supports that: of **433 positions opened between 2016 and 2026, 408
(94%) exited at +6.5%**, with a median holding period of 63 days.

## How it was tested

- **Universe is read from the live trading bot's own source**, so the backtest
  cannot drift from what is actually deployed.
- **The benchmark receives the strategy's own monthly cashflows**, on the same
  dates. A benchmark running its own SIP schedule would measure the schedule as
  much as the strategy.
- **XIRR is computed from actual dates** (bisection on dated flows), not from
  assumed-equal monthly spacing.
- **Prices are sanitised against a 21-day rolling median** before use. See the
  next section for why that is not optional.
- Data: Yahoo Finance daily OHLC, 2015-01-01 to 2026-11-06.

## First, a data bug worth knowing about

Five Nippon India (BeES) ETFs carry corrupt prices on **2019-12-19 and
2019-12-20**, where Yahoo applied a bogus split factor for two days: 10× for
NIFTYBEES, BANKBEES, PSUBNKBEES and HNGSNGBEES, and **100× for GOLDBEES**,
which shows ₹0.34 against a true ₹34.

A conventional outlier filter does not catch this. Comparing each row to the
previous one in a single pass drops the −99% entry row and the +9,900% exit
row, but the **corrupt plateau between them survives** — its day-to-day changes
are tiny. The strategy read that plateau as the largest "fallen" signal in its
history, bought with everything it had, and booked a fictional ₹5.7M profit:
**99.7% of all profit in the 2016-2019 window.**

Comparing each price to a *centred rolling median* fixes it, because a
three-day plateau cannot drag a 21-day median it is a minority of.

| Window | Reported before | Actual |
|---|---:|---:|
| 2016-2019 | +92.1% | **+14.1%** |
| 2016-2026 | +27.8% | **+15.2%** |

If you backtest Indian ETFs on Yahoo data, check this date.

## Results

₹30,000/month, +15% a year, fresh start in each window.

| Window | Years | ETFs | Strategy XIRR | Nifty 50 | Nifty 500 | Max DD | Avg idle cash |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full history (2016→) | 10.9 | 37 | **+15.2%** | +10.3% | +11.9% | −33% | 28% |
| Pre-COVID (2016-19) | 4.0 | 13 | **+14.1%** | +10.9% | +8.2% | −13% | 45% |
| COVID crash + rally (2020-21) | 2.0 | 19 | +17.8% | **+32.1%** | +36.7% | −15% | 57% |
| Bear / sideways (2022) | 1.0 | 25 | **+26.4%** | +9.2% | +8.2% | −6% | 54% |
| Recent regime (2023→) | 3.9 | 37 | **+12.4%** | +5.7% | +7.3% | −9% | 28% |
| Last 5 years | 5.0 | 37 | **+13.3%** | +6.8% | +8.6% | −9% | 26% |
| Last 3 years | 3.0 | 37 | **+11.1%** | +3.7% | +4.3% | −11% | 25% |
| Last 1 year | 1.0 | 37 | **+13.5%** | +6.3% | +5.3% | −6% | 36% |

**It beat the index in 7 of 8 windows, by 5 to 17 percentage points.**

### The one loss is the interesting one

In the 2020-21 melt-up the strategy returned +17.8% against the Nifty's
+32.1% on identical cashflows. The cause is **throughput, not signal quality** —
and it is worth being precise, because the intuitive explanation is wrong.

It is tempting to say a one-way market gave it nothing to buy. It did not:
ETFs traded below their 10-day moving average on **41.0% of days in 2020-21**,
against **44.5% in 2022** — the year the strategy returned +26.4% and beat the
index by 17 points. Buy signals were abundant. What failed was the capacity to
act on them.

Two rules cap deployment: each purchase is net worth ÷ 40, and only one new
position may be opened per day. Starting from zero capital in January 2020 the
book was small, so every buy was small, while ₹30,000 of fresh SIP arrived each
month regardless. Cash piled up faster than the rules could spend it —
**average idle cash 57.4%**, median day **62.7%**, below 25% on only **10% of
days**. Through the fastest recovery in Indian market history, most of the
portfolio earned nothing.

The exit rule compounded it. Selling at +6.5% with a 0.5% trail produced **103
exits at a median hold of 31 days**, averaging ₹1,700 realised each, while the
Nifty rose **128% off its March 2020 low**. The strategy harvested repeated
6.5% slices and re-entered higher; the index held the whole move. A SIP into
the index also puts every rupee to work the day it arrives.

The mirror image is 2022: index +9.2%, strategy **+26.4%**. The same mechanics
that cost 14 points in the rally earned 17 in the chop.

### What drives the returns

- **Exits are frequent and small.** 94% of positions close just above +6.5%,
  median hold 63 days. Returns come from turnover, not from holding winners.
- **Cash is the binding constraint.** 25-28% of net worth sits idle in mature
  windows and over half in young ones — and it is the position-sizing and
  one-buy-a-day rules that cause it, not a shortage of signals.
- **Mean reversion is the edge.** The strategy is structurally long volatility
  and short trend: it lags sustained rallies and dominates ranges.

## Limitations — read these before trusting the numbers

1. **Universe availability, not survivorship.** Only 10 of the 37 ETFs existed
   in 2016; six listed in 2024. The 2016 window is really a 10-ETF strategy
   growing into a 37-ETF one. It is point-in-time correct — no lookahead — but
   the early years are not testing today's strategy.
2. **Every window starts from zero capital.** Each buy is net worth ÷ 40, so a
   young book deploys slowly. That is why short windows show 36-57% idle cash.
   A mature portfolio does not carry that drag, so short-window results
   understate a running deployment.
3. **No costs modelled beyond a flat ₹20 per sell.** No brokerage on buys, no
   STT, no stamp duty, no slippage. Real-world figures will be lower; the live
   deployment's contract notes show roughly ₹1,500 of charges per ₹6 lakh
   traded.
4. **Max drawdown is softened by inflows.** It is peak-to-trough on net worth,
   and continuing SIP money lifts the curve. Treat it as comparable between
   windows, not as an absolute risk measure.
5. **One parameter set, tested on the same data it was chosen on.** The
   parameters below were not selected by this backtest, but neither have they
   been walk-forward validated.

## Parameter sensitivity

Varying one parameter at a time, over the full 2016-2026 window and the last
five years:

| Parameter | Live | Alternatives tested | Verdict |
|---|---|---|---|
| DMA window | 10 | 5 → +15.4%, 20 → +13.2%, 50 → +12.1% | **10 is right** (+15.2%) |
| Profit threshold | 6.5% | 4% → +15.5%, 10% → +16.0%, 15% → +16.6% | Higher looked better on two windows, then beat live in only 2 of 8 — **keep 6.5%** |
| Avg-down threshold | 4% | 2% → +13.7%, 8% → +12.7% | **4% is right** |
| Trailing stop | 0.5% | 1.0% → +14.8%, 2.0% → +14.3% | **0.5% is right** |

The profit-threshold row is the useful lesson: a change that wins on the
windows you tuned on can easily lose across all of them. Tune on a subset,
validate on everything.

## Research note: the averaging-down mechanism is starved

The no-stop-loss thesis works, but the averaging that underpins it rarely
fires. **66% of exited positions were never averaged down at all**, and some
positions were held for years without a single top-up despite qualifying for
months:

| | Held | Cost vs now | Worst dip | Days eligible to average | Avg-downs fired |
|---|---:|---:|---:|---:|---:|
| INFRABEES | 848d | +2.9% | −15.9% | 138 of 576 | **0** |
| LOWVOLIETF | 757d | −1.6% | −14.0% | 232 of 512 | **0** |
| ALPL30IETF | 528d | +0.1% | −9.5% | 43 of 360 | **0** |

Two causes:

1. **Averaging is gated on a momentum screen.** A held position is only topped
   up if it ranks in the day's top-3 most-fallen *versus its 10-day DMA*. An
   ETF that drifted 14% below cost over several months is not falling *today*,
   so it never ranks. LOWVOLIETF spent 45% of its holding period eligible to be
   averaged and was averaged zero times.
2. **A dead band between −4% and +6.5%.** Too high to average, too low to exit.
   Those three sat there for 55-88% of their lives. INFRABEES was exit-eligible
   on 1 day out of 576; the other two never once reached +6.5%.

The capital was not losing. It was stuck.

Triggering averaging on **drawdown from average cost** instead of the momentum
ranking, with a daily slot reserved so it never competes with new purchases:

| | Mean XIRR across 8 windows | Beats live | Underwater positions at window end |
|---|---:|---:|---:|
| Live | +15.5% | — | 90 |
| Average on cost drawdown + reserved slot | **+17.2%** | 6/8 | **69** |

More averaging, fewer stuck positions, ~1.7 points more return. It is weaker in
the pre-COVID window, when only 13 ETFs existed. **This is a research finding,
not a recommendation** — it has not been walk-forward validated, and it is not
what the live deployment runs.

## Reproducing this

```bash
git clone https://github.com/rajatbhardwaj1/etf-sip-strategy-backtesting.git
cd etf-sip-strategy-backtesting
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python download_data.py        # Yahoo Finance, 2015 →
./.venv/bin/python backtest_windows.py     # the regime table above
./.venv/bin/python param_sweep.py          # one-at-a-time sensitivity
./.venv/bin/python candidate_configs.py    # validate a variant on every window
./.venv/bin/python plot_windows.py         # interactive charts → docs/
```

## Not investment advice

This is a record of a backtest on historical data, published because the method
and the data bug are more interesting than the returns. Past results do not
predict future ones, the limitations above are material, and nothing here is a
recommendation to buy or sell anything.
