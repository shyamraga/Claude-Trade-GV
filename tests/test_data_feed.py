import unittest
from datetime import datetime, timezone

from src.data.models import Bar, Quote, TimeFrame
from src.data.alpaca_client import AlpacaDataClient
from src.data.yahoo_client import YahooDataClient
from src.data.feed_manager import FeedManager


class TestDataModels(unittest.TestCase):
    def test_bar_serialization(self):
        now = datetime.now(timezone.utc)
        bar = Bar(
            symbol="AAPL",
            timestamp=now,
            open=150.0,
            high=155.0,
            low=149.0,
            close=154.0,
            volume=10000.0,
            vwap=153.2
        )
        d = bar.to_dict()
        self.assertEqual(d["symbol"], "AAPL")
        self.assertEqual(d["close"], 154.0)

        restored = Bar.from_dict(d)
        self.assertEqual(restored.symbol, bar.symbol)
        self.assertEqual(restored.close, bar.close)
        self.assertEqual(restored.vwap, bar.vwap)

    def test_quote_properties(self):
        now = datetime.now(timezone.utc)
        q = Quote(
            symbol="SPY",
            timestamp=now,
            bid_price=500.0,
            ask_price=500.20,
            bid_size=10.0,
            ask_size=15.0
        )
        self.assertAlmostEqual(q.mid_price, 500.10)
        self.assertAlmostEqual(q.spread, 0.20)
        d = q.to_dict()
        self.assertEqual(d["symbol"], "SPY")
        self.assertEqual(d["spread"], 0.20)


class TestDataClients(unittest.TestCase):
    def test_yahoo_client_bars(self):
        yahoo = YahooDataClient()
        bars = yahoo.get_bars("SPY", TimeFrame.D1, limit=5)
        self.assertGreater(len(bars), 0)
        self.assertEqual(bars[0].symbol, "SPY")
        self.assertGreater(bars[0].close, 0)

    def test_alpaca_client_live_bars(self):
        try:
            alpaca = AlpacaDataClient()
            bars = alpaca.get_bars("SPY", TimeFrame.M15, limit=5)
            self.assertGreater(len(bars), 0)
            self.assertEqual(bars[0].symbol, "SPY")
        except Exception as e:
            self.skipTest(f"Alpaca credentials or connectivity not active: {e}")

    def test_feed_manager_fallback(self):
        feed = FeedManager(primary_provider="alpaca")
        bars = feed.get_bars("AAPL", TimeFrame.M15, limit=5)
        self.assertGreater(len(bars), 0)
        self.assertEqual(bars[0].symbol, "AAPL")
        self.assertGreater(bars[0].close, 0)


if __name__ == "__main__":
    unittest.main()
