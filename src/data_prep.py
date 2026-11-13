"""Phase 1: turn the raw class file into clean hourly and daily tables.

Why: every later step (vol forecast, option pricing, backtest, VaR) works on
one daily table whose close is the 16:00 New York price, with VXN and the
risk-free rate attached. This module builds it, and records every data issue
in a quality report instead of fixing it silently.

Three facts about the class file drive the design (evidence in
notebooks/01_data_prep.ipynb):

1. Each bar is stamped with its OPEN time, so the 16:00 New York price is the
   close of the bar stamped 15:00 New York, summer and winter alike.
2. It is a CFD that trades about 23 hours a day from Sunday 18:00 to Friday
   17:00 New York. A "trading day" here is everything between two cash closes,
   so Sunday-evening bars and holiday sessions fold into the next trading day.
3. The raw file is never changed. Nothing is deleted or filled: bars after a
   closure or a data gap are flagged so their returns can be told apart.

Run `python -m src.data_prep` to write data/processed/ and results/tables/.
Only 1-hour and daily bars are built (professor's rule; hedging is daily).
"""
import numpy as np
import pandas as pd

from src import fred
from src.config import PROCESSED, ROOT, TABLES, load_config

HOUR = pd.Timedelta(hours=1)

# The FRED columns of the daily table: (prefix of the *_stale_days column,
# value column, key under data.fred_series in config). Listed once so the
# merge, the quality report and the tests cannot drift apart.
FRED_COLUMNS = [("vxn", "vxn_points", "implied_vol"), ("rate", "rate", "rate"),
                ("vix", "vix_points", "comparison_vol")]


def load_hourly(cfg) -> pd.DataFrame:
    """Read the class file, indexed by bar-open time in UTC.

    Adds the New York wall-clock time of the bar's open and of its end, because
    the market's schedule (16:00 close, 17:00 break) is fixed in New York time
    while its UTC hour moves with daylight saving. `volume` is renamed
    `tick_activity`: it is a vendor activity measure of unknown unit (almost
    every value is fractional, so it is not a count), not traded volume.
    """
    data = cfg["data"]
    bars = pd.read_csv(ROOT / data["class_file"], parse_dates=["timestamp"])
    bars = bars.rename(columns={"timestamp": "time_utc", "volume": "tick_activity"})
    bars = bars.set_index("time_utc")
    bars["time_ny"] = bars.index.tz_convert(data["session_timezone"])
    bars["bar_end_ny"] = bars["time_ny"] + HOUR
    return bars


def add_returns_and_gaps(bars: pd.DataFrame, cfg) -> pd.DataFrame:
    """Add the hourly log return and flags for bars that follow a break.

    Why: a return measured across a closed market covers more than one hour
    (2 hours over the daily pause, 50 over a weekend), so it must not be treated
    as an ordinary hourly return. Two cases are separated:
    - after_closure: the gap crosses the daily 17:00-18:00 pause (normal: daily
      break, weekend, holiday).
    - after_data_gap: bars are missing inside one session (the vendor lost data).
    A session runs from the 18:00 reopen to the next 17:00 pause, so shifting
    the clock forward by (24 - reopen hour) gives every bar of a session the
    same calendar date.
    """
    out = bars.copy()
    out["gap_hours"] = out.index.to_series().diff() / HOUR
    shift = pd.Timedelta(hours=24 - cfg["data"]["session_open_hour"])
    session = (out["time_ny"].dt.tz_localize(None) + shift).dt.normalize()
    same_session = session == session.shift()
    out["after_closure"] = (out["gap_hours"] > 1) & ~same_session
    out["after_data_gap"] = (out["gap_hours"] > 1) & same_session
    out["log_return"] = np.log(out["close"]).diff()
    return out


def is_closing_bar(bars: pd.DataFrame, cfg) -> pd.Series:
    """Mark the bars whose end is a cash-market close.

    Why: these bars define the trading calendar. A normal day closes with the
    bar ending at 16:00 New York. On the early-close dates listed in config the
    cash market shut at 13:00, so the bar ending at 13:00 is the close. CFD-only
    holiday sessions have neither, so they never become a trading day.
    """
    data = cfg["data"]
    end = bars["bar_end_ny"]
    early_day = end.dt.tz_localize(None).dt.normalize().isin(
        pd.to_datetime(data["early_close_dates"]))
    close_hour = np.where(early_day, data["early_close_hour"], data["daily_close_hour"])
    return end.dt.hour == close_hour


