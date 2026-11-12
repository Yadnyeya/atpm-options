# USATECH Options Project — Draft Plan

Oct 8, 2026 · @Yadnyeya Vairat

## Start here: the workflow in plain words

Options are insurance on the Nasdaq-100. VXN says how pricey that insurance is each day; the class data says how much the index really moved. When insurance looks overpriced versus our forecast we sell it, when underpriced we buy it, and we hedge so we only bet on the size of moves, not their direction.

&#91;embedded content: simplified project workflow · 3 inputs, 9 steps\]

The class data is the real world, VXN is the daily price of insurance, and the chain snapshot only checks that our prices and costs look realistic. Every later section of this plan details one box.

## Project at a glance

We trade options on the Nasdaq-100 (class file USATECH) by pricing them ourselves with Black-Scholes, using VXN from FRED as the market's implied vol and the class price data as the underlying. Project 10 asks for an options pricing strategy, Greeks-based hedging and a VaR engine, plus backtesting, risk evaluation and a few optimization scenarios.

| Item | Status | Detail |
| --- | --- | --- |
| Project | Locked | #10 Options Trading with Risk Management |
| Underlying | Locked | USATECH.IDXUSD, 1h, 2020-07-01 to 2025-06-30 (UTC) |
| Implied vol source | Locked | VXN (FRED series VXNCLS) |
| Team | Locked | 2 people, 10-minute presentation, both speak |
| Language | Locked | Python (pandas, numpy, scipy, arch, matplotlib) |
| Allowed bars | Locked (rule) | 1h, 4h, daily only |
| Core trade | Open | Choose from the candidates below |
| Hedge frequency, tenor, strikes | Open | Settled by the optimization runs |

**Course rules that shape every step:**

- The strategy must be built on the class data. Outside data (FRED, chain) is a supplement only.
- No timeframes outside 1h, 4h and daily, for analysis or optimization.
- Deliverables: documented Python code, a written report with charts, backtest metrics, and slides. Upload everything to Canvas and email a PDF or HTML copy to the professor.

**Course dates that line up with the project:**

| Date | Class | Why it matters |
| --- | --- | --- |
| Oct 8 | Lecture 5: covariance and volatility forecasting | GARCH/EWMA for our vol forecast |
| Oct 15 | Midterm | Project pause week |
| Oct 29 | Lecture 7: risk management | VaR methods for the engine |
| Nov 12 | Project progress report | Need a working backtest by then |
| Nov 19 | Lecture 9: backtesting | Look-ahead and overfitting checks |
| Dec 3 | Final presentations (syllabus) | The project sheet also mentions Dec 8; confirm with the professor |

## Data sources

Four inputs, all free. The class file drives every price and P\&L; the other three only supply what the class data cannot (implied vol, rates, market skew and costs).

