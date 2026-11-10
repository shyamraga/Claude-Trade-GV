"""Tests for Claude sentiment analysis and AI integration."""

import unittest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from src.ai.models import NewsArticle, SentimentAnalysis, MarketContext
from src.ai.claude_analyzer import ClaudeAnalyzer, APIError, RateLimitError
from src.ai.sentiment_scorer import SentimentScorer
from src.ai.integration import AIMarketIntelligence


class TestClaudeAnalyzer(unittest.TestCase):
    """Test Claude API sentiment analyzer."""

    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = ClaudeAnalyzer(api_key="test-key-12345")
        self.analyzer.clear_cache()

    def tearDown(self):
        """Clean up after tests."""
        self.analyzer.clear_cache()

    def test_analyzer_initialization(self):
        """Test analyzer initialization."""
        self.assertEqual(self.analyzer.api_key, "test-key-12345")
        self.assertEqual(self.analyzer.cache_ttl_minutes, 30)

    def test_analyzer_missing_api_key(self):
        """Test analyzer with missing API key."""
        analyzer = ClaudeAnalyzer(api_key=None)
        articles = [
            NewsArticle(
                symbol="AAPL",
                title="Test",
                source="Test",
                published_at=datetime.now(),
                url="https://test.com",
            )
        ]

        result = analyzer.analyze_news(articles, "AAPL")
        self.assertEqual(result.sentiment, "neutral")
        self.assertEqual(result.confidence, 0.5)

    @patch("src.ai.claude_analyzer.anthropic.Anthropic")
    def test_successful_sentiment_analysis(self, mock_anthropic):
        """Test successful sentiment analysis."""
        # Mock Claude API response
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [
            Mock(
                text='{"sentiment": "bullish", "confidence": 0.85, "themes": ["earnings beat"], "risks": [], "summary": "Strong Q4"}'
            )
        ]
        mock_client.messages.create.return_value = mock_response

        articles = [
            NewsArticle(
                symbol="AAPL",
                title="Apple Beats Earnings",
                description="Strong Q4 results",
                source="CNBC",
                published_at=datetime.now(),
                url="https://cnbc.com",
            )
        ]

        result = self.analyzer.analyze_news(articles, "AAPL")

        self.assertEqual(result.sentiment, "bullish")
        self.assertEqual(result.confidence, 0.85)
        self.assertIn("earnings beat", result.themes)

    @patch("src.ai.claude_analyzer.anthropic.Anthropic")
    def test_bearish_sentiment_analysis(self, mock_anthropic):
        """Test bearish sentiment analysis."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [
            Mock(
                text='{"sentiment": "bearish", "confidence": 0.72, "themes": ["layoffs"], "risks": ["competition"], "summary": "Weak guidance"}'
            )
        ]
        mock_client.messages.create.return_value = mock_response

        articles = [
            NewsArticle(
                symbol="TSLA",
                title="Tesla Announces Layoffs",
                description="Major workforce reduction",
                source="Reuters",
                published_at=datetime.now(),
                url="https://reuters.com",
            )
        ]

        result = self.analyzer.analyze_news(articles, "TSLA")

        self.assertEqual(result.sentiment, "bearish")
        self.assertAlmostEqual(result.confidence, 0.72)
        self.assertIn("competition", result.risks)

    @patch("src.ai.claude_analyzer.anthropic.Anthropic")
    def test_sentiment_caching(self, mock_anthropic):
        """Test that sentiment results are cached."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [Mock(text='{"sentiment": "neutral", "confidence": 0.5}')]
        mock_client.messages.create.return_value = mock_response

        articles = [
            NewsArticle(
                symbol="SPY",
                title="Market Update",
                source="MarketWatch",
                published_at=datetime.now(),
                url="https://mw.com",
            )
        ]

        # First call should hit API
        result1 = self.analyzer.analyze_news(articles, "SPY")
        self.assertEqual(mock_client.messages.create.call_count, 1)

        # Second call should use cache
        result2 = self.analyzer.analyze_news(articles, "SPY")
        self.assertEqual(mock_client.messages.create.call_count, 1)  # Still 1
        self.assertEqual(result1.sentiment, result2.sentiment)

    @patch("src.ai.claude_analyzer.anthropic.Anthropic")
    def test_malformed_json_response(self, mock_anthropic):
        """Test handling of malformed JSON response."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        # Response with malformed JSON
        mock_response = Mock()
        mock_response.content = [
            Mock(text="The sentiment is bullish based on... {invalid json}")
        ]
        mock_client.messages.create.return_value = mock_response

        articles = [
            NewsArticle(
                symbol="AAPL",
                title="Test",
                source="Test",
                published_at=datetime.now(),
                url="https://test.com",
            )
        ]

        result = self.analyzer.analyze_news(articles, "AAPL")

        # Should return neutral on parse error
        self.assertEqual(result.sentiment, "neutral")
        self.assertEqual(result.confidence, 0.5)

    @patch("src.ai.claude_analyzer.anthropic.Anthropic")
    def test_confidence_clamping(self, mock_anthropic):
        """Test that confidence values are clamped to [0, 1]."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [
            Mock(text='{"sentiment": "bullish", "confidence": 1.5}')
        ]
        mock_client.messages.create.return_value = mock_response

        articles = [
            NewsArticle(
                symbol="AAPL",
                title="Test",
                source="Test",
                published_at=datetime.now(),
                url="https://test.com",
            )
        ]

        result = self.analyzer.analyze_news(articles, "AAPL")

        # Confidence should be clamped to 1.0
        self.assertEqual(result.confidence, 1.0)


