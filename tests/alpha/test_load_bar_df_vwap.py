"""
Regression tests for price normalization inside ``AlphaLab.load_bar_df``.

``load_bar_df`` rebases every symbol's prices on its own first close so that
symbols trading at 10 and at 1000 become comparable. Upstream rebased four
columns by name — open, high, low, close — and computed ``vwap =
turnover / volume`` beforehand, in **raw price units**. vwap was then left
un-rebased, which made Alpha158's

    vwap_0 = vwap / close = (raw_vwap / raw_close) * close_0

a per-symbol constant times a ratio that hugs 1.0. In other words the column
was a **stock identifier**, not a factor: on the workspace's ten-symbol Hong
Kong panel the per-symbol ranges did not overlap at all (1810.SEHK spanned
[10.62, 11.91], 388.SEHK [257.74, 295.30], 700.SEHK [303.71, 330.59]), and the
shipped LightGBM booster used it as the root split of all three of its trees.

Two properties are pinned here, and the second is the load-bearing one:

* All symbols' ``vwap / close`` must live on **one** scale, whatever their
  price level. This is the defect stated directly.
* A given bar's ``vwap / close`` must not change when the caller moves the
  query's start date. ``close_0`` is the first close *inside the window*, so
  the old code made one bar's factor value a property of the **query** rather
  than of the data — measured on the real panel, 700.SEHK's 2026-07-22 bar
  reported vwap_0 = 317.615229 / 288.685555 / 413.775838 from three different
  start dates. No refactor can satisfy this second property while leaving vwap
  on a different scale from close.

These tests deliberately do not go through Alpha101's own test fixture, which
builds ``vwap = (high + low + close) / 3`` and is therefore in the same units
as the prices by construction — that fixture cannot see this defect, which is
why 110 tests stayed green while every production vwap factor was wrong.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl
import pytest

from vnpy.alpha.lab import AlphaLab
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData


# ---------------------------------------------------------------------------
# Synthetic bars
# ---------------------------------------------------------------------------

N_DAYS: int = 40

# Two symbols an order of magnitude apart in price level. The gap is what turns
# an un-rebased vwap into a label: whatever else changes, a penny stock and a
# blue chip must not be separable by a factor value alone.
PRICE_LEVELS: dict[str, float] = {"CHEAP.SEHK": 8.0, "RICH.SEHK": 800.0}


def make_bars(vt_symbol: str, base: float) -> list[BarData]:
    """Build a deterministic daily series whose vwap sits inside the day's range.

    The intraday average price is put at a fixed 0.4% below the close, so the
    expected ``vwap / close`` is a known constant and any leaked price level
    shows up immediately.
    """
    symbol, exchange = vt_symbol.split(".")

    bars: list[BarData] = []
    for i in range(N_DAYS):
        # A mild deterministic drift — no RNG, because the CI interpreter
        # (Windows / 3.13) differs from this workstation's (macOS / 3.14).
        close: float = base * (1.0 + 0.01 * ((i % 7) - 3))
        volume: float = 1000.0 + 10.0 * (i % 11)

        bars.append(
            BarData(
                gateway_name="TEST",
                symbol=symbol,
                exchange=Exchange(exchange),
                datetime=datetime(2024, 1, 1) + timedelta(days=i),
                interval=Interval.DAILY,
                volume=volume,
                turnover=close * 0.996 * volume,
                open_interest=0.0,
                open_price=close * 0.99,
                high_price=close * 1.02,
                low_price=close * 0.97,
                close_price=close,
            )
        )

    return bars


def build_lab(lab_path: str) -> AlphaLab:
    """Create a lab on disk and fill it with both symbols' daily bars."""
    lab: AlphaLab = AlphaLab(lab_path)

    for vt_symbol, base in PRICE_LEVELS.items():
        lab.save_bar_data(make_bars(vt_symbol, base))

    return lab


def vwap_over_close(df: pl.DataFrame) -> pl.DataFrame:
    """Reduce a loaded frame to one ratio column per row."""
    return df.select(
        pl.col("datetime"),
        pl.col("vt_symbol"),
        (pl.col("vwap") / pl.col("close")).alias("ratio")
    )


