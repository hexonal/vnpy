"""
Cross Section Operators
===================================

* **``cs_rank`` answers a fraction in ``(0, 1]``, not an ordinal position.**
  Kakushadze (2016) writes only "rank(x) = cross-sectional rank" in Appendix
  A.1 and never says what it is divided by, so the definition has to be read off
  the formulas that consume it — and they settle it three separate times.
  Alpha#1 ends in ``rank(...) - 0.5``, Alpha#27 branches on ``0.5 < rank(...)``,
  and Alpha#19 / Alpha#39 add ``1 + rank(...)``: every one of those constants is
  meaningless against an ordinal that runs to the size of the universe. Alpha#85
  and Alpha#94 settle it a fourth way, by raising one rank to the power of
  another — bounded in ``(0, 1]`` that is an ordinary number, ordinal it is
  ``N**N``.

* **What the ordinal actually cost, measured.** On the fifty-symbol panel in
  ``tests/test_alpha101.py``, ``alpha85`` reached ``8.88e+84`` and ``alpha78``
  ``1.26e+84`` — ``50**50`` to the digit, not an overflow bug anywhere in
  ``pow2``. On the ten-symbol ``hk_bluechip_10`` lab the same two columns peak
  at ``1e+10`` (``10**10``), which is the same defect wearing the universe's
  size as a costume. ``alpha86`` was worse than large: its comparison against a
  ``ts_rank`` in ``[0, 1]`` could never be true, so the column was the constant
  ``0`` on all 7350 rows.

* **The scale was not merely wrong, it was date-dependent.** An ordinal rank's
  ceiling is however many symbols happen to have a value that day, so on a panel
  with listings, delistings or warm-up gaps the same relative position reads as
  a different number from one date to the next. That is the property the
  ``- 0.5`` and ``0.5 <`` constants above were written to rely on being absent.

* **Non-finite input is excluded from the ranking rather than ranked.** Polars
  sorts NaN above every real number, so an unmasked ``rank()`` handed a
  suspended day or a warm-up NaN awards it the *top* rank in the cross section.
  Masking to null first also fixes the denominator: dividing by the count of
  real values keeps the best real symbol at exactly 1.0 whether two symbols are
  missing that day or none, which is the whole point of leaving the ordinal
  behind.

* **``.cast(pl.Float64)`` before the mask, because ``is_not_nan`` is the only
  part that needs it.** ``cs_rank`` is routinely handed Int32 — every
  ``DataProxy`` comparison and every ``quesval`` / ``sign`` branch produces one
  (see ``ts_function``'s module docstring for why). Polars raises
  ``InvalidOperationError`` on ``is_not_nan`` for integer dtypes, and an integer
  can never be NaN anyway, so the cast is what makes one code path serve both.

* **The other four operators here are left alone.** ``cs_mean`` / ``cs_std`` /
  ``cs_sum`` do not skip NaN — one suspended symbol turns the whole date's
  answer into NaN for every symbol, and ``cs_scale`` inherits it through
  ``cs_sum``. That is real and measured (``alpha28`` is NaN on its first date
  for all ten symbols) but it is a separate change with a separate blast radius,
  and unlike the ranking it is a fail-*closed* failure: it produces NaN, not a
  plausible wrong number.
"""

import polars as pl

from .utility import DataProxy


def cs_rank(feature: DataProxy) -> DataProxy:
    """Perform cross-sectional ranking, as a fraction of the cross section"""
    value: pl.Expr = pl.col("data").cast(pl.Float64)
    finite: pl.Expr = pl.when(value.is_not_null() & value.is_not_nan()).then(value)

    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        (finite.rank().over("datetime") / finite.count().over("datetime")).alias("data")
    )
    return DataProxy(df)


def cs_mean(feature: DataProxy) -> DataProxy:
    """Calculate cross-sectional mean"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").mean().over("datetime")
    )
    return DataProxy(df)


def cs_std(feature: DataProxy) -> DataProxy:
    """Calculate cross-sectional standard deviation"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").std().over("datetime")
    )
    return DataProxy(df)


def cs_sum(feature: DataProxy) -> DataProxy:
    """Calculate cross-sectional sum"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").sum().over("datetime")
    )
    return DataProxy(df)


def cs_scale(feature: DataProxy) -> DataProxy:
    """Scale the feature by the sum of absolute values in the cross section"""
    abs_feature = abs(feature)
    sum_abs = cs_sum(abs_feature)

    df_merged: pl.DataFrame = feature.df.join(sum_abs.df, on=["datetime", "vt_symbol"], suffix="_sum")

    df: pl.DataFrame = df_merged.with_columns(
        pl.when(pl.col("data_sum") != 0)
        .then(pl.col("data") / pl.col("data_sum"))
        .otherwise(0)
        .alias("data")
    ).select(["datetime", "vt_symbol", "data"])

    return DataProxy(df)
