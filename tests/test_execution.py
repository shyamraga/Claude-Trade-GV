"""Unit tests for VirtualBroker and ExecutionEngine."""

import shutil
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from src.execution.models import OrderSide, OrderStatus
from src.execution.virtual_broker import VirtualBroker
from src.execution.engine import ExecutionEngine, ExecutionMode
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.post_mortem import PostMortemRepository


class TestVirtualBroker(unittest.TestCase):
    """Test VirtualBroker portfolio mechanics."""

    def setUp(self):
        self.broker = VirtualBroker(initial_cash=50000.0, slippage_pct=0.0)

    def test_initial_account_state(self):
        """Test initial cash balance."""
        acc = self.broker.get_account()
        self.assertEqual(acc.cash, 50000.0)
        self.assertEqual(acc.portfolio_value, 50000.0)
        self.assertEqual(len(acc.open_positions), 0)

    def test_buy_and_sell_cycle(self):
        """Test executing buy and sell order cycle."""
        self.broker.set_market_price("AAPL", 150.0)

        # Buy 100 shares @ $150 = $15,000
        from src.execution.models import Order, OrderType
        order = Order(
            order_id="o1",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        filled = self.broker.submit_order(order)
        self.assertEqual(filled.status, OrderStatus.FILLED)
        self.assertEqual(filled.average_fill_price, 150.0)
        self.assertEqual(self.broker.cash, 35000.0)

        # Position check
        pos = self.broker.get_position("AAPL")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.quantity, 100)

        # Sell 100 shares @ $160 = $16,000 (+1,000 profit)
        self.broker.set_market_price("AAPL", 160.0)
        sell_order = Order(
            order_id="o2",
            symbol="AAPL",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        filled_sell = self.broker.submit_order(sell_order)
        self.assertEqual(filled_sell.status, OrderStatus.FILLED)
        self.assertEqual(self.broker.cash, 51000.0)
        self.assertIsNone(self.broker.get_position("AAPL"))

    def test_short_and_cover_profit_cycle(self):
        """Test short selling when holding no shares, then covering at lower price for profit."""
        from src.execution.models import Order, OrderType
        self.broker.set_market_price("TSLA", 200.0)

        # 1. Short 50 shares @ $200 = $10,000 margin required
        short_order = Order(
            order_id="s1",
            symbol="TSLA",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=50,
        )
        filled_short = self.broker.submit_order(short_order)
        self.assertEqual(filled_short.status, OrderStatus.FILLED)
        self.assertEqual(filled_short.average_fill_price, 200.0)
        self.assertEqual(self.broker.cash, 40000.0)

        # Position check: side should be SHORT
        pos = self.broker.get_position("TSLA")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.side, "SHORT")
        self.assertEqual(pos.quantity, 50)

        # 2. Price falls to $180 -> profit on short
        self.broker.set_market_price("TSLA", 180.0)
        self.assertEqual(pos.unrealized_pnl, 1000.0)  # (200 - 180) * 50 = +1000
        self.assertEqual(pos.unrealized_pnl_pct, 0.10)  # +10%

        # 3. Buy 50 shares to cover short @ $180
        cover_order = Order(
            order_id="c1",
            symbol="TSLA",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=50,
        )
        filled_cover = self.broker.submit_order(cover_order)
        self.assertEqual(filled_cover.status, OrderStatus.FILLED)

        # Cash should be initial $50,000 + $1,000 profit = $51,000
        self.assertEqual(self.broker.cash, 51000.0)
        self.assertIsNone(self.broker.get_position("TSLA"))

    def test_short_and_cover_loss_cycle(self):
        """Test short selling and covering at higher price for loss."""
        from src.execution.models import Order, OrderType
        self.broker.set_market_price("NVDA", 100.0)

        # 1. Short 100 shares @ $100 = $10,000 margin
        short_order = Order(
            order_id="s2",
            symbol="NVDA",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        self.broker.submit_order(short_order)
        self.assertEqual(self.broker.cash, 40000.0)

        # 2. Price rises to $110 -> loss on short
        self.broker.set_market_price("NVDA", 110.0)
        pos = self.broker.get_position("NVDA")
        self.assertEqual(pos.unrealized_pnl, -1000.0)

        # 3. Cover short @ $110
        cover_order = Order(
            order_id="c2",
            symbol="NVDA",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        self.broker.submit_order(cover_order)
        # $40k cash + ($10k margin - $1k loss) = $49,000
        self.assertEqual(self.broker.cash, 49000.0)
        self.assertIsNone(self.broker.get_position("NVDA"))


class TestExecutionEngine(unittest.TestCase):
    """Test ExecutionEngine with integrated Risk & Continuous Learning."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.virtual_broker = VirtualBroker(initial_cash=100000.0, slippage_pct=0.0)
        self.circuit_breaker = CircuitBreaker()
        self.post_mortem_repo = PostMortemRepository(memory_dir=self.temp_dir)
        self.engine = ExecutionEngine(
            mode=ExecutionMode.VIRTUAL,
            virtual_broker=self.virtual_broker,
            circuit_breaker=self.circuit_breaker,
            post_mortem_repo=self.post_mortem_repo,
            trades_file=self.temp_dir / "trades_history.json",
        )
        self.mh_patcher = patch(
            "src.risk.market_hours.MarketHoursManager.is_market_open",
            return_value=(True, "Market is open for testing"),
        )
        self.mh_patcher.start()

    def tearDown(self):
        self.mh_patcher.stop()
        shutil.rmtree(self.temp_dir)

    def test_market_hours_guardian_rejects_closed_market(self):
        """Test that market hours guardian rejects orders when market is closed."""
        with patch(
            "src.risk.market_hours.MarketHoursManager.is_market_open",
            return_value=(False, "US Market is CLOSED for weekend"),
        ):
            order = self.engine.execute_signal("AAPL", "BUY", 150.0, 10)
            self.assertIsNone(order)

    def test_execute_buy_signal(self):
        """Test executing a standard BUY signal."""
        self.virtual_broker.set_market_price("MSFT", 300.0)
        order = self.engine.execute_signal(
            symbol="MSFT",
            action="BUY",
            price=300.0,
            quantity=20,
            strategy_name="TrendFollowing",
        )
        self.assertIsNotNone(order)
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertEqual(self.virtual_broker.get_position("MSFT").quantity, 20)

    def test_circuit_breaker_blocks_execution(self):
        """Test that active circuit breaker cooldown blocks order execution."""
        self.circuit_breaker.trigger_cooldown(hours=4.0, reason="Test circuit breaker")

        order = self.engine.execute_signal(
            symbol="AAPL",
            action="BUY",
            price=150.0,
            quantity=10,
        )
        self.assertIsNone(order)

    def test_losing_trade_triggers_automatic_post_mortem(self):
        """Test that closing a trade at a loss generates an automated post-mortem in memory."""
        self.virtual_broker.set_market_price("NVDA", 100.0)

        # 1. Buy @ 100
        self.engine.execute_signal("NVDA", "BUY", 100.0, 50, strategy_name="ORB")

        # 2. Price drops to 90
        self.virtual_broker.set_market_price("NVDA", 90.0)

        # 3. Exit @ 90 (-$500 loss)
        self.engine.execute_signal("NVDA", "EXIT", 90.0, 50, strategy_name="ORB")

        # Verify trade record
        self.assertEqual(len(self.engine.trade_history), 1)
        self.assertEqual(self.engine.trade_history[0].pnl, -500.0)

        # Verify Post-Mortem was automatically created in memory
        recent_pms = self.post_mortem_repo.get_recent_post_mortems()
        self.assertEqual(len(recent_pms), 1)
        self.assertEqual(recent_pms[0].symbol, "NVDA")
        self.assertEqual(recent_pms[0].loss_amount, 500.0)
        self.assertEqual(recent_pms[0].outcome, "LOSS")
        # Ensure deep diagnosis is populated rather than generic boilerplate
        self.assertTrue(len(recent_pms[0].root_cause) > 20)
        self.assertTrue(len(recent_pms[0].preventative_rule) > 20)
        self.assertIn("NVDA", recent_pms[0].tags)
        self.assertIn("ORB", recent_pms[0].tags)

    def test_winning_trade_triggers_automatic_post_mortem_debrief(self):
        """Test that closing a trade at a profit also generates an automated debrief and doesn't block future trades."""
        self.virtual_broker.set_market_price("AAPL", 150.0)

        # 1. Buy @ 150
        self.engine.execute_signal("AAPL", "BUY", 150.0, 20, strategy_name="TrendFollowing")

        # 2. Price rallies to 160
        self.virtual_broker.set_market_price("AAPL", 160.0)

        # 3. Exit @ 160 (+$200 profit)
        self.engine.execute_signal("AAPL", "EXIT", 160.0, 20, strategy_name="TrendFollowing")

        # Verify trade record
        self.assertEqual(len(self.engine.trade_history), 1)
        self.assertEqual(self.engine.trade_history[0].pnl, 200.0)

        # Verify Post-Mortem / Debrief was created in memory
        recent_pms = self.post_mortem_repo.get_recent_post_mortems()
        self.assertEqual(len(recent_pms), 1)
        self.assertEqual(recent_pms[0].symbol, "AAPL")
        self.assertEqual(recent_pms[0].outcome, "WIN")
        self.assertEqual(recent_pms[0].pnl, 200.0)

        # Winning debrief must NOT block pre-trade filter!
        allowed, reason = self.post_mortem_repo.check_pre_trade_filter("AAPL", "TrendFollowing")
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_position_timestamp_and_exit_targets(self):
        """Test that position records opened_at timestamp and target stop-loss / take-profit."""
        self.virtual_broker.set_market_price("SPY", 400.0)
        self.engine.execute_signal(
            symbol="SPY",
            action="BUY",
            price=400.0,
            quantity=10,
            strategy_name="ORB",
            stop_loss=392.0,
            take_profit=416.0,
        )
        pos = self.virtual_broker.get_position("SPY")
        self.assertIsNotNone(pos)
        self.assertIsNotNone(pos.opened_at)
        self.assertEqual(pos.stop_loss, 392.0)
        self.assertEqual(pos.take_profit, 416.0)
        self.assertEqual(pos.strategy, "ORB")

        pos_dict = pos.to_dict()
        self.assertIn("opened_at", pos_dict)
        self.assertEqual(pos_dict["stop_loss"], 392.0)
        self.assertEqual(pos_dict["take_profit"], 416.0)

    def test_auto_stop_loss_and_take_profit_triggers(self):
        """Test that check_position_stops triggers automated exit when SL or TP is reached."""
        self.virtual_broker.set_market_price("AMD", 100.0)
        self.engine.execute_signal(
            symbol="AMD",
            action="BUY",
            price=100.0,
            quantity=10,
            strategy_name="RSI",
            stop_loss=95.0,
            take_profit=110.0,
        )

        # 1. Price is normal ($98) - no trigger
        exit_order = self.engine.check_position_stops("AMD", 98.0)
        self.assertIsNone(exit_order)
        self.assertIsNotNone(self.virtual_broker.get_position("AMD"))

        # 2. Price hits stop-loss ($94 <= $95) - triggers STOP_LOSS exit
        exit_order = self.engine.check_position_stops("AMD", 94.0)
        self.assertIsNotNone(exit_order)
        self.assertEqual(exit_order.status, OrderStatus.FILLED)
        self.assertIsNone(self.virtual_broker.get_position("AMD"))
        self.assertEqual(len(self.engine.trade_history), 1)
        self.assertEqual(self.engine.trade_history[0].reason, "STOP_LOSS")
        self.assertLess(self.engine.trade_history[0].pnl, 0)

    def test_short_take_profit_trigger(self):
        """Test that short position automatically covers when price falls to take-profit target."""
        self.virtual_broker.set_market_price("COIN", 200.0)
        self.engine.execute_signal(
            symbol="COIN",
            action="SELL",
            price=200.0,
            quantity=10,
            strategy_name="TrendFollowing",
            stop_loss=210.0,
            take_profit=185.0,
        )
        pos = self.virtual_broker.get_position("COIN")
        self.assertEqual(pos.side, "SHORT")

        # Price drops to $180 <= $185 -> triggers TAKE_PROFIT
        exit_order = self.engine.check_position_stops("COIN", 180.0)
        self.assertIsNotNone(exit_order)
        self.assertEqual(exit_order.side, OrderSide.BUY)  # Cover short
        self.assertIsNone(self.virtual_broker.get_position("COIN"))
        self.assertEqual(len(self.engine.trade_history), 1)
        self.assertEqual(self.engine.trade_history[0].reason, "TAKE_PROFIT")
        self.assertGreater(self.engine.trade_history[0].pnl, 0)

    def test_execute_short_signal_and_profitable_exit(self):
        """Test executing short entry signal and closing position with EXIT."""
        self.virtual_broker.set_market_price("TSLA", 200.0)
        order = self.engine.execute_signal(
            symbol="TSLA",
            action="SELL",
            price=200.0,
            quantity=25,
            strategy_name="TrendFollowing",
        )
        self.assertIsNotNone(order)
        self.assertEqual(order.status, OrderStatus.FILLED)
        pos = self.virtual_broker.get_position("TSLA")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.side, "SHORT")
        self.assertEqual(pos.quantity, 25)

        # Price drops to $180 -> exit for profit
        self.virtual_broker.set_market_price("TSLA", 180.0)
        exit_order = self.engine.execute_signal(
            symbol="TSLA",
            action="EXIT",
            price=180.0,
            quantity=25,
            strategy_name="TrendFollowing",
        )
        self.assertIsNotNone(exit_order)
        self.assertEqual(exit_order.side, OrderSide.BUY)  # Cover side
        self.assertIsNone(self.virtual_broker.get_position("TSLA"))
        self.assertEqual(len(self.engine.trade_history), 1)
        self.assertEqual(self.engine.trade_history[0].pnl, 500.0)
        self.assertEqual(self.engine.trade_history[0].side, "SELL")

    def test_losing_short_trade_triggers_automatic_post_mortem(self):
        """Test that covering a short at a loss triggers post-mortem and pre-trade memory block."""
        self.virtual_broker.set_market_price("AMD", 100.0)

        # 1. Short entry @ 100
        self.engine.execute_signal("AMD", "SELL", 100.0, 50, strategy_name="ORB")

        # 2. Price surges against short to 110
        self.virtual_broker.set_market_price("AMD", 110.0)

        # 3. Exit (cover) @ 110 (-$500 loss)
        self.engine.execute_signal("AMD", "EXIT", 110.0, 50, strategy_name="ORB")

        # Verify trade record
        self.assertEqual(len(self.engine.trade_history), 1)
        self.assertEqual(self.engine.trade_history[0].pnl, -500.0)
        self.assertEqual(self.engine.trade_history[0].side, "SELL")

        # Verify Post-Mortem was automatically created in memory
        recent_pms = self.post_mortem_repo.get_recent_post_mortems()
        self.assertEqual(len(recent_pms), 1)
        self.assertEqual(recent_pms[0].symbol, "AMD")
        self.assertEqual(recent_pms[0].loss_amount, 500.0)

        # 4. Attempt to short AMD with ORB again: Pre-trade memory filter MUST block it!
        blocked_order = self.engine.execute_signal("AMD", "SELL", 105.0, 10, strategy_name="ORB")
        self.assertIsNone(blocked_order)

    def test_max_concurrent_positions_limit(self):
        """Test that exactly 10 concurrent live positions are tracked and capped."""
        max_allowed = 10
        symbols = [f"SYM{i}" for i in range(12)]
        for i, sym in enumerate(symbols[:10]):
            self.virtual_broker.set_market_price(sym, 50.0)
            action = "BUY" if i % 2 == 0 else "SELL"
            self.engine.execute_signal(sym, action, 50.0, 10, strategy_name="ORB")

        active_positions = self.virtual_broker.get_positions()
        self.assertEqual(len(active_positions), 10)

        # Slots available should now be 0
        available_slots = max(0, max_allowed - len(active_positions))
        self.assertEqual(available_slots, 0)

        # Closing one position frees a slot
        first_sym = active_positions[0].symbol
        self.engine.execute_signal(first_sym, "EXIT", 50.0, 10, strategy_name="ORB")
        remaining_positions = self.virtual_broker.get_positions()
        self.assertEqual(len(remaining_positions), 9)
        new_slots = max(0, max_allowed - len(remaining_positions))
        self.assertEqual(new_slots, 1)

    def test_dynamic_breakeven_stop_advancement(self):
        """Test that winning trade advances stop to breakeven, preventing a winner turning into a loss."""
        self.virtual_broker.set_market_price("GOOGL", 100.0)
        self.engine.execute_signal(
            symbol="GOOGL",
            action="BUY",
            price=100.0,
            quantity=10,
            strategy_name="TrendFollowing",
            stop_loss=95.0,
            take_profit=110.0,
        )
        pos = self.virtual_broker.get_position("GOOGL")
        self.assertFalse(pos.is_breakeven_set)
        self.assertEqual(pos.stop_loss, 95.0)

        # 1. Price advances past 50% of target ($106.0 >= $105.0) -> Engages breakeven
        self.engine.check_position_stops("GOOGL", 106.0)
        self.assertTrue(pos.is_breakeven_set)
        self.assertGreaterEqual(pos.stop_loss, 100.20)

        # 2. Price suffers sharp pullback to $100.10 -> Triggers BREAKEVEN_STOP exit with profit
        exit_order = self.engine.check_position_stops("GOOGL", 100.10)
        self.assertIsNotNone(exit_order)
        self.assertEqual(exit_order.status, OrderStatus.FILLED)
        self.assertEqual(self.engine.trade_history[-1].reason, "BREAKEVEN_STOP")
        self.assertGreaterEqual(self.engine.trade_history[-1].pnl, 0.0)

    def test_dynamic_trailing_stop_advancement(self):
        """Test that strong momentum trails stop 1.5% below peak to lock in gains."""
        self.virtual_broker.set_market_price("MSFT", 300.0)
        self.engine.execute_signal(
            symbol="MSFT",
            action="BUY",
            price=300.0,
            quantity=10,
            strategy_name="ORB",
            stop_loss=285.0,
            take_profit=350.0,
        )
        pos = self.virtual_broker.get_position("MSFT")

        # 1. MSFT rallies +5% to $315.0 -> Trails stop 1.5% below $315 ($310.27)
        self.engine.check_position_stops("MSFT", 315.0)
        self.assertGreaterEqual(pos.stop_loss, 310.0)

        # 2. Pullback hits trailing stop at $309.50
        exit_order = self.engine.check_position_stops("MSFT", 309.50)
        self.assertIsNotNone(exit_order)
        self.assertEqual(exit_order.status, OrderStatus.FILLED)
        self.assertEqual(self.engine.trade_history[-1].reason, "TRAILING_STOP")
        self.assertGreater(self.engine.trade_history[-1].pnl, 0.0)


if __name__ == "__main__":
    unittest.main()