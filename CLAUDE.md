# ATPM Project 10 — USATECH Options Strategy with VaR (Claude Code handoff)

You are taking over the coding of a graduate class project. Everything below was planned in an earlier session. Read this whole file before writing any code, then work phase by phase (section 9), stopping after each phase to show results and explain them in plain language.

---

## 1. Context

- **Course:** Algorithmic Trading & Portfolio Management (Rutgers MQF, Fall 2026, Prof. Mhamed Bettaieb).
- **Project:** #10 "Options Trading with Risk Management": implement an options pricing strategy (Black-Scholes, Greeks-based hedging) combined with a VaR engine. It must include backtesting, risk evaluation and at least a few optimization scenarios that show robustness.
- **Team:** 2 students (call them P1 and P2). 10-minute presentation; both speak.
- **AI use:** allowed by the professor for this project.
- **Dates:** progress report Nov 12, 2026; final presentation Dec 3, 2026 (the project sheet also mentions Dec 8; unconfirmed). Prioritize a working end-to-end MVP first (section 9, Phase 1–5), then extend.
- **Living plan doc** (human-readable version of this file): https://claude.ai/artifact/C4PNohueTTZi7J945L33Wc

## 2. Hard rules from the professor (never break)

1. The strategy must be **based on the class-provided data**. Outside data (FRED, option chain) is allowed only as a supplement.
2. Only **1-hour, 4-hour and daily** bars may be used anywhere: analysis, signals, hedging, optimization. No other resampling (no 15-min, no weekly signals).
3. **Python only** (pandas, numpy, scipy, arch, statsmodels, matplotlib, yfinance OK).
4. Deliverables: well-documented code (explain each step and key decision), backtest with performance metrics, a report with charts and insights, slides.
5. Never modify the raw data file. Keep it read-only in `data/raw/`.

## 3. Strategy in plain words

Options are insurance on the Nasdaq-100. **VXN** (Cboe Nasdaq-100 volatility index) is the market's daily price of that insurance (30-day implied vol). The **class data** tells us how much the index actually moves. We forecast realized vol from the class data; if VXN is well above our forecast, options are expensive → **sell** a straddle; if well below → **buy** one; otherwise stay flat. We **delta-hedge** with the underlying so we only bet on the size of moves, not direction. A **VaR engine** sizes positions and reports daily risk.

Core relation (delta-hedged option P&L per step):

    P&L ≈ ½ · Γ · S² · (σ_realized² − σ_implied²) · Δt

Strategy modes to support via config (build in this order):
- `short` (option B): sell only when VXN > forecast + threshold. **MVP.**
- `two_sided` (option A, the target): also buy when VXN < forecast − threshold.
- `long` (option E): buy only. Reported as a comparison.

## 4. Data

### 4.1 Class file (the underlying) — required

- File: `USATECH.IDXUSD_1h_2020-07-01_to_2025-06-30_UTC.csv` (from Canvas > Files > RawDataDoNotModify > DataSet2). Ask the user for its path if it is not in `data/raw/`.
- Columns: `timestamp,open,high,low,close,volume`. Timestamp format like `2020-07-01 04:00:00+00:00` (UTC).
- Verified facts:
  - 29,508 hourly rows, 2020-07-01 04:00 UTC to 2025-07-01 04:00 UTC (**5 years**), no duplicates, no unparseable timestamps.
  - It is the **Nasdaq-100** (≈10,140 at start, ≈22,643 at end; 2022: 16,385 → 10,958, −33%).
  - CFD feed (Dukascopy-style): trades ~23h/day, Sunday evening to Friday, with a short daily break (fewer bars at 21–22 UTC).
  - `volume` is provider tick activity, **not** real volume. Do not use it as a signal or report it as volume.
  - Naive daily resampling gives ~310 "days"/year because of Sunday bars. **Fold Sunday-evening bars into Monday** so there are ≈252 trading days/year.
- **Verify before using:** whether timestamps mark the bar's **open** time (likely) or close time. The "daily close" must be the price at **16:00 New York time** (US/Eastern, DST-aware) — i.e. the close of the bar that ends at 16:00 ET (if open-time stamped: the bar stamped 15:00 ET = 19:00 UTC in summer / 20:00 UTC in winter). Document the finding.

### 4.2 FRED (implied vol + rate) — supplement

Download without an API key via `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>`:
- `VXNCLS` — VXN daily close, in vol points (25 = 25%). Missing days appear as "." → NaN.
- `DGS3MO` — 3-month T-bill, percent annual → decimal; use as continuous r (approximation fine, state it).
- Optional: `VIXCLS` for a comparison chart only.
Cache raw downloads in `data/raw/` with the download date in the file name.

### 4.3 Option chain snapshot — calibration only

- Use `yfinance` for `^NDX` options if available, else `QQQ` (scale moneyness, not price). One snapshot, expiries near 7, 30, 60 days; keep strike, bid, ask, mid, impliedVolatility, openInterest. Save as is to `data/raw/chain_<SYMBOL>_<YYYY-MM-DD>.csv`.
- It is a 2026 snapshot: use it **only** to (a) estimate skew = IV(K)/IV_ATM as a function of moneyness, (b) estimate bid-ask half-spread as % of mid by moneyness, (c) validate the pricer. Never use it as backtest prices.
- If chain download fails: fall back to configurable assumptions (flat skew; option half-spread 2% of mid) and flag it in the report.

