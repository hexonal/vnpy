"""
Value-level regression net for Alpha101, which until now had none.

``tests/test_alpha101.py`` is an upstream file, and every one of its hundred
assertions is the same line: ``assert "data" in result.columns``. It proves the
expression parses. It does not look at a single number — measured, by running
the three operator defects this fork just fixed against it: an ordinal
``cs_rank`` that drove ``alpha85`` to ``50 ** 50``, a ``quesval2`` that answered
every comparison backwards, and a ``pow2`` that replaced 75% of ``alpha78`` with
manufactured zeros while the column reported a 0.00% missing rate. **All hundred
stayed green through all three.** That is the whole reason those defects
survived to be found by hand.

This file asserts properties instead of shapes, chosen so that each one fails
loudly under exactly one of the defects:

* **A bound that does not move with the size of the universe.** The ordinal
  ``cs_rank`` produced ``N ** N``, so the same expression read ``8.92e+12`` on
  twelve symbols and ``1.05e+26`` on twenty. Running one expression over two
  cross-section widths and requiring the same ceiling is a sharper statement
  than any single threshold, because it names the defect's mechanism rather
  than one of its readings.

* **No exact zero on a column whose real range excludes it.** ``pow2`` and
  ``pow1`` both used to end by turning "undefined" into ``0``. Counting zeros is
  what a missing-value rate cannot see: the fabricated rows *were* the reason
  the rate read 0.00%.

* **Missingness that is reported rather than hidden.** The same four columns now
  carry a non-zero missing rate on a panel with a suspension in it. This is the
  price of the fix and it is asserted, not assumed, so that a future change
  which quietly starts filling those rows again has to argue with a red test.

The panel is synthetic and deliberately carries a four-session halt per symbol.
Real suspensions are what make the difference visible, and a fixture without one
would let every assertion here pass under code that only works on clean data.

**One defect of the three is invisible from here, and saying so is the point.**
Reversing ``quesval2``'s comparison was measured in isolation against this same
code: eleven of the 82 columns change value — alpha7, 21, 23, 61, 74, 75, 81,
86, 92, 95, 99, exactly the eleven that route through it — and **not one of them
changes its magnitude, its missing rate, its distinct count or its flat-group
fraction.** A factor with the wrong sign is still a well-behaved column. Nothing
a column-level screen can measure will ever catch it, so the guard against it
has to be the direct operator test in ``test_quesval2_direction.py``, and adding
a column-level assertion here that happened to go red would only be measuring
some other defect wearing its name.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import polars as pl

from vnpy.alpha.dataset.datasets.alpha_101 import Alpha101
from vnpy.alpha.dataset.utility import calculate_by_expression
from vnpy.alpha.semantics import FLAT_GROUP_LIMIT, FeatureHealth, measure_feature


NAN: float = float("nan")
NDAYS: int = 320

# alpha78 / alpha85 are `cs_rank(...) ** cs_rank(...)`; alpha94 is
# `cs_rank(...) ** ts_rank(...)`; alpha84 is `pow2` over a ts_rank base. All four
# have a real range inside (0, 1] on the rank side, which is what makes both an
# exact 0 and a value above 1 impossible without a defect.
POW2_COLUMNS: tuple[str, ...] = ("alpha78", "alpha84", "alpha85", "alpha94")


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

def build_panel(n_symbols: int) -> pl.DataFrame:
    """Build a bar frame shaped like `load_bar_df`, one four-day halt per symbol.

    Seeded per symbol index rather than once for the whole frame, so widening
    the cross section adds symbols instead of redrawing the existing ones —
    otherwise the two widths in the universe-size test would differ in their
    data as well as their width, and the comparison would prove nothing.
    """
    dates: list[datetime] = [datetime(2023, 1, 2) + timedelta(days=i) for i in range(NDAYS)]
    rows: dict[str, list] = {key: [] for key in
                             ("datetime", "vt_symbol", "open", "high", "low",
                              "close", "volume", "turnover", "vwap")}

    for index in range(n_symbols):
        rng: np.random.Generator = np.random.default_rng(4101 + index)
        close: np.ndarray = np.abs(1.0 + np.cumsum(rng.normal(0, 0.012, NDAYS))) + 0.5
        # A flat run, so the ordering comparisons see exact ties as well.
        close[40:46] = close[40]
        open_: np.ndarray = close * (1 + rng.normal(0, 0.002, NDAYS))
        high: np.ndarray = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, NDAYS)))
        low: np.ndarray = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, NDAYS)))
        volume: np.ndarray = rng.integers(1_000, 200_000, NDAYS).astype(float)
        vwap: np.ndarray = (open_ + high + low + close) / 4 * (1 + rng.normal(0, 0.001, NDAYS))

        columns: dict[str, np.ndarray] = {
            "open": open_, "high": high, "low": low, "close": close,
            "volume": volume, "turnover": volume * vwap, "vwap": vwap,
        }
        for day in range(150 + index * 3, 150 + index * 3 + 4):
            for series in columns.values():
                series[day] = NAN

        rows["datetime"] += dates
        rows["vt_symbol"] += [f"S{index:02d}.SEHK"] * NDAYS
        for name, series in columns.items():
            rows[name] += list(series)

    return pl.DataFrame(rows)


def compute(frame: pl.DataFrame, name: str) -> np.ndarray:
    """Evaluate one Alpha101 expression over a panel."""
    dataset: Alpha101 = Alpha101(
        frame,
        ("2023-01-01", "2023-06-01"),
        ("2023-06-01", "2023-09-01"),
        ("2023-09-01", "2027-01-01"),
    )
    result: pl.DataFrame = calculate_by_expression(frame, dataset.feature_expressions[name])

    return result["data"].to_numpy().astype(float)


# ---------------------------------------------------------------------------
# The bound must not follow the size of the universe
# ---------------------------------------------------------------------------

def test_rank_over_rank_columns_are_bounded_the_same_on_any_cross_section_width() -> None:
    # The ordinal cs_rank gave `N ** N`: measured 8.92e+12 on twelve symbols and
    # 1.05e+26 on twenty, for alpha78 and alpha85 alike. Asserting one threshold
    # would have been satisfied by an ordinal on a small enough panel; asserting
    # that the ceiling is the same at two widths cannot be.
    narrow: pl.DataFrame = build_panel(12)
    wide: pl.DataFrame = build_panel(20)

    for name in ("alpha78", "alpha85"):
        for frame in (narrow, wide):
            values: np.ndarray = compute(frame, name)
            finite: np.ndarray = values[np.isfinite(values)]

            assert finite.size, name
            assert finite.max() <= 1.0, (name, frame["vt_symbol"].n_unique())
            assert finite.min() > 0.0, (name, frame["vt_symbol"].n_unique())


def test_alpha1_stays_inside_the_half_interval_its_own_formula_subtracts() -> None:
    # alpha1 ends in `cs_rank(...) - 0.5`, a constant that only means anything
    # against a rank in (0, 1]. With the ordinal it reached 11.5 on twelve
    # symbols — the formula's own arithmetic saying the input was wrong.
    values: np.ndarray = compute(build_panel(12), "alpha1")
    finite: np.ndarray = values[np.isfinite(values)]

    assert finite.size
    assert np.abs(finite).max() <= 0.5


# ---------------------------------------------------------------------------
# Undefined must stay visible
# ---------------------------------------------------------------------------

def test_the_power_columns_hold_no_exact_zero_and_admit_their_missing_rows() -> None:
    # Two halves of one statement, and they have to be asserted together: a
    # column with no zeros could have got there by filling them with something
    # else, and a column with a missing rate could have got there by breaking.
    #
    # Measured on this panel before the fix: alpha78 held 397 exact zeros and
    # reported 0.00% missing, alpha84 held 696, alpha85 130, alpha94 751. Every
    # one of those was an undefined row wearing a number.
    frame: pl.DataFrame = build_panel(12)

    for name in POW2_COLUMNS:
        values: np.ndarray = compute(frame, name)
        finite: np.ndarray = values[np.isfinite(values)]

        assert finite.size, name
        assert not (finite == 0.0).any(), name
        assert (~np.isfinite(values)).any(), name


def test_the_comparison_columns_are_not_degenerate_by_the_shipped_health_screen() -> None:
    # alpha27 / alpha86 / alpha95 each compare a `cs_rank` against something
    # bounded in [0, 1]. An ordinal rank runs to the size of the universe, so
    # the comparison lands the same way on nearly every date and the column
    # stops ranking anything — which is what `flat_group_fraction` measures.
    #
    # Reusing FLAT_GROUP_LIMIT rather than a threshold invented here, so the
    # screen `semantics.py` publishes is load-bearing instead of decorative.
    # Measured on this panel: with the ordinal rank the three read 0.881 / 0.734
    # / 1.000 flat — alpha95 collapses to a single value across the whole frame
    # — against 0.003 / 0.172 / 0.147 now.
    frame: pl.DataFrame = build_panel(12)

    for name in ("alpha27", "alpha86", "alpha95"):
        values: np.ndarray = compute(frame, name)
        column: pl.DataFrame = pl.DataFrame({"datetime": frame["datetime"], name: values})
        health: FeatureHealth = measure_feature(column, name, "datetime")

        assert health.n_unique > 1, name
        assert health.flat_group_fraction < FLAT_GROUP_LIMIT, health.describe()


# ---------------------------------------------------------------------------
# What the fix costs, written down so it cannot drift back
# ---------------------------------------------------------------------------

def test_a_halt_inside_a_250_day_window_blanks_alpha19_instead_of_ranking_the_gap() -> None:
    # This is the price and it is a large one. alpha19 contains
    # `ts_sum(returns, 250)`, so one suspended session poisons 250 windows; the
    # ordinal cs_rank used to hide that by handing the NaN the top rank, which
    # is why the column looked healthy while being partly invented.
    #
    # Measured: on a suspension-free panel alpha19's missing rate is exactly the
    # warm-up floor 250/N — 83.3% at 300 days, 31.2% at 800 — identical before
    # and after the fix. With one four-day halt per symbol on a 320-day panel it
    # is total, because every window reaches a halt. The honest reading is that
    # Alpha101's long-window columns need a suspension-free panel, not that the
    # guard broke them.
    values: np.ndarray = compute(build_panel(12), "alpha19")

    assert not np.isfinite(values).any()