# ---------------------------------------------------------------------------
# vwap shares the prices' scale
# ---------------------------------------------------------------------------

def test_load_bar_df_normalizes_vwap_against_the_same_close_0_as_prices(tmp_path) -> None:  # noqa: ANN001
    lab: AlphaLab = build_lab(str(tmp_path))

    df: pl.DataFrame | None = lab.load_bar_df(
        list(PRICE_LEVELS),
        Interval.DAILY,
        "2024-01-01",
        "2024-02-09",
        extended_days=0
    )
    assert df is not None

    ratios: pl.DataFrame = vwap_over_close(df)

    # Each symbol's own band, then the two bands compared. Un-rebased vwap puts
    # CHEAP around 8 and RICH around 800; rebased vwap puts both at 0.996.
    per_symbol: dict[str, tuple[float, float]] = {}
    for vt_symbol in PRICE_LEVELS:
        column: pl.Series = ratios.filter(pl.col("vt_symbol") == vt_symbol)["ratio"]
        per_symbol[vt_symbol] = (column.min(), column.max())     # type: ignore[assignment]

    cheap_low, cheap_high = per_symbol["CHEAP.SEHK"]
    rich_low, rich_high = per_symbol["RICH.SEHK"]

    assert cheap_low == pytest.approx(rich_low)
    assert cheap_high == pytest.approx(rich_high)


def test_load_bar_df_keeps_vwap_inside_the_normalized_price_scale(tmp_path) -> None:  # noqa: ANN001
    # The bars are built with the day's average price 0.4% under the close, so
    # the ratio is a known number rather than merely "small".
    lab: AlphaLab = build_lab(str(tmp_path))

    df: pl.DataFrame | None = lab.load_bar_df(
        list(PRICE_LEVELS),
        Interval.DAILY,
        "2024-01-01",
        "2024-02-09",
        extended_days=0
    )
    assert df is not None

    ratios: pl.Series = vwap_over_close(df)["ratio"]

    assert ratios.min() == pytest.approx(0.996)
    assert ratios.max() == pytest.approx(0.996)


# ---------------------------------------------------------------------------
# The ratio belongs to the data, not to the query
# ---------------------------------------------------------------------------

def test_load_bar_df_vwap_ratio_does_not_depend_on_the_query_start_date(tmp_path) -> None:  # noqa: ANN001
    lab: AlphaLab = build_lab(str(tmp_path))

    shared_day: datetime = datetime(2024, 1, 30)

    def ratio_from(start: str) -> float:
        df: pl.DataFrame | None = lab.load_bar_df(
            list(PRICE_LEVELS),
            Interval.DAILY,
            start,
            "2024-02-09",
            extended_days=0
        )
        assert df is not None

        row: pl.DataFrame = vwap_over_close(df).filter(
            (pl.col("datetime") == shared_day) & (pl.col("vt_symbol") == "RICH.SEHK")
        )
        assert row.height == 1

        return float(row["ratio"][0])

    # The two windows have different first closes — 800.0 * (1 - 0.03) against
    # 800.0 * (1 + 0.02) on this drift — so an un-rebased vwap gives two
    # different answers for one and the same bar.
    early: float = ratio_from("2024-01-01")
    late: float = ratio_from("2024-01-20")

    assert early == pytest.approx(late)


def test_load_bar_df_leaves_the_close_column_rebased_to_one(tmp_path) -> None:  # noqa: ANN001
    # Guards the other direction: the fix must divide vwap by close_0, not
    # multiply close by anything. If a future edit rebased vwap by rebasing the
    # raw close first, close_0 would collapse to 1.0 and every price column
    # would silently stop being normalized at all.
    lab: AlphaLab = build_lab(str(tmp_path))

    df: pl.DataFrame | None = lab.load_bar_df(
        ["RICH.SEHK"],
        Interval.DAILY,
        "2024-01-01",
        "2024-02-09",
        extended_days=0
    )
    assert df is not None

    assert float(df["close"][0]) == pytest.approx(1.0)
