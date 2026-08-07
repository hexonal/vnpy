"""
Regression tests for ``pow2`` refusing to invent a number it does not have.

``pow2`` used to end with ``.fill_nan(None).fill_null(0)``. That line repaired
nothing — it renamed "undefined" to "0" and handed it downstream as data, with
the column reporting a 0.00% NaN rate the whole time. Measured on
``hk_bluechip_10``: ``alpha78``'s exponent is NaN on 73.76% of rows, because its
inner ``ts_corr`` of two rank series is undefined on any window where either
series is constant, so **75.32% of that column was a manufactured zero**. The
other three call sites — alpha84, alpha85, alpha94 — fabricated 2.72%, 3.12%
and 7.14% the same way.

Zero is the worst available stand-in for these four expressions specifically.
Every one of them is ``rank(...)^rank(...)`` or ``rank(...)^ts_rank(...)``,
whose real values live in ``(0, 1]``: the invented value is not a neutral
middle, it sits below the entire legitimate range and reads to a model as the
most extreme observation in the column. NaN would have been dropped or imputed
by ``process_drop_na`` / ``process_cs_fill_na``; a 0 is trained on.

One subtlety worth pinning: polars evaluates ``NaN > 0`` as **true**, so a NaN
base takes the first branch and comes back NaN from ``.pow()`` on its own. The
undefined cases that actually need the final ``otherwise`` are a negative base
with a fractional exponent, and zero raised to a non-positive power.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import polars as pl

from vnpy.alpha.dataset.cs_function import cs_rank
from vnpy.alpha.dataset.math_function import pow1, pow2
from vnpy.alpha.dataset.utility import DataProxy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_proxy(name: str, values: list[float]) -> DataProxy:
    """Build a single-symbol DataProxy over consecutive days."""
    dates: list[datetime] = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(len(values))]

    return DataProxy(pl.DataFrame({"datetime": dates, "vt_symbol": ["A"] * len(values), name: values}))


def powered(base: list[float], exponent: list[float]) -> list[float]:
    """Run pow2 over two aligned value lists, nulls rendered as NaN."""
    result: DataProxy = pow2(make_proxy("base", base), make_proxy("exponent", exponent))
    return [float("nan") if v is None else float(v) for v in result.df["data"].to_list()]


NAN: float = float("nan")


# ---------------------------------------------------------------------------
# Undefined stays undefined
# ---------------------------------------------------------------------------

def test_pow2_missing_base_answers_nan_rather_than_zero() -> None:
    """A warm-up NaN on the base side must not surface as a real value."""
    values: list[float] = powered([NAN, 4.0], [2.0, 2.0])

    assert math.isnan(values[0])
    assert values[1] == 16.0


def test_pow2_missing_exponent_answers_nan_rather_than_zero() -> None:
    """This is alpha78's case: 73.76% of its exponent rows are NaN."""
    values: list[float] = powered([0.5, 0.5], [NAN, 2.0])

    assert math.isnan(values[0])
    assert values[1] == 0.25


def test_pow2_negative_base_with_a_fractional_exponent_answers_nan() -> None:
    """The result is complex, so there is no real number to report."""
    values: list[float] = powered([-4.0, -4.0], [0.5, 3.0])

    assert math.isnan(values[0])
    assert values[1] == -64.0


def test_pow2_zero_base_with_a_non_positive_exponent_answers_nan() -> None:
    """``0**0`` and ``0**-1`` have no value; only a positive exponent does."""
    values: list[float] = powered([0.0, 0.0, 0.0], [0.0, -1.0, 2.0])

    assert math.isnan(values[0])
    assert math.isnan(values[1])
    assert values[2] == 0.0


# ---------------------------------------------------------------------------
# Defined stays defined
# ---------------------------------------------------------------------------

def test_pow2_positive_base_keeps_the_ordinary_answer() -> None:
    """Fractional bases and fractional exponents are the normal case here."""
    values: list[float] = powered([4.0, 0.25, 1.0], [0.5, 2.0, 7.0])

    assert values == [2.0, 0.0625, 1.0]