def assign_trading_day(bars: pd.DataFrame, cfg) -> pd.DataFrame:
    """Label each bar with the trading day whose close it leads up to.

    A bar belongs to the first trading day whose close is at or after the bar's
    end. Why this rule: the closing bar becomes the last bar of its day; the
    bar stamped 16:00 and the evening bars go to the next day; Sunday evening
    folds into Monday; a holiday session folds into the next real trading day.
    Bars after the last close in the file get no trading day (NaT).
    """
    out = bars.copy()
    bar_end = out.index + HOUR
    closes = bar_end[is_closing_bar(out, cfg)]
    days = closes.tz_convert(cfg["data"]["session_timezone"]).tz_localize(None).normalize()
    position = closes.searchsorted(bar_end)
    out["trading_day"] = days.append(pd.DatetimeIndex([pd.NaT]))[position]
    return out


def build_daily(hourly: pd.DataFrame, cfg) -> pd.DataFrame:
    """Aggregate hourly bars into one row per trading day.

    Open is the first bar's open, high the maximum, low the minimum, and close
    the last bar's close (the 16:00 New York price). The day starts right after
    the previous cash close, so `open` is about the previous close (NOT the
    09:30 cash open) and high/low cover the evening, the night and any folded
    holiday session. Realized variance is the sum of squared hourly log returns
    from the previous close to this close; it is the input of the HAR-RV
    forecast. It includes the returns across the 17:00 pause, weekends and
    holiday closures (about 6.5% of the total), so that it measures the same
    move as the squared daily return: the day's hourly returns add up exactly
    to the daily log return. The first day has no previous close, so its return
    and realized variance are left empty.
    """
    by_day = hourly.groupby("trading_day")
    daily = by_day.agg(open=("open", "first"), high=("high", "max"),
                       low=("low", "min"), close=("close", "last"),
                       n_bars=("close", "size"))
    daily.index.name = "date"
    daily["close_time_ny"] = by_day["bar_end_ny"].last()
    daily["early_close"] = daily["close_time_ny"].dt.hour != cfg["data"]["daily_close_hour"]
    daily["log_return"] = np.log(daily["close"]).diff()
    squared = hourly["log_return"] ** 2
    daily["realized_var"] = squared.groupby(hourly["trading_day"]).agg(
        lambda day: day.sum(skipna=False))
    return daily


def load_fred(cfg) -> pd.DataFrame:
    """Return the FRED series named in config side by side, indexed by date."""
    names = cfg["data"]["fred_series"].values()
    return pd.concat([fred.load(name) for name in names], axis=1, sort=True)


def merge_fred(daily: pd.DataFrame, fred_table: pd.DataFrame, cfg) -> pd.DataFrame:
    """Attach VXN, the 3-month rate and VIX to the daily table, past values only.

    For each trading day the value used is the latest one dated on or before
    that day (never a later one: that would be look-ahead). `*_stale_days`
    records how many calendar days old the value is; 0 means same day. A value
    older than `fred_max_stale_days` is an error, not something to fill.
    VXN is stored in vol points (25 = 25%) and as a decimal (0.25); the rate is
    converted from percent to a decimal.

    Timing caveat: "on or before that day" is by DATE. The same-day VXN and
    rate are published shortly after the 16:00 close the row trades at, so they
    are not strictly known at that close. The plan accepts this for the
    baseline (entry at close t with VXN(t)); shift the column one row to get a
    value strictly known at the close (the next-day-entry robustness run).
    """
    data = cfg["data"]
    limit = pd.Timedelta(days=data["fred_max_stale_days"])
    out = daily.copy()
    for prefix, column, key in FRED_COLUMNS:
        name = data["fred_series"][key]
        known = fred_table[name].dropna()
        out[column] = known.reindex(out.index, method="ffill", tolerance=limit)
        source = known.index.to_series().reindex(out.index, method="ffill", tolerance=limit)
        out[prefix + "_stale_days"] = (out.index - source).dt.days
        if out[column].isna().any():
            raise ValueError(f"{name}: no value within {limit.days} days for "
                             f"{out.index[out[column].isna()][0]:%Y-%m-%d}")
    out["vxn_decimal"] = out["vxn_points"] / 100
    out["rate"] = out["rate"] / 100
    return out


