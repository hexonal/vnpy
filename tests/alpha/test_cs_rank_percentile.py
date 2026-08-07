"""
Regression tests for ``cs_rank`` answering a fraction rather than an ordinal.

Kakushadze (2016) Appendix A.1 says only "rank(x) = cross-sectional rank" and
never names a denominator, so the definition has to be read off the formulas
that consume it. Three of them settle it: Alpha#1 ends in ``rank(...) - 0.5``,
Alpha#27 branches on ``0.5 < rank(...)``, and Alpha#19 adds ``1 + rank(...)``.
None of those constants means anything against an ordinal that runs to the size
of the universe — and an ordinal's ceiling moves with the number of symbols
priced that day, so the same relative position reads as a different number from
one date to the next.

Measured before the fix: ``alpha85`` (``rank(...)^rank(...)``) peaked at
``8.88e+84`` on the fifty-symbol panel in ``tests/test_alpha101.py`` — that is
``50**50`` to the digit, arithmetic rather than an overflow bug — and at
``1e+10`` on the ten-symbol ``hk_bluechip_10`` lab. ``alpha86`` was worse than
large: comparing an ordinal against a ``ts_rank`` bounded in ``[0, 1]``, its
condition could never fire and the column was the constant 0 on all 7350 rows.

The NaN half matters just as much and is easier to miss. Polars sorts NaN above
every real number, so the old unmasked ``rank()`` handed a suspended day or a
warm-up NaN the **top** rank in the cross section — a fabricated extreme, not a
missing value. The tests below pin both halves.
"""

from __future__ import annotations

import math
from datetime import datetime

import polars as pl

from vnpy.alpha.dataset.cs_function import cs_rank
from vnpy.alpha.dataset.utility import DataProxy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DAY_ONE: datetime = datetime(2024, 1, 1)
DAY_TWO: datetime = datetime(2024, 1, 2)


def make_proxy(rows: list[tuple[datetime, str, float]]) -> DataProxy:
    """Build a DataProxy from explicit (datetime, vt_symbol, value) rows."""
    df: pl.DataFrame = pl.DataFrame(
        {
            "datetime": [row[0] for row in rows],
            "vt_symbol": [row[1] for row in rows],
            "value": [row[2] for row in rows],
        }
    )
    return DataProxy(df)


def ranked(proxy: DataProxy) -> list[float]:
    """Read a cs_rank result back as plain floats, nulls rendered as NaN."""
    return [float("nan") if v is None else float(v) for v in cs_rank(proxy).df["data"].to_list()]


# ---------------------------------------------------------------------------
# The scale itself
# ---------------------------------------------------------------------------

def test_cs_rank_returns_fractions_with_the_best_symbol_at_one() -> None:
    """A four-symbol cross section ranks onto 0.25/0.5/0.75/1.0, not 1/2/3/4."""
    proxy = make_proxy([
        (DAY_ONE, "A", 10.0),
        (DAY_ONE, "B", 40.0),
        (DAY_ONE, "C", 20.0),
        (DAY_ONE, "D", 30.0),
    ])

    assert ranked(proxy) == [0.25, 1.0, 0.5, 0.75]


def test_cs_rank_top_is_one_whatever_the_cross_section_size() -> None:
    """The scale must not drift with the number of symbols priced that day.

    This is the property Alpha#1's ``- 0.5`` and Alpha#27's ``0.5 <`` are
    written against. Two symbols on one date and five on the next is the
    ordinary shape of a panel with listings and delistings in it.
    """
    proxy = make_proxy(
        [(DAY_ONE, "A", 1.0), (DAY_ONE, "B", 2.0)]
        + [(DAY_TWO, name, value) for name, value in zip("ABCDE", [5.0, 4.0, 3.0, 2.0, 1.0], strict=True)]
    )

    values: list[float] = ranked(proxy)

    assert max(values[:2]) == 1.0
    assert max(values[2:]) == 1.0
    assert min(values[:2]) == 0.5
    assert min(values[2:]) == 0.2


def test_cs_rank_alpha1_centering_lands_inside_plus_minus_a_half() -> None:
    """``cs_rank(x) - 0.5`` is a centred score, which is what Alpha#1 assumes."""
    proxy = make_proxy([(DAY_ONE, name, value) for name, value in zip("ABCDEF", [6.0, 5.0, 4.0, 3.0, 2.0, 1.0], strict=True)])

    centred: list[float] = [value - 0.5 for value in ranked(proxy)]

    assert min(centred) > -0.5
    assert max(centred) == 0.5


def test_cs_rank_ties_share_the_averaged_fraction() -> None:
    """Tied inputs get one shared value, so ties cannot invent an ordering."""
    proxy = make_proxy([
        (DAY_ONE, "A", 1.0),
        (DAY_ONE, "B", 1.0),
        (DAY_ONE, "C", 2.0),
        (DAY_ONE, "D", 3.0),
    ])

    assert ranked(proxy) == [0.375, 0.375, 0.75, 1.0]


# ---------------------------------------------------------------------------
# Missing values
# ---------------------------------------------------------------------------

def test_cs_rank_leaves_nan_missing_instead_of_ranking_it_top() -> None:
    """A NaN symbol stays missing, and the real best symbol still reads 1.0.

    Before the fix polars' NaN-sorts-last behaviour gave the NaN row rank 4 of
    4 — the fabricated top of the cross section — and pushed the genuinely
    largest value down to 0.75.
    """
    proxy = make_proxy([
        (DAY_ONE, "A", 3.0),
        (DAY_ONE, "B", 1.0),
        (DAY_ONE, "C", float("nan")),
        (DAY_ONE, "D", 2.0),
    ])

    values: list[float] = ranked(proxy)

    assert math.isnan(values[2])
    assert values[0] == 1.0
    assert values[1] == 1 / 3
    assert values[3] == 2 / 3


def test_cs_rank_denominator_counts_only_the_symbols_that_have_a_value() -> None:
    """Three live symbols out of five rank onto thirds, not fifths."""
    proxy = make_proxy([
        (DAY_ONE, "A", 1.0),
        (DAY_ONE, "B", 2.0),
        (DAY_ONE, "C", 3.0),
        (DAY_ONE, "D", float("nan")),
        (DAY_ONE, "E", float("nan")),
    ])

    values: list[float] = ranked(proxy)

    assert values[:3] == [1 / 3, 2 / 3, 1.0]
    assert math.isnan(values[3]) and math.isnan(values[4])


# ---------------------------------------------------------------------------
# Integer inputs
# ---------------------------------------------------------------------------

def test_cs_rank_accepts_the_int32_that_comparisons_and_quesval_produce() -> None:
    """Int32 in, fractions out — without an is_not_nan dtype error.

    ``cs_rank`` is routinely handed an Int32 column: every ``DataProxy``
    comparison casts to Int32 deliberately, and ``quesval`` / ``quesval2`` /
    ``sign`` build their branches out of ``pl.lit(1)`` / ``pl.lit(0)``, which is
    Int32 too. ``is_not_nan`` raises ``InvalidOperationError`` on an integer
    column, so the mask only works because of the Float64 cast in front of it.
    """
    df: pl.DataFrame = pl.DataFrame(
        {
            "datetime": [DAY_ONE] * 3,
            "vt_symbol": ["A", "B", "C"],
            "value": pl.Series([0, 1, 1], dtype=pl.Int32),
        }
    )

    assert ranked(DataProxy(df)) == [1 / 3, 5 / 6, 5 / 6]
