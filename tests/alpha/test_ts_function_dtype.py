"""
Regression tests for integer inputs flowing through the rolling operators.

Polars casts whatever a ``rolling_map`` callable returns back to the **input
column's** dtype. Feed an Int32 column to ``ts_mean`` and the mean 0.6 comes
back as 0 — truncated toward zero, silently, with no warning and no dtype
change that the caller could notice. Measured on polars 1.43.0 with the input
``[1, 0, 1, 1, 0, 1, 0, 0]`` and ``window=5``: ``ts_mean`` returned
``[1, 0, 0, 0, 0, 0, 0, 0]`` instead of ``[1.0, 0.5, 0.667, 0.75, 0.6, …]``
and ``ts_std`` returned all zeros instead of ``[0, 0.5, 0.471, 0.433, …]``.

Integer columns are not exotic in this codebase — they are the normal output of
**two** producers, and both reach the same operators:

* ``DataProxy`` comparisons (``utility.py``) cast to Int32 on purpose, because
  ``rolling_map`` refuses Boolean outright (``InvalidOperationError:
  'rolling_map' operation not supported for dtype 'bool'``). Alpha158's fifteen
  ``cnt*`` features are ``ts_mean(close > ts_delay(close, 1), w)``.
* ``quesval`` / ``quesval2`` / ``sign`` (``math_function.py``) build their
  branches from ``pl.lit(1)`` / ``pl.lit(0)``, which is also Int32 and never
  touches the comparison helper at all. Alpha101's ``alpha92`` goes down this
  second path.

That second producer is why the fix sits in the operators rather than in the
comparison helper: the set of integer producers is a list somebody has to keep
complete, while "a mean is a real number" holds for every input that will ever
exist. The tests below therefore assert **values, not dtypes** — a dtype
assertion would be satisfied by ``template.py``'s ``fill_null(float("nan"))``,
which promotes even a dead all-zero column to Float64 on its way out of
``prepare_data``.

The three lossless operators (``ts_argmax`` / ``ts_argmin`` / ``ts_product``)
are deliberately left un-cast: on an integer input their answers are integers by
definition, so there is nothing to lose.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import polars as pl
import pytest

from vnpy.alpha.dataset.ts_function import (
    ts_decay_linear,
    ts_mean,
    ts_quantile,
    ts_rank,
    ts_std,
)
from vnpy.alpha.dataset.utility import DataProxy, calculate_by_expression


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A run of up/down flags, exactly the shape a `close > ts_delay(close, 1)`
# comparison hands to ts_mean. Chosen so that no window average lands on a
# whole number by accident — every truncation is visible.
FLAGS: list[int] = [1, 0, 1, 1, 0, 1, 0, 0]

# Distinct integers, for the operators whose contract is about interpolation
# (ts_quantile) rather than about averaging.
STEPS: list[int] = [1, 2, 3, 4, 5, 6, 7, 8]

# Non-monotone distinct integers for ts_rank. A monotone series would hide the
# defect entirely: the last element of every window is then the window maximum,
# whose percentile is exactly 1.0, and 1.0 survives an Int32 round trip intact.
WIGGLES: list[int] = [3, 1, 4, 1, 5, 9, 2, 6]


def make_proxy(values: list[int], dtype: pl.DataType) -> DataProxy:
    """Build a single-symbol DataProxy holding one typed value column."""
    df: pl.DataFrame = pl.DataFrame(
        {
            "datetime": [datetime(2024, 1, 1) + timedelta(days=i) for i in range(len(values))],
            "vt_symbol": ["TEST.HK"] * len(values),
            "data": pl.Series(values, dtype=dtype),
        }
    )
    return DataProxy(df)


def as_floats(proxy: DataProxy) -> list[float]:
    """Read the data column as plain floats, rendering nulls as NaN."""
    return proxy.df["data"].cast(pl.Float64).fill_null(float("nan")).to_list()


def assert_integer_input_matches_float_input(
    from_integers: DataProxy,
    from_floats: DataProxy
) -> None:
    """Assert the two runs agree value by value, NaN positions included."""
    assert as_floats(from_integers) == pytest.approx(as_floats(from_floats), nan_ok=True)


# ---------------------------------------------------------------------------
# The five lossy operators
# ---------------------------------------------------------------------------

def test_ts_mean_on_integer_input_matches_float_input() -> None:
    assert_integer_input_matches_float_input(
        ts_mean(make_proxy(FLAGS, pl.Int32), 5),
        ts_mean(make_proxy(FLAGS, pl.Float64), 5),
    )


def test_ts_std_on_integer_input_matches_float_input() -> None:
    assert_integer_input_matches_float_input(
        ts_std(make_proxy(FLAGS, pl.Int32), 5),
        ts_std(make_proxy(FLAGS, pl.Float64), 5),
    )


def test_ts_rank_on_integer_input_matches_float_input() -> None:
    assert_integer_input_matches_float_input(
        ts_rank(make_proxy(WIGGLES, pl.Int32), 5),
        ts_rank(make_proxy(WIGGLES, pl.Float64), 5),
    )


def test_ts_quantile_on_integer_input_matches_float_input() -> None:
    # 0.3 of [1..5] interpolates to 2.2, which an Int32 round trip reports as 2.
    assert_integer_input_matches_float_input(
        ts_quantile(make_proxy(STEPS, pl.Int32), 5, 0.3),
        ts_quantile(make_proxy(STEPS, pl.Float64), 5, 0.3),
    )


def test_ts_decay_linear_on_integer_input_matches_float_input() -> None:
    assert_integer_input_matches_float_input(
        ts_decay_linear(make_proxy(FLAGS, pl.Int32), 5),
        ts_decay_linear(make_proxy(FLAGS, pl.Float64), 5),
    )


def test_ts_mean_of_a_zero_one_flag_column_returns_the_fraction_not_zero() -> None:
    # The failure spelled out on the smallest possible case: three ones in a
    # five-day window is 0.6, and 0.6 truncated toward zero is 0.
    result: DataProxy = ts_mean(make_proxy(FLAGS, pl.Int32), 5)

    assert as_floats(result)[4] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# Both integer producers still produce integers — the fix is downstream
# ---------------------------------------------------------------------------

def test_comparison_operators_still_hand_integer_data_to_the_operators() -> None:
    # Pins the decision NOT to touch `_comparison_series`. Upstream made
    # comparisons return Int32 on purpose (so their results can take part in
    # arithmetic), and Boolean cannot go through rolling_map at all. If this
    # ever flips to Float64, the operator-side cast becomes belt-and-braces
    # rather than the only thing standing between cnt* and a constant column.
    left: DataProxy = make_proxy(STEPS, pl.Float64)
    right: DataProxy = make_proxy([2] * len(STEPS), pl.Float64)

    assert (left > right).df["data"].dtype == pl.Int32


# ---------------------------------------------------------------------------
# Panel level: Alpha158 cnt* and Alpha101 alpha92
# ---------------------------------------------------------------------------

N_SYMBOLS: int = 4
N_DAYS: int = 120

# Alpha101's alpha92, copied verbatim from alpha_101.py:300. It is the only
# Alpha101 expression that reaches a rolling operator through quesval2, so it is
# the one that goes green here and nowhere else.
ALPHA92: str = (
    "ts_less("
    "ts_rank(ts_decay_linear(quesval2(((high + low) / 2 + close), (low + open), 1, 0), 15), 19), "
    "ts_rank(ts_decay_linear(ts_corr(cs_rank(low), cs_rank(ts_mean(volume, 30)), 8), 7), 7)"
    ")"
)


def make_panel() -> pl.DataFrame:
    """Build a deterministic multi-symbol OHLCV panel.

    Closed-form rather than seeded-random: a numpy Generator stream is not
    contractually stable across versions, and CI runs a different interpreter
    (Windows / 3.13) from this workstation (macOS / 3.14). The sine mixture
    gives runs of up and down days of uneven length, which is what stops every
    rolling window from averaging to a whole number.
    """
    rows: dict = {
        "datetime": [], "vt_symbol": [],
        "open": [], "high": [], "low": [], "close": [], "volume": []
    }

    for k in range(N_SYMBOLS):
        base: float = 10.0 * (k + 1)
        previous: float = base

        for i in range(N_DAYS):
            close: float = base * (1.0 + 0.03 * math.sin(0.7 * i + 1.3 * k) + 0.01 * math.cos(0.23 * i))

            rows["datetime"].append(datetime(2024, 1, 1) + timedelta(days=i))
            rows["vt_symbol"].append(f"S{k}.HK")
            rows["open"].append(previous)
            rows["high"].append(max(previous, close) * 1.004)
            rows["low"].append(min(previous, close) * 0.996)
            rows["close"].append(close)
            rows["volume"].append(1000.0 + 10.0 * ((i * 7 + k * 13) % 37))

            previous = close

    return pl.DataFrame(rows).sort(["datetime", "vt_symbol"])


def count_strictly_between_zero_and_one(values: pl.Series) -> int:
    """Count the values that are neither 0 nor 1 — i.e. genuine fractions."""
    return int(((values > 0) & (values < 1)).sum() or 0)


def test_ts_mean_of_a_quesval_indicator_is_still_a_fraction() -> None:
    # The second integer producer: quesval2's branches are pl.lit(1)/pl.lit(0),
    # also Int32, and they never pass through the comparison helper. Fixing
    # only `_comparison_series` would leave this one exactly as broken.
    df: pl.DataFrame = make_panel()

    values: pl.Series = (
        calculate_by_expression(df, "ts_mean(quesval2(close, open, 1, 0), 10)")["data"]
        .cast(pl.Float64)
    )

    assert count_strictly_between_zero_and_one(values) > 0
    assert values.n_unique() > 4


def test_cnt_features_are_fractions_rather_than_zero_one_indicators() -> None:
    # Alpha158's cntp/cntn/cntd, one window each. Truncation turns
    # `ts_mean(flag, w)` into "were ALL of the last w days up days", because
    # the only mean that survives toward-zero truncation is exactly 1.0.
    # Measured on this panel: strictly-inside counts were 0 / 0 / 0 before the
    # fix and 465 / 415 / 59 after; n_unique went 3 / 3 / 4 -> 32 / 11 / 16.
    df: pl.DataFrame = make_panel()

    expressions: tuple[tuple[str, str], ...] = (
        ("cntp_20", "ts_mean(close > ts_delay(close, 1), 20)"),
        ("cntn_5", "ts_mean(close < ts_delay(close, 1), 5)"),
        (
            "cntd_10",
            "ts_mean(close > ts_delay(close, 1), 10) - ts_mean(close < ts_delay(close, 1), 10)"
        ),
    )

    for name, expression in expressions:
        values: pl.Series = calculate_by_expression(df, expression)["data"].cast(pl.Float64)

        assert count_strictly_between_zero_and_one(values) > 0, name
        assert values.n_unique() > 4, name


def test_cnt_feature_is_not_constant_across_the_cross_section() -> None:
    # The shape the audit actually found in production: on 4137 of 4172 trading
    # days every symbol carried the identical cnt* value, which makes the column
    # worthless as a cross-sectional signal even though it is not literally a
    # constant column.
    df: pl.DataFrame = make_panel()

    result: pl.DataFrame = calculate_by_expression(df, "ts_mean(close > ts_delay(close, 1), 20)")
    per_day: pl.DataFrame = (
        result
        .drop_nulls("data")
        .group_by("datetime")
        .agg(pl.col("data").cast(pl.Float64).n_unique().alias("distinct"))
    )

    flat_days: int = int((per_day["distinct"] == 1).sum())

    assert flat_days < per_day.height / 2


def test_alpha92_is_not_flattened_to_a_single_value() -> None:
    # alpha92 reaches ts_decay_linear and ts_rank through quesval2, so it stays
    # broken even if one only fixes the comparison helper. Measured on this
    # panel: every non-null value was exactly 0.0 before the fix (n_unique 3
    # counting nulls and NaN), against 34 distinct values and a maximum of 1.0
    # after.
    df: pl.DataFrame = make_panel()

    values: pl.Series = calculate_by_expression(df, ALPHA92)["data"].cast(pl.Float64)

    assert count_strictly_between_zero_and_one(values) > 0
    assert values.n_unique() > 4