def label_sample(daily: pd.DataFrame, cfg) -> pd.DataFrame:
    """Tag each day in_sample or out_of_sample using the dates in config.

    Why: parameters are chosen on the in-sample period only; the out-of-sample
    period is run once at the end. Storing the label avoids repeating the dates.
    A day covered by neither window is an error: it would silently drop out of
    both periods.
    """
    out = daily.copy()
    out["sample"] = pd.Series(pd.NA, index=out.index, dtype="str")
    for name in ("in_sample", "out_of_sample"):
        start, end = cfg["sample"][name]
        out.loc[start:end, "sample"] = name
    unlabelled = out.index[out["sample"].isna()]
    if len(unlabelled):
        raise ValueError(f"{len(unlabelled)} trading days are in neither sample window of "
                         f"config.yaml, first {unlabelled[0]:%Y-%m-%d}")
    return out


def build_tables(bars: pd.DataFrame, fred_table: pd.DataFrame, cfg):
    """Run every step and return (hourly, daily).

    Kept as one function of its inputs so the look-ahead test can rerun it on
    truncated data and compare.
    """
    hourly = assign_trading_day(add_returns_and_gaps(bars, cfg), cfg)
    daily = label_sample(merge_fred(build_daily(hourly, cfg), fred_table, cfg), cfg)
    return hourly, daily


def annualization_factors(hourly: pd.DataFrame, daily: pd.DataFrame) -> dict:
    """Count trading days and hourly bars per year in the data itself.

    Why: a CFD trades about 23 hours a day, so the textbook 252 x 6.5 hours is
    wrong here. Volatility is annualized with what the file actually contains.
    """
    span = hourly["bar_end_ny"].iloc[-1] - hourly["time_ny"].iloc[0]
    years = span / pd.Timedelta(days=365.25)
    return {"years_of_data": years,
            "trading_days_per_year": len(daily) / years,
            "hourly_bars_per_year": len(hourly) / years}


def session_profile(hourly: pd.DataFrame) -> pd.DataFrame:
    """Per New York hour: number of bars and average high-low range in bp.

    Why: this is the evidence for the timestamp convention. If stamps are open
    times, the range jumps at the bar stamped 09:00 (it contains the 09:30
    cash open), stays high through the bar stamped 15:00 (the last cash hour)
    and collapses at 16:00; and no bar is ever stamped 17:00 (the daily pause).
    """
    range_bp = (hourly["high"] / hourly["low"] - 1) * 1e4
    profile = range_bp.groupby(hourly["time_ny"].dt.hour).agg(["size", "mean"])
    profile.columns = ["bars", "mean_range_bp"]
    profile.index.name = "hour_ny"
    return profile


