"""Figures for the report, saved as PNG in results/figures/.

Run `python -m src.plots` after `python -m src.data_prep`.
"""
import matplotlib.pyplot as plt
import pandas as pd

from src.config import FIGURES, PROCESSED


def plot_data_sanity(hourly: pd.DataFrame, daily: pd.DataFrame):
    """Draw four panels that let a reader check the prepared data by eye.

    Why each panel: the price shows the series is the Nasdaq-100 with no bad
    ticks; hourly returns show volatility clusters and that returns after a
    closure (orange) are a different population; VXN against VIX shows the
    implied-vol input is sensible; bars per day shows the trading-day rule
    (23 on a normal day, about 40 after a holiday, fewer on a short day).
    Saves results/figures/data_sanity.png and returns the figure.
    """
    fig, axes = plt.subplots(4, 1, figsize=(11, 13))

    axes[0].plot(hourly.index, hourly["close"], lw=0.6, color="tab:blue")
    axes[0].set(title="USATECH (Nasdaq-100 CFD), hourly close", ylabel="Index points")

    gap = hourly["after_closure"] | hourly["after_data_gap"]
    axes[1].plot(hourly.index[~gap], hourly["log_return"][~gap] * 100, lw=0.4,
                 color="tab:blue", label="Back-to-back hourly bars")
    axes[1].scatter(hourly.index[gap], hourly["log_return"][gap] * 100, s=3,
                    alpha=0.6, color="tab:orange", zorder=3, label="First bar after a closure or gap")
    axes[1].set(title="Hourly log returns", ylabel="Percent")
    axes[1].legend(loc="upper left")

    axes[2].plot(daily.index, daily["vxn_points"], lw=0.9, color="tab:red",
                 label="VXN (Nasdaq-100 implied vol)")
    axes[2].plot(daily.index, daily["vix_points"], lw=0.9, color="tab:gray",
                 label="VIX (S&P 500 implied vol, comparison only)")
    axes[2].set(title="Implied volatility from FRED, daily close", ylabel="Vol points (25 = 25%)")
    axes[2].legend(loc="upper center")  # clear of the April 2025 spike on the right

    axes[3].scatter(daily.index, daily["n_bars"], s=5, color="tab:blue")
    axes[3].set(title="Hourly bars in each trading day (16:00 to 16:00 New York)",
                ylabel="Number of bars", xlabel="Date")

    for ax in axes:
        ax.grid(alpha=0.3)
    fig.tight_layout()
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / "data_sanity.png", dpi=150)
    return fig


if __name__ == "__main__":
    plot_data_sanity(pd.read_parquet(PROCESSED / "hourly.parquet"),
                     pd.read_parquet(PROCESSED / "daily.parquet"))
