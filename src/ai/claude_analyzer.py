"""Claude API client for sentiment analysis of financial news."""

import os
import time
import logging
import json
from datetime import datetime, timedelta
from typing import Optional

import anthropic

from src.ai.models import NewsArticle, SentimentAnalysis

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial analyst assessing market sentiment from news articles.
Provide your analysis as structured JSON with the following fields:
- sentiment: "bullish", "bearish", or "neutral"
- confidence: a float from 0.0 to 1.0 indicating your confidence in the sentiment
- themes: an array of key themes or topics mentioned
- risks: an array of risks or concerns mentioned
- summary: a brief 1-2 sentence summary of the market sentiment

Focus on the most recent news and its potential impact on the stock price.
Be conservative in your confidence assessments - only assign high confidence
when there is clear, unambiguous information."""


class ClaudeAnalyzer:
    """Analyzes financial news using Claude API for sentiment detection."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-20240620"):
        """
        Initialize Claude API client.

        Args:
            api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.
            model: Claude model to use for analysis.
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self._cache: dict[str, tuple[SentimentAnalysis, datetime]] = {}
        self.cache_ttl_minutes = 30
        self.max_retries = 3
        self.retry_delay = 2.0

        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not configured - sentiment analysis disabled")

    def _get_cache_key(self, symbol: str) -> str:
        """Generate cache key for a symbol."""
        return f"sentiment_{symbol.upper()}"

    def _is_cache_valid(self, cached_at: datetime) -> bool:
        """Check if cached sentiment is still valid."""
        age = datetime.now() - cached_at
        return age.total_seconds() < (self.cache_ttl_minutes * 60)

    def _get_from_cache(self, symbol: str) -> Optional[SentimentAnalysis]:
        """Get cached sentiment for a symbol."""
        key = self._get_cache_key(symbol)
        if key in self._cache:
            sentiment, cached_at = self._cache[key]
            if self._is_cache_valid(cached_at):
                logger.debug(f"Sentiment cache hit for {symbol}")
                return sentiment
            else:
                del self._cache[key]
        return None

    def _save_to_cache(self, symbol: str, sentiment: SentimentAnalysis) -> None:
        """Save sentiment analysis to cache."""
        key = self._get_cache_key(symbol)
        self._cache[key] = (sentiment, datetime.now())

    def clear_cache(self) -> None:
        """Clear all cached sentiment results."""
        self._cache.clear()
        logger.info("Sentiment cache cleared")

    def _build_news_context(self, articles: list[NewsArticle]) -> str:
        """Build formatted news context for Claude prompt."""
        if not articles:
            return "No recent news articles available."

        context_parts = []
        for article in articles[:10]:  # Limit to 10 most recent articles
            date_str = article.published_at.strftime("%Y-%m-%d %H:%M")
            context_parts.append(
                f"[{date_str}] {article.source}: {article.title}\n"
                f"  Description: {article.description or 'N/A'}"
            )

        return "\n\n".join(context_parts)

    def analyze_news(
        self, articles: list[NewsArticle], symbol: str, force_refresh: bool = False
    ) -> SentimentAnalysis:
        """
        Analyze news articles for a stock symbol using Claude API.

        Args:
            articles: List of NewsArticle objects to analyze
            symbol: Stock ticker symbol
            force_refresh: Bypass cache and force fresh analysis

        Returns:
            SentimentAnalysis object with market sentiment
        """
        if not self.api_key:
            logger.warning("No API key available, returning neutral sentiment")
            return SentimentAnalysis(
                symbol=symbol,
                sentiment="neutral",
                confidence=0.5,
                summary="API key not configured - sentiment analysis unavailable",
            )

        symbol = symbol.upper()

        # Check cache first
        if not force_refresh:
            cached = self._get_from_cache(symbol)
            if cached:
                return cached

        # Build news context
        news_context = self._build_news_context(articles)

        # Construct Claude prompt
        user_prompt = f"""Analyze the following financial news articles for {symbol} stock and provide sentiment assessment.

{news_context}

Please provide your analysis as JSON with: sentiment, confidence, themes, risks, and summary."""

        # Call Claude API with retry logic
        response_text = None
        for attempt in range(self.max_retries):
            try:
                response_text = self._call_claude_api(user_prompt)
                break
            except RateLimitError:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2**attempt)
                    logger.warning(
                        f"Rate limited, retrying in {wait_time}s (attempt {attempt + 1})"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error("Rate limit exceeded after retries")
            except APIError as e:
                logger.error(f"Claude API error: {e}")
                return SentimentAnalysis(
                    symbol=symbol,
                    sentiment="neutral",
                    confidence=0.5,
                    summary=f"API error during analysis: {str(e)}",
                )
            except Exception as e:
                logger.error(f"Unexpected error calling Claude API: {e}")
                return SentimentAnalysis(
                    symbol=symbol,
                    sentiment="neutral",
                    confidence=0.5,
                    summary=f"Unexpected error during analysis: {str(e)}",
                )

        # Parse response
        sentiment = self._parse_response(response_text, symbol)
        self._save_to_cache(symbol, sentiment)

        return sentiment

    def _call_claude_api(self, user_prompt: str) -> str:
        """Make API call to Claude."""
        if not self.api_key:
            raise APIError("API key not configured")

        client = anthropic.Anthropic(api_key=self.api_key)

        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=1000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

            return message.content[0].text

        except anthropic.RateLimitError as e:
            raise RateLimitError(f"Claude API rate limit: {e}")
        except anthropic.APIError as e:
            raise APIError(f"Claude API error: {e}")
        except Exception as e:
            raise APIError(f"API call failed: {e}")

    def _parse_response(self, response_text: str, symbol: str) -> SentimentAnalysis:
        """Parse Claude API response into SentimentAnalysis object."""
        try:
            # Try to extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                data = json.loads(json_str)
            else:
                # Try parsing the whole response as JSON
                data = json.loads(response_text)

            # Validate required fields
            sentiment = data.get("sentiment", "neutral")
            if sentiment not in ("bullish", "bearish", "neutral"):
                sentiment = "neutral"

            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]

            return SentimentAnalysis(
                symbol=symbol,
                sentiment=sentiment,
                confidence=confidence,
                themes=data.get("themes", []),
                risks=data.get("risks", []),
                summary=data.get("summary", ""),
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Claude response as JSON: {e}")
            return SentimentAnalysis(
                symbol=symbol,
                sentiment="neutral",
                confidence=0.5,
                summary="Failed to parse sentiment response",
            )


class APIError(Exception):
    """General Claude API error."""

    pass


class RateLimitError(APIError):
    """Rate limit exceeded error."""

    pass