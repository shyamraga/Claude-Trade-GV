"""Unit tests for risk management, circuit breakers, and post-mortem learning loop."""

import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from src.risk.models import RiskConfig, TradeRecord
from src.risk.circuit_breaker import CircuitBreaker
from src.risk.post_mortem import PostMortemRepository, TradePostMortem


class TestCircuitBreaker(unittest.TestCase):
    """Test portfolio circuit breakers and cooldown logic."""

    def setUp(self):
        self.config = RiskConfig(
            max_daily_drawdown_pct=0.03,  # 3%
            consecutive_loss_limit=3,
            cooldown_duration_hours=4.0,
        )
        self.cb = CircuitBreaker(self.config)
        self.cb.reset_daily_metrics(starting_equity=100000.0)

    def test_pre_trade_normal_approval(self):
        """Test normal pre-trade check."""
        res = self.cb.validate_pre_trade("AAPL", "BUY", price=150.0, proposed_shares=50)
        self.assertTrue(res.approved)
        self.assertEqual(res.risk_level, "NORMAL")
        self.assertEqual(res.max_allowed_shares, 50)
        self.assertEqual(res.calculated_stop_loss, 147.0)  # 2% below 150
        self.assertEqual(res.calculated_take_profit, 156.0)  # 4% above 150

    def test_position_size_scaling(self):
        """Test that position size is scaled down if exceeding 10% max allocation."""
        # 100k equity, 10% is 10k. 200 shares @ $100 = 20k -> should scale to 100 shares.
        res = self.cb.validate_pre_trade("SPY", "BUY", price=100.0, proposed_shares=200)
        self.assertTrue(res.approved)
        self.assertEqual(res.risk_level, "ELEVATED")
        self.assertEqual(res.max_allowed_shares, 100)

    def test_three_consecutive_losses_triggers_4h_cooldown(self):
        """Test that 3 consecutive losses pause trading for 4 hours."""
        t1 = TradeRecord("t1", "AAPL", "BUY", 10, 150, 145, -50.0, -0.033, datetime.now(), datetime.now(), "ORB")
        t2 = TradeRecord("t2", "TSLA", "BUY", 10, 200, 195, -50.0, -0.025, datetime.now(), datetime.now(), "ORB")
        t3 = TradeRecord("t3", "NVDA", "BUY", 10, 120, 115, -50.0, -0.041, datetime.now(), datetime.now(), "ORB")

        self.cb.record_trade(t1)
        self.assertFalse(self.cb.is_cooldown_active())

        self.cb.record_trade(t2)
        self.assertFalse(self.cb.is_cooldown_active())

        # 3rd loss triggers 4-hour cooldown
        self.cb.record_trade(t3)
        self.assertTrue(self.cb.is_cooldown_active())
        self.assertIn("consecutive", self.cb.cooldown_reason)

        # Pre-trade checks must now be blocked
        res = self.cb.validate_pre_trade("MSFT", "BUY", 400.0, 10)
        self.assertFalse(res.approved)
        self.assertEqual(res.risk_level, "BLOCKED")

    def test_win_resets_consecutive_loss_counter(self):
        """Test that a profitable trade resets the loss counter."""
        t1 = TradeRecord("t1", "AAPL", "BUY", 10, 150, 145, -50.0, -0.033, datetime.now(), datetime.now(), "ORB")
        t2 = TradeRecord("t2", "TSLA", "BUY", 10, 200, 210, 100.0, 0.05, datetime.now(), datetime.now(), "ORB")
        t3 = TradeRecord("t3", "NVDA", "BUY", 10, 120, 115, -50.0, -0.041, datetime.now(), datetime.now(), "ORB")

        self.cb.record_trade(t1)
        self.assertEqual(self.cb.consecutive_losses, 1)

        self.cb.record_trade(t2)  # Win
        self.assertEqual(self.cb.consecutive_losses, 0)

        self.cb.record_trade(t3)
        self.assertEqual(self.cb.consecutive_losses, 1)
        self.assertFalse(self.cb.is_cooldown_active())

    def test_max_daily_drawdown_trigger(self):
        """Test that exceeding max daily drawdown pauses trading."""
        # Starting equity 100k, 3% max drawdown is 3k loss
        large_loss = TradeRecord("t1", "SPY", "BUY", 100, 400, 360, -4000.0, -0.10, datetime.now(), datetime.now(), "Trend")
        self.cb.record_trade(large_loss)

        self.assertTrue(self.cb.is_cooldown_active())
        self.assertIn("drawdown", self.cb.cooldown_reason.lower())

    def test_manual_override(self):
        """Test user manual override clears the cooldown."""
        t1 = TradeRecord("t1", "A", "BUY", 1, 10, 5, -5, -0.5, datetime.now(), datetime.now(), "S")
        t2 = TradeRecord("t2", "B", "BUY", 1, 10, 5, -5, -0.5, datetime.now(), datetime.now(), "S")
        t3 = TradeRecord("t3", "C", "BUY", 1, 10, 5, -5, -0.5, datetime.now(), datetime.now(), "S")
        self.cb.record_trade(t1)
        self.cb.record_trade(t2)
        self.cb.record_trade(t3)
        self.assertTrue(self.cb.is_cooldown_active())

        # Activate user override
        self.cb.set_manual_override(True)
        self.assertFalse(self.cb.is_cooldown_active())


