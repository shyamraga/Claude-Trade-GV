"""Unit tests for MarketHoursManager and holiday calendars across global timezones."""

import unittest
from datetime import datetime, date, time
from zoneinfo import ZoneInfo

from src.risk.market_hours import (
    MarketHoursManager,
    MarketType,
    TZ_US,
    TZ_INDIA,
    TZ_UTC,
    get_easter_date,
    get_nth_weekday_of_month,
)


class TestMarketTypeClassification(unittest.TestCase):
    """Test classification of assets into US Equity, Indian Equity, and Crypto."""

    def test_crypto_symbols(self):
        crypto_symbols = [
            "BTC-USD",
            "ETH-USD",
            "SOL-USD",
            "AVAX-USD",
            "DOGE-USD",
            "BNB-USD",
            "XRP-USD",
            "ADA-USD",
            "BTC/USD",
            "ETHUSDT",
        ]
        for sym in crypto_symbols:
            self.assertEqual(
                MarketHoursManager.get_market_type(sym),
                MarketType.CRYPTO,
                f"{sym} should be classified as CRYPTO",
            )

    def test_indian_equity_symbols(self):
        indian_symbols = [
            "RELIANCE.NS",
            "TCS.NS",
            "INFY.NS",
            "HDFCBANK.NS",
            "TATAMOTORS.BO",
            "WIPRO.BO",
        ]
        for sym in indian_symbols:
            self.assertEqual(
                MarketHoursManager.get_market_type(sym),
                MarketType.INDIA_EQUITY,
                f"{sym} should be classified as INDIA_EQUITY",
            )

    def test_us_equity_symbols(self):
        us_symbols = ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN", "SPY", "QQQ"]
        for sym in us_symbols:
            self.assertEqual(
                MarketHoursManager.get_market_type(sym),
                MarketType.US_EQUITY,
                f"{sym} should be classified as US_EQUITY",
            )


class TestUSMarketHours(unittest.TestCase):
    """Test US equity trading hours (09:30 - 16:00 ET), weekends, holidays, and early closes."""

    def test_us_regular_hours_open(self):
        # Wednesday at 10:30 AM ET
        dt_open = datetime(2026, 11, 18, 10, 30, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_open)
        self.assertTrue(is_open)
        self.assertIn("OPEN", msg)

    def test_us_premarket_closed(self):
        # Wednesday at 08:30 AM ET
        dt_pre = datetime(2026, 11, 18, 8, 30, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_pre)
        self.assertFalse(is_open)
        self.assertIn("PRE-MARKET", msg)

    def test_us_afterhours_closed(self):
        # Wednesday at 16:30 ET
        dt_after = datetime(2026, 11, 18, 16, 30, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_after)
        self.assertFalse(is_open)
        self.assertIn("AFTER-HOURS", msg)

    def test_us_weekend_closed(self):
        # Saturday at 12:00 PM ET
        dt_sat = datetime(2026, 11, 14, 12, 0, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_sat)
        self.assertFalse(is_open)
        self.assertIn("CLOSED for weekend (Saturday", msg)

        # Sunday at 12:00 PM ET
        dt_sun = datetime(2026, 11, 15, 12, 0, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_sun)
        self.assertFalse(is_open)
        self.assertIn("CLOSED for weekend (Sunday", msg)

    def test_us_thanksgiving_holiday_closed(self):
        # Thanksgiving 2026: Nov 26 (4th Thursday in November)
        dt_thanksgiving = datetime(2026, 11, 26, 11, 0, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_thanksgiving)
        self.assertFalse(is_open)
        self.assertIn("Thanksgiving Day", msg)

    def test_us_black_friday_early_close(self):
        # Black Friday 2026: Nov 27 (day after Thanksgiving)
        # Should be open 09:30 - 13:00 ET
        dt_bf_morning = datetime(2026, 11, 27, 10, 30, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_bf_morning)
        self.assertTrue(is_open, "Black Friday should be OPEN at 10:30 ET")
        self.assertIn("13:00 ET", msg)

        # After 13:00 ET, Black Friday is CLOSED
        dt_bf_afternoon = datetime(2026, 11, 27, 13, 15, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_bf_afternoon)
        self.assertFalse(is_open, "Black Friday should be CLOSED after 13:00 ET")
        self.assertIn("Black Friday", msg)

    def test_us_christmas_eve_early_close(self):
        # Christmas Eve 2026: Dec 24 (Thursday)
        dt_xmas_eve_open = datetime(2026, 12, 24, 11, 0, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_xmas_eve_open)
        self.assertTrue(is_open, "Christmas Eve should be OPEN at 11:00 ET")

        dt_xmas_eve_closed = datetime(2026, 12, 24, 13, 30, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_xmas_eve_closed)
        self.assertFalse(is_open, "Christmas Eve should be CLOSED after 13:00 ET")

    def test_us_christmas_holiday_closed(self):
        # Christmas Day 2026: Dec 25 (Friday)
        dt_xmas = datetime(2026, 12, 25, 11, 0, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_xmas)
        self.assertFalse(is_open)
        self.assertIn("Christmas Day", msg)

    def test_easter_and_good_friday_calculation(self):
        # Easter 2026 is April 5; Good Friday is April 3
        easter_2026 = get_easter_date(2026)
        self.assertEqual(easter_2026, date(2026, 4, 5))

        dt_good_friday = datetime(2026, 4, 3, 11, 0, tzinfo=TZ_US)
        is_open, msg = MarketHoursManager.is_us_market_open(dt_good_friday)
        self.assertFalse(is_open)
        self.assertIn("Good Friday", msg)