def test_pow2_over_two_real_cs_rank_columns_stays_inside_the_unit_interval() -> None:
    """The shape alpha78 / alpha85 actually compute, cs_rank included.

    With an ordinal cs_rank the same two columns reached ``50**50 = 8.88e+84``
    on the fifty-symbol test panel. Nothing in ``pow2`` overflowed — it was
    handed the wrong numbers. Bounding the inputs is what bounds the output, so
    this is the standing check that the two fixes stay paired.

    **The first version of this test called itself that and was not.** It fed
    ``pow2`` the literals ``[0.1, 0.5, 0.9, 1.0]`` and never imported
    ``cs_rank`` at all, so reverting ``cs_rank`` to an ordinal left it green —
    measured, by running exactly that mutation. A test whose docstring claims a
    pairing it does not exercise is worse than no test, because the next reader
    stops looking for one.
    """
    dates: list[datetime] = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(3)]
    symbols: list[str] = [f"S{i}.SEHK" for i in range(20)]

    frame: pl.DataFrame = pl.DataFrame({
        "datetime": [day for day in dates for _ in symbols],
        "vt_symbol": symbols * len(dates),
        "raw": [float(i * 7 % 23) for i in range(len(dates) * len(symbols))],
    })
    ranked: DataProxy = cs_rank(DataProxy(frame))
    result: DataProxy = pow2(ranked, ranked)

    values: list[float] = [float(v) for v in result.df["data"].to_list() if v is not None]

    assert len(values) == len(dates) * len(symbols)
    assert all(0.0 < value <= 1.0 for value in values)
    # Ordinal ranks over twenty symbols would top out at 20**20 = 1.05e+26.
    assert max(values) <= 1.0


def test_pow2_zero_is_reserved_for_a_base_that_is_really_zero() -> None:
    """No undefined row may share the output value that a real 0 base produces."""
    values: list[float] = powered([0.0, NAN, -1.0], [3.0, 3.0, 0.5])

    assert values[0] == 0.0
    assert math.isnan(values[1])
    assert math.isnan(values[2])


# ---------------------------------------------------------------------------
# pow1 carried the same fail-open, reached a different way
# ---------------------------------------------------------------------------

def test_pow1_missing_base_answers_nothing_rather_than_zero() -> None:
    """A null base does not satisfy ``> 0`` or ``< 0``, so it fell through.

    Polars answers a comparison against null with null rather than false, which
    is why the old ``.otherwise(0)`` caught it. NaN takes the ``> 0`` branch on
    its own (polars ranks NaN above every number) and comes back NaN from
    ``.pow()``, so the two missing markers leave by different doors.
    """
    values: list[float | None] = pow1(make_proxy("base", [0.0, NAN, 3.0]), 2.0).df["data"].to_list()

    assert values[0] == 0.0
    assert values[1] is not None and math.isnan(values[1])
    assert values[2] == 9.0

    with_null: pl.DataFrame = make_proxy("base", [0.0, 0.0]).df.with_columns(
        pl.Series("data", [None, 3.0], dtype=pl.Float64)
    )

    assert pow1(DataProxy(with_null), 2.0).df["data"].to_list() == [None, 9.0]


def test_pow1_over_a_cs_rank_keeps_the_missing_symbol_missing() -> None:
    """alpha71 / alpha81 / alpha95 are all ``pow1(cs_rank(...), k)``.

    This is the pairing that made ``pow1`` this round's business rather than a
    later one: once ``cs_rank`` stopped ranking non-finite input and started
    answering null for it, ``pow1`` was the thing turning that null back into a
    number. Measured before the fix on this exact cross section — ``cs_rank``
    gave ``[0.333, null, 0.667, 1.0]`` and ``pow1`` returned ``[0.111, 0.0,
    0.444, 1.0]``, putting the missing symbol below every real one on a column
    whose range is ``(0, 1]``.
    """
    day: datetime = datetime(2024, 1, 1)
    frame: pl.DataFrame = pl.DataFrame({
        "datetime": [day] * 4,
        "vt_symbol": [f"S{i}.SEHK" for i in range(4)],
        "raw": [1.0, NAN, 3.0, 4.0],
    })

    values: list[float | None] = pow1(cs_rank(DataProxy(frame)), 2.0).df["data"].to_list()

    assert values[1] is None
    assert [round(v, 6) for v in values if v is not None] == [0.111111, 0.444444, 1.0]


def test_pow1_zero_base_with_a_negative_exponent_answers_nothing() -> None:
    """``0 ** -1`` has no value; alpha47 is the only call site that can ask."""
    assert pow1(make_proxy("base", [0.0, 2.0]), -1.0).df["data"].to_list() == [None, 0.5]
    assert pow1(make_proxy("base", [0.0, 2.0]), 2.0).df["data"].to_list() == [0.0, 4.0]
