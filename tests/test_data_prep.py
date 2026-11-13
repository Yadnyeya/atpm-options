"""Checks on Phase 1: the daily close, the trading calendar and look-ahead."""
import copy

import numpy as np
import pandas as pd
import pytest

from src import data_prep
from src.config import load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def inputs(cfg):
    """The raw hourly bars and the FRED table, loaded once for all tests."""
    return data_prep.load_hourly(cfg), data_prep.load_fred(cfg)


@pytest.fixture(scope="module")
def tables(inputs, cfg):
    """(hourly, daily) built from the full inputs."""
    return data_prep.build_tables(*inputs, cfg)


def test_truncating_inputs_does_not_change_the_past(inputs, tables, cfg):
    """Look-ahead guard: rows up to T must not depend on anything after T.

    All inputs are cut at the close of T and the tables rebuilt. If any value
    up to T used later data (a backward fill, a full-sample statistic), it
    would differ from the full build.
    """
    bars, fred_table = inputs
    hourly, daily = tables
    for day in ["2021-03-12", "2022-10-07", "2024-11-11"]:  # last one is a bond holiday (rate is filled)
        close_utc = daily.loc[day, "close_time_ny"].tz_convert("UTC")
        cut_bars = bars[bars.index + data_prep.HOUR <= close_utc]
        cut_hourly, cut_daily = data_prep.build_tables(cut_bars, fred_table.loc[:day], cfg)
        pd.testing.assert_frame_equal(cut_daily, daily.loc[:day])
        pd.testing.assert_frame_equal(cut_hourly, hourly.loc[cut_hourly.index])


def test_fred_values_match_the_raw_files(tables):
    """Look-ahead guard anchored to the raw FRED files, not to our own loader.

    The numbers below were typed by hand from data/raw/fred_*_2026-11-12.csv. A
    one-row shift or a date slip anywhere from loading to merging breaks them.
    """
    daily = tables[1]
    assert daily.loc["2024-11-11", "vxn_points"] == 18.37
    assert daily.loc["2024-11-11", "vix_points"] == 14.97
    assert daily.loc["2021-04-05", "vxn_points"] == 23.93
    # Bond holidays (stocks open): the rate is carried from the Friday before.
    assert daily.loc["2024-11-11", "rate"] == pytest.approx(0.0463)   # 4.63 on 2024-11-08
    assert daily.loc["2020-10-12", "rate"] == pytest.approx(0.0010)   # 0.10 on 2020-10-09
    # Alignment smoke test: VXN rises on the day the index falls. With VXN
    # shifted by one day this correlation is about +0.10 instead of -0.72.
    assert daily["vxn_points"].diff().corr(daily["log_return"]) < -0.5


def test_fred_values_come_from_the_row_date_or_earlier(inputs, tables, cfg):
    """Each merged value must equal the FRED value dated `stale_days` before the row."""
    fred_table, daily = inputs[1], tables[1]
    for prefix, column, key in data_prep.FRED_COLUMNS:
        name, scale = cfg["data"]["fred_series"][key], 100 if column == "rate" else 1
        stale = daily[prefix + "_stale_days"]
        assert (stale >= 0).all()
        source_dates = daily.index - pd.to_timedelta(stale.to_numpy(), unit="D")
        np.testing.assert_allclose(daily[column] * scale, fred_table[name].loc[source_dates])
    assert (daily["vxn_stale_days"] == 0).all()  # VXN exists on every trading day
    assert daily["rate_stale_days"].max() == 3   # bond holiday on a Monday
    np.testing.assert_allclose(daily["vxn_decimal"] * 100, daily["vxn_points"])


@pytest.mark.parametrize("day, bar_open_utc", [
    ("2021-07-15", "2021-07-15 19:00"),  # summer: 15:00 New York = 19:00 UTC
    ("2021-01-15", "2021-01-15 20:00"),  # winter: 15:00 New York = 20:00 UTC
    ("2020-11-27", "2020-11-27 17:00"),  # early close: 12:00 New York = 17:00 UTC
])
def test_daily_close_is_the_bar_ending_at_the_new_york_close(tables, day, bar_open_utc):
    """The daily close is the close of the bar stamped one hour before the cash close."""
    hourly, daily = tables
    assert daily.loc[day, "close"] == hourly.loc[pd.Timestamp(bar_open_utc, tz="UTC"), "close"]


