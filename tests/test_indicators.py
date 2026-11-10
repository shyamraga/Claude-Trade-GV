import unittest
from datetime import datetime, timezone, timedelta
import math

from src.data.models import Bar
from src.indicators.calculator import IndicatorCalculator
from src.indicators.models import MACDResult, BollingerBandsResult, IndicatorSnapshot


class TestIndicatorCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = IndicatorCalculator()
        self.base_time = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)

    def test_sma_calculation(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        sma_3 = self.calc.sma(data, 3)
        self.assertEqual(len(sma_3), 5)
        self.assertIsNone(sma_3[0])
        self.assertIsNone(sma_3[1])
        self.assertAlmostEqual(sma_3[2], 2.0, places=5)
        self.assertAlmostEqual(sma_3[3], 3.0, places=5)
        self.assertAlmostEqual(sma_3[4], 4.0, places=5)

        # Insufficient data
        sma_short = self.calc.sma([1.0, 2.0], 5)
        self.assertEqual(sma_short, [None, None])

    def test_ema_calculation(self):
        data = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        # Period 3: multiplier = 2 / (3 + 1) = 0.5
        # Index 2: SMA = (10+11+12)/3 = 11.0
        # Index 3: (13 - 11.0) * 0.5 + 11.0 = 12.0
        # Index 4: (14 - 12.0) * 0.5 + 12.0 = 13.0
        # Index 5: (15 - 13.0) * 0.5 + 13.0 = 14.0
        ema_3 = self.calc.ema(data, 3)
        self.assertEqual(len(ema_3), 6)
        self.assertIsNone(ema_3[0])
        self.assertIsNone(ema_3[1])
        self.assertAlmostEqual(ema_3[2], 11.0, places=5)
        self.assertAlmostEqual(ema_3[3], 12.0, places=5)
        self.assertAlmostEqual(ema_3[4], 13.0, places=5)
        self.assertAlmostEqual(ema_3[5], 14.0, places=5)

    def test_rsi_extremes(self):
        # Strictly rising prices -> RSI = 100
        rising = [10.0 + i for i in range(25)]
        rsi_rising = self.calc.rsi(rising, period=14)
        self.assertEqual(len(rsi_rising), 25)
        self.assertIsNone(rsi_rising[13])
        self.assertEqual(rsi_rising[14], 100.0)
        self.assertEqual(rsi_rising[-1], 100.0)

        # Strictly falling prices -> RSI = 0
        falling = [50.0 - i for i in range(25)]
        rsi_falling = self.calc.rsi(falling, period=14)
        self.assertEqual(rsi_falling[14], 0.0)
        self.assertEqual(rsi_falling[-1], 0.0)

    def test_rsi_oscillating(self):
        # Oscillating prices
        prices = [100.0, 102.0, 101.0, 103.0, 102.5, 104.0, 103.0, 105.0,
                  104.0, 106.0, 105.0, 107.0, 106.0, 108.0, 107.0, 109.0,
                  108.5, 110.0, 109.0, 111.0, 110.0, 112.0]
        rsi_res = self.calc.rsi(prices, period=14)
        for i, val in enumerate(rsi_res):
            if i >= 14:
                self.assertIsNotNone(val)
                self.assertGreaterEqual(val, 0.0)
                self.assertLessEqual(val, 100.0)

    def test_macd_calculation(self):
        # 50 data points to allow slow EMA (26) and signal line (9)
        prices = [100.0 + math.sin(i / 3.0) * 5.0 + (i * 0.2) for i in range(50)]
        res = self.calc.macd(prices, fast_period=12, slow_period=26, signal_period=9)

        self.assertIsInstance(res, MACDResult)
        self.assertEqual(len(res.macd), 50)
        self.assertEqual(len(res.signal), 50)
        self.assertEqual(len(res.histogram), 50)

        # Before slow_period - 1 (25), MACD should be None
        self.assertIsNone(res.macd[24])
        self.assertIsNotNone(res.macd[25])

        # Signal line needs 26 - 1 + 9 - 1 = 33 data points to be warmed up
        self.assertIsNotNone(res.latest_macd)
        self.assertIsNotNone(res.latest_signal)
        self.assertIsNotNone(res.latest_histogram)

        # Histogram = MACD - Signal
        diff = res.latest_macd - res.latest_signal
        self.assertAlmostEqual(res.latest_histogram, diff, places=4)

    def test_bollinger_bands(self):
        # Constant prices: std = 0, upper = middle = lower
        constant_prices = [100.0] * 25
        bb_const = self.calc.bollinger_bands(constant_prices, period=20, num_std=2.0)
        self.assertIsInstance(bb_const, BollingerBandsResult)
        self.assertAlmostEqual(bb_const.latest_middle, 100.0, places=4)
        self.assertAlmostEqual(bb_const.latest_upper, 100.0, places=4)
        self.assertAlmostEqual(bb_const.latest_lower, 100.0, places=4)
        self.assertEqual(bb_const.latest_percent_b, 0.5)

        # Volatile prices
        volatile_prices = [100.0 + (i % 5) * 2.0 for i in range(30)]
        bb_vol = self.calc.bollinger_bands(volatile_prices, period=20, num_std=2.0)
        self.assertGreater(bb_vol.latest_upper, bb_vol.latest_middle)
        self.assertGreater(bb_vol.latest_middle, bb_vol.latest_lower)
        self.assertGreater(bb_vol.bandwidth[-1], 0.0)

    def test_atr_calculation(self):
        bars = []
        for i in range(25):
            bars.append(
                Bar(
                    symbol="TEST",
                    timestamp=self.base_time + timedelta(minutes=15 * i),
                    open=100.0 + i,
                    high=105.0 + i,
                    low=98.0 + i,
                    close=103.0 + i,
                    volume=1000.0,
                )
            )
        atr_vals = self.calc.atr(bars, period=14)
        self.assertEqual(len(atr_vals), 25)
        self.assertIsNone(atr_vals[12])
        self.assertIsNotNone(atr_vals[13])
        self.assertIsNotNone(atr_vals[-1])
        # High - Low is 7.0, so ATR should be around 7.0
        self.assertAlmostEqual(atr_vals[-1], 7.0, places=1)

    def test_vwap_calculation(self):
        # 3 bars on day 1, 2 bars on day 2
        day1 = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)
        day2 = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)
        bars = [
            Bar(symbol="TEST", timestamp=day1, open=10, high=12, low=8, close=10, volume=100),   # TP=10, Vol=100, Cum=1000/100 = 10
            Bar(symbol="TEST", timestamp=day1 + timedelta(hours=1), open=10, high=22, low=18, close=20, volume=100), # TP=20, Vol=100, Cum=(1000+2000)/200 = 15
            Bar(symbol="TEST", timestamp=day2, open=30, high=32, low=28, close=30, volume=100),   # New day reset: TP=30, Vol=100 -> VWAP = 30
        ]
        vwap_res = self.calc.vwap(bars)
        self.assertEqual(len(vwap_res), 3)
        self.assertAlmostEqual(vwap_res[0], 10.0, places=2)
        self.assertAlmostEqual(vwap_res[1], 15.0, places=2)
        self.assertAlmostEqual(vwap_res[2], 30.0, places=2)

    def test_snapshot_generation(self):
        bars = [
            Bar(
                symbol="AAPL",
                timestamp=self.base_time + timedelta(minutes=15 * i),
                open=150.0 + i * 0.5,
                high=152.0 + i * 0.5,
                low=149.0 + i * 0.5,
                close=151.0 + i * 0.5,
                volume=10000.0,
            )
            for i in range(60)
        ]
        snap = self.calc.snapshot(bars)
        self.assertIsNotNone(snap)
        self.assertEqual(snap.symbol, "AAPL")
        self.assertIsNotNone(snap.sma_20)
        self.assertIsNotNone(snap.sma_50)
        self.assertIsNotNone(snap.ema_9)
        self.assertIsNotNone(snap.ema_21)
        self.assertIsNotNone(snap.ema_50)
        self.assertIsNotNone(snap.rsi_14)
        self.assertIsNotNone(snap.macd)
        self.assertIsNotNone(snap.macd_signal)
        self.assertIsNotNone(snap.bb_upper)
        self.assertIsNotNone(snap.atr_14)
        self.assertIsNotNone(snap.vwap)

        # Test dictionary serialization
        snap_dict = snap.to_dict()
        self.assertEqual(snap_dict["symbol"], "AAPL")
        self.assertIn("timestamp", snap_dict)
        self.assertIn("rsi_14", snap_dict)


if __name__ == "__main__":
    unittest.main()
