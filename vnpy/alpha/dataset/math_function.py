"""
Math Functions
"""

import polars as pl

from .utility import DataProxy


def less(feature1: DataProxy, feature2: DataProxy | float) -> DataProxy:
    """Return the minimum value between two features"""
    if isinstance(feature2, DataProxy):
        df_merged: pl.DataFrame = feature1.df.join(feature2.df, on=["datetime", "vt_symbol"], maintain_order="left")
    else:
        df_merged = feature1.df.with_columns(pl.lit(feature2).alias("data_right"))

    df: pl.DataFrame = df_merged.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.min_horizontal("data", "data_right").over("vt_symbol").alias("data")
    )

    return DataProxy(df)


def greater(feature1: DataProxy, feature2: DataProxy | float) -> DataProxy:
    """Return the maximum value between two features"""
    if isinstance(feature2, DataProxy):
        df_merged: pl.DataFrame = feature1.df.join(feature2.df, on=["datetime", "vt_symbol"], maintain_order="left")

    else:
        df_merged = feature1.df.with_columns(pl.lit(feature2).alias("data_right"))

    df: pl.DataFrame = df_merged.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.max_horizontal("data", "data_right").over("vt_symbol").alias("data")
    )

    return DataProxy(df)


def log(feature: DataProxy) -> DataProxy:
    """Calculate the natural logarithm of the feature"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").log().over("vt_symbol")
    )
    return DataProxy(df)


def abs(feature: DataProxy) -> DataProxy:
    """Calculate the absolute value of the feature"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").abs().over("vt_symbol")
    )
    return DataProxy(df)


