from collections import defaultdict

import polars as pl

from vnpy.trader.object import BarData, TradeData
from vnpy.trader.constant import Direction
from vnpy.trader.utility import round_to

from vnpy.alpha import AlphaStrategy


class EquityDemoStrategy(AlphaStrategy):
    """Equity Long-Only Demo Strategy"""

    top_k: int = 50                 # Maximum number of stocks to hold
    n_drop: int = 5                 # Number of stocks to sell each time
    min_days: int = 3               # Minimum holding period in days
    cash_ratio: float = 0.95        # Cash utilization ratio
    min_volume: int = 100           # Minimum trading unit (fallback lot size)
    board_lots: dict | None = None  # Per-vt_symbol board lot overrides — HKEX
                                    # lots vary per stock (100/200/400/500/...),
                                    # a single min_volume constant produces
                                    # share counts that are not executable
                                    # on the real board-lot market
    open_rate: float = 0.0005       # Opening commission rate
    close_rate: float = 0.0015      # Closing commission rate
    min_commission: int = 5         # Minimum commission value
    price_add: float = 0.05         # Order price adjustment ratio

    def on_init(self) -> None:
        """Strategy initialization callback"""
        # Dictionary to track stock holding days
        self.holding_days: defaultdict = defaultdict(int)

        self.write_log("Strategy initialized")

    def on_trade(self, trade: TradeData) -> None:
        """Trade execution callback"""
        # Remove holding days record when selling
        if trade.direction == Direction.SHORT:
            self.holding_days.pop(trade.vt_symbol, None)

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """K-line slice callback"""
        # Get the latest signals and sort them
        last_signal: pl.DataFrame = self.get_signal()

        # A missing signal batch for this date (calendar gap, timezone
        # mismatch, upstream data hole) is a DATA problem, not "every
        # holding dropped out of the investable universe" — without this
        # guard, component_symbols below becomes the empty set and the
        # strategy force-liquidates the ENTIRE book on a plumbing gap.
        if last_signal.is_empty():
            self.write_log("当日无信号数据,保持现有持仓不动")
            return

        # Deterministic ordering: polars sort makes no tie-order guarantee,
        # so two symbols with exactly equal signal values could flip across
        # the top_k/n_drop boundary between reruns of identical code+data.
        # vt_symbol as secondary key makes the ordering a total order.
        last_signal = last_signal.sort(
            ["signal", "vt_symbol"], descending=[True, False]
        )

        # Get position symbols and update holding days
        pos_symbols: list[str] = [vt_symbol for vt_symbol, pos in self.pos_data.items() if pos]

        for vt_symbol in pos_symbols:
            self.holding_days[vt_symbol] += 1

        # Generate sell list
        active_symbols: set[str] = set(last_signal["vt_symbol"][:self.top_k])                         # Extract symbols with highest signals
        active_symbols.update(pos_symbols)                                                            # Merge with currently held symbols
        active_df: pl.DataFrame = last_signal.filter(pl.col("vt_symbol").is_in(active_symbols))       # Filter signals for these symbols

        component_symbols: set[str] = set(last_signal["vt_symbol"])                 # Extract current index component symbols
        sell_symbols: set[str] = set(pos_symbols).difference(component_symbols)     # Sell positions not in components

        for vt_symbol in active_df["vt_symbol"][-self.n_drop:]:                     # Iterate through lowest signal portion
            if vt_symbol in pos_symbols:                                            # If the contract is in current positions
                sell_symbols.add(vt_symbol)                                         # Add it to sell list

        # Generate buy list
        buyable_df: pl.DataFrame = last_signal.filter(~pl.col("vt_symbol").is_in(pos_symbols))  # Filter contracts available for purchase
        buy_quantity: int = len(sell_symbols) + self.top_k - len(pos_symbols)                   # Calculate number of contracts to buy
        buy_symbols: list = list(buyable_df[:buy_quantity]["vt_symbol"])                        # Select buy contract code list

        # Sell rebalancing
        cash: float = self.get_cash_available()                     # Get available cash after yesterday's settlement

        for vt_symbol in sell_symbols:
            if self.holding_days[vt_symbol] < self.min_days:        # Check if holding period exceeds threshold
                continue

            bar: BarData | None = bars.get(vt_symbol)               # Get current price of the contract
            if not bar:
                continue
            sell_price: float = bar.close_price

            sell_volume: float = self.get_pos(vt_symbol)            # Get current holding volume

            self.set_target(vt_symbol, target=0)                    # Set target volume to 0

            turnover: float = sell_price * sell_volume              # Calculate selling turnover
            # Use the rate the ENGINE will actually charge for this
            # symbol, not this class's decorative close_rate default —
            # the two were previously unconnected, so the cash budget
            # here could diverge from real post-settlement cash.
            engine_rate: float = self.strategy_engine.short_rates.get(vt_symbol, self.close_rate)
            cost: float = max(turnover * engine_rate, self.min_commission)
            cash += turnover - cost                                 # Update available cash

        # Buy rebalancing
        if buy_symbols:
            buy_value: float = cash * self.cash_ratio / len(buy_symbols)        # Calculate investment amount per contract

            for vt_symbol in buy_symbols:
                # A symbol can carry a signal for a date it has no bar on
                # (suspension / data hole): bars[vt_symbol] raised KeyError
                # here, and run_backtesting()'s broad except then silently
                # truncated the whole backtest at that date while still
                # printing full-looking statistics for the partial period.
                buy_bar: BarData | None = bars.get(vt_symbol)
                if not buy_bar:
                    continue
                buy_price: float = buy_bar.close_price                          # Get current price of the contract
                if not buy_price:
                    continue

                lot: int = (self.board_lots or {}).get(vt_symbol, self.min_volume)
                buy_volume: float = round_to(buy_value / buy_price, lot)        # Calculate volume to buy

                self.set_target(vt_symbol, buy_volume)                          # Set target holding volume

        # Execute trading
        self.execute_trading(bars, price_add=self.price_add)
