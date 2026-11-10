"""NewsAPI client for fetching financial news."""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json

from src.ai.models import NewsArticle

logger = logging.getLogger(__name__)

# Company name mapping for better news matching
COMPANY_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Google Alphabet",
    "GOOG": "Google Alphabet",
    "AMZN": "Amazon",
    "TSLA": "Tesla",
    "META": "Meta Facebook",
    "NVDA": "Nvidia",
    "AMD": "AMD",
    "SPY": "S&P 500",
    "QQQ": "Nasdaq",
    "IWM": "Russell 2000",
    "DIA": "Dow Jones",
}


class NewsAPIClient:
    """Client for fetching financial news from NewsAPI.org."""

    BASE_URL = "https://newsapi.org/v2"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with API key from environment."""
        self.api_key = api_key or os.getenv("NEWS_API_KEY")
        self._cache: dict[str, tuple[list[NewsArticle], datetime]] = {}
        self.cache_ttl_minutes = 15
        self.max_retries = 3
        self.retry_delay = 2.0

    def _get_cache_key(self, symbol: str) -> str:
        """Generate cache key for a symbol."""
        return symbol.upper()

    def _is_cache_valid(self, cached_at: datetime) -> bool:
        """Check if cached data is still valid."""
        age = datetime.now() - cached_at
        return age.total_seconds() < (self.cache_ttl_minutes * 60)

    def _get_from_cache(self, symbol: str) -> Optional[list[NewsArticle]]:
        """Get cached news articles for a symbol."""
        key = self._get_cache_key(symbol)
        if key in self._cache:
            articles, cached_at = self._cache[key]
            if self._is_cache_valid(cached_at):
                logger.debug(f"Cache hit for {symbol}")
                return articles
            else:
                del self._cache[key]
        return None

    def _save_to_cache(self, symbol: str, articles: list[NewsArticle]) -> None:
        """Save news articles to cache."""
        key = self._get_cache_key(symbol)
        self._cache[key] = (articles, datetime.now())

    def clear_cache(self) -> None:
        """Clear all cached news."""
        self._cache.clear()
        logger.info("News cache cleared")

    def _build_query(self, symbol: str) -> str:
        """Build search query for symbol."""
        company_name = COMPANY_NAMES.get(symbol.upper(), symbol.upper())
        return f'"{symbol} stock" OR "{company_name}"'

    def fetch_news(
        self, symbol: str, limit: int = 10, force_refresh: bool = False
    ) -> list[NewsArticle]:
        """
        Fetch latest news articles for a stock symbol.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL")
            limit: Maximum number of articles to return
            force_refresh: Bypass cache and fetch fresh data

        Returns:
            List of NewsArticle objects
        """
        symbol = symbol.upper()

        # Check cache first
        if not force_refresh:
            cached = self._get_from_cache(symbol)
            if cached:
                return cached[:limit]

        if not self.api_key:
            logger.warning("NEWS_API_KEY not configured, returning empty results")
            return []

        # Build API request
        query = self._build_query(symbol)
        url = (
            f"{self.BASE_URL}/everything?"
            f"q={query}&"
            f"sortBy=publishedAt&"
            f"language=en&"
            f"pageSize={limit}&"
            f"apiKey={self.api_key}"
        )

        # Make request with retry logic
        articles = []
        for attempt in range(self.max_retries):
            try:
                response = self._make_request(url)
                articles = self._parse_response(response, symbol)
                break
            except RateLimitError:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2**attempt)
                    logger.warning(
                        f"Rate limited, retrying in {wait_time}s (attempt {attempt + 1})"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Rate limit exceeded for {symbol}")
            except NewsAPIError as e:
                logger.error(f"NewsAPI error for {symbol}: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error fetching news for {symbol}: {e}")
                break

        # Cache results
        if articles:
            self._save_to_cache(symbol, articles)

        return articles[:limit]

    def _make_request(self, url: str) -> dict:
        """Make HTTP request to NewsAPI."""
        request = Request(url, headers={"User-Agent": "ClaudeTrading/1.0"})

        with urlopen(request, timeout=30) as response:
            if response.status == 429:
                raise RateLimitError("Rate limit exceeded")

            if response.status != 200:
                raise NewsAPIError(f"API returned status {response.status}")

            data = json.loads(response.read().decode("utf-8"))

            if data.get("status") == "error":
                code = data.get("code", "unknown")
                message = data.get("message", "Unknown error")
                if code == "apiKeyInvalid":
                    raise NewsAPIError(f"Invalid API key: {message}")
                elif code == "rateLimited":
                    raise RateLimitError(message)
                raise NewsAPIError(f"{code}: {message}")

            return data

    def _parse_response(self, data: dict, symbol: str) -> list[NewsArticle]:
        """Parse NewsAPI response into NewsArticle objects."""
        articles = []

        for item in data.get("articles", []):
            try:
                source = item.get("source", {}).get("name", "Unknown")
                published_at = item.get("publishedAt")
                if published_at:
                    published_at = datetime.fromisoformat(
                        published_at.replace("Z", "+00:00")
                    )

                article = NewsArticle(
                    symbol=symbol,
                    title=item.get("title", ""),
                    description=item.get("description"),
                    source=source,
                    published_at=published_at or datetime.now(),
                    url=item.get("url", ""),
                    content_snippet=item.get("content"),
                )
                articles.append(article)
            except Exception as e:
                logger.warning(f"Failed to parse article: {e}")
                continue

        logger.info(f"Fetched {len(articles)} articles for {symbol}")
        return articles

    def fetch_multiple(
        self, symbols: list[str], limit: int = 10
    ) -> dict[str, list[NewsArticle]]:
        """
        Fetch news for multiple symbols.

        Args:
            symbols: List of stock ticker symbols
            limit: Maximum articles per symbol

        Returns:
            Dictionary mapping symbols to their news articles
        """
        results = {}
        for symbol in symbols:
            results[symbol] = self.fetch_news(symbol, limit)
        return results


class NewsAPIError(Exception):
    """General NewsAPI error."""

    pass


class RateLimitError(NewsAPIError):
    """Rate limit exceeded error."""

    pass