def quality_report(hourly, daily, fred_table, cfg) -> pd.DataFrame:
    """List every data check with its count, a detail and how it was handled.

    Why: the reader must be able to see what is wrong with the data and that
    nothing was removed to make results look better. Every issue is flagged in
    a column or listed here; no row is deleted and no price is changed. Every
    count and every "none found" is computed from the tables, never typed in.
    """
    data = cfg["data"]
    price = hourly[["open", "high", "low", "close"]]
    ny, ret = hourly["time_ny"], hourly["log_return"].dropna()
    off_session = ((ny.dt.hour == data["session_open_hour"] - 1) | (ny.dt.day_of_week == 5)
                   | ((ny.dt.day_of_week == 6) & (ny.dt.hour < data["session_open_hour"])))
    bad_ohlc = ((hourly["high"] < price.max(axis=1)) | (hourly["low"] > price.min(axis=1)))
    flat = price.nunique(axis=1) == 1
    stale_close = hourly["close"] == hourly["close"].shift()
    open_jump_bp = (hourly["open"] / hourly["close"].shift() - 1).abs() * 1e4
    open_jump_bp = open_jump_bp[hourly["gap_hours"] == 1]  # back-to-back bars only
    open_jump_bp = open_jump_bp[open_jump_bp > data["open_jump_bp"]]
    closure, data_gap = hourly[hourly["after_closure"]], hourly[hourly["after_data_gap"]]
    late_reopen = closure[closure["time_ny"].dt.hour != data["session_open_hour"]]
    distance = (ret - ret.median()).abs()  # distance of each return from the typical one
    sigma = 1.4826 * distance.median()     # robust standard deviation (from the MAD)
    extreme = ret[distance > data["extreme_return_sigmas"] * sigma]
    unassigned = hourly["trading_day"].isna().sum()
    usual_bars = int(daily["n_bars"].mode()[0])
    short_days = daily["n_bars"][daily["n_bars"] < usual_bars]
    # The first day is complete only if the file starts right after a cash close.
    starts_after_close = is_closing_bar(
        pd.DataFrame({"bar_end_ny": hourly["time_ny"].iloc[:1]}), cfg).iloc[0]
    vxn_name = data["fred_series"]["implied_vol"]
    vxn = fred_table[vxn_name].dropna()
    vxn_off_calendar = vxn.loc[daily.index[0]:daily.index[-1]].index.difference(daily.index)
    vxn_repeats = (vxn == vxn.shift())[vxn_off_calendar].sum()

    def stamps(index):
        return ", ".join(f"{t:%Y-%m-%d %H:%M}" for t in index) or "none"

    def dates(index):
        return ", ".join(f"{t:%Y-%m-%d}" for t in index) or "none"

    def none_found(count, meaning=""):
        return "none found" + meaning if count == 0 else "FOUND: not fixed, investigate"

    if len(extreme):
        largest = extreme.abs().idxmax()
        extreme_detail = (
            f"; largest {extreme[largest]:+.2%} at {largest:%Y-%m-%d %H:%M} UTC; "
            f"{hourly.loc[extreme.index, 'after_closure'].sum()} follow a closure; by year: "
            + ", ".join(f"{y} {n}" for y, n in extreme.groupby(extreme.index.year).size().items()))
    else:
        extreme_detail = "; none beyond the threshold"
    if len(open_jump_bp):
        jump_detail = (f"largest {open_jump_bp.max():.0f} bp at "
                       f"{open_jump_bp.idxmax():%Y-%m-%d %H:%M} UTC")
    else:
        jump_detail = "none"

    rows = [
        ("hourly rows", len(hourly),
         f"{hourly.index[0]:%Y-%m-%d %H:%M} to {hourly.index[-1]:%Y-%m-%d %H:%M} UTC",
         "all rows kept"),
        ("duplicate timestamps", (n := hourly.index.duplicated().sum()), "", none_found(n)),
        ("timestamps out of order", (n := (hourly["gap_hours"] <= 0).sum()), "", none_found(n)),
        ("missing values in price columns", (n := price.isna().sum().sum()), "", none_found(n)),
        ("zero or negative prices", (n := (price <= 0).sum().sum()), "", none_found(n)),
        ("OHLC inconsistencies", (n := bad_ohlc.sum()),
         "high below open/close, or low above open/close", none_found(n)),
        ("flat bars (open = high = low = close)", flat.sum(),
         stamps(hourly.index[flat]) + " UTC", "kept"),
        ("close equal to the previous bar's close", stale_close.sum(),
         stamps(hourly.index[stale_close]) + " UTC", "kept: gives a zero hourly return"),
        (f"open more than {data['open_jump_bp']} bp from the previous close",
         len(open_jump_bp), jump_detail + " (back-to-back bars only)",
         "kept: returns use closes only, so these do not enter any return"),
        ("bars outside the CFD session", (n := off_session.sum()),
         "stamped 17:00 New York, on Saturday, or on Sunday before 18:00",
         none_found(n, ": confirms stamps are bar-open times")),
        ("normal closures", len(closure),
         "; ".join(f"{int(h)}h x {n}" for h, n in
                   closure["gap_hours"].value_counts().sort_index().items()),
         "flagged after_closure; return kept but spans more than 1 hour"),
        (f"closures that reopen later than {data['session_open_hour']}:00 New York",
         len(late_reopen),
         ", ".join(f"{t:%Y-%m-%d %H:%M} New York" for t in late_reopen["time_ny"]) or "none",
         "kept and counted as a closure; the bars before the late reopen are missing"),
        ("data gaps inside a session", len(data_gap),
         f"{int((data_gap['gap_hours'] - 1).sum())} bars missing; first bar after each gap: "
         f"{stamps(data_gap.index)} UTC",
         "flagged after_data_gap; not filled or interpolated"),
        (f"hourly returns beyond {data['extreme_return_sigmas']} robust sigmas", len(extreme),
         f"robust sigma {sigma:.4%}" + extreme_detail,
         "kept: real market moves, the tail a short-vol strategy must survive"),
        ("tick_activity values that are not whole numbers", (hourly["tick_activity"] % 1 != 0).sum(),
         "raw 'volume' column: a vendor activity measure of unknown unit, not a count "
         "and not traded volume",
         "renamed tick_activity; never used as a signal"),
        ("bars after the last close in the file", unassigned,
         "belong to an unfinished trading day", "kept in hourly with no trading_day; not in daily"),
        ("trading days", len(daily),
         "per year: " + ", ".join(f"{y} {n}" for y, n in
                                  daily.groupby(daily.index.year).size().items()),
         "one daily row each"),
        ("early-close days (13:00 New York)", daily["early_close"].sum(),
         dates(daily.index[daily["early_close"]]),
         "flagged early_close; close = bar ending 13:00"),
        ("trading days holding more than 24 hourly bars", (daily["n_bars"] > 24).sum(),
         "day after a holiday: the CFD-only holiday session has no cash close",
         "holiday bars folded into the next trading day; see n_bars"),
        (f"trading days holding fewer than {usual_bars} hourly bars", len(short_days),
         ", ".join(f"{day:%Y-%m-%d} ({n})" for day, n in short_days.items()) or "none",
         "kept as they are: partial first day, early closes, data gaps, no afternoon session after "
         "an early close; see n_bars"),
        ("first trading day is partial", int(not starts_after_close),
         f"{daily.index[0]:%Y-%m-%d} has {daily['n_bars'].iloc[0]} bars; file starts at "
         f"{ny.iloc[0]:%H:%M} New York, "
         + ("right after a cash close" if starts_after_close else "mid-session"),
         "close valid; log_return and realized_var left empty (no previous close)"),
        ("Sunday-dated daily rows", (n := (daily.index.day_of_week == 6).sum()), "",
         none_found(n, ": Sunday evening folds into Monday")),
        (f"{vxn_name} values on non-trading days", len(vxn_off_calendar),
         f"{dates(vxn_off_calendar)}; {vxn_repeats} of {len(vxn_off_calendar)} repeat the "
         "previous value",
         "ignored: the calendar comes from the class file, not from FRED"),
    ]
    for prefix, _, key in FRED_COLUMNS:
        name = data["fred_series"][key]
        stale = daily[prefix + "_stale_days"]
        rows.append((f"{name} carried forward from an earlier day", (stale > 0).sum(),
                     f"oldest value used is {stale.max()} calendar days old",
                     "filled from the past only; see " + prefix + "_stale_days"))
    return pd.DataFrame(rows, columns=["check", "count", "detail", "how_handled"])


