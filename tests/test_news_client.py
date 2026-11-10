"""Tests for news client and AI models."""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

from src.ai.models import NewsArticle, SentimentAnalysis, MarketContext
from src.ai.news_client import NewsAPIClient, NewsAPIError, RateLimitError


class TestNewsArticle(unittest.TestCase):
    """Test NewsArticle data model."""

    def test_serialization(self):
        """Test to_dict serialization."""
        article = NewsArticle(
            symbol="AAPL",
            title="Apple Beats Q4 Earnings",
            description="Apple reported strong Q4 results",
            source="CNBC",
            published_at=datetime(2026, 11, 10, 12, 0, 0),
            url="https://example.com/article",
            content_snippet="Full article text...",
        )

        data = article.to_dict()
        self.assertEqual(data["symbol"], "AAPL")
        self.assertEqual(data["title"], "Apple Beats Q4 Earnings")
        self.assertIsInstance(data["published_at"], str)

    def test_deserialization(self):
        """Test from_dict deserialization."""
        data = {
            "symbol": "AAPL",
            "title": "Apple Stock Rises",
            "description": "Stock up 5%",
            "source": "Reuters",
            "published_at": "2026-11-10T12:00:00",
            "url": "https://example.com",
        }

        article = NewsArticle.from_dict(data)
        self.assertEqual(article.symbol, "AAPL")
        self.assertEqual(article.title, "Apple Stock Rises")
        self.assertIsInstance(article.published_at, datetime)


class TestSentimentAnalysis(unittest.TestCase):
    """Test SentimentAnalysis data model."""

    def test_sentiment_bullish_modulation(self):
        """Test bullish sentiment modulation."""
        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="bullish",
            confidence=0.85,
            themes=["earnings beat", "guidance raise"],
            risks=[],
            summary="Strong fundamentals",
        )

        modulation = sentiment.to_signal_modulation()
        self.assertGreater(modulation, 1.0)
        self.assertLess(modulation, 1.15)
        self.assertAlmostEqual(modulation, 1.0 + (0.85 * 0.15), places=2)

    def test_sentiment_bearish_modulation(self):
        """Test bearish sentiment modulation."""
        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="bearish",
            confidence=0.75,
            themes=[],
            risks=["regulatory pressure"],
            summary="Negative outlook",
        )

        modulation = sentiment.to_signal_modulation()
        self.assertLess(modulation, 1.0)
        self.assertGreater(modulation, 0.8)

    def test_sentiment_neutral_modulation(self):
        """Test neutral sentiment modulation."""
        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="neutral",
            confidence=0.5,
        )

        modulation = sentiment.to_signal_modulation()
        self.assertEqual(modulation, 1.0)


class TestMarketContext(unittest.TestCase):
    """Test MarketContext aggregation."""

    def test_is_stale_fresh_cache(self):
        """Test that recent cache is not stale."""
        context = MarketContext(
            symbol="AAPL",
            news_articles=[],
            cached_at=datetime.now(),
        )

        # Fresh cache should not be stale
        self.assertFalse(context.is_stale(ttl_minutes=30))

    def test_is_stale_old_cache(self):
        """Test that old cache is stale."""
        context = MarketContext(
            symbol="AAPL",
            news_articles=[],
            cached_at=datetime.now() - timedelta(minutes=35),
        )

        # Old cache should be stale
        self.assertTrue(context.is_stale(ttl_minutes=30))

    def test_serialization_roundtrip(self):
        """Test serialize and deserialize."""
        article = NewsArticle(
            symbol="AAPL",
            title="Test Article",
            source="Test",
            published_at=datetime.now(),
            url="https://test.com",
        )

        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="bullish",
            confidence=0.8,
        )

        context = MarketContext(
            symbol="AAPL",
            news_articles=[article],
            sentiment=sentiment,
        )

        data = context.to_dict()
        restored = MarketContext.from_dict(data)

        self.assertEqual(restored.symbol, "AAPL")
        self.assertEqual(len(restored.news_articles), 1)
        self.assertIsNotNone(restored.sentiment)
        self.assertEqual(restored.sentiment.sentiment, "bullish")