def test_every_daily_close_is_at_16_or_13_new_york(tables, cfg):
    """All closes are observed at 16:00 New York, or 13:00 on the listed early closes."""
    daily, data = tables[1], cfg["data"]
    hour = daily["close_time_ny"].dt.hour
    assert (hour[~daily["early_close"]] == data["daily_close_hour"]).all()
    assert (hour[daily["early_close"]] == data["early_close_hour"]).all()
    assert list(daily.index[daily["early_close"]]) == list(pd.to_datetime(data["early_close_dates"]))
    assert (daily["close_time_ny"].dt.tz_localize(None).dt.normalize() == daily.index).all()


def test_trading_days_per_year(tables):
    """The calendar matches the official Nasdaq-100 sessions, year by year.

    The counts were checked once against the official index (^NDX, outside
    data). Days when the stock market was closed must not appear.
    """
    hourly, daily = tables
    per_year = daily.groupby(daily.index.year).size()
    assert per_year.to_dict() == {2020: 128, 2021: 252, 2022: 251, 2023: 250, 2024: 252, 2025: 122}
    # Good Friday, Christmas Day observed, national day of mourning (Carter).
    closed = pd.to_datetime(["2021-04-02", "2021-12-24", "2025-01-09"])
    assert not daily.index.isin(closed).any()
    factors = data_prep.annualization_factors(hourly, daily)
    assert 248 <= factors["trading_days_per_year"] <= 254
    assert 5800 <= factors["hourly_bars_per_year"] <= 6000


def test_no_weekend_daily_bars(tables):
    """Sunday-evening bars fold into Monday, so every daily row is a weekday."""
    hourly, daily = tables
    assert (daily.index.day_of_week < 5).all()
    sunday = hourly[hourly["time_ny"].dt.day_of_week == 6]
    assert len(sunday) > 1000
    assert (sunday["trading_day"].dt.day_of_week != 6).all()


def test_daily_values_reconcile_with_hourly(tables):
    """Daily numbers are exactly what the hourly bars of that trading day imply."""
    hourly, daily = tables
    by_day = hourly.groupby("trading_day")
    later = daily.index[1:]  # the first day has no previous close
    np.testing.assert_allclose(by_day["log_return"].sum()[later], daily["log_return"][later],
                               atol=1e-12)
    np.testing.assert_allclose((hourly["log_return"] ** 2).groupby(hourly["trading_day"]).sum()[later],
                               daily["realized_var"][later])
    assert (daily["realized_var"][later] > 0).all()
    assert daily[["log_return", "realized_var"]].iloc[0].isna().all()
    assert daily["n_bars"].sum() == hourly["trading_day"].notna().sum()
    assert (daily["high"] == by_day["high"].max()).all()
    assert (daily["low"] == by_day["low"].min()).all()
    assert (daily["open"] == by_day["open"].first()).all()
    assert (daily["high"] >= daily[["open", "close"]].max(axis=1)).all()


def test_gap_flags(tables):
    """Every return spanning more than one hour is flagged as closure or data gap."""
    hourly = tables[0]
    flagged = hourly["after_closure"] | hourly["after_data_gap"]
    assert (flagged == (hourly["gap_hours"] > 1)).all()
    assert not (hourly["after_closure"] & hourly["after_data_gap"]).any()
    assert hourly["after_data_gap"].sum() == 3
    assert (hourly["time_ny"].dt.hour != 17).all()  # the daily pause: stamps are open times


def test_sample_labels_follow_config(tables, cfg):
    """The in/out-of-sample split in the table is the one written in config."""
    daily = tables[1]
    start = pd.Timestamp(cfg["sample"]["out_of_sample"][0])
    assert (daily.loc[daily.index < start, "sample"] == "in_sample").all()
    assert (daily.loc[daily.index >= start, "sample"] == "out_of_sample").all()


