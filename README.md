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
