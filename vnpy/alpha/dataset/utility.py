from datetime import datetime
from enum import Enum
from numbers import Real
from typing import Union, cast
from collections.abc import Callable

import polars as pl


EXPRESSION_FUNCTIONS: dict[str, Callable] = {}


def register_functions(functions: list[Callable]) -> None:
    """Register custom expression functions by function name."""
    for func in functions:
        EXPRESSION_FUNCTIONS[func.__name__] = func


class DataProxy:
    """Feature data proxy"""

    def __init__(self, df: pl.DataFrame) -> None:
        """Constructor"""
        self.name: str = df.columns[-1]
        self.df: pl.DataFrame = df.rename({self.name: "data"})

        # Note that for numerical expressions, variables should be placed before numbers. e.g. a * 2
    @staticmethod
    def _as_series(value: object) -> pl.Series:
        """Normalize an operator result to a Polars series."""
        if isinstance(value, pl.Series):
            return value

        return cast(pl.Series, value)

    def _comparison_series(self, value: object) -> pl.Series:
        """Normalize comparison results to an Int32 series."""
        if isinstance(value, pl.Series):
            return value.cast(pl.Int32)

        if isinstance(value, bool):
            return pl.Series(name="data", values=[int(value)] * len(self.df))

        if isinstance(value, Real):
            return pl.Series(name="data", values=[int(bool(value))] * len(self.df))

        raise TypeError(f"Unsupported comparison result type: {type(value)!r}")

    @staticmethod
    def _ordering_operand(values: pl.Series) -> pl.Series:
        """Mask NaN to null, so an ordering comparison answers nothing about it.

        Polars ranks NaN above every real number and hands back a verdict for
        it, which is the one thing a missing observation must never get.
        Measured on polars 1.43.0 over Float64 columns: ``NaN > 11.0`` is
        ``True`` while ``12.0 > NaN`` is ``False`` — the same absent price reads
        as "greater" from one side and "not greater" from the other.

        ``load_bar_df`` writes ``float("nan")`` across every column of a
        suspended day, so this lands squarely on Alpha158's fifteen ``cnt*``
        features, every one of them shaped ``ts_mean(close > ts_delay(close, 1),
        w)``. Measured on ``close = [10, 11, NaN, NaN, NaN, 12, 11.5, 11.8]``,
        the unmasked flag series is ``[null, 1, 1, 0, 0, 0, 0, 1]``: the first
        suspended day is booked as a rise (``NaN > 11.0``), and the resumption
        day — a real 11.0 -> 12.0, +9.1% — is booked as *not* a rise
        (``12.0 > NaN``). One halt fabricates one rise and deletes a real one,
        so the bias is not even one-directional, which is why "cnt* overstates
        up days" was the wrong description of it.

        None of that leaves a trace. ``_comparison_series`` casts the Boolean to
        Int32 and the rolling mean averages it, so the fabricated day produces
        no NaN, no dtype change and no warning. Measured on a synthetic 800-row
        panel carrying a single three-day halt — 0.375% of the rows — ``cntd_5``
        moved by 0.800 on a column whose entire range is [-1, 1], ``cntp_5`` and
        ``cntn_5`` by 0.600 on [0, 1] columns, and the 60-day windows had their
        trailing 49 to 60 readings rewritten.

        Masking to null rather than dropping the row keeps the answer finite
        *for short halts*: ``ts_mean`` is ``rolling_map(np.nanmean,
        min_samples=1)``, so a null window member is skipped and ``cnt*`` reads
        "of the days actually observed, what fraction were up days" — which is
        what qlib's ``Mean($close>Ref($close,1), w)`` meant all along.

        **The "short" is load-bearing and was missing from the first version of
        this note.** A halt of ``h`` sessions blanks ``h + 1`` consecutive
        flags, not ``h``: the halted days plus the resumption day, whose
        ``ts_delay(close, 1)`` is the last halted day rather than the last
        traded one. So a window of ``w`` has nothing left to average whenever
        ``h >= w - 1`` and the reading goes missing. Measured on a single
        symbol, counting missing ``cnt*`` readings by halt length: ``w=5`` first
        loses a reading at ``h=4`` and loses ``h - 3`` of them thereafter, while
        ``w=10`` / ``w=20`` / ``w=60`` are still lossless at ``h=8``. Alpha158's
        narrowest window is 5, so **a four-session suspension — routine in
        A-shares, and normal in HK pending an announcement — already blanks
        ``cntp_5`` / ``cntn_5`` / ``cntd_5``**, and ``process_drop_na`` then
        drops those rows outright.

        That is the intended behaviour and not a residual defect: with no
        observed day in the window there is no fraction to report, and refusing
        is the whole point. It is written down because the earlier wording
        ("zero extra NaN") was measured on a three-day halt only and would have
        been read, by whoever first builds an A-share panel, as a promise the
        code never made.

        **``__eq__`` and ``__ne__`` keep their NaN on purpose.** Polars answers
        ``NaN == NaN`` with ``True`` (measured; IEEE 754 says otherwise), and
        that is a definition rather than an accident — masking it would trade a
        defined answer for a null.

        **What this does not cover**, written down so nobody reads it as a
        general NaN guard: ``sign`` returns 1 for NaN, ``quesval`` /
        ``quesval2`` take their true branch on it, ``ts_less(x, literal)``
        swallows it, and ``Series.arg_max`` skips it. Four separate producers,
        four separate mechanisms. Alpha158 reaches none of them; Alpha101
        reaches all four.
        """
        # Guarded on the dtype rather than called unconditionally: NaN is not a
        # value an Int32 can hold — and every comparison result in this class is
        # Int32 — so `semantics.finite_predicate` splits on `is_float()` for the
        # same reason.
        if values.dtype.is_float():
            return values.fill_nan(None)

        return values

    def result(self, s: pl.Series) -> "DataProxy":
        """Convert series data to feature object"""
        result: pl.DataFrame = self.df[["datetime", "vt_symbol"]]
        result = result.with_columns(other=s)

        return DataProxy(result)

    def __add__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Addition operation"""
        if isinstance(other, DataProxy):
            s = self._as_series(self.df["data"] + other.df["data"])
        else:
            s = self._as_series(self.df["data"] + other)
        return self.result(s)

    def __radd__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Right addition operation"""
        if isinstance(other, DataProxy):
            s = self._as_series(other.df["data"] + self.df["data"])
        else:
            s = self._as_series(other + self.df["data"])
        return self.result(s)

    def __sub__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Subtraction operation"""
        if isinstance(other, DataProxy):
            s = self._as_series(self.df["data"] - other.df["data"])
        else:
            s = self._as_series(self.df["data"] - other)
        return self.result(s)

    def __rsub__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Right subtraction operation"""
        if isinstance(other, DataProxy):
            s = self._as_series(other.df["data"] - self.df["data"])
        else:
            s = self._as_series(other - self.df["data"])
        return self.result(s)

    def __mul__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Multiplication operation"""
        if isinstance(other, DataProxy):
            s = self._as_series(self.df["data"] * other.df["data"])
        else:
            s = self._as_series(self.df["data"] * other)
        return self.result(s)

    def __rmul__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Right multiplication operation"""
        if isinstance(other, DataProxy):
            s = self._as_series(self.df["data"]  * other.df["data"])
        else:
            s = self._as_series(self.df["data"] * other)
        return self.result(s)

    def __truediv__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Division operation"""
        if isinstance(other, DataProxy):
            s = self._as_series(self.df["data"] / other.df["data"])
        else:
            s = self._as_series(self.df["data"] / other)
        return self.result(s)

    def __rtruediv__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Right division operation"""
        if isinstance(other, DataProxy):
            s = self._as_series(other.df["data"] / self.df["data"])
        else:
            s = self._as_series(other / self.df["data"])
        return self.result(s)

    def __floordiv__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Floor division operation"""
        if isinstance(other, DataProxy):
            s = self._as_series(self.df["data"] // other.df["data"])
        else:
            s = self._as_series(self.df["data"] // other)
        return self.result(s)

    def __mod__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Modulo operation"""
        if isinstance(other, DataProxy):
            s = self._as_series(self.df["data"] % other.df["data"])
        else:
            s = self._as_series(self.df["data"] % other)
        return self.result(s)

    def __pow__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Power operation"""
        if isinstance(other, DataProxy):
            s = self._as_series(self.df["data"].pow(other.df["data"]))
        else:
            s = self._as_series(self.df["data"].pow(cast(int | float, other)))
        return self.result(s)

    def __abs__(self) -> "DataProxy":
        """Get absolute value"""
        s: pl.Series = self.df["data"].abs()
        return self.result(s)

    def __neg__(self) -> "DataProxy":
        """Negation operation"""
        s: pl.Series = -self.df["data"]
        return self.result(s)

    def __gt__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Greater than comparison"""
        left: pl.Series = self._ordering_operand(self.df["data"])
        if isinstance(other, DataProxy):
            s: object = left > self._ordering_operand(other.df["data"])
        else:
            s = left > other
        return self.result(self._comparison_series(s))

    def __ge__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Greater than or equal comparison"""
        left: pl.Series = self._ordering_operand(self.df["data"])
        if isinstance(other, DataProxy):
            s: object = left >= self._ordering_operand(other.df["data"])
        else:
            s = left >= other
        return self.result(self._comparison_series(s))

    def __lt__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Less than comparison"""
        left: pl.Series = self._ordering_operand(self.df["data"])
        if isinstance(other, DataProxy):
            s: object = left < self._ordering_operand(other.df["data"])
        else:
            s = left < other
        return self.result(self._comparison_series(s))

    def __le__(self, other: Union["DataProxy", Real]) -> "DataProxy":
        """Less than or equal comparison"""
        left: pl.Series = self._ordering_operand(self.df["data"])
        if isinstance(other, DataProxy):
            s: object = left <= self._ordering_operand(other.df["data"])
        else:
            s = left <= other
        return self.result(self._comparison_series(s))

    def __eq__(self, other: Union["DataProxy", Real]) -> "DataProxy":  # type: ignore[override]
        """Equal comparison"""
        if isinstance(other, DataProxy):
            s: object = self.df["data"] == other.df["data"]
        else:
            s = self.df["data"] == other
        return self.result(self._comparison_series(s))

    def __ne__(self, other: Union["DataProxy", Real]) -> "DataProxy":  # type: ignore[override]
        """Not equal comparison"""
        if isinstance(other, DataProxy):
            s: object = self.df["data"] != other.df["data"]
        else:
            s = self.df["data"] != other
        return self.result(self._comparison_series(s))