class TestNewsAPIClient(unittest.TestCase):
    """Test NewsAPIClient."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = NewsAPIClient(api_key="test-key-12345")
        self.client.clear_cache()

    def tearDown(self):
        """Clean up after tests."""
        self.client.clear_cache()

    def test_cache_hit(self):
        """Test that cache prevents duplicate API calls."""
        articles = [
            NewsArticle(
                symbol="AAPL",
                title="Test Article",
                source="Test",
                published_at=datetime.now(),
                url="https://test.com",
            )
        ]

        self.client._save_to_cache("AAPL", articles)
        cached = self.client._get_from_cache("AAPL")

        self.assertIsNotNone(cached)
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0].title, "Test Article")

    def test_cache_expiration(self):
        """Test that cache expires after TTL."""
        articles = [
            NewsArticle(
                symbol="AAPL",
                title="Test",
                source="Test",
                published_at=datetime.now(),
                url="https://test.com",
            )
        ]

        self.client._cache["AAPL"] = (articles, datetime.now() - timedelta(minutes=20))
        cached = self.client._get_from_cache("AAPL")

        self.assertIsNone(cached)

    def test_clear_cache(self):
        """Test cache clearing."""
        self.client._cache["AAPL"] = ([], datetime.now())
        self.assertEqual(len(self.client._cache), 1)

        self.client.clear_cache()
        self.assertEqual(len(self.client._cache), 0)

    @patch("src.ai.news_client.urlopen")
    def test_successful_api_response(self, mock_urlopen):
        """Test successful API response parsing."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(
            {
                "status": "ok",
                "articles": [
                    {
                        "title": "Apple Earnings Beat",
                        "description": "Strong Q4 results",
                        "source": {"name": "CNBC"},
                        "publishedAt": "2026-11-10T12:00:00Z",
                        "url": "https://cnbc.com/article",
                        "content": "Full article content",
                    },
                    {
                        "title": "Tech Rally Continues",
                        "description": "Markets up 2%",
                        "source": {"name": "Reuters"},
                        "publishedAt": "2026-11-10T11:00:00Z",
                        "url": "https://reuters.com/article",
                    },
                ],
            }
        ).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        articles = self.client.fetch_news("AAPL", limit=5)

        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0].title, "Apple Earnings Beat")
        self.assertEqual(articles[0].symbol, "AAPL")
        self.assertEqual(articles[1].source, "Reuters")

    @patch("src.ai.news_client.urlopen")
    def test_rate_limit_retry(self, mock_urlopen):
        """Test rate limit retry logic."""
        mock_response_429 = Mock()
        mock_response_429.status = 429

        mock_response_200 = Mock()
        mock_response_200.status = 200
        mock_response_200.read.return_value = json.dumps(
            {"status": "ok", "articles": []}
        ).encode("utf-8")
        mock_response_200.__enter__ = Mock(return_value=mock_response_200)
        mock_response_200.__exit__ = Mock(return_value=False)

        mock_urlopen.side_effect = [
            MagicMock(__enter__=Mock(return_value=mock_response_429), __exit__=Mock(return_value=False)),
            mock_response_200,
        ]

        self.client.retry_delay = 0.01  # Speed up test

        articles = self.client.fetch_news("AAPL")

        # Should retry and eventually succeed
        self.assertIsInstance(articles, list)

    @patch("src.ai.news_client.urlopen")
    def test_api_error_handling(self, mock_urlopen):
        """Test API error handling."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(
            {
                "status": "error",
                "code": "apiKeyInvalid",
                "message": "Your API key is invalid or incorrect",
            }
        ).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        articles = self.client.fetch_news("AAPL")

        # Should return empty list on error
        self.assertEqual(len(articles), 0)

    def test_missing_api_key(self):
        """Test handling of missing API key."""
        client = NewsAPIClient(api_key=None)
        articles = client.fetch_news("AAPL")

        self.assertEqual(len(articles), 0)

    @patch("src.ai.news_client.urlopen")
    def test_fetch_multiple_symbols(self, mock_urlopen):
        """Test fetching news for multiple symbols."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps(
            {
                "status": "ok",
                "articles": [
                    {
                        "title": "Test Article",
                        "source": {"name": "Test"},
                        "publishedAt": "2026-11-10T12:00:00Z",
                        "url": "https://test.com",
                    }
                ],
            }
        ).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        results = self.client.fetch_multiple(["AAPL", "MSFT", "GOOGL"])

        self.assertEqual(len(results), 3)
        self.assertIn("AAPL", results)
        self.assertIn("MSFT", results)
        self.assertIn("GOOGL", results)


if __name__ == "__main__":
    unittest.main()