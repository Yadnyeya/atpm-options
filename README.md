# ATPM Project 10: USATECH options strategy with VaR

Sell or buy Nasdaq-100 straddles when VXN (implied vol) is far from our own
forecast of realized vol, delta-hedge with the underlying, and size positions
with a VaR cap. Full plan: `CLAUDE.md`.

## Setup

    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -r requirements.txt
    .venv/bin/python -m pytest

## Data

| File in `data/raw/` | Source | Refresh with |
|---|---|---|
| `USATECH.IDXUSD_1h_...csv` | Canvas, class data (read-only, never edit) | re-download from Canvas |
| `fred_VXNCLS_<date>.csv` | FRED, VXN daily close | `.venv/bin/python -m src.fred` |
| `fred_DGS3MO_<date>.csv` | FRED, 3-month T-bill | same |
| `fred_VIXCLS_<date>.csv` | FRED, VIX (comparison chart only) | same |
| `chain_NDX_<date>.csv`, `chain_QQQ_<date>.csv` | Yahoo Finance option chain snapshot (calibration only) | `.venv/bin/python -m src.chain` |

All assumptions live in `config.yaml`.

## Run order

Run from the project root. Each step reads what the previous one wrote.

| Step | Command | Writes |
|---|---|---|
| 0. Downloads (only to refresh) | `.venv/bin/python -m src.fred` and `.venv/bin/python -m src.chain` | dated files in `data/raw/` |
| 1. Data preparation | `.venv/bin/python -m src.data_prep` | `data/processed/hourly.parquet`, `data/processed/daily.parquet`, `results/tables/quality_report.csv`, `data_dictionary.csv`, `annualization.csv` |
| 1. Sanity figure | `.venv/bin/python -m src.plots` | `results/figures/data_sanity.png` |
| Tests | `.venv/bin/python -m pytest -q` | nothing |

The same steps with explanations are in `notebooks/01_data_prep.ipynb`
(rerun with `.venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/01_data_prep.ipynb`).

Phase 1 in one paragraph: the class file stamps each hourly bar with its open
time, so the daily close is the close of the bar stamped 15:00 New York (the
16:00 price), in summer and winter. A trading day runs from one cash close to
the next, which folds Sunday evening and holiday sessions into the next trading
day and gives 1,255 days (about 251 per year). Nothing is deleted from the data;
issues are flagged and listed in the quality report.