class TestPostMortemRepository(unittest.TestCase):
    """Test post-mortem continuous learning memory."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo = PostMortemRepository(memory_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_create_and_load_post_mortem(self):
        """Test creating post-mortem and verifying file persistence."""
        trade = TradeRecord(
            trade_id="trade_123",
            symbol="NVDA",
            side="BUY",
            quantity=50,
            entry_price=120.0,
            exit_price=114.0,
            pnl=-300.0,
            pnl_pct=-0.05,
            entry_time=datetime(2026, 11, 10, 9, 30),
            exit_time=datetime(2026, 11, 10, 10, 15),
            strategy_name="OpeningRangeBreakout",
        )

        pm = self.repo.create_post_mortem(
            trade=trade,
            root_cause="False breakout on low volume",
            market_condition="Choppy pre-market open",
            preventative_rule="Require volume > 1.5x 20-day SMA before taking ORB breakout",
            tags=["NVDA", "ORB", "volume_trap"],
        )

        self.assertEqual(pm.symbol, "NVDA")
        self.assertEqual(pm.loss_amount, 300.0)

        # Check files were written
        json_files = list(self.temp_dir.glob("*.json"))
        md_files = list(self.temp_dir.glob("*.md"))
        self.assertEqual(len(json_files), 1)
        self.assertEqual(len(md_files), 1)

    def test_pre_trade_memory_filter(self):
        """Test pre-trade filter warns and blocks repeating known failure setups."""
        trade = TradeRecord(
            trade_id="t_fail",
            symbol="TSLA",
            side="BUY",
            quantity=20,
            entry_price=250.0,
            exit_price=240.0,
            pnl=-200.0,
            pnl_pct=-0.04,
            entry_time=datetime.now() - timedelta(hours=2),
            exit_time=datetime.now() - timedelta(hours=1),
            strategy_name="MACrossover",
        )
        self.repo.create_post_mortem(
            trade=trade,
            root_cause="Choppy consolidation whipped out MA crossover",
            market_condition="Sideways low ATR market",
            preventative_rule="Avoid MACrossover when ATR is below 14-day average",
        )

        # Check pre-trade for same symbol and strategy
        allowed, reason = self.repo.check_pre_trade_filter("TSLA", "MACrossover")
        self.assertFalse(allowed)
        self.assertIn("prior loss with MACrossover", reason)
        self.assertIn("Avoid MACrossover", reason)

        # Check different symbol - should pass
        allowed_other, _ = self.repo.check_pre_trade_filter("AAPL", "MACrossover")
        self.assertTrue(allowed_other)


if __name__ == "__main__":
    unittest.main()