class TestSentimentScorer(unittest.TestCase):
    """Test sentiment scoring and modulation."""

    def setUp(self):
        """Set up test fixtures."""
        self.scorer = SentimentScorer()

    def test_aggregate_single_sentiment(self):
        """Test aggregating single sentiment."""
        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="bullish",
            confidence=0.8,
        )

        aggregated = self.scorer.aggregate_sentiment([sentiment])

        self.assertEqual(aggregated.sentiment, "bullish")
        self.assertEqual(aggregated.confidence, 0.8)

    def test_aggregate_multiple_bullish(self):
        """Test aggregating multiple bullish sentiments."""
        sentiments = [
            SentimentAnalysis(
                symbol="AAPL",
                sentiment="bullish",
                confidence=0.8,
                themes=["earnings"],
            ),
            SentimentAnalysis(
                symbol="AAPL",
                sentiment="bullish",
                confidence=0.7,
                themes=["guidance"],
            ),
        ]

        aggregated = self.scorer.aggregate_sentiment(sentiments)

        self.assertEqual(aggregated.sentiment, "bullish")
        self.assertGreater(aggregated.confidence, 0.7)

    def test_aggregate_mixed_sentiments(self):
        """Test aggregating mixed bullish and bearish."""
        sentiments = [
            SentimentAnalysis(
                symbol="AAPL",
                sentiment="bullish",
                confidence=0.9,
            ),
            SentimentAnalysis(
                symbol="AAPL",
                sentiment="bearish",
                confidence=0.4,
            ),
        ]

        aggregated = self.scorer.aggregate_sentiment(sentiments)

        self.assertEqual(aggregated.sentiment, "bullish")

    def test_modulate_buy_signal_bullish(self):
        """Test boosting BUY signal with bullish sentiment."""
        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="bullish",
            confidence=0.8,
        )

        modulated = self.scorer.modulate_signal_confidence(0.7, sentiment, "BUY")

        # Should be boosted
        self.assertGreater(modulated, 0.7)
        self.assertLessEqual(modulated, 1.0)

    def test_modulate_buy_signal_bearish(self):
        """Test dampening BUY signal with bearish sentiment."""
        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="bearish",
            confidence=0.75,
        )

        modulated = self.scorer.modulate_signal_confidence(0.8, sentiment, "BUY")

        # Should be dampened
        self.assertLess(modulated, 0.8)
        self.assertGreaterEqual(modulated, 0.0)

    def test_modulate_exit_signal_bearish(self):
        """Test boosting EXIT signal with bearish sentiment."""
        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="bearish",
            confidence=0.7,
        )

        modulated = self.scorer.modulate_signal_confidence(0.5, sentiment, "EXIT")

        # Should be boosted
        self.assertGreater(modulated, 0.5)
        self.assertLessEqual(modulated, 1.0)

    def test_modulate_neutral_sentiment(self):
        """Test that neutral sentiment doesn't modulate."""
        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="neutral",
            confidence=0.5,
        )

        modulated = self.scorer.modulate_signal_confidence(0.75, sentiment, "BUY")

        # Should remain unchanged
        self.assertEqual(modulated, 0.75)

    def test_get_trade_recommendation(self):
        """Test generating trade recommendations."""
        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="bullish",
            confidence=0.85,
            summary="Strong earnings",
        )

        rec = self.scorer.get_trade_recommendation("AAPL", sentiment)

        self.assertIn("BUY", rec)
        self.assertIn("AAPL", rec)
        self.assertIn("high", rec)


