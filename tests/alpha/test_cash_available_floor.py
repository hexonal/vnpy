"""
Regression tests for `BacktestingEngine.get_cash_available` flooring at zero.

The engine deducts fills from `self.cash` unconditionally, so an overdrawn
account is ordinary rather than exceptional: `equity_demo_strategy` budgets at
the bar close but orders at `close * (1 + price_add)` and rounds the share
count **up** to the nearest board lot, so a single fill can cost more than the
budget it came from. Measured on the panel below — capital 10,000, one buy of
a 50.00 name — the budget buys 190 shares, `round_to` returns 200, and the fill
at 52.50 plus 13.65 of commission leaves the account at **-513.65**.

Returning that number to a strategy is what this module is about. Nothing
downstream reads it as "you are overdrawn"; it is consumed as a budget, and a
negative budget means *buy a negative amount*. The chain runs:
`buy_value = cash * cash_ratio / len(buy_symbols)` goes negative,
`round_to(-97.59, 100)` answers **-100.0** (plain Decimal rounding, no sign
opinion), `set_target` accepts it, and `AlphaStrategy.execute_trading` sees
`diff = -100 - 0 < 0` with `pos == 0` and calls `self.short()`. A **long-only**
demo strategy opens a short leg — no exception, no log line, no rejected order.

The damage outlives the short. `on_trade` pops `holding_days` only on
`Direction.SHORT`, so the `cover` that flattens the short leaves the counter
standing, and `on_bars` has been ticking it up the whole time because `if pos`
is true for -100. The counter is then already past `min_days` when the symbol
is next bought for real, and the position is marked for sale on its **first**
day. That is the shape asserted here: with the floor reverted the panel holds
S2 for exactly 1 bar under `min_days=2`; with the floor in place no holding
period in the same panel comes in under 2.

Two things these tests deliberately do **not** claim. First, the floor is not
an accounting fix — `self.cash` still goes negative afterwards, and on the real
`hk_bluechip_10` panel it goes negative on *more* bars with the floor (38) than
without (24), because a floored budget buys more. Second, the panel is driven
one `new_bars` call at a time rather than through `run_backtesting`, because
that method wraps the loop in a broad `except` that logs and returns — a test
built on it would report a green truncated backtest as a pass.

`test_reverting_the_floor_...` monkeypatches the fix away on purpose. Without
it this file would keep passing against an engine that never overdraws at all,
and the panel's whole job is to overdraw.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl
import pytest

from vnpy.trader.constant import Direction, Exchange, Interval, Offset
from vnpy.trader.object import BarData, TradeData
from vnpy.trader.utility import round_to
from vnpy.alpha.strategy.backtesting import BacktestingEngine
from vnpy.alpha.strategy.template import AlphaStrategy
from vnpy.alpha.strategy.strategies.equity_demo_strategy import EquityDemoStrategy


BASE: datetime = datetime(2026, 1, 5)

SYMBOLS: tuple[str, ...] = ("S1.SEHK", "S2.SEHK", "S3.SEHK")

# One 50.00 name that the whole account gets spent on, and two 5.00 names cheap
# enough that a small negative budget still rounds to a whole lot of -100 rather
# than to zero. `round_to(-0.6, 100)` is 0.0, so a defect that only ever divides
# a small overdraft by an expensive share price hides itself.
PANEL: tuple[tuple[int, str, float, float, float, float], ...] = (
    (0, "S1.SEHK", 50.0, 50.5, 49.5, 50.0),
    (0, "S2.SEHK", 5.0, 5.1, 4.9, 5.0),
    (0, "S3.SEHK", 5.0, 5.1, 4.9, 5.0),

    (1, "S1.SEHK", 53.0, 54.0, 52.0, 53.0),
    (1, "S2.SEHK", 5.0, 5.1, 4.9, 5.0),
    (1, "S3.SEHK", 5.0, 5.1, 4.9, 5.0),

    (2, "S1.SEHK", 53.0, 54.0, 52.0, 53.0),
    (2, "S2.SEHK", 5.0, 5.2, 4.7, 5.0),
    (2, "S3.SEHK", 5.0, 5.1, 4.9, 5.0),

    (3, "S1.SEHK", 53.0, 54.0, 52.0, 53.0),
    (3, "S2.SEHK", 5.0, 5.2, 4.7, 5.0),
    (3, "S3.SEHK", 5.0, 5.1, 4.9, 5.0),

    (4, "S1.SEHK", 53.0, 54.0, 52.0, 53.0),
    (4, "S2.SEHK", 5.0, 5.2, 4.7, 5.0),
    (4, "S3.SEHK", 5.0, 5.1, 4.9, 5.0),

    (5, "S1.SEHK", 53.0, 54.0, 52.0, 53.0),
    (5, "S2.SEHK", 5.0, 5.2, 4.7, 5.0),
    (5, "S3.SEHK", 5.0, 5.1, 4.9, 5.0),

    (6, "S1.SEHK", 53.0, 54.0, 52.0, 53.0),
    (6, "S2.SEHK", 5.0, 5.2, 4.7, 5.0),
    (6, "S3.SEHK", 5.0, 5.1, 4.9, 5.0),

    (7, "S1.SEHK", 53.0, 54.0, 52.0, 53.0),
    (7, "S2.SEHK", 5.0, 5.2, 4.7, 5.0),
    (7, "S3.SEHK", 5.0, 5.1, 4.9, 5.0),
)

# Only the ordering carries meaning — `on_bars` reads rank, never the value.
# The rotation is what forces a buy candidate onto a bar whose cash is already
# negative, which is the only situation the defect needs.
SIGNAL: tuple[tuple[int, str, float], ...] = (
    (0, "S1.SEHK", 0.9), (0, "S2.SEHK", 0.5), (0, "S3.SEHK", 0.1),
    (1, "S2.SEHK", 0.9), (1, "S3.SEHK", 0.5), (1, "S1.SEHK", 0.1),
    (2, "S1.SEHK", 0.9), (2, "S3.SEHK", 0.5), (2, "S2.SEHK", 0.1),
    (3, "S1.SEHK", 0.9), (3, "S3.SEHK", 0.5), (3, "S2.SEHK", 0.1),
    (4, "S2.SEHK", 0.9), (4, "S3.SEHK", 0.5), (4, "S1.SEHK", 0.1),
    (5, "S3.SEHK", 0.9), (5, "S1.SEHK", 0.5), (5, "S2.SEHK", 0.1),
    (6, "S3.SEHK", 0.9), (6, "S1.SEHK", 0.5), (6, "S2.SEHK", 0.1),
    (7, "S3.SEHK", 0.9), (7, "S1.SEHK", 0.5), (7, "S2.SEHK", 0.1),
)

CAPITAL: int = 10_000

MIN_DAYS: int = 2

SETTING: dict[str, int] = {"top_k": 1, "n_drop": 1, "min_days": MIN_DAYS}

# HKEX-shaped: 13bp both ways, one share per unit, a tenth of a cent per tick.
CONTRACT_SETTINGS: dict[str, dict[str, float]] = {
    vt_symbol: {
        "long_rate": 0.0013,
        "short_rate": 0.0013,
        "size": 1,
        "pricetick": 0.001,
    }
    for vt_symbol in SYMBOLS
}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeLab:
    """The one method `set_parameters` calls, and nothing else.

    Bars are pushed into `history_data` directly rather than loaded, so
    `load_bar_data` is never reached — a lab that answered it would let a
    future edit start reading real parquet from disk without saying so.
    """

    def load_contract_setttings(self) -> dict:
        return {vt_symbol: dict(row) for vt_symbol, row in CONTRACT_SETTINGS.items()}


class RecordingTargets:
    """Keeps every value handed to `set_target`, not just the surviving ones.

    Reading `strategy.target_data` after the replay does **not** work, and the
    first draft of this module made that mistake: a target is overwritten on
    the next rebalance, so by the last bar the dictionary holds nothing
    negative even in a run that shorted. Measured with the floor reverted, the
    end-state check passed while `set_target` had been handed -100.0.
    """

    def __init__(self, strategy: AlphaStrategy) -> None:
        self.calls: list[tuple[str, float]] = []
        self.wrapped = strategy.set_target
        strategy.set_target = self      # type: ignore[method-assign]

    def __call__(self, vt_symbol: str, target: float) -> None:
        self.calls.append((vt_symbol, target))
        self.wrapped(vt_symbol, target)

    def negatives(self) -> list[tuple[str, float]]:
        return [call for call in self.calls if call[1] < 0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_engine() -> BacktestingEngine:
    """A backtesting engine loaded with the panel above, ready for `new_bars`."""
    engine: BacktestingEngine = BacktestingEngine(FakeLab())     # type: ignore[arg-type]
    engine.set_parameters(
        vt_symbols=list(SYMBOLS),
        interval=Interval.DAILY,
        start=BASE,
        end=BASE + timedelta(days=30),
        capital=CAPITAL,
    )

    for day, vt_symbol, open_price, high, low, close in PANEL:
        dt: datetime = BASE + timedelta(days=day)
        engine.history_data[(dt, vt_symbol)] = BarData(
            symbol=vt_symbol.split(".")[0],
            exchange=Exchange.SEHK,
            datetime=dt,
            open_price=open_price,
            high_price=high,
            low_price=low,
            close_price=close,
            gateway_name="FAKE",
        )
        engine.dts.add(dt)

    signal: pl.DataFrame = pl.DataFrame({
        "datetime": [BASE + timedelta(days=day) for day, _, _ in SIGNAL],
        "vt_symbol": [vt_symbol for _, vt_symbol, _ in SIGNAL],
        "signal": [value for _, _, value in SIGNAL],
    })
    engine.add_strategy(EquityDemoStrategy, dict(SETTING), signal)

    return engine


def replay(engine: BacktestingEngine) -> list[float]:
    """Drive every bar and return the closing cash balance after each one."""
    engine.strategy.on_init()

    balances: list[float] = []
    for dt in sorted(engine.dts):
        engine.new_bars(dt)
        balances.append(engine.cash)

    return balances


def short_opens(engine: BacktestingEngine) -> list[TradeData]:
    """Fills that opened a short leg — the thing a long-only strategy owes zero of."""
    return [
        trade for trade in engine.trades.values()
        if trade.direction == Direction.SHORT and trade.offset == Offset.OPEN
    ]


def holding_spans(engine: BacktestingEngine) -> list[tuple[str, int]]:
    """How many bars each completed long position was actually held.

    Counted in bars off the trade timestamps rather than in calendar days,
    because `min_days` is compared against `holding_days`, which `on_bars`
    increments once per bar.
    """
    days: list[datetime] = sorted(engine.dts)
    index_of: dict[datetime, int] = {dt: i for i, dt in enumerate(days)}

    opened: dict[str, int] = {}
    spans: list[tuple[str, int]] = []

    for trade in sorted(engine.trades.values(), key=lambda t: (t.datetime, t.tradeid)):
        if trade.direction == Direction.LONG and trade.offset == Offset.OPEN:
            opened.setdefault(trade.vt_symbol, index_of[trade.datetime])
        elif trade.direction == Direction.SHORT and trade.offset == Offset.CLOSE:
            entry: int | None = opened.pop(trade.vt_symbol, None)
            if entry is not None:
                spans.append((trade.vt_symbol, index_of[trade.datetime] - entry))

    return spans


# ---------------------------------------------------------------------------
# The floor itself
# ---------------------------------------------------------------------------

def test_get_cash_available_returns_zero_instead_of_negative_cash() -> None:
    # -21526.24 is the low-water mark measured on lab/hk_bluechip_10 over
    # 2026-01-02..2026-07-22 with top_k=3 / n_drop=1 / min_days=3 / 5bp
    # slippage — the reading this floor exists to keep out of a strategy.
    engine: BacktestingEngine = build_engine()
    engine.cash = -21526.24

    assert engine.get_cash_available() == 0.0


def test_the_floor_reports_zero_without_rewriting_the_cash_balance() -> None:
    # The books stay honest: this is a floor on what a strategy may spend, not
    # a write-off of the overdraft. A fix that clamped `self.cash` itself would
    # invent money — the next sell would settle on top of a zeroed balance.
    engine: BacktestingEngine = build_engine()
    engine.cash = -21526.24

    engine.get_cash_available()

    assert engine.cash == -21526.24


def test_get_cash_available_leaves_a_positive_balance_untouched() -> None:
    engine: BacktestingEngine = build_engine()
    engine.cash = 1_234.56

    assert engine.get_cash_available() == pytest.approx(1_234.56)


def test_round_to_answers_a_negative_budget_with_a_negative_lot() -> None:
    # The step that turns a negative budget into a short order, pinned as a
    # plain function call: `round_to` is Decimal quantisation and has no sign
    # opinion, so the guard cannot live there. -0.6 is included because it
    # rounds to 0.0 — a small overdraft against an expensive share price is
    # harmless, which is exactly why this defect is intermittent.
    assert round_to(-123.952491, 100) == -100.0
    assert round_to(-475.0, 500) == -500.0
    assert round_to(-0.6, 100) == 0.0


# ---------------------------------------------------------------------------
# The chain, end to end on the panel
# ---------------------------------------------------------------------------

def test_the_panel_overdraws_the_account_on_the_first_fill() -> None:
    # Fixture sanity, and the reason it is a test rather than a comment: every
    # assertion below is vacuous on a panel that never runs out of cash. The
    # budget buys 190 shares of a 50.00 name, `round_to` rounds that up to a
    # whole 200-share lot, and the fill at 52.50 plus 13.65 commission spends
    # 10513.65 of a 10000.00 account.
    engine: BacktestingEngine = build_engine()

    balances: list[float] = replay(engine)

    assert balances[1] == pytest.approx(-513.65)
    assert min(balances) < 0


def test_long_only_demo_strategy_never_opens_a_short_when_cash_runs_out() -> None:
    engine: BacktestingEngine = build_engine()

    replay(engine)

    assert short_opens(engine) == []
    assert all(pos >= 0 for pos in engine.strategy.pos_data.values())


def test_no_target_is_ever_negative_for_a_long_only_strategy() -> None:
    # One layer earlier than the order: `execute_trading` can only route a
    # short if something asked for a negative target, so this is where the
    # defect is legible even on a panel whose short order happens not to fill.
    engine: BacktestingEngine = build_engine()
    targets: RecordingTargets = RecordingTargets(engine.strategy)

    replay(engine)

    assert targets.calls, "the panel must rebalance at least once"
    assert targets.negatives() == []


def test_every_holding_period_clears_min_days_with_the_floor_in_place() -> None:
    engine: BacktestingEngine = build_engine()

    replay(engine)
    spans: list[tuple[str, int]] = holding_spans(engine)

    assert spans, "the panel must complete at least one round trip"
    assert all(span >= MIN_DAYS for _, span in spans), spans


# ---------------------------------------------------------------------------
# The same panel with the floor taken back out
# ---------------------------------------------------------------------------

def test_reverting_the_floor_opens_a_short_leg_and_defeats_the_min_days_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The upstream body, restored. Everything else in the panel is identical,
    # so what this asserts is that the floor — and not the fixture — is what
    # keeps the three tests above green.
    monkeypatch.setattr(
        BacktestingEngine, "get_cash_available", lambda self: self.cash
    )

    engine: BacktestingEngine = build_engine()
    targets: RecordingTargets = RecordingTargets(engine.strategy)
    replay(engine)

    # -513.65 of cash, times cash_ratio 0.95, over one buy candidate priced at
    # 5.00, is -97.59 shares — which `round_to` widens to a whole lot.
    assert targets.negatives() == [("S2.SEHK", -100.0)]

    # A long-only strategy then sells 100 shares it does not own.
    opens: list[TradeData] = short_opens(engine)
    assert [(t.vt_symbol, t.volume) for t in opens] == [("S2.SEHK", 100.0)]

    # And the counter that the `cover` failed to clear turns the next genuine
    # entry into a same-day sale: one bar held against min_days=2.
    spans: list[tuple[str, int]] = holding_spans(engine)
    assert ("S2.SEHK", 1) in spans, spans
