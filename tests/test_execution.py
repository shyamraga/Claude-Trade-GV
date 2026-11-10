"""Unit tests for VirtualBroker and ExecutionEngine."""

import shutil
import tempfile
import unittest
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
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

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

        # 4. Now attempt to buy NVDA with ORB again: Pre-trade memory filter MUST block it!
        blocked_order = self.engine.execute_signal("NVDA", "BUY", 95.0, 10, strategy_name="ORB")
        self.assertIsNone(blocked_order)


if __name__ == "__main__":
    unittest.main()