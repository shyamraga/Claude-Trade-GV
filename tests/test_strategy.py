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
        self.assertIsNotNone(buy_signals[0].take_profit, "Golden cross signal must include dynamic take-profit")
        self.assertGreater(buy_signals[0].take_profit, buy_signals[0].price, "Buy take profit must be above entry price")

    def test_macrossover_death_cross_short_signal(self):
        # Create price series where fast EMA crosses below slow EMA (Death Cross)
        bars = []
        prices = [95.0, 97.0, 99.0, 102.0, 105.0, 106.0, 104.0, 100.0, 94.0, 88.0, 82.0]
        for i, price in enumerate(prices):
            bars.append(
                Bar(
                    symbol="TEST",
                    timestamp=self.base_time + timedelta(minutes=i * 15),
                    open=price + 0.5,
                    high=price + 0.5,
                    low=price - 0.5,
                    close=price,
                    volume=1000.0,
                )
            )

        strategy = MACrossoverStrategy(fast_period=3, slow_period=5, atr_multiplier=1.5)
        signals = strategy.generate_signals(bars)
        sell_signals = [s for s in signals if s.action == SignalAction.SELL]
        self.assertGreater(len(sell_signals), 0, "MACrossover should generate SELL (Short) signals on death cross")
        self.assertGreater(sell_signals[0].stop_loss, sell_signals[0].price, "Short stop loss should be above price")
        self.assertIsNotNone(sell_signals[0].take_profit, "Death cross short signal must include dynamic take-profit")
        self.assertLess(sell_signals[0].take_profit, sell_signals[0].price, "Short take profit must be below entry price")

    def test_orb_breakdown_short_signal(self):
        # Opening range: 3 bars between 98 and 102 with avg volume 1000
        bars = []
        prices = [100.0, 101.0, 99.0]
        for i, p in enumerate(prices):
            bars.append(
                Bar(
                    symbol="TEST",
                    timestamp=self.base_time + timedelta(minutes=i * 15),
                    open=p,
                    high=102.0,
                    low=98.0,
                    close=p,
                    volume=1000.0,
                )
            )
        # Bar 4 breaks down below opening low (98.0) to 95.0 on high volume 2500
        bars.append(
            Bar(
                symbol="TEST",
                timestamp=self.base_time + timedelta(minutes=3 * 15),
                open=97.5,
                high=97.8,
                low=94.5,
                close=95.0,
                volume=2500.0,
            )
        )
        # Bar 5 continuation
        bars.append(
            Bar(
                symbol="TEST",
                timestamp=self.base_time + timedelta(minutes=4 * 15),
                open=95.0,
                high=95.5,
                low=93.0,
                close=94.0,
                volume=1500.0,
            )
        )
        strategy = OpeningRangeBreakoutStrategy(opening_bars=3, volume_multiplier=1.5)
        signals = strategy.generate_signals(bars)
        sell_signals = [s for s in signals if s.action == SignalAction.SELL]
        self.assertEqual(len(sell_signals), 1, "ORB should generate SELL (Short) signal on breakdown below opening low")
        self.assertEqual(sell_signals[0].stop_loss, 102.0, "Short stop loss should be at opening high")
        self.assertIsNotNone(sell_signals[0].take_profit, "ORB short breakdown signal must include dynamic take-profit")
        self.assertLess(sell_signals[0].take_profit, sell_signals[0].price, "Short take profit must be below entry price")

    def test_rsi_overbought_bearish_reversion_short_signal(self):
        # Build prices that rally up high (RSI > 70) and then start reversing down (RSI crosses below 70)
        bars = []
        prices = [
            100, 102, 105, 109, 114, 120, 126, 133, 140, 146, 150, 152, 151, 147, 142
        ]
        for i, p in enumerate(prices):
            bars.append(
                Bar(
                    symbol="TEST",
                    timestamp=self.base_time + timedelta(minutes=i * 15),
                    open=float(p - 1),
                    high=float(p + 1),
                    low=float(p - 1),
                    close=float(p),
                    volume=1000.0,
                )
            )
        strategy = RSIMeanReversionStrategy(rsi_period=7, overbought_threshold=70.0)
        signals = strategy.generate_signals(bars)
        sell_signals = [s for s in signals if s.action == SignalAction.SELL]
        self.assertGreater(len(sell_signals), 0, "RSI should generate SELL (Short) signal on bearish reversion from overbought")
        self.assertGreater(sell_signals[0].stop_loss, sell_signals[0].price, "Short stop loss should be above price")
        self.assertIsNotNone(sell_signals[0].take_profit, "RSI short reversion signal must include dynamic take-profit")
        self.assertLess(sell_signals[0].take_profit, sell_signals[0].price, "Short take profit must be below entry price")

    def test_trend_following_downtrend_short_signal(self):
        # 60 bars: first 35 bars ranging around 150-155, then sustained downtrend to 120
        bars = []
        prices = [150.0 + (i % 3) * 0.5 for i in range(35)]
        # Add 25 bars in a strong downtrend
        curr = prices[-1]
        for i in range(25):
            curr -= 1.2
            prices.append(curr)

        for i, p in enumerate(prices):
            bars.append(
                Bar(
                    symbol="TEST",
                    timestamp=self.base_time + timedelta(minutes=i * 15),
                    open=p + 0.5,
                    high=p + 0.8,
                    low=p - 0.8,
                    close=p,
                    volume=1000.0,
                )
            )
        strategy = TrendFollowingStrategy(fast_ema=10, slow_ema=25, rsi_period=14, rsi_lower=50.0, rsi_upper=70.0)
        signals = strategy.generate_signals(bars)
        sell_signals = [s for s in signals if s.action == SignalAction.SELL]
        self.assertGreater(len(sell_signals), 0, "TrendFollowing should generate SELL (Short) signal on downtrend")
        self.assertGreater(sell_signals[0].stop_loss, sell_signals[0].price, "Short stop loss should be above entry price")
        self.assertIsNotNone(sell_signals[0].take_profit, "TrendFollowing short signal must include dynamic take-profit")
        self.assertLess(sell_signals[0].take_profit, sell_signals[0].price, "Short take profit must be below entry price")


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