## 5. Key assumptions (all in one config; each is a sensitivity knob)

| Setting | Default | Notes |
|---|---|---|
| Starting capital | $1,000,000 | |
| Contract unit | option on 1 index point × multiplier (e.g. 1) | sizing done by VaR cap, not fixed count |
| Dividend yield q | 0.7%/yr constant | test 0.5–1.0% |
| Option tenor | 30 calendar days | grid: 7, 30, 60 |
| Term structure | reuse VXN for all tenors | alt: scale by chain short/long IV ratio |
| Structure | ATM straddle | alt: 25-delta strangle (skew-adjusted vol) |
| Entry | daily, at the 16:00 ET close, using VXN(t) | robustness: enter next day's close with VXN(t) (removes 15-min VXN timing gap) |
| Holding | to expiry, then roll if signal still on | alt: exit when signal flips |
| Hedge frequency | daily, at the 16:00 ET close | decided 2026-11-12: daily only, no intraday (1h/4h/band) hedging |
| Hedge cost | 1 bp of traded notional | grid: 0.5–3 bp |
| Option cost | half bid-ask from chain by moneyness | fallback 2% of mid |
| VaR | 1-day, 99% (95% also), plus Expected Shortfall | |
| VaR cap | 2% of capital | grid: 1%, 2%, 3% |
| In-sample | 2020-07-01 → 2023-12-31 | |
| Out-of-sample | 2024-01-01 → 2025-06-30 | run once with frozen params |

## 6. Components to build

### 6.1 Data prep
- Load, parse UTC, convert to America/New_York for session logic.
- Quality report table: row counts, date range, gaps (separate normal closures from true gaps), zero/negative prices, OHLC inconsistencies (high < max(open,close) etc.), extreme returns (> 8σ: investigate and log, do not delete).
- Resample to daily (O first, H max, L min, C last); no 4h bars are needed (hedging is daily only); daily anchored at the 16:00 ET close with Sunday folded into Monday.
- Log returns; annualization factor computed from the actual bars-per-year in the data (not 252×6.5).
- Merge VXN and rate onto the daily table, forward-filling only from the past.
- Save processed parquet/CSV + a data dictionary (column, unit, source).

### 6.2 Volatility forecasts (only past data at each date)
- EWMA (λ≈0.94) on daily returns.
- GARCH(1,1) (`arch` package), refit on an expanding window (e.g. monthly refits for speed).
- HAR-RV (upgrade): realized variance from hourly returns aggregated to daily; regress next-month RV on daily/weekly/monthly RV.
- Output: forecast of annualized vol over the option tenor, comparable to VXN/100.

### 6.3 Pricing and Greeks
- Black-Scholes-Merton with continuous q: price, delta, gamma, vega, theta for calls/puts (vectorized).
- σ = VXN/100 × skew multiplier(moneyness) for non-ATM strikes.
- Validation tests: matches chain mids using chain IVs (report error %), put-call parity, analytic Greeks vs bump-and-reprice.

### 6.4 Signal
- gap_t = VXN_t − forecast_t (vol points). Sell if gap > +θ; buy if gap < −θ (two_sided/long); else flat. θ grid: 0, 2, 4, 6.

### 6.5 Backtest engine with delta hedging
- Event loop on daily bars; option decisions and the hedge rebalance both happen at the daily 16:00 ET close.
- Track per position: strike(s), expiry, quantity, entry vol, Greeks.
- Mark options daily with that day's VXN (so vega P&L appears).
- Moves between two daily closes are unhedged and land in P&L (report the worst days).
- Daily ledger: option MTM change, hedge P&L, interest on cash at r, option costs, hedge costs, net P&L, equity, net delta/gamma/vega, VaR, ES.
- P&L attribution per day: delta, ½ΓΔS² (gamma), Θ·dt (theta), ν·Δσ (vega), residual. Small residual = consistency check.

### 6.6 VaR engine
- Risk factors: daily USATECH log return and daily ΔVXN, taken jointly.
- Historical simulation: last N=500 joint daily moves applied to today's book with **full repricing**.
- Delta-gamma-vega parametric: factor covariance from the same window, normal assumption.
- Monte Carlo: ≥10,000 correlated draws (normal; optional GARCH/Student-t variant), full repricing.
- Report VaR 95/99 and ES for each method, every day.
- Pre-trade sizing: scale new position so total book VaR (choose one primary method, e.g. historical) ≤ cap.
- Validation: breach counts, Kupiec POF test (p-value), optional Christoffersen independence test.
- Stress tests: replay 2022 bear market and April 2025 sell-off windows; hypothetical shock (index −10%, VXN +15 points overnight).