class TestIndianMarketHours(unittest.TestCase):
    """Test Indian equity trading hours (09:15 - 15:30 IST), weekends, and NSE holidays."""

    def test_indian_regular_hours_open(self):
        # Wednesday at 11:30 AM IST
        dt_open = datetime(2026, 11, 18, 11, 30, tzinfo=TZ_INDIA)
        is_open, msg = MarketHoursManager.is_indian_market_open(dt_open)
        self.assertTrue(is_open)
        self.assertIn("Indian Market is OPEN", msg)

    def test_indian_premarket_closed(self):
        # Wednesday at 08:45 AM IST (Pre-market)
        dt_pre = datetime(2026, 11, 18, 8, 45, tzinfo=TZ_INDIA)
        is_open, msg = MarketHoursManager.is_indian_market_open(dt_pre)
        self.assertFalse(is_open)
        self.assertIn("PRE-MARKET", msg)

    def test_indian_postmarket_closed(self):
        # Wednesday at 15:45 IST (After 15:30 close)
        dt_post = datetime(2026, 11, 18, 15, 45, tzinfo=TZ_INDIA)
        is_open, msg = MarketHoursManager.is_indian_market_open(dt_post)
        self.assertFalse(is_open)
        self.assertIn("POST-MARKET", msg)

    def test_indian_weekend_closed(self):
        # Saturday at 11:00 AM IST
        dt_sat = datetime(2026, 11, 14, 11, 0, tzinfo=TZ_INDIA)
        is_open, msg = MarketHoursManager.is_indian_market_open(dt_sat)
        self.assertFalse(is_open)
        self.assertIn("CLOSED for weekend", msg)

    def test_indian_fixed_holidays_closed(self):
        # Republic Day: Jan 26
        dt_republic = datetime(2026, 1, 26, 11, 0, tzinfo=TZ_INDIA)
        is_open, msg = MarketHoursManager.is_indian_market_open(dt_republic)
        self.assertFalse(is_open)
        self.assertIn("Republic Day", msg)

        # Independence Day: Aug 15
        dt_indep = datetime(2026, 8, 15, 11, 0, tzinfo=TZ_INDIA)
        is_open, msg = MarketHoursManager.is_indian_market_open(dt_indep)
        self.assertFalse(is_open)

        # Gandhi Jayanti: Oct 2
        dt_gandhi = datetime(2026, 10, 2, 11, 0, tzinfo=TZ_INDIA)
        is_open, msg = MarketHoursManager.is_indian_market_open(dt_gandhi)
        self.assertFalse(is_open)
        self.assertIn("Mahatma Gandhi Jayanti", msg)

    def test_indian_floating_holidays_closed(self):
        # Holi 2026: March 4
        dt_holi = datetime(2026, 3, 4, 11, 0, tzinfo=TZ_INDIA)
        is_open, msg = MarketHoursManager.is_indian_market_open(dt_holi)
        self.assertFalse(is_open)
        self.assertIn("Holiday", msg)


