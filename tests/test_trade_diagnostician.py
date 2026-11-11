"""Unit tests for TradeDiagnostician root-cause analysis and preventative rule engine."""

import unittest
from datetime import datetime, timedelta

from src.risk.models import TradeRecord
from src.risk.trade_diagnostician import TradeDiagnostician


class TestTradeDiagnostician(unittest.TestCase):
    """Test diagnostic classification across strategies, durations, and market triggers."""

    def test_win_take_profit_diagnosis(self):
        """Test winning trade reaching take-profit."""
        now = datetime.now()
        trade = TradeRecord(
            trade_id="t1",
            symbol="BTC-USD",
            side="BUY",
            quantity=1,
            entry_price=70000.0,
            exit_price=73500.0,
            pnl=3500.0,
            pnl_pct=0.05,
            entry_time=now - timedelta(minutes=45),
            exit_time=now,
            strategy_name="TrendFollowing",
            reason="TAKE_PROFIT",
        )
        cause, market_cond, rule, tags = TradeDiagnostician.diagnose_trade(trade)
        self.assertIn("Flawless execution", cause)
        self.assertIn("Validated setup", rule)
        self.assertIn("crypto", tags)
        self.assertIn("win", tags)

    def test_win_trailing_stop_diagnosis(self):
        """Test winning trade closed via trailing stop."""
        now = datetime.now()
        trade = TradeRecord(
            trade_id="t2",
            symbol="SPY",
            side="BUY",
            quantity=10,
            entry_price=580.0,
            exit_price=592.0,
            pnl=120.0,
            pnl_pct=0.0207,
            entry_time=now - timedelta(minutes=90),
            exit_time=now,
            strategy_name="ORB",
            reason="TRAILING_STOP",
        )
        cause, market_cond, rule, tags = TradeDiagnostician.diagnose_trade(trade)
        self.assertIn("Trailing stop successfully protected profit", cause)
        self.assertIn("Dynamic trailing stop mechanism", rule)
        self.assertIn("us-equity", tags)

    def test_orb_bull_trap_premature_breakout(self):
        """Test ORB premature long breakout failing within 15 minutes."""
        now = datetime.now()
        trade = TradeRecord(
            trade_id="t3",
            symbol="AAPL",
            side="BUY",
            quantity=20,
            entry_price=230.0,
            exit_price=226.0,
            pnl=-80.0,
            pnl_pct=-0.0174,
            entry_time=now - timedelta(minutes=8),
            exit_time=now,
            strategy_name="ORB",
            reason="STOP_LOSS",
        )
        cause, market_cond, rule, tags = TradeDiagnostician.diagnose_trade(trade)
        self.assertIn("Bull Trap", cause)
        self.assertIn("bull-trap", tags)
        self.assertIn("1.5x relative volume", rule)

    def test_orb_failed_continuation(self):
        """Test ORB breakout held >15 min failing on momentum exhaustion."""
        now = datetime.now()
        trade = TradeRecord(
            trade_id="t4",
            symbol="NVDA",
            side="BUY",
            quantity=15,
            entry_price=145.0,
            exit_price=141.0,
            pnl=-60.0,
            pnl_pct=-0.0276,
            entry_time=now - timedelta(minutes=45),
            exit_time=now,
            strategy_name="ORB",
            reason="STOP_LOSS",
        )
        cause, market_cond, rule, tags = TradeDiagnostician.diagnose_trade(trade)
        self.assertIn("Failed Continuation", cause)
        self.assertIn("failed-continuation", tags)
        self.assertIn("advance stop-loss to entry", rule)

    def test_orb_bear_trap_breakdown(self):
        """Test ORB Short breakdown quickly failing into squeeze (<15 min)."""
        now = datetime.now()
        trade = TradeRecord(
            trade_id="t5",
            symbol="TSLA",
            side="SELL",
            quantity=10,
            entry_price=220.0,
            exit_price=225.0,
            pnl=-50.0,
            pnl_pct=-0.0227,
            entry_time=now - timedelta(minutes=6),
            exit_time=now,
            strategy_name="ORB",
            reason="STOP_LOSS",
        )
        cause, market_cond, rule, tags = TradeDiagnostician.diagnose_trade(trade)
        self.assertIn("Bear Trap", cause)
        self.assertIn("bear-trap", tags)
        self.assertIn("do not short if the broader market index", rule)

    def test_trend_following_exhaustion(self):
        """Test TrendFollowing buying at late-cycle top."""
        now = datetime.now()
        trade = TradeRecord(
            trade_id="t6",
            symbol="COIN",
            side="BUY",
            quantity=10,
            entry_price=300.0,
            exit_price=288.0,
            pnl=-120.0,
            pnl_pct=-0.04,
            entry_time=now - timedelta(minutes=8),
            exit_time=now,
            strategy_name="TrendFollowing",
            reason="STOP_LOSS",
        )
        cause, market_cond, rule, tags = TradeDiagnostician.diagnose_trade(trade)
        self.assertIn("Late Trend Exhaustion", cause)
        self.assertIn("trend-exhaustion", tags)
        self.assertIn("2.5x ATR", rule)

    def test_rsi_reversion_falling_knife(self):
        """Test RSI long buying into persistent liquidation waterfall."""
        now = datetime.now()
        trade = TradeRecord(
            trade_id="t7",
            symbol="SOL-USD",
            side="BUY",
            quantity=5,
            entry_price=88.0,
            exit_price=82.0,
            pnl=-30.0,
            pnl_pct=-0.068,
            entry_time=now - timedelta(minutes=25),
            exit_time=now,
            strategy_name="RSIReversion",
            reason="STOP_LOSS",
        )
        cause, market_cond, rule, tags = TradeDiagnostician.diagnose_trade(trade)
        self.assertIn("Falling Knife", cause)
        self.assertIn("falling-knife", tags)
        self.assertIn("bullish divergence candle", rule)

    def test_ma_crossover_consolidation_lag(self):
        """Test Moving Average crossover whipsaw in low-ADX chop."""
        now = datetime.now()
        trade = TradeRecord(
            trade_id="t8",
            symbol="RELIANCE.NS",
            side="BUY",
            quantity=10,
            entry_price=1350.0,
            exit_price=1330.0,
            pnl=-200.0,
            pnl_pct=-0.0148,
            entry_time=now - timedelta(minutes=60),
            exit_time=now,
            strategy_name="MACrossover",
            reason="STOP_LOSS",
        )
        cause, market_cond, rule, tags = TradeDiagnostician.diagnose_trade(trade)
        self.assertIn("Moving Average Lag", cause)
        self.assertIn("ma-lag-whipsaw", tags)
        self.assertIn("indian-equity", tags)
        self.assertIn("ADX > 22", rule)


if __name__ == "__main__":
    unittest.main()
