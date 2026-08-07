"""
Time Series Operators
=====================

* **Every ``rolling_map`` input is cast to Float64 first — except where an
  integer answer is the definition.** Polars pushes whatever the Python
  callable returns back through the *input* column's dtype, so an Int32 input
  makes ``ts_mean`` truncate its own average toward zero. Measured on polars
  1.43.0, input ``[1, 0, 1, 1, 0, 1, 0, 0]`` with ``window=5``: ``ts_mean``
  answered ``[1, 0, 0, 0, 0, 0, 0, 0]`` where the arithmetic says
  ``[1.0, 0.5, 0.667, 0.75, 0.6, 0.6, 0.6, 0.4]``, and ``ts_std`` answered all
  zeros. No warning, no dtype change the caller could notice — the column just
  quietly became a "were ALL of the last w days up days" indicator, because 1.0
  is the only mean that survives truncation.

* **Integer inputs are routine, not exotic.** ``DataProxy`` comparisons cast to
  Int32 deliberately (``rolling_map`` refuses Boolean outright with
  ``InvalidOperationError``), which is how Alpha158's fifteen ``cnt*`` features
  arrive; and ``quesval`` / ``quesval2`` / ``sign`` build ``pl.lit(1)`` /
  ``pl.lit(0)`` branches that are Int32 too and never pass through the
  comparison helper at all, which is how Alpha101's ``alpha92`` arrives.

* **Why the cast lives here rather than at the producers.** The set of integer
  producers is a list somebody has to keep complete — and the first attempt at
  enumerating it already missed the ``quesval`` branch. "A mean is a real
  number" needs no enumeration and holds for producers that do not exist yet.
  The cost is a wider merge surface against upstream, which is rewriting this
  file: a textual conflict is loud, a silently re-introduced truncation is not.

* **The three operators left un-cast** — ``ts_argmax``, ``ts_argmin``,
  ``ts_product`` — return integers by definition when fed integers, so the
  round trip loses nothing. ``rolling_map`` itself has no ``return_dtype``
  parameter in polars 1.43.0 (passing one raises ``TypeError``), which is why
  the input is retyped rather than the output.
"""

from typing import cast

from scipy import stats
import polars as pl
import numpy as np

from .utility import DataProxy


def ts_delay(feature: DataProxy, window: int) -> DataProxy:
    """Get the value from a fixed time in the past"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").shift(window).over("vt_symbol")
    )
    return DataProxy(df)


def ts_min(feature: DataProxy, window: int) -> DataProxy:
    """Calculate the minimum value over a rolling window"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").rolling_min(window, min_samples=1).over("vt_symbol")
    )
    return DataProxy(df)


def ts_max(feature: DataProxy, window: int) -> DataProxy:
    """Calculate the maximum value over a rolling window"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").rolling_max(window, min_samples=1).over("vt_symbol")
    )
    return DataProxy(df)


def ts_argmax(feature: DataProxy, window: int) -> DataProxy:
    """Return the index of the maximum value over a rolling window"""
    # No Float64 cast here or in ts_argmin: a position within the window is a
    # whole number whatever the values are, so dtype round-tripping is exact.
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").rolling_map(lambda s: cast(int, s.arg_max()) + 1, window).over("vt_symbol")
    )
    return DataProxy(df)


def ts_argmin(feature: DataProxy, window: int) -> DataProxy:
    """Return the index of the minimum value over a rolling window"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").rolling_map(lambda s: cast(int, s.arg_min()) + 1, window).over("vt_symbol")
    )
    return DataProxy(df)


def ts_rank(feature: DataProxy, window: int) -> DataProxy:
    """Calculate the percentile rank of the current value within the window"""
    # Float64 in — a percentile is a fraction (see the module docstring).
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").cast(pl.Float64).rolling_map(lambda s: stats.percentileofscore(s, s[-1]) / 100, window).over("vt_symbol")
    )
    return DataProxy(df)