class TestCryptoMarketHours(unittest.TestCase):
    """Test Crypto 24/7 continuous trading with zero interruptions."""

    def test_crypto_always_open(self):
        # Saturday midnight
        is_open, msg = MarketHoursManager.is_crypto_market_open()
        self.assertTrue(is_open)
        self.assertIn("24/7", msg)

        # Check via is_market_open for crypto symbol
        dt_weekend = datetime(2026, 11, 15, 3, 0, tzinfo=TZ_UTC)
        is_open, _ = MarketHoursManager.is_market_open("BTC-USD", dt=dt_weekend)
        self.assertTrue(is_open)

        is_open_eth, _ = MarketHoursManager.is_market_open("ETH-USD", dt=dt_weekend)
        self.assertTrue(is_open_eth)


class TestSymbolFilteringAcrossTimezones(unittest.TestCase):
    """Test timezone-aware symbol partitioning during live market sessions."""

    def test_filtering_during_indian_market_hours(self):
        # Wednesday at 10:30 AM IST (05:00 UTC / 00:00 ET midnight)
        dt_india_session = datetime(2026, 11, 18, 10, 30, tzinfo=TZ_INDIA)
        symbols = ["AAPL", "MSFT", "RELIANCE.NS", "TCS.NS", "BTC-USD", "ETH-USD"]

        open_symbols = MarketHoursManager.filter_open_symbols(symbols, dt=dt_india_session)

        # Indian equities and Crypto should be open
        self.assertIn("RELIANCE.NS", open_symbols)
        self.assertIn("TCS.NS", open_symbols)
        self.assertIn("BTC-USD", open_symbols)
        self.assertIn("ETH-USD", open_symbols)

        # US equities should be closed (midnight ET)
        self.assertNotIn("AAPL", open_symbols)
        self.assertNotIn("MSFT", open_symbols)

    def test_filtering_during_us_market_hours(self):
        # Wednesday at 11:00 AM ET (16:00 UTC / 21:30 IST at night)
        dt_us_session = datetime(2026, 11, 18, 11, 0, tzinfo=TZ_US)
        symbols = ["AAPL", "MSFT", "RELIANCE.NS", "TCS.NS", "BTC-USD", "ETH-USD"]

        open_symbols = MarketHoursManager.filter_open_symbols(symbols, dt=dt_us_session)

        # US equities and Crypto should be open
        self.assertIn("AAPL", open_symbols)
        self.assertIn("MSFT", open_symbols)
        self.assertIn("BTC-USD", open_symbols)
        self.assertIn("ETH-USD", open_symbols)

        # Indian equities should be closed (21:30 IST)
        self.assertNotIn("RELIANCE.NS", open_symbols)
        self.assertNotIn("TCS.NS", open_symbols)

    def test_filtering_during_weekend(self):
        # Sunday at 12:00 PM UTC
        dt_weekend = datetime(2026, 11, 15, 12, 0, tzinfo=TZ_UTC)
        symbols = ["AAPL", "MSFT", "RELIANCE.NS", "TCS.NS", "BTC-USD", "ETH-USD"]

        open_symbols = MarketHoursManager.filter_open_symbols(symbols, dt=dt_weekend)

        # ONLY Crypto trades on weekends
        self.assertEqual(set(open_symbols), {"BTC-USD", "ETH-USD"})

    def test_open_markets_summary(self):
        dt = datetime(2026, 11, 18, 11, 0, tzinfo=TZ_US)
        summary = MarketHoursManager.get_open_markets_summary(dt)

        self.assertIn("us_market", summary)
        self.assertIn("indian_market", summary)
        self.assertIn("crypto_market", summary)
        self.assertTrue(summary["us_market"]["open"])
        self.assertFalse(summary["indian_market"]["open"])
        self.assertTrue(summary["crypto_market"]["open"])


if __name__ == "__main__":
    unittest.main()