def test_a_day_outside_both_sample_windows_is_an_error(tables, cfg):
    """A day with no label would silently vanish from both periods, so it must fail."""
    gap_cfg = copy.deepcopy(cfg)
    gap_cfg["sample"]["in_sample"][1] = "2023-06-30"  # leaves July-December 2023 uncovered
    with pytest.raises(ValueError, match="neither sample window"):
        data_prep.label_sample(tables[1].drop(columns="sample"), gap_cfg)


def test_daily_table_survives_saving(tables, tmp_path):
    """Reading the saved parquet gives exactly the table that was built."""
    tables[1].to_parquet(tmp_path / "daily.parquet")
    pd.testing.assert_frame_equal(pd.read_parquet(tmp_path / "daily.parquet"), tables[1])


def test_reports_cover_the_tables(inputs, tables, cfg):
    """The data dictionary names every column; the quality report finds no broken rows."""
    hourly, daily = tables
    dictionary = data_prep.data_dictionary()
    for name, table in [("hourly", hourly), ("daily", daily)]:
        documented = set(dictionary.loc[dictionary["table"] == name, "column"])
        assert documented == set(table.columns) | {table.index.name}
    report = data_prep.quality_report(hourly, daily, inputs[1], cfg).set_index("check")["count"]
    must_be_zero = ["duplicate timestamps", "timestamps out of order",
                    "missing values in price columns", "zero or negative prices",
                    "OHLC inconsistencies", "bars outside the CFD session",
                    "Sunday-dated daily rows"]
    assert (report[must_be_zero] == 0).all()
    assert report["hourly rows"] == len(inputs[0]) == 29508  # nothing deleted
    # The numbers the report publishes, pinned so a change cannot go unnoticed.
    published = {"flat bars (open = high = low = close)": 1,
                 "close equal to the previous bar's close": 7,
                 "open more than 10 bp from the previous close": 12,
                 "normal closures": 1291,
                 "closures that reopen later than 18:00 New York": 1,
                 "data gaps inside a session": 3,
                 "hourly returns beyond 8 robust sigmas": 224,
                 "bars after the last close in the file": 8,
                 "early-close days (13:00 New York)": 9,
                 "trading days holding more than 24 hourly bars": 36,
                 "trading days holding fewer than 23 hourly bars": 9,
                 "first trading day is partial": 1,
                 "VXNCLS values on non-trading days": 2,
                 "DGS3MO carried forward from an earlier day": 9}
    assert report[list(published)].to_dict() == published


def test_quality_report_text_is_computed_not_typed(inputs, tables, cfg):
    """The report must describe the data it is given, not the class file it was written for."""
    bars, fred_table = inputs
    hourly, daily = tables

    # A threshold no return reaches: the row reports zero instead of crashing.
    high_cfg = copy.deepcopy(cfg)
    high_cfg["data"]["extreme_return_sigmas"] = 1000
    report = data_prep.quality_report(hourly, daily, fred_table, high_cfg).set_index("check")
    assert report.loc["hourly returns beyond 1000 robust sigmas", "count"] == 0

    # A broken row is reported as found, never as "none found".
    broken = pd.concat([hourly, hourly.iloc[[100]]])
    report = data_prep.quality_report(broken, daily, fred_table, cfg).set_index("check")
    assert report.loc["duplicate timestamps", "count"] == 1
    assert report.loc["duplicate timestamps", "how_handled"].startswith("FOUND")

    # A file that starts right after a cash close has a complete first day.
    first_evening = bars.index[bars["time_ny"].dt.hour == cfg["data"]["daily_close_hour"]][0]
    full_hourly, full_daily = data_prep.build_tables(bars[first_evening:], fred_table, cfg)
    report = data_prep.quality_report(full_hourly, full_daily, fred_table, cfg).set_index("check")
    assert report.loc["first trading day is partial", "count"] == 0