def calculate_by_expression(df: pl.DataFrame, expression: str) -> pl.DataFrame:
    """Execute calculation based on expression"""
    # Import operators locally to avoid polluting global namespace
    from .ts_function import (              # noqa
        ts_delay,
        ts_min, ts_max,
        ts_argmax, ts_argmin,
        ts_rank, ts_sum,
        ts_mean, ts_std,
        ts_slope, ts_quantile,
        ts_rsquare, ts_resi,
        ts_corr,
        ts_less, ts_greater,
        ts_log, ts_abs,
        ts_delta, ts_cov,
        ts_decay_linear,
        ts_product
    )
    from .cs_function import (              # noqa
        cs_rank,
        cs_mean,
        cs_std,
        cs_sum,
        cs_scale
    )
    from .ta_function import (              # noqa
        ta_rsi,
        ta_atr
    )
    from .math_function import (              # noqa
        less, greater, log, abs,
        sign, pow1, pow2,
        quesval, quesval2
    )

    # Extract feature objects to local space
    d: dict = locals()
    d.update(EXPRESSION_FUNCTIONS)

    for column in df.columns:
        # Filter index columns
        if column in {"datetime", "vt_symbol"}:
            continue

        # Cache feature df
        column_df = df[["datetime", "vt_symbol", column]]
        d[column] = DataProxy(column_df)

    # Use eval to execute calculation
    other: DataProxy = eval(expression, {}, d)

    # Return result DataFrame
    return other.df


def calculate_by_polars(df: pl.DataFrame, expression: pl.expr.expr.Expr) -> pl.DataFrame:
    """Execute calculation based on Polars expression"""
    return df.select([
        "datetime",
        "vt_symbol",
        expression.alias("data")
    ])


def to_datetime(arg: datetime | str) -> datetime:
    """Convert time data type"""
    if isinstance(arg, str):
        if "-" in arg:
            fmt: str = "%Y-%m-%d"
        else:
            fmt = "%Y%m%d"

        return datetime.strptime(arg, fmt)
    else:
        return arg


class Segment(Enum):
    """Data segment enumeration values"""

    TRAIN = 1
    VALID = 2
    TEST = 3