| # | Input | Where | How to get it | Used for | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 | USATECH hourly OHLC | Canvas > Files > RawDataDoNotModify > DataSet2 | Download the CSV | Underlying price, realized vol, delta-hedge P&L, VaR scenarios | Last modified Sep 24, later than the other files: re-download the current version. Never edit the raw file |
| 2 | VXN daily close | [FRED VXNCLS](https://fred.stlouisfed.org/series/VXNCLS) | CSV download, or a free FRED API key with `fredapi` / `pandas_datareader` | Implied vol (ATM, 30-day) on each backtest day | Holidays show as "." (blank); it is in percent points |
| 3 | 3-month T-bill | FRED DGS3MO | Same as above | Risk-free rate r in Black-Scholes | Percent, annual; convert to a decimal |
| 4 | QQQ (or NDX) option chain | Yahoo Finance via `yfinance` | One snapshot, saved to CSV with its date | Skew shape, bid-ask cost, checking our pricer | A 2026 snapshot: calibration only, never backtest prices |

**Assumption to state in the report:** Nasdaq-100 dividend yield q held constant (roughly 0.6 to 0.8% a year), with a sensitivity check. Confirm the figure when we pull data.

**What to pull from the chain snapshot:**

- Three expiries near 7, 30 and 60 days.
- For each strike: bid, ask, mid, implied vol, open interest.
- Save it as is to `data/raw/` with the snapshot date in the file name.

**Folder layout:** `data/raw/` (untouched downloads) · `data/processed/` (cleaned, merged) · `notebooks/` · `src/` · `results/` (tables, charts) · `report/`.

## Data preparation

The goal of this stage is one clean, merged table per bar size (1h, 4h, daily) where every value was knowable at that bar's timestamp.

**What the class file contains** (checked against the downloaded CSV):

| Check | Finding | What we do about it |
| --- | --- | --- |
| Columns | timestamp, open, high, low, close, volume | Use OHLC; ignore volume |
| Period | Jul 1, 2020 to Jul 1, 2025: 5 years, not 6 | State the exact window in the report |
| Rows | 29,508 hourly bars; no duplicates or bad timestamps | Still log the gap check |
| Which index | Nasdaq-100 (ends near 22,640; the Composite was about 20,400) | Matches VXN, which is built on Nasdaq-100 options |
| Price levels | About 10,140 at the start, 22,643 at the end; 2022 fell 16,385 to 10,958 (−33%) | Sanity check passes |
| Trading hours | CFD feed, about 23 hours a day, Sunday evening to Friday, short daily break | Treat like Nasdaq-100 futures hours, not the 9:30–4pm session |
| Timezone | UTC | 4pm New York close = 20:00 UTC in summer, 21:00 UTC in winter |
| Volume | Provider tick activity (values like 6.3), not shares or contracts | Never use it as a signal or report it as volume |
| Sunday bars | Resampling as-is gives about 310 "days" a year | Fold Sunday-evening bars into Monday (about 252 days a year) |

1. **Load and inspect the class file.** Check column names, data types, the first and last timestamps, and the row count.
2. **Fix time.** Timestamps are UTC. Convert to New York time so a "daily close" means the 4pm ET bar, which matches when VXN closes. That is the 20:00 UTC bar in summer and the 21:00 UTC bar in winter, switching with daylight saving in March and November.
3. **Quality checks.** Log each issue in a table rather than silently fixing it.
   - Duplicate timestamps and missing hours (separate normal closures like weekends from true gaps).
   - Zero or negative prices; bars where high is below open or close.
   - Extreme returns (for example above 8 standard deviations): investigate, don't delete.
4. **Resample to 4h and daily.** Open = first, high = max, low = min, close = last. No other bar sizes.
5. **Returns and annualizing.** Log returns per bar. Count bars per year from the data itself, since the CFD trades almost 24 hours and 252 × 6.5 would be wrong. Fold Sunday-evening bars into Monday so daily bars come to about 252 a year.
6. **Merge FRED series onto the daily table.** VXN and the T-bill rate for day t are used only at or after the 4pm close of day t. Missing FRED days carry the previous value forward, never a later one.
7. **Process the chain snapshot.** For each expiry: mid price, moneyness (strike / spot), and implied vol relative to ATM vol. This gives the skew curve and the bid-ask spread as a % of mid, both by moneyness.
8. **Save and document.** Write processed files plus a short data dictionary (column, unit, source).

**Stage is done when:** a summary table shows row counts, date range, gaps found, and how each was handled; plots of price, hourly returns and VXN look sane; and a check shows no column uses information from a later timestamp.

## Core trade candidates (to choose)

Recommendation: **A, two-sided volatility trading**. It uses every rubric piece (pricing, Greeks, hedging, VaR) and contains B and E as special cases, so we can report those as comparisons for free.

**The idea behind A, B and E.** Implied vol (VXN) is what the market charges for options. Realized vol is what the index actually does afterwards. Historically implied tends to sit above realized, so option sellers earn a premium on average but lose heavily in crashes. A delta-hedged option's daily P&L is approximately:

```latex
\text{P\&L}_t \approx \tfrac{1}{2}\,\Gamma_t\,S_t^2\left(\sigma_{\text{realized}}^2 - \sigma_{\text{implied}}^2\right)\Delta t
```

If you are long the option you profit when realized beats implied; short, the reverse. Our edge, if any, is forecasting realized vol from the class data better than VXN implies.

| Option | How it works | Entry signal | Hedging | Rubric fit | Build effort | Main risk |
| --- | --- | --- | --- | --- | --- | --- |
| **A. Two-sided vol** | Sell a straddle when VXN is rich, buy one when cheap, flat in between | Gap between VXN and our realized-vol forecast, beyond a threshold | Delta-hedge with USATECH | Full | Medium-high | Forecast errors; crash losses on the short side |
| **B. Short vol only** | Only the selling half of A (straddle or 25-delta strangle) | VXN above forecast by a threshold | Delta-hedge | Full | Medium | Big losses in sudden sell-offs (for example early 2022) |
| **C. Put-write with filter** | Sell 30-day puts with cash set aside; skip when trend or vol regime is bad | Trend (moving average) or VXN level filter | None or partial | Partial: weak on Greeks hedging | Low | Same crash risk, plus full directional exposure |
| **D. Collar on a long position** | Hold USATECH, buy a protective put, sell a call to pay for it | Always on, or switched by trend | None (the options are the hedge) | Partial | Low | Caps upside; story is about risk shaping, not alpha |
| **E. Gamma scalping (long vol)** | Only the buying half of A; rebalance delta to lock in gains from swings | Forecast above VXN | Delta-hedge, often 1h | Full | Medium | Slow bleed from time decay when markets are calm |
| **F. Directional with options** | A price signal from the class data (for example moving-average crossover) traded via call or put spreads | Technical signal | None | Partial | Low-medium | Overlaps projects 3 and 14; options are secondary |

**How to choose:** if we want the strongest project with a compelling Q&A story, pick A. If time gets tight before the Nov 12 progress report, ship B first (A is B plus one more branch). C and D are fallbacks only.

## Option pricing and Greeks

We price European options on the USATECH level with Black-Scholes-Merton, the model in the professor's *Options Pricing with Python*. NDX options are European and cash-settled, so this is a fair match (QQQ options are American and less clean).

| Input | Value used | Source |
| --- | --- | --- |
| Spot S | USATECH close at the trade or hedge bar | Class data |
| Strike K | Chosen by the strategy (ATM, or 25-delta for strangles) | Strategy rule |
| Time to expiry T | 7, 30 or 60 calendar days / 365 (30 is the base case) | Optimization axis |
| Volatility σ | VXN / 100, times a skew multiplier for non-ATM strikes | FRED + chain snapshot |
| Rate r | 3-month T-bill | FRED DGS3MO |
| Dividend yield q | Constant, about 0.7% | Assumption, sensitivity-tested |

**Lock-ins:**

- **Greeks:** delta, gamma, vega and theta from the closed-form formulas, computed at every hedge bar.
- **Marking:** positions are revalued each day with that day's VXN, so vega P&L shows up.
- **Term structure:** VXN is a 30-day measure. For 7- and 60-day tenors we either reuse VXN (simple) or scale it by the chain's short/long IV ratio. Pick one and state it.
- **Option costs:** pay half the bid-ask spread on every option trade, using the % spread by moneyness from the chain.
- **Underlying costs:** a fixed cost per hedge trade (for example 1 basis point). This is an assumption to test in the optimization.
- **Sizing unit:** one contract = an option on 1 index point × a multiplier, against a fixed starting capital (for example $1,000,000).

**Pricer is done when** three checks pass:

- Our prices match chain mids within a small error, using the chain's own IVs.
- Put-call parity holds.
- Analytic Greeks match bump-and-reprice estimates.

## Delta hedging

We neutralize the option book's direction by trading USATECH itself, which is where the class data's hourly granularity earns its keep. Hedge frequency (1h vs 4h vs daily) is our cleanest optimization axis because it maps exactly onto the allowed bar sizes.

| Decision | Base case | Variants to test |
| --- | --- | --- |
| Hedge instrument | USATECH (class data) | none |
| When to rebalance | Every daily close | Every 1h or 4h bar; or only when net delta drifts past a band (for example ±0.10 per contract) |
| Vol used between days | Latest known VXN close (yesterday's for intraday bars) | none: anything later is look-ahead |
| Position lifecycle | Enter at the 4pm close, hold to expiry, then roll | Early exit when the signal flips; a stop at a multiple of premium collected |
| Closed-market gaps | No hedging when the CFD isn't trading; gap risk lands in P&L | none, but report the worst gaps |

**Daily P&L accounting** (one line per day in the results table):

- Option mark-to-market change.
- Hedge P&L from the USATECH position.
- Interest on cash at r.
- Minus option and hedge trading costs.

**P&L attribution:** split each day into delta, gamma, theta and vega parts plus an unexplained residual. A small residual is a good sign the pricer and Greeks are consistent; we chart it in the report.

## VaR engine

The VaR engine does two jobs: it sizes every new position (pre-trade limit) and reports daily risk (monitoring). We build three methods and compare them, because an option book's losses are non-linear and the methods disagree most exactly when it matters.

**Risk factors:** the USATECH return and the change in VXN, moved together as they did historically (they are strongly negatively correlated).

| Method | How it works | Strength | Weakness |
| --- | --- | --- | --- |
| Historical simulation | Apply each of the last N daily (index, VXN) moves to today's book and fully reprice | No distribution assumption; real joint moves | Only knows the window it sees |
| Delta-gamma-vega (parametric) | Approximate P&L with Greeks, assume normal factor moves | Fast, explainable | Misses large non-linear moves |
| Monte Carlo | Simulate many paths (GBM or GARCH vol), fully reprice | Flexible, can stress vol | Model-dependent, slowest |

**Lock-ins:**

- Horizon 1 day; confidence 99% (95% also reported).
- Also report Expected Shortfall (average loss beyond VaR), since short options have fat left tails.
- Sizing rule: scale the new position so total book VaR stays under a cap, for example 2% of capital. The cap is an optimization axis.

**Validation:**

- Count VaR breaches over the backtest and run the Kupiec test (does the breach rate match 1%?).
- Optionally add the Christoffersen test (do breaches cluster?).

**Stress tests:**

- Replay the worst historical windows inside our data: the 2022 bear market and the April 2025 sell-off.
- Hypothetical shocks, for example index −10% with VXN +15 points overnight.

## Backtest and optimization

The backtest makes one decision per trading day at the 4pm ET close, hedges on the chosen bar size, and is tuned only on 2020–2023 before a single untouched run on 2024–2025.

**Vol forecast (our edge), built only from past class data:**

- EWMA (RiskMetrics style, λ around 0.94) on daily returns. Simple baseline.
- GARCH(1,1), refit on an expanding or rolling window. Covered in Lecture 5.
- Optional upgrade: HAR-RV, which forecasts from daily, weekly and monthly realized vol computed from the hourly bars. This uses the class data's granularity directly.
- Each forecast is turned into an expected 30-day annualized vol to compare with VXN.

**Signal:** gap = VXN − forecast, in vol points. Above +threshold: sell. Below −threshold (option A only): buy. Otherwise flat.

**Sample split:**

| Period | Dates | Use |
| --- | --- | --- |
| In-sample | 2020-07-01 to 2023-12-31 | Fit models, run the grid, pick parameters |
| Out-of-sample | 2024-01-01 to 2025-06-30 | One run with frozen parameters; report as is |
| Optional walk-forward | Rolling 2-year fit, 6-month test | Robustness check |

**Optimization grid (a few scenarios, as the brief asks):**

| Parameter | Values to test |
| --- | --- |
| Signal threshold | 0, 2, 4, 6 vol points |
| Tenor | 7, 30, 60 days |
| Structure | ATM straddle, 25-delta strangle |
| Hedge frequency | 1h, 4h, daily, delta band |
| Vol forecast model | EWMA, GARCH, HAR-RV |
| VaR cap | 1%, 2%, 3% of capital |

**Guarding against overfitting:** keep the grid small, show results as heatmaps, and prefer a parameter set whose neighbours also do well over the single best cell.

**Benchmarks:**

- Buy and hold USATECH.
- Always-short straddle with no signal, to show whether the signal adds value.
- The same strategy without hedging, to show what hedging buys.

## Metrics and charts

Every strategy run and benchmark is reported with the same metric table, in-sample and out-of-sample side by side.

| Metric | What it tells us |
| --- | --- |
| Annualized return and volatility | Basic reward and risk |
| Sharpe and Sortino ratios | Return per unit of total and downside risk |
| Max drawdown and its length | Worst peak-to-trough loss and time to recover |
| Calmar ratio | Return per unit of max drawdown |
| Skewness and worst day | Short-option tail risk in one number each |
| Win rate, average win / average loss | Trade-level profile |
| Number of trades, turnover, total costs | How much the costs eat |
| VaR breaches and Kupiec p-value | Whether the VaR engine is honest |
| Average Expected Shortfall | Tail loss beyond VaR |

**Charts for the report and slides:**

- Equity curve of the strategy vs the benchmarks, with drawdown underneath.
- VXN vs our vol forecast over time, with the trade signals marked.
- P&L attribution by Greek (delta, gamma, theta, vega, residual).
- Daily P&L vs the VaR line, breaches highlighted.
- Optimization heatmaps (for example threshold × tenor; hedge frequency × costs).
- Skew curve from the chain snapshot (IV vs moneyness).

## Definition of done

The project is done when every box below is ticked; each one maps to a line in the project brief.

**Code**

- [ ] Runs end to end from raw downloads to final charts with one command or one notebook run order
- [ ] Every function and notebook step has a short explanation of what it does and why
- [ ] Raw data untouched; all assumptions (q, costs, sizing, term structure) in one config section
- [ ] Only 1h, 4h and daily bars used anywhere

**Backtesting and validation**

- [ ] Pricer checks pass (chain mids, put-call parity, Greeks)
- [ ] No look-ahead: signals use only data known at the decision time
- [ ] In-sample grid run plus one frozen out-of-sample run
- [ ] At least 3 optimization scenarios shown with heatmaps
- [ ] Benchmarks reported with the same metric table

**Risk**

- [ ] Three VaR methods implemented and compared
- [ ] VaR backtested with breach counts and the Kupiec test
- [ ] Stress tests on 2022 and April 2025, plus one hypothetical shock

**Report and presentation**

- [ ] Report covers strategy, data, method, results, risks, limitations, with charts
- [ ] 10-minute slide deck; both members present a section
- [ ] Rehearsed Q&A on the main weak points (see the last section)
- [ ] Files uploaded to Canvas; PDF or HTML copy emailed to the professor

## Timeline and two-person split

The plan aims for a working end-to-end backtest (option B, daily hedging, one VaR method) by the Nov 12 progress report, then spends the last three weeks on optimization, the other VaR methods and the write-up.

&#91;embedded content: project timeline · 6 workstreams, 3 dated gates\]

P1 owns the vol forecast, signal and optimization; P2 owns hedging, the backtest loop and VaR. Data prep, the pricer and the report are shared so both can present any part.

| Owner | Builds | Presents |
| --- | --- | --- |
| P1 | Vol forecasts (EWMA, GARCH, HAR-RV), signal, optimization grid, out-of-sample run | Strategy idea, signal, results and robustness |
| P2 | Delta hedging, P&L accounting and attribution, VaR engine, stress tests | Pricing, hedging, risk and VaR validation |
| Both | Data prep, pricer and checks, report, slides | Opening and Q&A |

## Open decisions and risks

**Decisions still open:**

- [ ] Core trade: A (recommended), B, or another candidate
- [ ] Term-structure rule for 7- and 60-day tenors
- [ ] Starting capital, contract multiplier, and the hedge cost assumption
- [ ] Presentation date: Dec 3 (syllabus) or Dec 8 (project sheet)

**Risks and likely Q&A challenges:**

| Risk | Why it matters | Our answer or fallback |
| --- | --- | --- |
| Synthetic option prices | No historical chain, so prices are modelled | VXN is a real market price of vol; skew and costs come from a real chain; pricer validated against it |
| VXN vs our underlying | VXN measures NDX options; USATECH is a CFD on the same index | Show that USATECH tracks the index closely; small basis noted as a limitation |
| Flat skew over time | One 2026 snapshot stands in for 2020–2025 skew | Sensitivity run with steeper and flatter skew |
| Crash exposure on short vol | One bad week can erase a year of premium | VaR cap, stress tests, and the long-vol branch of option A |
| Overfitting | Many parameters, short history | Small grid, heatmaps, single frozen out-of-sample run |
| Time crunch before Nov 12 | Midterm Oct 15 eats a week | Ship option B with daily hedging first; add the rest after |
