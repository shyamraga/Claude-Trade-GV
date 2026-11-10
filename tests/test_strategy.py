import unittest
from datetime import datetime, timezone, timedelta

from src.data.models import Bar
from src.strategy import (
    Signal,
    SignalAction,
    Strategy,
    MACrossoverStrategy,
    RSIMeanReversionStrategy,
    OpeningRangeBreakoutStrategy,
    TrendFollowingStrategy,
    StrategyEngine,
)


class TestSignal(unittest.TestCase):
    def test_signal_creation(self):
        sig = Signal(
            symbol="AAPL",
            action=SignalAction.BUY,
            timestamp=datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc),
            price=150.0,
            confidence=0.85,
            strategy_name="TestStrategy",
            reason="Test signal",
        )
        self.assertEqual(sig.symbol, "AAPL")
        self.assertEqual(sig.action, SignalAction.BUY)
        self.assertEqual(sig.confidence, 0.85)
        self.assertEqual(sig.quantity, 1)

    def test_invalid_confidence_raises(self):
        with self.assertRaises(ValueError):
            Signal(
                symbol="AAPL",
                action=SignalAction.BUY,
                timestamp=datetime.now(timezone.utc),
                price=150.0,
                confidence=1.5,
                strategy_name="Test",
            )

    def test_signal_serialization(self):
        sig = Signal(
            symbol="AAPL",
            action=SignalAction.BUY,
            timestamp=datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc),
            price=150.0,
            confidence=0.80,
            strategy_name="TestStrategy",
            stop_loss=145.0,
            take_profit=155.0,
        )
        sig_dict = sig.to_dict()
        self.assertEqual(sig_dict["symbol"], "AAPL")
        self.assertEqual(sig_dict["action"], "BUY")
        self.assertIn("timestamp", sig_dict)
        self.assertEqual(sig_dict["stop_loss"], 145.0)
        self.assertEqual(sig_dict["take_profit"], 155.0)


class TestTrendPreview(unittest.TestCase):
    """Quick integration tests using synthetic data."""
    base_time = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)

    def test_macrossover_buy_signal(self):
        # Create price series with clear crossover: start declining, then rally
        # Fast EMA starts below slow EMA, then crosses above
        bars = []
        # Decline first (fast below slow), then strong rally (fast crosses above)
        prices = [105.0, 103.0, 101.0, 99.0, 97.0, 96.0, 95.0, 94.0, 100.0, 108.0, 115.0, 120.0]
        for i, price in enumerate(prices):
            bars.append(
                Bar(
                    symbol="TEST",
                    timestamp=self.base_time + timedelta(minutes=i * 15),
                    open=price - 0.5,
                    high=price + 0.5,
                    low=price - 0.5,
                    close=price,
                    volume=1000.0,
                )
            )

        strategy = MACrossoverStrategy(fast_period=3, slow_period=5, atr_multiplier=1.5)
        signals = strategy.generate_signals(bars)
        buy_signals = [s for s in signals if s.action == SignalAction.BUY]

        # Should have golden cross signal when fast crosses above slow
        self.assertGreater(len(buy_signals), 0, "MACrossover should generate BUY signals on crossover")


class TestStrategyEngine(unittest.TestCase):
    def test_strategy_engine_registration(self):
        engine = StrategyEngine()
        strategy = MACrossoverStrategy()
        engine.register_strategy(strategy)

        self.assertEqual(len(engine.list_strategies()), 1)
        self.assertEqual(engine.get_strategy("MA_Crossover"), strategy)

    def test_strategy_engine_removal(self):
        engine = StrategyEngine()
        strategy = MACrossoverStrategy()
        engine.register_strategy(strategy)

        removed = engine.unregister_strategy("MA_Crossover")
        self.assertTrue(removed)
        self.assertIsNone(engine.get_strategy("MA_Crossover"))
        self.assertEqual(len(engine.list_strategies()), 0)

    def test_run_all_strategies(self):
        engine = StrategyEngine()
        engine.register_strategy(MACrossoverStrategy(fast_period=3, slow_period=5))
        engine.register_strategy(RSIMeanReversionStrategy(rsi_period=14, oversold_threshold=30))

        bars = []
        prices = [100.0, 102.0, 101.0, 103.0, 104.0, 102.5, 105.0, 103.0]
        for i, price in enumerate(prices):
            bars.append(
                Bar(
                    symbol="TEST",
                    timestamp=datetime(2026, 11, 10, 9, 0).replace(tzinfo=timezone.utc) + timedelta(minutes=i * 15),
                    open=price,
                    high=price + 0.2,
                    low=price - 0.2,
                    close=price + 0.1,
                    volume=1000.0,
                )
            )

        results = engine.run_all(bars)
        self.assertEqual(len(results), 2)  # Two registered strategies
        self.assertIn("MA_Crossover", results)
        self.assertIn("RSI_MeanReversion", results)

    def test_consensus_signals(self):
        engine = StrategyEngine()
        engine.register_strategy(MACrossoverStrategy(fast_period=3, slow_period=5))
        engine.register_strategy(RSIMeanReversionStrategy(rsi_period=14, oversold_threshold=35, overbought_threshold=65))

        bars = []
        prices = [110.0, 108.0, 107.0, 109.0, 112.0, 115.0, 114.0, 116.0, 118.0, 120.0, 121.0, 119.0, 117.0]
        for i, price in enumerate(prices):
            bars.append(
                Bar(
                    symbol="TEST",
                    timestamp=datetime(2026, 11, 10, 9, 0).replace(tzinfo=timezone.utc) + timedelta(minutes=i * 15),
                    open=price,
                    high=price + 0.5,
                    low=price - 0.5,
                    close=price,
                    volume=1000.0,
                )
            )

        consensus = engine.get_consensus_signals(bars)
        # Consensus signals represent multiple agreeing strategies at same timestamp
        self.assertIsInstance(consensus, list)


if __name__ == "__main__":
    unittest.main()