def ts_sum(feature: DataProxy, window: int) -> DataProxy:
    """Calculate the sum over a rolling window"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").rolling_sum(window).over("vt_symbol")
    )
    return DataProxy(df)


def ts_mean(feature: DataProxy, window: int) -> DataProxy:
    """Calculate the mean over a rolling window"""
    # Float64 in — the mean of 0/1 flags is a fraction (see the module docstring).
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").cast(pl.Float64).rolling_map(lambda s: np.nanmean(s), window, min_samples=1).over("vt_symbol")
    )
    return DataProxy(df)


def ts_std(feature: DataProxy, window: int) -> DataProxy:
    """Calculate the standard deviation over a rolling window"""
    # Float64 in — without it an integer input reports zero dispersion always.
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").cast(pl.Float64).rolling_map(lambda s: np.nanstd(s, ddof=0), window, min_samples=1).over("vt_symbol")
    )
    return DataProxy(df)


def ts_slope(feature: DataProxy, window: int) -> DataProxy:
    """Calculate the slope of linear regression over a rolling window (optimized)"""
    # 预计算 x 相关的常数 (x = 0, 1, 2, ..., window-1)
    n = window
    sum_x = n * (n - 1) / 2  # 等差数列求和
    sum_x2 = (n - 1) * n * (2 * n - 1) / 6  # 平方和公式
    denominator = n * sum_x2 - sum_x * sum_x

    # 计算 sum(i * y[t-window+1+i]) for i in 0..window-1
    # 等价于 sum((window-1-j) * y[t-j]) for j in 0..window-1
    sum_xy_expr: pl.Expr = pl.sum_horizontal([
        (window - 1 - j) * pl.col("data").shift(j)
        for j in range(window)
    ])

    df: pl.DataFrame = feature.df.with_columns([
        pl.col("data").rolling_sum(window, min_samples=window).over("vt_symbol").alias("sum_y"),
        sum_xy_expr.over("vt_symbol").alias("sum_xy")
    ])

    df = df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        ((n * pl.col("sum_xy") - sum_x * pl.col("sum_y")) / denominator).alias("data")
    )
    return DataProxy(df)


def ts_quantile(feature: DataProxy, window: int, quantile: float) -> DataProxy:
    """Calculate the quantile value over a rolling window"""
    # Float64 in — linear interpolation lands between the samples by design.
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").cast(pl.Float64).rolling_map(lambda s: s.quantile(quantile=quantile, interpolation="linear"), window).over("vt_symbol")
    )
    return DataProxy(df)


def ts_rsquare(feature: DataProxy, window: int) -> DataProxy:
    """Calculate the R-squared value of linear regression over a rolling window (optimized)"""
    # 预计算 x 相关的常数 (x = 0, 1, 2, ..., window-1)
    n = window
    sum_x2 = (n - 1) * n * (2 * n - 1) / 6  # 平方和公式
    mean_x = (n - 1) / 2
    var_x = sum_x2 / n - mean_x * mean_x  # 总体方差

    # 计算 sum(i * y[t-window+1+i]) for i in 0..window-1
    sum_xy_expr: pl.Expr = pl.sum_horizontal([
        (window - 1 - j) * pl.col("data").shift(j)
        for j in range(window)
    ])

    df: pl.DataFrame = feature.df.with_columns([
        pl.col("data").rolling_sum(window, min_samples=window).over("vt_symbol").alias("sum_y"),
        pl.col("data").rolling_var(window, min_samples=window, ddof=0).over("vt_symbol").alias("var_y"),
        sum_xy_expr.over("vt_symbol").alias("sum_xy")
    ])

    # mean_y 和 cov(x, y) = E(xy) - E(x)E(y)
    df = df.with_columns([
        (pl.col("sum_y") / n).alias("mean_y"),
    ])

    df = df.with_columns([
        (pl.col("sum_xy") / n - mean_x * pl.col("mean_y")).alias("cov_xy")
    ])

    # r = cov(x,y) / (std_x * std_y), r^2 = cov(x,y)^2 / (var_x * var_y)
    df = df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        (pl.col("cov_xy").pow(2) / (var_x * pl.col("var_y"))).alias("data")
    )

    df = df.with_columns(
        pl.when(pl.col("data").is_infinite() | pl.col("data").is_nan())
        .then(None)
        .otherwise(pl.col("data"))
        .alias("data")
    )

    return DataProxy(df)


def ts_resi(feature: DataProxy, window: int) -> DataProxy:
    """Calculate the residual of linear regression over a rolling window (optimized)"""
    # 预计算 x 相关的常数 (x = 0, 1, 2, ..., window-1)
    n = window
    sum_x = n * (n - 1) / 2  # 等差数列求和
    sum_x2 = (n - 1) * n * (2 * n - 1) / 6  # 平方和公式
    mean_x = (n - 1) / 2
    denominator = n * sum_x2 - sum_x * sum_x

    # 计算 sum(i * y[t-window+1+i]) for i in 0..window-1
    sum_xy_expr: pl.Expr = pl.sum_horizontal([
        (window - 1 - j) * pl.col("data").shift(j)
        for j in range(window)
    ])

    df: pl.DataFrame = feature.df.with_columns([
        pl.col("data").rolling_sum(window, min_samples=window).over("vt_symbol").alias("sum_y"),
        sum_xy_expr.over("vt_symbol").alias("sum_xy")
    ])

    # 计算 slope 和 intercept
    df = df.with_columns([
        ((n * pl.col("sum_xy") - sum_x * pl.col("sum_y")) / denominator).alias("slope"),
        (pl.col("sum_y") / n).alias("mean_y"),
    ])

    df = df.with_columns([
        (pl.col("mean_y") - pl.col("slope") * mean_x).alias("intercept")
    ])

    # residual = y - (slope * (n-1) + intercept)，最后一个点的 x = n-1
    df = df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        (pl.col("data") - (pl.col("slope") * (n - 1) + pl.col("intercept"))).alias("data")
    )

    return DataProxy(df)


def ts_corr(feature1: DataProxy, feature2: DataProxy, window: int) -> DataProxy:
    """Calculate the correlation between two features over a rolling window"""
    df_merged: pl.DataFrame = feature1.df.join(feature2.df, on=["datetime", "vt_symbol"], maintain_order="left")

    df: pl.DataFrame = df_merged.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.rolling_corr("data", "data_right", window_size=window, min_samples=1).over("vt_symbol").alias("data")
    )

    df = df.with_columns(
        pl.when(pl.col("data").is_infinite()).then(None).otherwise(pl.col("data")).alias("data")
    )

    return DataProxy(df)


def ts_less(feature1: DataProxy, feature2: DataProxy | float) -> DataProxy:
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


def ts_greater(feature1: DataProxy, feature2: DataProxy | float) -> DataProxy:
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


def ts_log(feature: DataProxy) -> DataProxy:
    """Calculate the natural logarithm of the feature"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").log().over("vt_symbol")
    )
    return DataProxy(df)


