"""Download and load FRED series (implied vol and the risk-free rate).

Why: the class data gives prices only. VXN (the market's 30-day implied vol on
the Nasdaq-100) and the 3-month T-bill rate come from FRED as a supplement.

Run `python -m src.fred` to download every series named in config.yaml.
Each download is saved untouched in data/raw/ with the download date in its
name, so the backtest always reads a fixed, dated copy.
"""
import urllib.request
from datetime import date

import pandas as pd

from src.config import RAW, load_config

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"


def download(series: str):
    """Save the raw FRED CSV for one series and return its path."""
    path = RAW / f"fred_{series}_{date.today():%Y-%m-%d}.csv"
    with urllib.request.urlopen(URL.format(series), timeout=30) as response:
        path.write_bytes(response.read())
    return path


def load(series: str) -> pd.Series:
    """Read the newest saved copy of a series, indexed by date.

    FRED writes "." on days with no value (holidays); those become NaN here.
    Filling them is left to the merge step, which only fills from the past.
    """
    latest = sorted(RAW.glob(f"fred_{series}_*.csv"))[-1]
    table = pd.read_csv(latest, na_values=".", parse_dates=["observation_date"])
    return table.set_index("observation_date")[series]


if __name__ == "__main__":
    for name in load_config()["data"]["fred_series"].values():
        saved = download(name)
        values = load(name)
        print(f"{name}: {len(values)} rows, {values.index[0]:%Y-%m-%d} to "
              f"{values.index[-1]:%Y-%m-%d}, {values.isna().sum()} missing -> {saved.name}")
