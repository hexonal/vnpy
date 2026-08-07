"""
Regression tests for suspended days flowing through the ordering comparisons.

``load_bar_df`` writes ``float("nan")`` across every column of a suspended day,
and polars ranks NaN above every real number instead of refusing to answer.
Measured on polars 1.43.0 over Float64 columns: ``NaN > 11.0`` is ``True`` while
``12.0 > NaN`` is ``False``. Run that through Alpha158's fifteen ``cnt*``
features — all of them ``ts_mean(close > ts_delay(close, 1), w)`` shaped — and a
single halt does two wrong things at once: the first suspended day is booked as
a rise, and the real +9.1% on the day trading resumes is booked as *not* a rise.

The reason this needed tests rather than a fix and a shrug is that **nothing
downstream can see it**. The comparison result is cast to Int32 and averaged, so
the fabricated day leaves no NaN, no dtype change and no warning; the column
simply holds a different number. Measured with one three-day halt on an 800-row
panel, ``cntd_5`` moved by 0.800 on a column whose whole range is [-1, 1].

The tests below therefore assert **values**, never NaN counts: after the fix a
``cnt*`` column over a *short* halt is still finite everywhere it was finite
before — ``ts_mean`` is ``rolling_map(np.nanmean, min_samples=1)``, so a null
window member is skipped rather than propagated. Counting NaN would pass with
the fix reverted.

"Short" earns a test of its own. A halt of ``h`` sessions blanks ``h + 1``
flags, because the resumption day's ``ts_delay(close, 1)`` is itself a halted
day, so a window of ``w`` runs out of observations at ``h == w - 1``. Alpha158's
narrowest window is 5, which puts the boundary at a four-session suspension —
ordinary in A-shares. The reading then goes missing, which is the right answer
and a visible one; it is pinned here because the first draft of this module
wrote "zero extra NaN" after measuring a three-day halt and nothing else.

``__eq__`` / ``__ne__`` are covered here too, as the thing that must *not*
change: polars answers ``NaN == NaN`` with ``True``, which is a definition and
not an accident, and there is a test pinning it so that a future "let us mask
NaN everywhere" sweep has to argue with it first.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import polars as pl

import vnpy
from vnpy.alpha.dataset.utility import DataProxy, calculate_by_expression
from vnpy.alpha.semantics import FEATURE_SEMANTICS_VERSION


NAN: float = float("nan")

# Two flat days, a three-day halt, then a real 11.0 -> 12.0 rise on the day
# trading resumes. The resumption gain is what makes the second half of the
# defect visible: an implementation that only stopped counting the halted days
# as rises would still lose this one.
CLOSE_WITH_HALT: list[float] = [10.0, 11.0, NAN, NAN, NAN, 12.0, 11.5, 11.8]

# The same series with the halt filled in by trading, for the invariant that
# the guard is inert on data that has no suspended day in it.
CLOSE_NO_HALT: list[float] = [10.0, 11.0, 11.2, 11.1, 11.4, 12.0, 11.5, 11.8]

# The four operators the guard covers, paired with the answer each one owes on
# `left <op> right` where exactly one side is NaN. `None` means "no verdict".
ORDERING_CASES: tuple[tuple[str, float, float, int | None], ...] = (
    ("gt", NAN, 11.0, None),
    ("gt", 12.0, NAN, None),
    ("ge", NAN, 11.0, None),
    ("ge", 12.0, NAN, None),
    ("lt", NAN, 11.0, None),
    ("lt", 12.0, NAN, None),
    ("le", NAN, 11.0, None),
    ("le", 12.0, NAN, None),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_frame(values: list[float], name: str = "close") -> pl.DataFrame:
    """Build a single-symbol frame shaped like a `load_bar_df` slice."""
    base: datetime = datetime(2024, 1, 1)

    return pl.DataFrame({
        "datetime": [base + timedelta(days=i) for i in range(len(values))],
        "vt_symbol": ["S1.SEHK"] * len(values),
        name: values,
    })


def make_proxy(values: list[float], name: str = "close") -> DataProxy:
    """Build a DataProxy over one float column."""
    return DataProxy(make_frame(values, name))


def data_of(proxy: DataProxy) -> list[int | None]:
    """Read a comparison result back as a plain list."""
    values: list[int | None] = proxy.df["data"].to_list()
    return values


def apply_operator(op: str, left: DataProxy, right: DataProxy | float) -> DataProxy:
    """Dispatch one of the four ordering operators by name."""
    if op == "gt":
        return left > right
    if op == "ge":
        return left >= right
    if op == "lt":
        return left < right
    return left <= right


# ---------------------------------------------------------------------------
# The comparison itself
# ---------------------------------------------------------------------------

def test_every_ordering_operator_answers_null_when_one_side_is_nan() -> None:
    for op, left, right, expected in ORDERING_CASES:
        result: DataProxy = apply_operator(op, make_proxy([left]), make_proxy([right]))

        assert data_of(result) == [expected], f"{op}({left}, {right})"


def test_ordering_against_a_scalar_masks_nan_on_the_proxy_side() -> None:
    # The scalar branch is a separate code path from the proxy branch, and it is
    # the one Alpha101 uses (`close > 0`). Unguarded it answered True for NaN.
    result: DataProxy = make_proxy([10.0, NAN, 12.0]) > 11.0

    assert data_of(result) == [0, None, 1]


def test_a_suspended_day_is_no_longer_counted_as_a_rise() -> None:
    # Unguarded this reads [None, 1, 1, 0, 0, 0, 0, 1]: index 2 is the fabricated
    # rise (NaN > 11.0) and index 5 is the deleted one (12.0 > NaN).
    frame: pl.DataFrame = make_frame(CLOSE_WITH_HALT)

    rises: pl.DataFrame = calculate_by_expression(frame, "close > ts_delay(close, 1)")

    assert rises["data"].to_list() == [None, 1, None, None, None, None, 0, 1]


def test_the_resumption_day_keeps_its_real_direction() -> None:
    # 11.0 -> 12.0 is a 9.1% gain, and the unguarded `<` booked it as a fall
    # because `12.0 < NaN` is True. The guard must not answer "fall" here — but
    # it also cannot answer "rise", because the previous traded close is three
    # days away and `ts_delay(close, 1)` does not reach it.
    frame: pl.DataFrame = make_frame(CLOSE_WITH_HALT)

    falls: pl.DataFrame = calculate_by_expression(frame, "close < ts_delay(close, 1)")

    assert falls["data"].to_list() == [None, 0, None, None, None, None, 1, 0]


def test_equality_still_answers_true_for_nan_against_nan() -> None:
    # Deliberately unguarded. Polars defines NaN == NaN as True (IEEE 754 does
    # not), so this is an answer rather than a coin flip; masking it would
    # replace a definition with a null.
    same: DataProxy = make_proxy([NAN, 1.0]) == make_proxy([NAN, 2.0])
    differ: DataProxy = make_proxy([NAN, 1.0]) != make_proxy([NAN, 2.0])

    assert data_of(same) == [1, 0]
    assert data_of(differ) == [0, 1]


def test_integer_operands_survive_the_guard_untouched() -> None:
    # The guard branches on `dtype.is_float()`. An Int32 column cannot hold NaN,
    # and comparison results in this class are Int32 — so a guard that reached
    # for `fill_nan` unconditionally would be betting on polars tolerating it.
    left: DataProxy = DataProxy(make_frame([0.0, 0.0, 0.0]).with_columns(
        pl.Series("close", [3, 1, 4], dtype=pl.Int32)
    ))
    right: DataProxy = DataProxy(make_frame([0.0, 0.0, 0.0]).with_columns(
        pl.Series("close", [1, 5, 4], dtype=pl.Int32)
    ))

    assert data_of(left > right) == [1, 0, 0]
    assert data_of(left <= right) == [0, 1, 1]


# ---------------------------------------------------------------------------
# The cnt* features, end to end
# ---------------------------------------------------------------------------

def test_cntp_over_a_halt_is_the_fraction_of_the_days_actually_observed() -> None:
    # Alpha158's expression, verbatim from alpha_158.py:94.
    frame: pl.DataFrame = make_frame(CLOSE_WITH_HALT)

    result: pl.DataFrame = calculate_by_expression(
        frame, "ts_mean(close > ts_delay(close, 1), 5)"
    )
    values: list[float | None] = result["data"].to_list()

    # Index 6's five-day window holds four nulls and one observed non-rise, so
    # the answer is 0.0 — "of what was observed, none were up days". Unguarded
    # the same window held four fabricated flags and answered 0.2.
    assert values[6] == 0.0
    # Index 7 sees one non-rise and one rise among the observed days.
    assert values[7] == 0.5


def test_cnt_features_over_a_halt_shorter_than_the_window_stay_finite() -> None:
    # `ts_mean` is rolling_map(np.nanmean, min_samples=1), so masking to null
    # skips the day instead of poisoning the window. Stated as a test because
    # the intuitive expectation — "the fix makes suspended days NaN" — is wrong,
    # and a regression suite written on that expectation would assert nothing.
    #
    # The three-day halt in CLOSE_WITH_HALT is the *short* case; the length
    # condition it depends on is pinned by the next test rather than left as an
    # accident of this fixture.
    frame: pl.DataFrame = make_frame(CLOSE_WITH_HALT)

    for window in (5, 10, 20, 30, 60):
        result: pl.DataFrame = calculate_by_expression(
            frame, f"ts_mean(close > ts_delay(close, 1), {window})"
        )
        tail: list[float | None] = result["data"].to_list()[1:]

        assert all(value is not None and math.isfinite(value) for value in tail), window


def test_a_halt_at_least_as_long_as_the_window_leaves_no_reading_at_all() -> None:
    # The boundary the docstring above claims, asserted rather than described.
    # A halt of h sessions blanks h + 1 flags — the halted days plus the
    # resumption day, whose ts_delay(close, 1) is itself a halted day — so a
    # window of w runs out of observations at h == w - 1 and loses h - w + 2
    # readings from there on.
    #
    # This is the honest half of the change and the reason the first draft of
    # this file said "zero extra NaN" and was wrong: that was measured on a
    # three-day halt only. Alpha158's narrowest window is 5, so an A-share
    # suspension of four sessions already blanks cntp_5 / cntn_5 / cntd_5.
    for halt, expected in ((3, 0), (4, 1), (5, 2), (7, 4)):
        closes: list[float] = [10.0, 11.0] + [NAN] * halt + [12.0, 11.5, 11.8, 12.2, 12.0, 12.4, 12.1]

        result: pl.DataFrame = calculate_by_expression(
            make_frame(closes), "ts_mean(close > ts_delay(close, 1), 5)"
        )
        missing: int = sum(1 for value in result["data"].to_list()[1:] if value is None)

        assert missing == expected, halt

    # The same halts are lossless on the wider windows, so this is a property of
    # the window rather than of the guard.
    for window in (10, 20, 60):
        closes = [10.0, 11.0] + [NAN] * 7 + [12.0, 11.5, 11.8, 12.2, 12.0, 12.4, 12.1]

        result = calculate_by_expression(
            make_frame(closes), f"ts_mean(close > ts_delay(close, 1), {window})"
        )

        assert all(value is not None for value in result["data"].to_list()[1:]), window


def test_a_panel_without_a_suspended_day_reads_exactly_as_it_did_before() -> None:
    # The invariant every already-computed artifact rests on, and the reason the
    # protocol frozen at us_ai_basket_2026-08-07 did not have to be re-run:
    # measured over hk_bluechip_10 (7350 rows, 0 rows tripping the suspension
    # mask) all 158 Alpha158 columns come out bit-identical. This is the
    # miniature of that check — it stays green with the guard reverted, on
    # purpose, because that is what "inert on clean data" means.
    frame: pl.DataFrame = make_frame(CLOSE_NO_HALT)

    result: pl.DataFrame = calculate_by_expression(
        frame, "ts_mean(close > ts_delay(close, 1), 5)"
    )

    assert result["data"].to_list()[1:] == [1.0, 1.0, 2 / 3, 0.75, 0.8, 0.6, 0.6]


# ---------------------------------------------------------------------------
# The stamp and the version segment move together
# ---------------------------------------------------------------------------

def test_the_local_version_segment_tracks_the_feature_semantics_version() -> None:
    # The gate is an equality test, so shipping code that computes v2 while
    # stamping v1 — or the reverse — makes it accept artifacts it exists to
    # refuse. `vnpy_alphakit/provenance.py` records `__version__` into every
    # run manifest and is the only other place the two can be told apart, so
    # they have to be bumped as one edit. This test is what makes "as one edit"
    # a machine's problem rather than a reviewer's.
    assert vnpy.__version__ == f"4.4.0+hexonal.{FEATURE_SEMANTICS_VERSION}"