def ts_abs(feature: DataProxy) -> DataProxy:
    """Calculate the absolute value of the feature"""
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").abs().over("vt_symbol")
    )
    return DataProxy(df)


def ts_delta(feature: DataProxy, window: int) -> DataProxy:
    """Calculate difference between current value and value from window periods ago"""
    return feature - ts_delay(feature, window)


def ts_cov(feature1: DataProxy, feature2: DataProxy, window: int) -> DataProxy:
    """Calculate covariance between two features over a rolling window"""
    return ts_corr(feature1, feature2, window) * ts_std(feature1, window) * ts_std(feature2, window)


def ts_decay_linear(feature: DataProxy, window: int) -> DataProxy:
    """Calculate linear decay weighted average"""
    def decay_func(s: pl.Series) -> float:
        """Calculate linear decay weighted average for a series"""
        weights = pl.Series(range(window, 0, -1))
        denominator: int = window * (window + 1) // 2
        return float((s * weights).sum() / denominator)

    # Float64 in — a weighted average divided by window*(window+1)/2 is a
    # fraction; alpha92 reaches this operator carrying quesval2's Int32 flags.
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").cast(pl.Float64).rolling_map(lambda s: decay_func(s), window).over("vt_symbol")
    )
    return DataProxy(df)


def ts_product(feature: DataProxy, window: int) -> DataProxy:
    """Calculate the product over a rolling window"""
    # No Float64 cast: a product of integers is an integer, so the round trip
    # is exact — and casting would trade that exactness for float rounding.
    df: pl.DataFrame = feature.df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        pl.col("data").rolling_map(lambda s: s.product(), window).over("vt_symbol")
    )
    return DataProxy(df)
