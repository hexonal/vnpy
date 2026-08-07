"""
Regression tests for the direction of ``quesval2``'s comparison.

``quesval2(threshold, feature1, x, y)`` has always documented itself as "return
``x`` if ``threshold < feature1``". It did the opposite. The mechanism was a
join suffix: written as ``threshold.df.join(feature1.df, suffix="_cond")``,
polars suffixes the **right** frame, so ``data_cond`` held ``feature1`` while
the bare ``data`` held ``threshold``, and ``pl.col("data_cond") < pl.col("data")``
read ``feature1 < threshold``. Measured: ``quesval2(0, 1, 1, 0)`` answered 0.

All eleven Alpha101 expressions that route through it — alpha7, 21, 23, 61, 74,
75, 81, 86, 92, 95, 99 — transcribe a ``(a < b) ? x : y`` from Kakushadze (2016)
with ``a`` passed as ``threshold``, so all eleven computed the negation. Only
``alpha86`` showed: with ``a`` a ``ts_rank`` in ``[0, 1]`` and ``b`` a
``cs_rank``, the reversed test could never fire and the column came out the
constant 0 on all 7350 rows of ``hk_bluechip_10``. The other ten stayed
plausible — a factor with the wrong sign still has variance and still trains,
which is why this survived.

The sibling ``quesval`` takes a scalar threshold, does no join, and was never
affected; the last test below pins the two against each other so a future edit
cannot desynchronise them.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

from vnpy.alpha.dataset.utility import calculate_by_expression


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_df() -> pl.DataFrame:
    """A two-symbol panel whose columns are ordered against each other by row.

    ``small`` and ``big`` cross over halfway through, so any implementation that
    answers a constant — which is exactly what the inverted comparison did to
    alpha86 — fails on cardinality alone before any value is inspected.
    """
    dates: list[datetime] = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(4)]

    return pl.DataFrame(
        {
            "datetime": dates * 2,
            "vt_symbol": ["A"] * 4 + ["B"] * 4,
            "small": [1.0, 2.0, 3.0, 4.0] * 2,
            "big": [4.0, 3.0, 2.0, 1.0] * 2,
            "same": [1.0, 2.0, 3.0, 4.0] * 2,
        }
    )


def evaluate(expression: str) -> list[float]:
    """Run an expression over the two-symbol panel and read the values back."""
    result: pl.DataFrame = calculate_by_expression(make_df(), expression)
    return [float(value) for value in result["data"].to_list()]


# ---------------------------------------------------------------------------
# Direction
# ---------------------------------------------------------------------------

def test_quesval2_takes_the_true_branch_where_threshold_is_below_feature1() -> None:
    """Threshold below feature1 selects the third argument, as documented."""
    assert evaluate("quesval2(small, big, 1, 0)") == [1.0, 1.0, 0.0, 0.0] * 2


def test_quesval2_takes_the_false_branch_where_threshold_is_above_feature1() -> None:
    """Swapping the two operands must swap the answer, not repeat it."""
    assert evaluate("quesval2(big, small, 1, 0)") == [0.0, 0.0, 1.0, 1.0] * 2


def test_quesval2_treats_equality_as_false_because_the_test_is_strict() -> None:
    """``a < a`` is false, so an equal pair falls through to the else branch."""
    assert evaluate("quesval2(small, same, 1, 0)") == [0.0] * 8


# ---------------------------------------------------------------------------
# Agreement with the operators Alpha101 uses side by side
# ---------------------------------------------------------------------------

def test_quesval2_agrees_with_the_bare_less_than_operator() -> None:
    """Alpha101 writes the same paper construct both ways; they must agree.

    alpha62 / alpha64 / alpha65 / alpha68 transcribe ``(a < b) * -1`` with the
    plain ``<`` operator, while alpha74 / alpha86 / alpha99 transcribe the same
    shape through ``quesval2``. Before the fix the two spellings disagreed on
    every row, and nothing in the suite noticed.
    """
    assert evaluate("quesval2(small, big, 1, 0)") == evaluate("(small < big) * 1")
    assert evaluate("quesval2(big, small, 1, 0)") == evaluate("(big < small) * 1")


def test_quesval2_agrees_with_quesval_on_a_constant_threshold() -> None:
    """The scalar-threshold sibling is the reference; it never had the bug."""
    assert evaluate("quesval2(same * 0 + 2, small, 1, 0)") == evaluate("quesval(2, small, 1, 0)")


# ---------------------------------------------------------------------------
# Branch values
# ---------------------------------------------------------------------------

def test_quesval2_carries_dataproxy_branches_not_only_scalars() -> None:
    """Both branches may themselves be features — alpha7 and alpha23 use that."""
    assert evaluate("quesval2(small, big, small, big)") == [1.0, 2.0, 2.0, 1.0] * 2