def sign(feature: DataProxy) -> DataProxy:
    """Calculate the sign of the feature"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.when(pl.col("data") > 0).then(1).when(pl.col("data") < 0).then(-1).otherwise(0).alias("data")
    )
    return DataProxy(df)


def quesval(threshold: float, feature1: DataProxy, feature2: DataProxy | float | int, feature3: DataProxy | float | int) -> DataProxy:
    """Return feature2 if threshold < feature1, otherwise feature3"""
    df_merged = feature1.df

    if isinstance(feature2, DataProxy):
        df_merged = df_merged.join(feature2.df, on=["datetime", "vt_symbol"], maintain_order="left", suffix="_true")
    else:
        df_merged = df_merged.with_columns(pl.lit(feature2).alias("data_true"))

    if isinstance(feature3, DataProxy):
        df_merged = df_merged.join(feature3.df, on=["datetime", "vt_symbol"], maintain_order="left", suffix="_false")
    else:
        df_merged = df_merged.with_columns(pl.lit(feature3).alias("data_false"))

    df: pl.DataFrame = df_merged.with_columns(
        pl.when(threshold < pl.col("data"))
        .then(pl.col("data_true"))
        .otherwise(pl.col("data_false"))
        .alias("data")
    ).select(["datetime", "vt_symbol", "data"])

    return DataProxy(df)


def quesval2(threshold: DataProxy, feature1: DataProxy, feature2: DataProxy | float | int, feature3: DataProxy | float | int) -> DataProxy:
    """Return feature2 if threshold < feature1, otherwise feature3 (DataProxy threshold version)

    The rename before the join is load-bearing, not cosmetic. Written as
    ``threshold.df.join(feature1.df, suffix="_cond")`` — which is what this
    function used to say — polars suffixes the *right* frame, so ``data_cond``
    held ``feature1`` and the bare ``data`` held ``threshold``; the comparison
    below then read ``feature1 < threshold`` and every caller got the negation
    of what it asked for. Measured: ``quesval2(0, 1, 1, 0)`` answered 0.

    All eleven Alpha101 expressions that route through here — alpha7, 21, 23,
    61, 74, 75, 81, 86, 92, 95, 99 — transcribe a ``(a < b) ? x : y`` from
    Kakushadze (2016) with ``a`` as ``threshold``, so all eleven were inverted.
    ``alpha86`` is the one that showed: with ``a`` a ``ts_rank`` in ``[0, 1]``
    and ``b`` a ``cs_rank``, the reversed test could never fire and the column
    came out the constant 0 on all 7350 rows of ``hk_bluechip_10``. The other
    ten stayed plausible-looking, which is why this survived — a factor with the
    wrong sign still has variance, still has a rank IC, and still trains.

    Naming the column instead of relying on which side of a join collects the
    suffix is the actual repair: the sibling ``quesval`` never had the bug
    because its threshold is a scalar and no join was involved.
    """
    df_merged: pl.DataFrame = threshold.df.rename({"data": "data_cond"}).join(
        feature1.df, on=["datetime", "vt_symbol"], maintain_order="left"
    )

    if isinstance(feature2, DataProxy):
        df_merged = df_merged.join(feature2.df, on=["datetime", "vt_symbol"], maintain_order="left", suffix="_true")
    else:
        df_merged = df_merged.with_columns(pl.lit(feature2).alias("data_true"))

    if isinstance(feature3, DataProxy):
        df_merged = df_merged.join(feature3.df, on=["datetime", "vt_symbol"], maintain_order="left", suffix="_false")
    else:
        df_merged = df_merged.with_columns(pl.lit(feature3).alias("data_false"))

    df: pl.DataFrame = df_merged.with_columns(
        pl.when(pl.col("data_cond") < pl.col("data"))
        .then(pl.col("data_true"))
        .otherwise(pl.col("data_false"))
        .alias("data")
    ).select(["datetime", "vt_symbol", "data"])

    return DataProxy(df)


def pow1(base: DataProxy, exponent: float) -> DataProxy:
    """Safe power operation for DataProxy (handles negative base values)

    handle logic:
    - base > 0: calculate base^exponent
    - base < 0: calculate -1 * |base|^exponent
    - base = 0 with a positive exponent: 0, which is the arithmetic answer
    - anything else (undefined, or the base missing): null, never a number

    This used to end in ``.otherwise(0)``, which is the same fail-open that
    ``pow2`` was carrying and was fixed one function down — the difference is
    only in how it is reached. A null base does not satisfy ``> 0`` or ``< 0``
    in polars (a comparison against null is null, not false), so it fell into
    the ``otherwise`` and came back as a real 0.

    **The reason this cannot wait for its own round: the cross-section fix put
    the nulls there.** Now that ``cs_rank`` excludes non-finite input from the
    ranking instead of awarding it the top rank, a suspended symbol gets a null
    rank — and alpha71, alpha81 and alpha95 are all shaped ``pow1(cs_rank(...),
    k)``. Measured on a four-symbol cross section with one NaN in it,
    ``cs_rank`` answers ``[0.333, null, 0.667, 1.0]`` and the old ``pow1``
    turned that into ``[0.111, 0.0, 0.444, 1.0]``. The 0 is not a middle value
    for these three expressions any more than it was for ``pow2``'s four: their
    range is ``(0, 1]``, so the invented number sits below every legitimate one
    and reads to a model as the strongest observation in the column. Leaving it
    would have moved the fabrication one hop downstream rather than removing it.

    The exponent is a Python float rather than a column, so ``0 ** exponent`` is
    settled once here instead of per row. All eight call sites pass a literal.
    """
    # Zero base: 0**k is 0 for k > 0 and undefined otherwise (0**0 and 0**-1
    # both). alpha47's `pow1(close, -1)` is the only call site with a negative
    # exponent, and a normalized close is never 0 — so this branch is a
    # statement of arithmetic rather than a hot path.
    zero_answer: pl.Expr = pl.lit(0.0) if exponent > 0 else pl.lit(None, dtype=pl.Float64)

    df: pl.DataFrame = base.df.with_columns(
        pl.when(pl.col("data") > 0)
        .then(pl.col("data").pow(exponent))
        .when(pl.col("data") < 0)
        .then(pl.lit(-1) * pl.col("data").abs().pow(exponent))
        .when(pl.col("data") == 0)
        .then(zero_answer)
        .otherwise(pl.lit(None, dtype=pl.Float64))
        .alias("data")
    )

    return DataProxy(df)


def pow2(base: DataProxy, exponent: DataProxy) -> DataProxy:
    """Power operation between two DataProxy objects (base^exponent)

    handle logic:
    - base > 0: calculate base^exponent
    - base < 0 and exponent is integer: calculate -1 * |base|^exponent
    - base = 0 with a positive exponent: 0, which is the arithmetic answer
    - anything else (undefined, or either side missing): NaN, never a number

    Note: use floor method to check integer rather than cast(Int64) method, because NaN cannot be converted to integer will report an error

    The trailing ``.fill_nan(None).fill_null(0)`` this function used to end with
    was the most expensive line in the file. It did not repair anything — it
    renamed "undefined" to "0" and handed it downstream as data. Measured on
    ``hk_bluechip_10``: ``alpha78``'s exponent is NaN on 73.76% of rows (its
    inner ``ts_corr`` of two rank series has no defined value on a window where
    either series is constant), so **75.32% of that column was a manufactured
    zero while the column reported a 0.00% NaN rate**. The other three call
    sites fabricated 2.72% / 3.12% / 7.14% the same way.

    Zero is the worst possible stand-in for these four expressions specifically.
    All of them are ``rank(...)^rank(...)`` or ``rank(...)^ts_rank(...)``, whose
    real values live in ``(0, 1]`` — so the invented value is not a neutral
    middle, it sits below the entire legitimate range and reads to any model as
    the most extreme observation in the column. A NaN would have been dropped or
    imputed by ``process_drop_na`` / ``process_cs_fill_na``; a 0 is trained on.
    """
    base_renamed = base.df.rename({"data": "base_data"})
    exp_renamed = exponent.df.rename({"data": "exp_data"})

    df_merged: pl.DataFrame = base_renamed.join(exp_renamed, on=["datetime", "vt_symbol"], maintain_order="left", how="left")

    df: pl.DataFrame = df_merged.with_columns(
        pl.when(pl.col("base_data") > 0)
        .then(pl.col("base_data").pow(pl.col("exp_data")))
        .when(
            (pl.col("base_data") < 0) &
            (~pl.col("exp_data").is_nan()) &
            (pl.col("exp_data").floor() == pl.col("exp_data"))
        )
        .then((-1) * pl.col("base_data").abs().pow(pl.col("exp_data")))
        .when(
            (pl.col("base_data") == 0) &
            (~pl.col("exp_data").is_nan()) &
            (pl.col("exp_data") > 0)
        )
        .then(pl.lit(0.0))
        .otherwise(pl.lit(None))
        .alias("data")
    ).select(["datetime", "vt_symbol", "data"])

    return DataProxy(df)


