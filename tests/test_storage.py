import unittest
from datetime import datetime, timezone, timedelta

from src.data.models import Bar, TimeFrame
from src.storage.db import Database
from src.storage.repository import MarketDataRepository
from src.data.pipeline import DataPipeline


class TestStorageAndRepository(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.repo = MarketDataRepository(self.db)

    def tearDown(self):
        self.db.close()

    def test_database_tables_exist(self):
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        self.assertIn("bars", tables)
        self.assertIn("watchlists", tables)
        self.assertIn("tick_events", tables)

    def test_save_and_retrieve_bars(self):
        now = datetime.now(timezone.utc)
        test_bars = [
            Bar(
                symbol="MSFT",
                timestamp=now - timedelta(minutes=15 * (5 - i)),
                open=400.0 + i,
                high=405.0 + i,
                low=398.0 + i,
                close=403.0 + i,
                volume=15000.0 + (i * 100),
                vwap=402.0 + i
            )
            for i in range(5)
        ]
        saved = self.repo.save_bars(test_bars, TimeFrame.M15)
        self.assertEqual(saved, 5)

        # Retrieve all
        retrieved = self.repo.get_bars("MSFT", TimeFrame.M15, limit=10)
        self.assertEqual(len(retrieved), 5)
        # Should be in chronological order
        self.assertLess(retrieved[0].timestamp, retrieved[-1].timestamp)
        self.assertEqual(retrieved[0].close, 403.0)
        self.assertEqual(retrieved[-1].close, 407.0)

    def test_duplicate_prevention_on_upsert(self):
        now = datetime.now(timezone.utc)
        bar = Bar(
            symbol="NVDA",
            timestamp=now,
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=50000.0
        )
        self.repo.save_bars([bar], TimeFrame.M5)
        self.assertEqual(self.repo.get_bar_count("NVDA", TimeFrame.M5), 1)

        # Insert again with updated close price
        updated_bar = Bar(
            symbol="NVDA",
            timestamp=now,
            open=100.0,
            high=106.0,
            low=99.0,
            close=105.5,
            volume=55000.0
        )
        self.repo.save_bars([updated_bar], TimeFrame.M5)
        # Count must remain 1
        self.assertEqual(self.repo.get_bar_count("NVDA", TimeFrame.M5), 1)
        latest = self.repo.get_latest_bar("NVDA", TimeFrame.M5)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.close, 105.5)

    def test_watchlist_operations(self):
        self.repo.add_to_watchlist("TSLA")
        self.repo.add_to_watchlist("AAPL")
        wl = self.repo.get_watchlist()
        self.assertIn("TSLA", wl)
        self.assertIn("AAPL", wl)

        self.repo.remove_from_watchlist("TSLA")
        wl_after = self.repo.get_watchlist()
        self.assertNotIn("TSLA", wl_after)
        self.assertIn("AAPL", wl_after)

    def test_pipeline_sync_symbol(self):
        pipeline = DataPipeline(repo=self.repo)
        saved = pipeline.sync_symbol("SPY", TimeFrame.M15, limit=5)
        self.assertGreater(saved, 0)
        count = self.repo.get_bar_count("SPY", TimeFrame.M15)
        self.assertEqual(count, saved)


if __name__ == "__main__":
    unittest.main()