class TestAIMarketIntelligence(unittest.TestCase):
    """Test AI market intelligence integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.ai = AIMarketIntelligence(
            news_api_key="test-news-key",
            anthropic_api_key="test-anthropic-key",
        )
        # Pre-mock the news client to avoid HTTP calls
        self.ai.news_client.fetch_news = Mock(return_value=[])

    def tearDown(self):
        """Clean up after tests."""
        self.ai.clear_cache()

    def test_get_market_context(self):
        """Test getting complete market context."""
        articles = [
            NewsArticle(
                symbol="AAPL",
                title="Earnings Beat",
                source="CNBC",
                published_at=datetime.now(),
                url="https://cnbc.com",
            )
        ]

        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="bullish",
            confidence=0.85,
        )

        # Mock the components
        self.ai.news_client.fetch_news = Mock(return_value=articles)
        self.ai.analyzer.analyze_news = Mock(return_value=sentiment)

        context = self.ai.get_market_context("AAPL")

        self.assertEqual(context.symbol, "AAPL")
        self.assertEqual(len(context.news_articles), 1)
        self.assertIsNotNone(context.sentiment)
        self.assertEqual(context.sentiment.sentiment, "bullish")

    def test_enrich_signal_confidence(self):
        """Test enriching signal with sentiment modulation."""
        # Create articles so analyzer is called
        articles = [
            NewsArticle(
                symbol="AAPL",
                title="Test",
                source="Test",
                published_at=datetime.now(),
                url="https://test.com",
            )
        ]
        sentiment = SentimentAnalysis(
            symbol="AAPL",
            sentiment="bullish",
            confidence=0.8,
        )

        # Mock to return articles and sentiment
        self.ai.news_client.fetch_news = Mock(return_value=articles)
        self.ai.analyzer.analyze_news = Mock(return_value=sentiment)

        modulated, returned_sentiment = self.ai.enrich_signal_confidence(
            0.7, "AAPL", "BUY"
        )

        # Should be modulated (boosted by bullish sentiment)
        self.assertGreaterEqual(modulated, 0.7)
        self.assertLessEqual(modulated, 1.0)
        self.assertIsNotNone(returned_sentiment)
        self.assertEqual(returned_sentiment.sentiment, "bullish")

    def test_get_sentiment_summary(self):
        """Test getting sentiment summary for dashboard."""
        articles = [
            NewsArticle(
                symbol="TSLA",
                title="Test",
                source="Test",
                published_at=datetime.now(),
                url="https://test.com",
            )
        ]
        sentiment = SentimentAnalysis(
            symbol="TSLA",
            sentiment="bearish",
            confidence=0.7,
            summary="Weak guidance",
        )

        self.ai.news_client.fetch_news = Mock(return_value=articles)
        self.ai.analyzer.analyze_news = Mock(return_value=sentiment)

        summary = self.ai.get_sentiment_summary("TSLA")

        self.assertIn("TSLA", summary)
        self.assertIn("AVOID", summary.upper())

    def test_get_sentiment_for_multiple_symbols(self):
        """Test fetching sentiment for multiple symbols."""
        articles = [
            NewsArticle(
                symbol="TEST",
                title="Test",
                source="Test",
                published_at=datetime.now(),
                url="https://test.com",
            )
        ]

        sentiments_dict = {
            "AAPL": SentimentAnalysis(
                symbol="AAPL",
                sentiment="bullish",
                confidence=0.8,
            ),
            "MSFT": SentimentAnalysis(
                symbol="MSFT",
                sentiment="neutral",
                confidence=0.5,
            ),
        }

        def analyze_side_effect(arts, symbol, force_refresh=False):
            return sentiments_dict.get(symbol.upper())

        self.ai.news_client.fetch_news = Mock(return_value=articles)
        self.ai.analyzer.analyze_news = Mock(side_effect=analyze_side_effect)

        results = self.ai.get_sentiment_for_symbols(["AAPL", "MSFT"])

        self.assertEqual(len(results), 2)
        self.assertIn("AAPL", results)
        self.assertIn("MSFT", results)
        self.assertEqual(results["AAPL"].sentiment, "bullish")


if __name__ == "__main__":
    unittest.main()