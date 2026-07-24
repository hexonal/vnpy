"""Tests for the ArrayManager linear-regression methods (linearreg / tsf /
linearreg_slope) added as thin talib wrappers.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData
from vnpy.trader.utility import ArrayManager


def _am_with_line(slope: float = 1.0, start: float = 100.0, n: int = 30) -> ArrayManager:
    """An ArrayManager fed a perfectly linear close series, so the regression
    methods have exact expected values."""
    am = ArrayManager(size=n)
    base = datetime(2026, 7, 24)
    for i in range(n):
        close = start + slope * i
        am.update_bar(
            BarData(
                gateway_name="t", symbol="X", exchange=Exchange.SEHK,
                datetime=base + timedelta(days=i), interval=Interval.DAILY,
                open_price=close, high_price=close, low_price=close,
                close_price=close, volume=1,
            )
        )
    return am


def test_linearreg_equals_current_bar_value_on_a_line() -> None:
    am = _am_with_line(slope=1.0, start=100.0, n=30)
    # On a perfect line, the regression value at the current bar == last close.
    assert abs(am.linearreg(14) - 129.0) < 1e-6


def test_tsf_projects_one_bar_ahead() -> None:
    am = _am_with_line(slope=1.0, start=100.0, n=30)
    # TSF forecasts the NEXT bar: 130 = 129 + slope(1).
    assert abs(am.tsf(14) - 130.0) < 1e-6


def test_linearreg_slope_is_price_change_per_bar() -> None:
    am = _am_with_line(slope=2.5, start=50.0, n=30)
    assert abs(am.linearreg_slope(14) - 2.5) < 1e-6


def test_tsf_equals_linearreg_plus_slope() -> None:
    am = _am_with_line(slope=1.7, start=10.0, n=30)
    assert abs(am.tsf(14) - (am.linearreg(14) + am.linearreg_slope(14))) < 1e-6


def test_array_return_shape() -> None:
    am = _am_with_line(n=30)
    arr = am.linearreg(14, array=True)
    assert arr.shape == (30,)
    # Scalar form is the last element.
    assert abs(am.linearreg(14) - arr[-1]) < 1e-9
