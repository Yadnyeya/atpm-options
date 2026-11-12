"""Download one option chain snapshot from Yahoo Finance.

Why: we have no historical option prices, so the backtest prices options with
Black-Scholes. One real chain tells us three things the model cannot: the skew
(how implied vol changes away from the money), the bid-ask cost, and whether
our pricer reproduces market prices. It is calibration only and is never used
as a backtest price.

Run `python -m src.chain`. The snapshot is saved as is in data/raw/.
"""
from datetime import date

import pandas as pd
import yfinance as yf

from src.config import RAW, load_config


def download(symbol, target_days):
    """Save the chain for one symbol and return its path.

    For each target (7, 30, 60 days) the listed expiry closest to it is kept.
    """
    today = date.today()
    ticker = yf.Ticker(symbol)
    expiries = pd.to_datetime(list(ticker.options))
    days = (expiries - pd.Timestamp(today)).days
    spot = float(ticker.history(period="5d")["Close"].iloc[-1])
    chosen = sorted({expiries[abs(days - target).argmin()] for target in target_days})
    parts = []
    for expiry in chosen:
        chain = ticker.option_chain(f"{expiry:%Y-%m-%d}")
        for kind, table in (("call", chain.calls), ("put", chain.puts)):
            parts.append(table.assign(type=kind, expiry=expiry.date(),
                                      days_to_expiry=(expiry.date() - today).days))
    snapshot = pd.concat(parts, ignore_index=True).assign(
        symbol=symbol, snapshot_date=today, spot=spot)
    snapshot["mid"] = (snapshot["bid"] + snapshot["ask"]) / 2
    path = RAW / f"chain_{symbol.lstrip('^')}_{today:%Y-%m-%d}.csv"
    snapshot.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    settings = load_config()["data"]
    for name in settings["chain_symbols"]:
        saved = download(name, settings["chain_target_days"])
        table = pd.read_csv(saved)
        print(f"saved {saved.name}: spot {table['spot'].iloc[0]:.2f}")
        print(table.groupby(["expiry", "days_to_expiry", "type"]).agg(
            strikes=("strike", "size"),
            quoted=("bid", lambda bid: int((bid > 0).sum())),
            open_interest=("openInterest", "sum")))