DICTIONARY = [
    # (column, table, unit, source, description)
    ("time_utc", "hourly", "UTC timestamp", "class file", "Bar open time (index)."),
    ("open", "hourly", "index points", "class file", "First price of the hour."),
    ("high", "hourly", "index points", "class file", "Highest price of the hour."),
    ("low", "hourly", "index points", "class file", "Lowest price of the hour."),
    ("close", "hourly", "index points", "class file", "Last price of the hour."),
    ("tick_activity", "hourly", "vendor units", "class file",
     "Raw 'volume' column: vendor activity measure of unknown unit, not traded volume. Not used."),
    ("time_ny", "hourly", "New York timestamp", "derived", "Bar open time in New York."),
    ("bar_end_ny", "hourly", "New York timestamp", "derived",
     "Bar open + 1 hour: the time at which 'close' was observed."),
    ("gap_hours", "hourly", "hours", "derived",
     "Time since the previous bar's open; 1 for back-to-back bars."),
    ("after_closure", "hourly", "true/false", "derived",
     "First bar after a normal closure (daily pause, weekend, holiday)."),
    ("after_data_gap", "hourly", "true/false", "derived",
     "First bar after bars missing inside a session."),
    ("log_return", "hourly", "decimal", "derived",
     "ln(close / previous close). Spans gap_hours hours."),
    ("trading_day", "hourly", "date", "derived",
     "Trading day this bar belongs to; empty after the last close."),
    ("date", "daily", "date", "derived",
     "Trading day (index): all bars after the previous cash close up to this day's close "
     "(16:00 to 16:00 New York), labelled by the closing date."),
    ("open", "daily", "index points", "class file",
     "Open of the first bar after the previous close: about equal to the previous close, "
     "NOT the 09:30 cash open."),
    ("high", "daily", "index points", "class file",
     "Highest hourly high since the previous close, including the evening, the overnight "
     "session and any folded holiday session (wider than the cash-session range)."),
    ("low", "daily", "index points", "class file",
     "Lowest hourly low since the previous close, same span as high."),
    ("close", "daily", "index points", "class file",
     "Close of the bar ending 16:00 New York (13:00 on early-close days)."),
    ("n_bars", "daily", "count", "derived", "Hourly bars in the trading day (usually 23)."),
    ("close_time_ny", "daily", "New York timestamp", "derived",
     "Moment the daily close was observed."),
    ("early_close", "daily", "true/false", "config", "Cash market closed at 13:00."),
    ("log_return", "daily", "decimal", "derived", "ln(close / previous close)."),
    ("realized_var", "daily", "decimal, per day", "derived",
     "Sum of squared hourly log returns from the previous close to this close, including the "
     "returns across the 17:00 pause, weekends and folded holiday sessions, so it is comparable "
     "with the squared daily log_return. Annualize: x trading days per year."),
    ("vxn_points", "daily", "vol points (25 = 25%)", "FRED VXNCLS",
     "Cboe Nasdaq-100 30-day implied vol, latest value on or before the date. Same-day value, "
     "published shortly after the 16:00 close; shift one row for a value strictly known at "
     "the close."),
    ("vxn_stale_days", "daily", "calendar days", "derived", "Age of vxn_points; 0 = same day."),
    ("vxn_decimal", "daily", "decimal per year", "FRED VXNCLS", "vxn_points / 100."),
    ("rate", "daily", "decimal per year", "FRED DGS3MO",
     "3-month T-bill yield / 100, used as the risk-free rate. Latest value on or before the "
     "date; a same-day value is published after the 16:00 close (shift one row for a strictly "
     "known value)."),
    ("rate_stale_days", "daily", "calendar days", "derived", "Age of rate; 0 = same day."),
    ("vix_points", "daily", "vol points", "FRED VIXCLS", "VIX, comparison chart only."),
    ("vix_stale_days", "daily", "calendar days", "derived", "Age of vix_points; 0 = same day."),
    ("sample", "daily", "label", "config", "in_sample or out_of_sample."),
]


def data_dictionary() -> pd.DataFrame:
    """Return the meaning, unit and source of every column in both tables."""
    return pd.DataFrame(DICTIONARY, columns=["column", "table", "unit", "source", "description"])


def main():
    """Build both tables and write them with the report tables."""
    cfg = load_config()
    fred_table = load_fred(cfg)
    hourly, daily = build_tables(load_hourly(cfg), fred_table, cfg)
    factors = annualization_factors(hourly, daily)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    hourly.to_parquet(PROCESSED / "hourly.parquet")
    daily.to_parquet(PROCESSED / "daily.parquet")
    quality_report(hourly, daily, fred_table, cfg).to_csv(
        TABLES / "quality_report.csv", index=False)
    data_dictionary().to_csv(TABLES / "data_dictionary.csv", index=False)
    pd.Series(factors, name="value").rename_axis("factor").to_csv(TABLES / "annualization.csv")

    print(f"hourly: {len(hourly)} bars, daily: {len(daily)} trading days "
          f"({daily.index[0]:%Y-%m-%d} to {daily.index[-1]:%Y-%m-%d})")
    for name, value in factors.items():
        print(f"{name}: {value:.2f}")


if __name__ == "__main__":
    main()