### 6.7 Optimization and robustness
- In-sample grid: θ × tenor × structure × vol model × VaR cap (keep it small; prune if slow).
- Show heatmaps (e.g. θ × tenor; θ × hedge cost; tenor × VaR cap). Prefer parameter sets whose neighbours also perform well over the single best cell.
- Freeze the choice, run out-of-sample once, report as is.
- Optional walk-forward: rolling 2-year fit, 6-month test.
- Sensitivities: q, costs, skew steeper/flatter, entry-timing variant.

### 6.8 Benchmarks
- Buy-and-hold USATECH.
- Always-short straddle (no signal) — does the signal add value?
- Same strategy unhedged — what does hedging buy?

### 6.9 Metrics (same table for every run, IS and OOS side by side)
Annualized return and vol; Sharpe; Sortino; max drawdown and its duration; Calmar; skewness; worst day; win rate; avg win/avg loss; number of trades; turnover; total costs; VaR breaches + Kupiec p-value; average ES.

### 6.10 Charts (save PNG to `results/figures/`)
1. Equity curve vs benchmarks with drawdown panel.
2. VXN vs vol forecast over time with entry/exit markers.
3. P&L attribution by Greek (stacked or cumulative lines).
4. Daily P&L vs VaR line with breaches highlighted.
5. Optimization heatmaps.
6. Skew curve from the chain snapshot.
7. Data sanity: price, hourly returns, VXN.

## 7. Repository layout

```
atpm-options/
  CLAUDE.md                # this file
  README.md                # how to run, results summary
  requirements.txt
  config.yaml              # every assumption from section 5
  data/raw/                # untouched downloads (gitignored if large)
  data/processed/
  src/
    data_prep.py  fred.py  chain.py  vol_forecast.py  pricing.py
    signals.py  backtest.py  var_engine.py  metrics.py  optimize.py  plots.py
  notebooks/
    01_data_prep.ipynb  02_vol_forecast.ipynb  03_pricer_checks.ipynb
    04_backtest.ipynb  05_var.ipynb  06_optimization.ipynb  07_report_figures.ipynb
  tests/                   # pytest: pricer, parity, Greeks, no-lookahead, VaR math
  results/tables/  results/figures/
  report/
```

Notebooks call functions in `src/`; logic lives in `src/`. Every function has a docstring saying what it does and why; notebooks have markdown cells explaining each step for a classmate who has not seen the code.

## 8. Look-ahead and correctness guards (test these)
- Any value used at time t must have timestamp ≤ t (write a test that shifts inputs and checks signals don't change retroactively).
- Vol forecasts use only data up to the decision date.
- FRED values forward-filled only.
- Out-of-sample period untouched until the final run.

## 9. Phases (stop after each, show outputs, explain in plain language)

| Phase | Deliverable | Done when |
|---|---|---|
| 0. Setup | repo, venv, requirements, config.yaml, git init | `pytest` runs (empty OK) |
| 1. Data | quality report, processed 1h/daily, merged VXN + rate, data dictionary, sanity plots | timestamp convention verified; ~252 days/yr; no look-ahead in merge |
| 2. Pricer | BSM + Greeks + chain snapshot + skew/spread curves | three pricer checks pass |
| 3. Vol forecast + signal | EWMA, GARCH (HAR-RV later), gap series, signal | forecast vs VXN chart looks sensible |
| 4. MVP backtest | `short` mode, ATM straddle, 30d, daily hedge, cost model, ledger, attribution | equity curve + metrics table; residual small |
| 5. VaR (MVP) | historical-sim VaR/ES, sizing cap, breaches, Kupiec | VaR line chart + test result |
| 6. Extend | `two_sided` and `long` modes, parametric + MC VaR, stress tests, HAR-RV | all methods compared in one table |
| 7. Optimize | IS grid, heatmaps, frozen choice, OOS run, benchmarks, sensitivities | IS vs OOS metric table |
| 8. Report assets | all charts in section 6.10, results tables, README with run order | one-command / ordered-notebook rerun reproduces everything |

Phases 1–5 = the MVP. Get there first.

## 10. Definition of done
- Code runs end to end from raw downloads to final charts; documented; assumptions only in config.
- Only 1h/4h/daily bars used.
- Pricer checks pass; no look-ahead tests pass.
- In-sample grid + one frozen OOS run; ≥3 optimization scenarios with heatmaps; benchmarks in the same metric table.
- Three VaR methods compared; VaR backtested (breaches + Kupiec); stress tests on 2022, April 2025 and one hypothetical shock.
- Figures and tables ready for a report and a 10-minute deck.

## 11. Known limitations to state honestly in the report
- Option prices are modelled (no historical chain); VXN is real market implied vol, skew/costs from a real chain.
- VXN is on NDX options; USATECH is a CFD on the same index (small basis).
- One 2026 skew snapshot stands in for 2020–2025 skew (sensitivity run covers it).
- Short-vol crash exposure; VaR cap and stress tests address it.
- In real life the hedge would use NQ/MNQ futures; USATECH prices stand in for them.

## 12. Working style for this session
- The user is learning: before each phase, say in 2–3 sentences what you'll build and why; after, summarize results with numbers and one chart.
- Ask before: deleting files, changing an assumption from section 5, or spending long compute on big grids.
- Keep commits small, one per phase.
