"""
Technical Analysis Operators
"""

import talib
import polars as pl
import pandas as pd

from .utility import DataProxy


def to_pd_series(feature: DataProxy) -> pd.Series:
    """Convert to pandas.Series data structure"""
    series: pd.Series = feature.df.to_pandas().set_index(["datetime", "vt_symbol"])["data"]
    return series


def to_pl_dataframe(series: pd.Series) -> pl.DataFrame:
    """Convert to polars.DataFrame data structure"""
    df: pl.DataFrame = pl.from_pandas(series.reset_index().rename(columns={0: "data"}))
    return df


def ta_rsi(close: DataProxy, window: int) -> DataProxy:
    """Calculate RSI indicator by contract.

    Grouped per vt_symbol — TA-Lib functions are single-series rolling
    computations; running them over the whole concatenated multi-symbol
    panel (as this previously did) blends the tail of one symbol into the
    head of the next at every symbol boundary, corrupting the first
    window-1 rows of every symbol after the first. Every other operator
    in this package (ts_function/cs_function) already isolates per symbol
    via .over("vt_symbol"); TA-Lib can't be driven by a polars window
    expression, so the isolation here is an explicit per-group map.
    """
    close_: pd.Series = to_pd_series(close)

    result: pd.Series = close_.groupby(level="vt_symbol", sort=False).transform(
        lambda s: talib.RSI(s, timeperiod=window)   # type: ignore
    )

    df: pl.DataFrame = to_pl_dataframe(result)
    return DataProxy(df)


def ta_atr(high: DataProxy, low: DataProxy, close: DataProxy, window: int) -> DataProxy:
    """Calculate ATR indicator by contract (per-symbol — see ta_rsi)."""
    high_: pd.Series = to_pd_series(high)
    low_: pd.Series = to_pd_series(low)
    close_: pd.Series = to_pd_series(close)

    parts: list[pd.Series] = []
    for symbol in close_.index.get_level_values("vt_symbol").unique():
        h = high_.xs(symbol, level="vt_symbol", drop_level=False)
        low_s = low_.xs(symbol, level="vt_symbol", drop_level=False)
        c = close_.xs(symbol, level="vt_symbol", drop_level=False)
        atr_values = talib.ATR(
            h.droplevel("vt_symbol").to_numpy(),
            low_s.droplevel("vt_symbol").to_numpy(),
            c.droplevel("vt_symbol").to_numpy(),
            timeperiod=window,
        )
        atr = pd.Series(atr_values, index=c.index)
        parts.append(atr)

    result: pd.Series = pd.concat(parts).reindex(close_.index)

    df: pl.DataFrame = to_pl_dataframe(result)
    return DataProxy(df)
