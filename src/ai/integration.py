"""AI Market Intelligence integration for strategy engine."""

import logging
from typing import Optional

from src.ai.models import NewsArticle, SentimentAnalysis, MarketContext
from src.ai.news_client import NewsAPIClient
from src.ai.claude_analyzer import ClaudeAnalyzer
from src.ai.sentiment_scorer import SentimentScorer

logger = logging.getLogger(__name__)


class AIMarketIntelligence:
    """
    Aggregates news, sentiment analysis, and scoring into market intelligence
    for trading strategy enrichment.
    """

    def __init__(
        self,
        news_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
    ):
        """
        Initialize AI market intelligence system.

        Args:
            news_api_key: NewsAPI key. If None, reads from NEWS_API_KEY env var.
            anthropic_api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.
        """
        self.news_client = NewsAPIClient(api_key=news_api_key)
        self.analyzer = ClaudeAnalyzer(api_key=anthropic_api_key)
        self.scorer = SentimentScorer()
        self._market_context_cache: dict[str, MarketContext] = {}

    def get_market_context(
        self, symbol: str, force_refresh: bool = False
    ) -> MarketContext:
        """
        Get unified market context for a symbol.

        Fetches news articles, analyzes sentiment, and returns complete context.

        Args:
            symbol: Stock ticker symbol
            force_refresh: Bypass cache and fetch fresh data

        Returns:
            MarketContext with news articles and sentiment analysis
        """
        symbol = symbol.upper()

        # Check cache first
        if not force_refresh and symbol in self._market_context_cache:
            context = self._market_context_cache[symbol]
            if not context.is_stale(ttl_minutes=30):
                logger.debug(f"Market context cache hit for {symbol}")
                return context

        # Fetch news articles
        articles = self.news_client.fetch_news(symbol, limit=15, force_refresh=force_refresh)
        logger.info(f"Fetched {len(articles)} articles for {symbol}")

        # Analyze sentiment if we have articles
        sentiment = None
        if articles:
            sentiment = self.analyzer.analyze_news(
                articles, symbol, force_refresh=force_refresh
            )
            logger.info(
                f"Analyzed sentiment for {symbol}: {sentiment.sentiment} ({sentiment.confidence:.0%})"
            )

        # Create and cache market context
        context = MarketContext(
            symbol=symbol,
            news_articles=articles,
            sentiment=sentiment,
        )

        self._market_context_cache[symbol] = context
        return context

    def _analyze_market_momentum_sentiment(self, symbol: str, bars: list) -> SentimentAnalysis:
        """Derive algorithmic market intelligence sentiment from multi-bar price and volume momentum."""
        if not bars or len(bars) < 10:
            return SentimentAnalysis(
                symbol=symbol,
                sentiment="neutral",
                confidence=0.5,
                summary="Insufficient bar data for momentum sentiment.",
            )

        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]

        # Calculate short-term vs medium-term return
        recent_ret = (closes[-1] - closes[-5]) / closes[-5] if len(closes) >= 5 else 0.0
        medium_ret = (closes[-1] - closes[-15]) / closes[-15] if len(closes) >= 15 else recent_ret

        # Volume trend
        avg_vol = sum(volumes[-15:]) / len(volumes[-15:]) if len(volumes) >= 15 else 1.0
        recent_vol = sum(volumes[-3:]) / 3.0 if len(volumes) >= 3 else avg_vol
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

        if recent_ret > 0.008 and medium_ret > 0.012:
            sentiment = "bullish"
            confidence = min(0.65 + (recent_ret * 10) + (vol_ratio * 0.05), 0.92)
            summary = f"Strong upward price momentum (+{recent_ret*100:.1f}%) with {vol_ratio:.1f}x volume accumulation."
        elif recent_ret < -0.008 and medium_ret < -0.012:
            sentiment = "bearish"
            confidence = min(0.65 + (abs(recent_ret) * 10) + (vol_ratio * 0.05), 0.92)
            summary = f"Negative price drift ({recent_ret*100:.1f}%) with elevated selling volume."
        elif recent_ret > 0.003:
            sentiment = "bullish"
            confidence = 0.65
            summary = "Mild bullish momentum with steady accumulation."
        elif recent_ret < -0.003:
            sentiment = "bearish"
            confidence = 0.65
            summary = "Mild bearish drift with cautious market order flow."
        else:
            sentiment = "neutral"
            confidence = 0.50
            summary = "Consolidation regime with balanced order book pressure."

        return SentimentAnalysis(
            symbol=symbol,
            sentiment=sentiment,
            confidence=round(confidence, 2),
            summary=summary,
        )

    def enrich_signal(
        self,
        symbol: str,
        action: str,
        confidence: float,
        bars: Optional[list] = None,
    ) -> dict:
        """
        Primary AI enrichment method used by the trading orchestrator.
        Combines news sentiment or multi-factor market momentum intelligence
        to modulate signal confidence up or down.
        """
        symbol = symbol.upper()
        action = action.upper()

        # 1. Try news & LLM sentiment first
        context = self.get_market_context(symbol)
        sentiment = context.sentiment

        # 2. Fall back to multi-factor market intelligence if no news API configured
        if not sentiment and bars:
            sentiment = self._analyze_market_momentum_sentiment(symbol, bars)

        if not sentiment:
            return {
                "modulated_confidence": confidence,
                "sentiment": "neutral",
                "sentiment_confidence": 0.5,
                "summary": "No market intelligence sentiment available",
            }

        modulated = self.scorer.modulate_signal_confidence(confidence, sentiment, action)

        return {
            "modulated_confidence": round(min(max(modulated, 0.0), 0.98), 3),
            "sentiment": sentiment.sentiment,
            "sentiment_confidence": sentiment.confidence,
            "summary": sentiment.summary,
        }

    def enrich_signal_confidence(
        self,
        base_confidence: float,
        symbol: str,
        action: str,
        force_refresh: bool = False,
    ) -> tuple[float, Optional[SentimentAnalysis]]:
        """
        Enrich a trading signal with sentiment-based confidence modulation.

        Args:
            base_confidence: Original signal confidence (0.0 - 1.0)
            symbol: Stock ticker symbol
            action: Trading action ("BUY", "SELL", "EXIT", "HOLD")
            force_refresh: Force fresh sentiment analysis

        Returns:
            Tuple of (modulated_confidence, sentiment_analysis)
        """
        context = self.get_market_context(symbol, force_refresh=force_refresh)

        if not context.sentiment:
            logger.debug(f"No sentiment available for {symbol}, returning base confidence")
            return base_confidence, None

        modulated = self.scorer.modulate_signal_confidence(
            base_confidence, context.sentiment, action
        )

        logger.info(
            f"Signal modulation for {symbol} {action}: {base_confidence:.2%} → {modulated:.2%} "
            f"({context.sentiment.sentiment})"
        )

        return modulated, context.sentiment

    def get_sentiment_summary(self, symbol: str) -> str:
        """
        Get human-readable sentiment summary for dashboard display.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Formatted sentiment summary string
        """
        context = self.get_market_context(symbol)

        if not context.sentiment:
            return f"{symbol}: No sentiment data available"

        return self.scorer.get_trade_recommendation(symbol, context.sentiment)

    def get_sentiment_for_symbols(
        self, symbols: list[str], force_refresh: bool = False
    ) -> dict[str, SentimentAnalysis]:
        """
        Get sentiment analysis for multiple symbols.

        Args:
            symbols: List of stock ticker symbols
            force_refresh: Force fresh analysis

        Returns:
            Dictionary mapping symbols to sentiment analyses
        """
        results = {}
        for symbol in symbols:
            context = self.get_market_context(symbol, force_refresh=force_refresh)
            if context.sentiment:
                results[symbol] = context.sentiment
        return results

    def clear_cache(self) -> None:
        """Clear all cached market context and sentiment."""
        self.news_client.clear_cache()
        self.analyzer.clear_cache()
        self._market_context_cache.clear()
        logger.info("AI market intelligence cache cleared")